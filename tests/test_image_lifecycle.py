"""Image identity, sanitization, binding, and frozen-export acceptance cases.

Tiny synthetic rasters exercise parser behavior; no external/private media is
used. Export layout and native object verification belong to the renderer suite.
"""
from __future__ import annotations

import copy
import hashlib
from io import BytesIO
from pathlib import Path
import struct
import zlib

from fastapi.testclient import TestClient
from PIL import Image, ImageCms, PngImagePlugin
import pytest

from foundry.api import create_app
from foundry.errors import DomainError
from foundry.jobs import Worker
from foundry.runtime import default_period
from foundry.service import ROOT, Service, validate_stored_snapshot
from foundry.storage import Store


def raster_bytes(color=(180, 50, 30), *, size=(12, 8), format='PNG', metadata=False, orientation=None):
    image = Image.new('RGB', size, color)
    kwargs = {}
    if metadata and format == 'PNG':
        info = PngImagePlugin.PngInfo()
        info.add_text('Description', 'fixture_metadata_must_not_reach_exports')
        kwargs['pnginfo'] = info
    if orientation is not None or format == 'JPEG' and metadata:
        exif = Image.Exif()
        if orientation is not None:
            exif[274] = orientation
        exif[270] = 'fixture_exif_must_not_reach_exports'
        kwargs['exif'] = exif
    result = BytesIO()
    image.save(result, format=format, **kwargs)
    image.close()
    return result.getvalue()


@pytest.fixture
def service(tmp_path):
    return Service(Store(tmp_path))


@pytest.fixture
def published(service, monkeypatch):
    """Exercise real publication gates with a narrow evaluation renderer stub."""
    created = service.create_type('Quarterly revenue with an image')
    program = created['program']
    for decision in program['decisions']:
        program = service.resolve(program['id'], decision['id'], decision['alternatives'][0]['value'], program['digest'])
    def smoke(snapshot, format, output_dir, **kwargs):
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f'smoke.{format}'
        path.write_bytes(b'Image lifecycle evaluation smoke fixture. ' * 5)
        return {'path': str(path)}
    with monkeypatch.context() as patch:
        patch.setattr('foundry.exporters.export_snapshot', smoke)
        program = service.evaluate(program['id'], program['digest'])
    assert program['evaluation']['passed']
    program = service.publish(program['id'], program['digest'])
    source = service.upload((ROOT / 'fixtures' / 'transactions.csv').read_bytes(), 'transactions.csv')
    return created['report_type'], program, source


def binding(asset, *, alt='A red rectangular report illustration.', decorative=False):
    return {'asset_id': asset['id'], 'alt_text': alt, 'decorative': decorative}


def request(service, published, *, image=None, key='image-run'):
    report_type, _, source = published
    return service.request_run(report_type['id'], source['id'], default_period().model_dump(mode='json'), key, image=image)


def materialize(service, published, *, image=None, key='image-run'):
    job = request(service, published, image=image, key=key)
    assert Worker(service).run_one()
    completed = service.store.job(job['id'])
    assert completed['status'] == 'completed', completed
    snapshot = service.store.get('snapshot', completed['result']['snapshot_id'])
    validate_stored_snapshot(snapshot)
    return snapshot


@pytest.mark.parametrize(('format', 'extension'), [('PNG', 'png'), ('JPEG', 'jpg'), ('JPEG', 'jpeg')])
def test_supported_raster_upload_preserves_original_and_captures_canonical_png(service, format, extension):
    original = raster_bytes(format=format, metadata=True)
    asset = service.upload(original, f'source.{extension}')
    assert asset['digest'] == hashlib.sha256(original).hexdigest()
    assert service.store.read_blob(asset['digest']) == original
    assert 'report_image' in asset['profile']['eligible_roles']
    profile = asset['profile']['image']
    assert (profile['width_px'], profile['height_px']) == (12, 8)
    assert profile['normalization'] == 'exif_transpose_strip_metadata_png'
    assert profile['media_type'] == 'image/png'
    canonical = service.store.read_blob(profile['render_digest'])
    assert canonical.startswith(b'\x89PNG\r\n\x1a\n')
    assert profile['render_digest'] == hashlib.sha256(canonical).hexdigest()
    with Image.open(BytesIO(canonical)) as decoded:
        assert decoded.size == (12, 8)
        assert not decoded.getexif()
        assert 'Description' not in decoded.info
        assert 'icc_profile' not in decoded.info
    assert b'fixture_metadata_must_not_reach_exports' not in canonical
    assert b'fixture_exif_must_not_reach_exports' not in canonical


def test_exif_orientation_is_applied_before_dimensions_and_digest_are_frozen(service):
    asset = service.upload(raster_bytes(size=(18, 10), format='JPEG', orientation=6), 'oriented.jpg')
    profile = asset['profile']['image']
    assert (profile['width_px'], profile['height_px']) == (10, 18)
    with Image.open(BytesIO(service.store.read_blob(profile['render_digest']))) as decoded:
        assert decoded.size == (10, 18)
        assert decoded.getexif().get(274) is None


def test_transparency_survives_metadata_sanitization(service):
    original = Image.new('RGBA', (5, 7), (30, 70, 140, 96))
    content = BytesIO()
    original.save(content, format='PNG')
    asset = service.upload(content.getvalue(), 'transparent.png')
    with Image.open(BytesIO(service.store.read_blob(asset['profile']['image']['render_digest']))) as decoded:
        assert decoded.convert('RGBA').getpixel((2, 3)) == (30, 70, 140, 96)


@pytest.mark.parametrize(('content', 'filename'), [
    (b'%PDF-1.4 fake image', 'disguised.png'),
    (b'not a JPEG', 'broken.jpeg'),
    (raster_bytes()[:40], 'truncated.png'),
    (raster_bytes(format='GIF'), 'disguised.gif.png'),
    (raster_bytes(format='JPEG'), 'wrong-extension.png'),
    (raster_bytes(), 'wrong-extension.jpg'),
])
def test_invalid_or_unsupported_content_is_rejected_without_a_usable_asset(service, content, filename):
    with pytest.raises(DomainError) as failure:
        service.upload(content, filename)
    assert failure.value.status_code == 422
    assert service.store.list('asset') == []


def test_animated_png_is_not_silently_flattened(service):
    frames = [Image.new('RGB', (5, 5), color) for color in ('red', 'blue')]
    content = BytesIO()
    frames[0].save(content, format='PNG', save_all=True, append_images=frames[1:], duration=100, loop=0)
    with Image.open(BytesIO(content.getvalue())) as animated:
        assert animated.n_frames == 2
    with pytest.raises(DomainError) as failure:
        service.upload(content.getvalue(), 'animated.png')
    assert failure.value.status_code == 422
    assert service.store.list('asset') == []


@pytest.mark.parametrize(('width', 'height'), [(100_000, 100_000), (8193, 1), (4001, 4000)])
def test_oversized_dimensions_fail_before_pixel_allocation(service, monkeypatch, width, height):
    # A valid PNG signature/IHDR with huge dimensions exercises the header gate
    # without allocating the corresponding multi-gigabyte bitmap in the test.
    small = raster_bytes()
    ihdr = struct.pack('>II', width, height) + small[24:29]
    huge = small[:16] + ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr)) + small[33:]
    load_calls = []
    def no_pixel_allocation(*args, **kwargs):
        load_calls.append(True)
        raise AssertionError('Oversized dimensions reached pixel decoding')
    monkeypatch.setattr(PngImagePlugin.PngImageFile, 'load', no_pixel_allocation)
    with pytest.raises(DomainError) as failure:
        service.upload(huge, 'oversized.png')
    assert failure.value.status_code == 422
    assert service.store.list('asset') == []
    assert not load_calls


def test_invalid_icc_profile_is_rejected_instead_of_silently_reinterpreted(service):
    image = Image.new('RGB', (6, 4), 'red')
    content = BytesIO()
    image.save(content, format='PNG', icc_profile=b'invalid fixture color profile')
    with pytest.raises(DomainError) as failure:
        service.upload(content.getvalue(), 'invalid-color-profile.png')
    assert failure.value.status_code == 422
    assert service.store.list('asset') == []


def test_valid_srgb_profile_is_resolved_and_not_embedded_in_canonical_image(service):
    image = Image.new('RGB', (6, 4), (50, 100, 150))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    content = BytesIO()
    image.save(content, format='PNG', icc_profile=profile)
    asset = service.upload(content.getvalue(), 'color-managed.png')
    with Image.open(BytesIO(service.store.read_blob(asset['profile']['image']['render_digest']))) as canonical:
        assert canonical.size == (6, 4)
        assert canonical.convert('RGB').getpixel((2, 2)) == (50, 100, 150)
        assert 'icc_profile' not in canonical.info


def test_metadata_only_difference_preserves_original_identity_and_reuses_render_digest(service):
    plain = service.upload(raster_bytes(), 'plain.png')
    annotated = service.upload(raster_bytes(metadata=True), 'annotated.png')
    assert plain['digest'] != annotated['digest']
    assert plain['profile']['image']['render_digest'] == annotated['profile']['image']['render_digest']


def test_non_image_source_cannot_bind_to_the_image_role(service, published):
    _, _, transactions = published
    with pytest.raises(DomainError):
        request(service, published, image=binding(transactions))
    assert service.store.jobs() == []


def test_image_run_pins_source_and_render_identity_without_changing_facts(service, published):
    image = service.upload(raster_bytes(metadata=True), 'report.png')
    without = materialize(service, published, key='without-image')
    with_image = materialize(service, published, image=binding(image), key='with-image')
    node = next(n for n in with_image['nodes'] if n['kind'] == 'image')
    assert node['asset_id'] == image['id']
    assert node['render_digest'] == image['profile']['image']['render_digest']
    assert node['media_type'] == 'image/png'
    assert node['alt_text'] == binding(image)['alt_text']
    assert node['decorative'] is False
    assert (node['width_px'], node['height_px']) == (12, 8)
    assert any(a['id'] == image['id'] and a['digest'] == image['digest'] for a in with_image['source_assets'])
    assert with_image['facts'] == without['facts']
    assert with_image['datasets'] == without['datasets']
    assert with_image['source_snapshot_digest'] != without['source_snapshot_digest']
    assert all(node['id'] in view['coverage']['required_node_ids'] for view in with_image['views'])


@pytest.mark.parametrize('change', ['asset', 'alt', 'decorative', 'removed'])
def test_image_binding_participates_in_request_idempotency(service, published, change):
    first = service.upload(raster_bytes(metadata=True), 'first.png')
    original = binding(first)
    one = request(service, published, image=original, key='same-request')
    repeated = request(service, published, image=copy.deepcopy(original), key='same-request')
    assert repeated['id'] == one['id']
    changed = copy.deepcopy(original)
    if change == 'asset':
        replacement = service.upload(raster_bytes((20, 40, 200)), 'different.png')
        changed['asset_id'] = replacement['id']
    elif change == 'alt':
        changed['alt_text'] = 'A differently described report image.'
    elif change == 'decorative':
        changed['decorative'] = True
    else:
        changed = None
    with pytest.raises(DomainError) as failure:
        request(service, published, image=changed, key='same-request')
    assert failure.value.code == 'IDEMPOTENCY_CONFLICT'


def test_changing_alt_text_creates_new_source_snapshot_identity(service, published):
    image = service.upload(raster_bytes(metadata=True), 'context.png')
    first = materialize(service, published, image=binding(image), key='description-a')
    second = materialize(service, published, image=binding(image, alt='A revised accessible description.'), key='description-b')
    assert first['source_snapshot_digest'] != second['source_snapshot_digest']
    assert first['facts'] == second['facts']


def test_editorial_revision_and_acceptance_preserve_frozen_image(service, published):
    asset = service.upload(raster_bytes(metadata=True), 'context.png')
    original = materialize(service, published, image=binding(asset))
    image = next(n for n in original['nodes'] if n['kind'] == 'image')
    revised = service.revise(original['id'], original['revision'], 'commentary', 'The image description was reviewed with the report.', 'Review context')
    accepted = service.accept(revised['id'], revised['revision'])
    for snapshot in (revised, accepted):
        assert next(n for n in snapshot['nodes'] if n['kind'] == 'image') == image
        assert snapshot['source_snapshot_digest'] == original['source_snapshot_digest']
        assert snapshot['source_assets'] == original['source_assets']
        assert snapshot['facts'] == original['facts']
    assert service.store.get('snapshot', original['id']) == original


def test_corrupted_frozen_image_blocks_export_without_publishing_bytes(service, published):
    asset = service.upload(raster_bytes(metadata=True), 'context.png')
    snapshot = materialize(service, published, image=binding(asset))
    render_digest = next(n for n in snapshot['nodes'] if n['kind'] == 'image')['render_digest']
    stored = service.store.blob_path(render_digest)
    stored.chmod(0o600)
    stored.write_bytes(b'corrupted canonical bitmap')
    job = service.request_export(snapshot['id'], 'pdf', 'compatible', 'corrupt-image-export')
    Worker(service).run_one()
    result = service.store.job(job['id'])
    assert result['status'] == 'blocked', result
    assert result['result'] is None
    assert service.store.list('export') == []


def test_export_uses_frozen_png_without_original_image_or_renormalization(service, published, monkeypatch):
    original = raster_bytes(metadata=True)
    asset = service.upload(original, 'metadata-bearing.png')
    snapshot = materialize(service, published, image=binding(asset))
    render_digest = asset['profile']['image']['render_digest']
    assert render_digest != asset['digest']
    # Original upload retention is independent of the already frozen derivative.
    service.store.blob_path(asset['digest']).unlink()
    def forbidden(*args, **kwargs):
        raise AssertionError('An export attempted to reinterpret original inputs')
    monkeypatch.setattr('foundry.runtime.prepare', forbidden)
    monkeypatch.setattr('foundry.service.inspect_asset', forbidden)
    monkeypatch.setattr('foundry.ingestion.inspect_asset', forbidden)
    monkeypatch.setattr('foundry.images.normalize_image', forbidden)
    for format in ('docx', 'xlsx', 'pdf', 'pptx'):
        job = service.request_export(snapshot['id'], format, 'compatible', f'frozen-image-{format}')
        Worker(service).run_one()
        result = service.store.job(job['id'])
        assert result['status'] == 'completed', result
        artifact = service.store.get('export', result['result']['export_id'])
        assert artifact['snapshot_digest'] == snapshot['digest']
        assert service.store.read_blob(artifact['digest'])
    assert service.store.get('snapshot', snapshot['id']) == snapshot


@pytest.mark.parametrize('image_patch', [
    {'alt_text': '', 'decorative': False},
    {'alt_text': '   ', 'decorative': False},
    {'alt_text': 'x' * 501, 'decorative': False},
    {'alt_text': 'A report image.', 'decorative': False, 'render_digest': 'a' * 64},
])
def test_api_rejects_missing_alt_and_undeclared_image_override(tmp_path, image_patch):
    with TestClient(create_app(tmp_path, start_worker=False)) as client:
        response = client.post('/api/report-runs', json={
            'report_type_id': 'not_resolved', 'asset_id': 'not_resolved',
            'period': default_period().model_dump(mode='json'), 'idempotency_key': 'invalid-image-binding',
            'image': {'asset_id': 'not_resolved', **image_patch},
        })
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'REQUEST_INVALID'


def test_decorative_image_can_have_empty_alt(service, published):
    image = service.upload(raster_bytes(), 'decoration.png')
    snapshot = materialize(service, published, image=binding(image, alt='', decorative=True))
    node = next(n for n in snapshot['nodes'] if n['kind'] == 'image')
    assert node['decorative'] is True and node['alt_text'] == ''
