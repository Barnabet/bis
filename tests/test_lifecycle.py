from __future__ import annotations
from io import BytesIO
import copy
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from foundry.storage import Store, digest, now, uid
from foundry.service import Service, ROOT, snapshot_dict
from foundry.api import create_app
from foundry.errors import DomainError
from foundry.ingestion import inspect_asset, transaction_rows
from foundry.runtime import fixture_snapshot, default_period


@pytest.fixture
def service(tmp_path):
    return Service(Store(tmp_path))


def test_immutable_object_integrity_and_no_path_escape(service):
    sha = service.store.put_blob(b'original')
    assert service.store.put_blob(b'original') == sha
    assert service.store.read_blob(sha) == b'original'
    with pytest.raises(DomainError):
        service.store.read_blob('../../etc/passwd')
    p = service.store.blob_path(sha)
    p.chmod(0o600)
    p.write_bytes(b'tampered')
    with pytest.raises(DomainError, match='digest'):
        service.store.read_blob(sha)


def test_idempotency_same_request_and_conflicting_request(service):
    a = service.store.enqueue('generation', 'type:a', 'request1', {'input': 1})
    b = service.store.enqueue('generation', 'type:a', 'request1', {'input': 1})
    assert a['id'] == b['id']
    with pytest.raises(DomainError) as err:
        service.store.enqueue('generation', 'type:a', 'request1', {'input': 2})
    assert err.value.code == 'IDEMPOTENCY_CONFLICT'
    assert service.store.enqueue('generation', 'type:b', 'request1', {'input': 2})['id'] != a['id']


def test_stale_worker_cannot_publish_and_restart_reclaims(service):
    job = service.store.enqueue('generation', 'a', 'k', {})
    old = service.store.claim(lease_seconds=-1)
    current = service.store.claim()
    assert old['token'] != current['token']
    with pytest.raises(DomainError):
        service.store.finish(old['id'], old['token'], records=[('snapshot', {'id': 'bad'})])
    assert service.store.list('snapshot') == []
    service.store.finish(current['id'], current['token'], result={'ok': True})
    assert service.store.job(job['id'])['status'] == 'completed'


def test_cancellation_fences_late_results(service):
    job = service.store.enqueue('export', 'a', 'k', {})
    claimed = service.store.claim()
    service.store.cancel(job['id'])
    with pytest.raises(DomainError):
        service.store.finish(job['id'], claimed['token'], result={'should_not_exist': True})
    assert service.store.job(job['id'])['result'] is None
    assert service.store.claim() is None


def test_snapshot_revision_is_new_and_facts_unchanged(service):
    snapshot = snapshot_dict(fixture_snapshot())
    service.store.insert('snapshot', snapshot)
    revision = service.revise(snapshot['id'], 1, 'commentary', 'Management commentary awaits supporting evidence.', 'Clarify this period')
    assert revision['id'] != snapshot['id']
    assert revision['parent_id'] == snapshot['id']
    assert revision['facts'] == snapshot['facts']
    assert revision['datasets'] == snapshot['datasets']
    assert service.store.get('snapshot', snapshot['id']) == snapshot
    with pytest.raises(DomainError) as err:
        service.revise(snapshot['id'], 1, 'commentary', 'Conflicting second edit.', 'Concurrent edit')
    assert err.value.code == 'VERSION_CONFLICT'
    with pytest.raises(DomainError) as err:
        service.revise(revision['id'], 2, 'summary', 'Replace computed revenue.', 'Try fact change')
    assert err.value.code == 'COMPUTED_FACT_LOCKED'


def test_bad_numeric_commentary_cannot_be_accepted(service):
    snapshot = snapshot_dict(fixture_snapshot())
    service.store.insert('snapshot', snapshot)
    revision = service.revise(snapshot['id'], 1, 'commentary', 'Revenue reached 999999 euros.', 'Bad fact override')
    assert revision['status'] == 'blocked'
    with pytest.raises(DomainError) as err:
        service.accept(revision['id'], revision['revision'])
    assert err.value.code == 'REPORT_BLOCKED'


def test_candidate_approval_cannot_replace_evaluation(service):
    p = service.create_type('Test revenue')['program']
    with pytest.raises(DomainError) as err:
        service.publish(p['id'], p['digest'])
    assert err.value.code == 'POLICY_UNRESOLVED'
    original_digest = p['digest']
    for decision in p['decisions']:
        p = service.resolve(p['id'], decision['id'], decision['alternatives'][0]['value'], p['digest'])
    assert p['digest'] != original_digest
    with pytest.raises(DomainError) as err:
        service.publish(p['id'], p['digest'])
    assert err.value.code == 'EVALUATION_REQUIRED'
    with pytest.raises(DomainError) as err:
        service.resolve(p['id'], 'selection', 'largest_absolute_change', original_digest)
    assert err.value.code == 'VERSION_CONFLICT'


def test_source_byte_changes_invalidate_identity(service):
    raw = (ROOT / 'fixtures' / 'transactions.csv').read_bytes()
    a = service.upload(raw, 'first.csv')
    b = service.upload(raw, 'renamed.csv')
    c = service.upload(raw.replace(b'500', b'501'), 'restated.csv')
    assert a['digest'] == b['digest']
    if c['digest'] == a['digest']:
        c = service.upload(raw + b'new,2026-02-01,North,posted,1.00,EUR\n', 'restated.csv')
    assert c['digest'] != a['digest']


def test_office_archive_external_relationships_rejected():
    b = BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('_rels/.rels', '<Relationships><Relationship TargetMode="External" Target="https://example.com/private"/></Relationships>')
    with pytest.raises(DomainError) as err:
        inspect_asset(b.getvalue(), 'unsafe.docx')
    assert err.value.code == 'EXTERNAL_RESOURCE'


def test_office_archive_traversal_rejected():
    b = BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('../outside', 'data')
    with pytest.raises(DomainError) as err:
        inspect_asset(b.getvalue(), 'unsafe.xlsx')
    assert err.value.code == 'ARCHIVE_INVALID'


def test_xlsx_formula_is_not_silently_bound():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['transaction_id', 'date', 'region', 'status', 'amount', 'currency'])
    ws.append(['a', '2026-01-01', 'North', 'posted', '=10+20', 'EUR'])
    b = BytesIO(); wb.save(b)
    asset = inspect_asset(b.getvalue(), 'formula.xlsx')
    assert 'transactions' not in asset['profile']['eligible_roles']
    assert asset['profile']['sheets'][0]['formula_count'] == 1


def test_xlsx_row_location_and_value_binding():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = 'Transactions'
    ws.append(['transaction_id', 'date', 'region', 'status', 'amount', 'currency'])
    ws.append(['a', '2026-01-01', 'North', 'posted', 30, 'EUR'])
    b = BytesIO(); wb.save(b)
    asset = inspect_asset(b.getvalue(), 'source.xlsx')
    rows = transaction_rows(b.getvalue(), asset['profile'])
    assert rows[0]['_locator'] == 'sheet=Transactions;row=2'
    assert rows[0]['amount'] == '30'


def test_api_strict_boundary_local_origin_and_missing_files(tmp_path):
    with TestClient(create_app(tmp_path, start_worker=False)) as client:
        assert client.get('/api/health').status_code == 200
        assert client.post('/api/report-types', json={'name': 'a', 'unapproved': True}).status_code == 422
        assert client.post('/api/report-types', json={'name': 'a'}, headers={'Origin': 'https://unrelated.example'}).status_code == 403
        assert client.get('/api/assets/missing/download').status_code == 404
        assert client.get('/api/not-a-route').status_code == 404
        response = client.post('/api/assets', files={'file': ('x.exe', b'bad')})
        assert response.status_code == 422
