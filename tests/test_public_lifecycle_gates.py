"""Service/worker regressions for blocked uploads and scoped reserved evidence.

Real parsers, storage, learning, evaluation and renderers are used. No provider
is allowed to run. Literal ONS development fixtures avoid relying on holdouts.
"""
from datetime import date, timedelta
from io import BytesIO
import json
import textwrap

from docx import Document
import pytest
from reportlab.pdfgen import canvas

from foundry.errors import DomainError
from foundry.jobs import Worker
from foundry.service import ROOT, Service
from foundry.storage import Store


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('Public lifecycle gate tests must never dispatch a model')
    monkeypatch.setattr('foundry.model_provider.OpenAIProvider.generate', forbidden)
    monkeypatch.setattr('foundry.model_provider._responses_transport', forbidden)
    monkeypatch.setattr('foundry.model_provider._https_transport', forbidden)


@pytest.fixture
def service(tmp_path):
    return Service(Store(tmp_path / 'workspace'))


def period(month, vintage):
    start = date.fromisoformat(month + '-01')
    return {'label': month, 'start': start.isoformat(),
            'end_exclusive': (start.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat(),
            'comparison': {'start': (start - timedelta(days=1)).replace(day=1).isoformat(),
                           'end_exclusive': start.isoformat()},
            'timezone': 'UTC', 'as_of': (date.fromisoformat(vintage) + timedelta(days=2)).isoformat() + 'T00:00:00Z'}


def finish(service, requested):
    assert Worker(service).run_one()
    return service.store.job(requested['id'])


def learn(service, program):
    requested = service.request_learning(program['id'], program['digest'], 'Registered headlines only.',
                                         'deterministic', 'learn')
    done = finish(service, requested)
    assert done['status'] == 'completed', done.get('error')
    assert not service.store.list('model_call')
    return service.store.get('program', program['id'])


def review(service, program, *, approve_scope=True):
    for decision in program['decisions']:
        if decision['id'] == 'scope' and not approve_scope:
            continue
        value = decision['alternatives'][0]['value']
        if decision['id'] == 'selection' and program['policy']['adapter'] == 'quarterly-revenue-v1':
            value = 'largest_absolute_change'
        program = service.resolve(program['id'], decision['id'], value, program['digest'])
    for region in program['learning']['coverage']:
        if region['status'] not in {'mapped', 'out_of_scope'}:
            program = service.review_coverage(program['id'], program['digest'], region['id'], 'out_of_scope',
                'Explicit test review: only the registered observations are reconstructed; remaining material stays unverified.')
    return program


def publish(service, program):
    evaluated = service.evaluate(program['id'], program['digest'])
    assert evaluated['evaluation']['passed'], evaluated['evaluation']
    return service.publish(evaluated['id'], evaluated['digest'], actor='lifecycle_test_scope_review')


def pdf_bytes(regions):
    output = BytesIO()
    document = canvas.Canvas(output)
    for region in regions:
        y = 800
        for paragraph in region['text'].splitlines():
            for line in textwrap.wrap(paragraph, 96) or ['']:
                document.drawString(40, y, line)
                y -= 14
        document.showPage()
    document.save()
    return output.getvalue()


def ons_pair(service, program, *, reserved=False, failure=None):
    from test_public_ons import source_rows, encode, report_asset, EXPECTED_JULY
    rows = source_rows()
    target = report_asset(july=reserved)
    month, vintage = ('2025-07', '2025-09-05') if reserved else ('2025-06', '2025-07-25')
    if reserved:
        rows[4][1:] = ['05-09-2025'] * 7
        rows[5][1:] = ['19 September 2025'] * 7
        rows[-1][1] = '0.3'
        rows.append(['2025 JUL', *EXPECTED_JULY.values()])
        target['profile']['regions'][0]['text'] += '\nReserved-only sentinel: withheld details must remain private.'
        if failure == 'missing_headline':
            last = target['profile']['regions'][-1]
            last['text'] = last['text'].split('As a result,')[0]
        elif failure == 'contradiction':
            overview = target['profile']['regions'][1]
            assert 'risen by 0.6%' in overview['text']
            overview['text'] = overview['text'].replace('risen by 0.6%', 'risen by 99.7%')
    source_data, report_data = encode(rows), pdf_bytes(target['profile']['regions'])
    source = service.upload(source_data, 'reserved-source.csv' if reserved else 'authoring-source.csv', public_family='ons_retail')
    report = service.upload(report_data, 'reserved-report.pdf' if reserved else 'authoring-report.pdf', public_family='ons_retail')
    window = period(month, vintage)
    example = service.add_example(program['report_type_id'], report['id'], [source['id']], window,
                                  'reserved' if reserved else 'authoring')
    return {'example': example, 'source': source, 'report': report, 'period': window,
            'source_bytes': source_data, 'report_bytes': report_data}


def public_reserved_setup(service, *, failure=None, approve_scope=True):
    program = service.create_type('Scoped reserved public report', family='ons_retail')['program']
    authoring = ons_pair(service, program)
    reserved = ons_pair(service, program, reserved=True, failure=failure)
    program = review(service, learn(service, program), approve_scope=approve_scope)
    assert reserved['example']['id'] not in program['learning']['example_ids']
    assert all(region['example_id'] == authoring['example']['id'] for region in program['learning']['coverage'])
    return program, authoring, reserved


def withheld_check(result):
    checks = [c for c in result['checks'] if c['name'].startswith('Reserved pair')]
    assert len(checks) == 1
    encoded = json.dumps(checks)
    assert 'Reserved-only sentinel' not in encoded and '99.7' not in encoded
    assert 'discrepancies' not in checks[0] and 'expected' not in checks[0]
    assert 'withheld' in checks[0]['detail'].lower()
    return checks[0]


@pytest.mark.parametrize('bad_cell,bad_value', [('C15', 99.9), ('C15', None)])
def test_blocking_census_upload_is_visible_and_direct_generation_is_durably_blocked(service, bad_cell, bad_value):
    from test_public_census import original, edit_cell
    program = service.create_type('Census blocking source gate', family='census_marts')['program']
    raw = original(5, 'source')
    source = service.upload(raw, 'may-source.xlsx', public_family='census_marts')
    report = service.upload(original(5, 'report'), 'may-report.pdf', public_family='census_marts')
    window = period('2025-05', '2025-06-17')
    service.add_example(program['report_type_id'], report['id'], [source['id']], window, 'authoring')
    released = publish(service, review(service, learn(service, program)))
    broken_data = edit_cell(raw, 2, bad_cell, bad_value)
    broken = service.upload(broken_data, 'broken-source.xlsx', public_family='census_marts')
    assert broken['status'] == 'blocked'
    assert broken['profile']['eligible_roles'] == ['public_source:census_marts']
    blocks = [i for i in broken['profile']['issues'] if i['severity'] == 'block']
    assert blocks and all(any(i['code'] in warning and i['message'] in warning for warning in broken['profile']['warnings']) for i in blocks)
    assert service.asset_view(broken['id'])['status'] == 'blocked'
    assert service.asset_bytes(broken['id'])[1] == broken_data  # evidence remains downloadable
    before = {kind: len(service.store.list(kind)) for kind in ('snapshot', 'export', 'model_call', 'release')}
    requested = service.request_run(released['report_type_id'], broken['id'], window, 'blocked-source')
    result = finish(service, requested)
    assert result['status'] == 'blocked' and result['error']['code'] == 'SOURCE_RECONCILIATION_REQUIRED'
    assert not result.get('result')
    assert {kind: len(service.store.list(kind)) for kind in before} == before
    retried = service.request_run(released['report_type_id'], broken['id'], window, 'blocked-source')
    assert retried['id'] == requested['id'] and retried['status'] == 'blocked'
    assert not Worker(service).run_one()


def test_scoped_reserved_headlines_pass_real_evaluation_and_publish_without_full_page_claim(service):
    program, _, reserved = public_reserved_setup(service)
    raw = service.store.get('example', reserved['example']['id'])
    assert any(r['status'] != 'mapped' for r in raw['inspection']['regions'])
    evaluated = service.evaluate(program['id'], program['digest'])
    check = withheld_check(evaluated['evaluation'])
    assert check['passed'] is True and evaluated['evaluation']['passed'] is True
    assert 'unverified' in check['detail'].lower()
    released = service.publish(evaluated['id'], evaluated['digest'], actor='lifecycle_test_scope_review')
    assert released['state'] == 'published'
    assert service.example_view(reserved['example']['id'])['inspection'] is None
    assert service.asset_view(reserved['report']['id'])['reserved'] is True
    assert not service.store.list('snapshot') and not service.store.list('model_call')


@pytest.mark.parametrize('failure,approve_scope', [(None, False), ('missing_headline', True), ('contradiction', True)])
def test_reserved_public_missing_scope_or_invalid_headlines_fail_without_leaking_details(service, failure, approve_scope):
    program, _, reserved = public_reserved_setup(service, failure=failure, approve_scope=approve_scope)
    evaluated = service.evaluate(program['id'], program['digest'])
    assert withheld_check(evaluated['evaluation'])['passed'] is False
    assert evaluated['evaluation']['passed'] is False
    assert 'Reserved-only sentinel' not in json.dumps(evaluated)
    assert '99.7' not in json.dumps(evaluated['evaluation'])
    with pytest.raises(DomainError) as rejected:
        service.publish(evaluated['id'], evaluated['digest'])
    assert rejected.value.code == ('EVALUATION_REQUIRED' if approve_scope else 'POLICY_UNRESOLVED')
    assert not service.store.list('release') and not service.store.list('snapshot')
    assert service.example_view(reserved['example']['id'])['inspection'] is None


def test_public_reserved_assets_and_aliases_cannot_feed_source_reuse_or_composition(service):
    program, authoring, reserved = public_reserved_setup(service)
    released = publish(service, program)
    generated = finish(service, service.request_run(released['report_type_id'], authoring['source']['id'], authoring['period'], 'authoring-only-run'))
    assert generated['status'] == 'completed'
    snapshot = service.store.get('snapshot', generated['result']['snapshot_id'])
    aliases = [service.upload(reserved['source_bytes'], 'renamed-source.csv', public_family='ons_retail'),
               service.upload(reserved['report_bytes'], 'renamed-report.pdf', public_family='ons_retail')]
    with service.store.connect() as db:
        before_jobs = db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    for asset in [reserved['source'], reserved['report'], *aliases]:
        view = service.asset_view(asset['id'])
        assert view['reserved'] is True and view['profile']['regions'] == []
        assert 'metadata' not in view['profile'] and 'normalized_digest' not in view['profile']
        with pytest.raises(DomainError) as read:
            service.asset_bytes(asset['id'])
        assert read.value.code == 'RESERVED_EVIDENCE'
        with pytest.raises(DomainError) as compose:
            service.request_composition(snapshot['id'], snapshot['revision'], [asset['id']], 'Describe the published figures.', 'compose-' + asset['id'])
        assert compose.value.code == 'RESERVED_EVIDENCE'
    for source in [reserved['source'], aliases[0]]:
        with pytest.raises(DomainError) as reuse:
            service.request_run(released['report_type_id'], source['id'], reserved['period'], 'reuse-' + source['id'])
        assert reuse.value.code == 'RESERVED_EVIDENCE'
    reserved_entry = next(e for e in program['learning']['corpus'] if e['role'] == 'reserved')
    with pytest.raises(DomainError) as learner:
        service._case(reserved_entry)
    assert learner.value.code == 'RESERVED_EVIDENCE'
    with service.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == before_jobs
    assert len(service.store.list('snapshot')) == 1 and not service.store.list('model_call')


def test_legacy_revenue_reserved_unknown_region_still_requires_complete_coverage(service):
    program = service.create_type('Legacy full-report reserved gate')['program']
    folder = ROOT / 'fixtures/learning/ambiguous'
    target = service.upload((folder / 'report.docx').read_bytes(), 'authoring.docx')
    source = service.upload((folder / 'transactions.csv').read_bytes(), 'authoring.csv')
    service.add_example(program['report_type_id'], target['id'], [source['id']], json.loads((folder / 'period.json').read_text()), 'authoring')
    folder = ROOT / 'fixtures/learning/discriminating'
    document = Document(BytesIO((folder / 'report.docx').read_bytes()))
    document.add_paragraph('Reserved-only sentinel: legacy unknown prose remains unverified.')
    output = BytesIO(); document.save(output)
    target = service.upload(output.getvalue(), 'reserved.docx')
    source = service.upload((folder / 'transactions.csv').read_bytes(), 'reserved.csv')
    service.add_example(program['report_type_id'], target['id'], [source['id']], json.loads((folder / 'period.json').read_text()), 'reserved')
    program = review(service, learn(service, program))
    result = service._evaluate_examples(program)
    assert withheld_check(result)['passed'] is False
    assert all(c['passed'] for c in result['checks'] if not c['name'].startswith('Reserved pair'))
    assert 'Reserved-only sentinel' not in json.dumps(result)
