"""Regression cases from independent lifecycle and ingestion review."""

from __future__ import annotations

import copy
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from fastapi.testclient import TestClient

from foundry.contracts import Snapshot
from foundry.api import create_app
from foundry.errors import DomainError
from foundry.ingestion import inspect_asset, transaction_rows, rows_from_csv
from foundry.jobs import Worker
from foundry.runtime import default_period, fixture_snapshot
from foundry.service import Service, ROOT, snapshot_dict, validate_stored_snapshot
from foundry.storage import Store, uid


@pytest.fixture
def service(tmp_path):
    return Service(Store(tmp_path))


def workbook_bytes(day):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Transactions'
    ws.append(['transaction_id', 'date', 'region', 'status', 'amount', 'currency'])
    ws.append(['native-date', day, 'North', 'posted', 30, 'EUR'])
    result = BytesIO()
    wb.save(result)
    wb.close()
    return result.getvalue()


def test_native_excel_date_upload_is_json_serializable_and_keeps_evidence(service):
    data = workbook_bytes(datetime(2026, 1, 5))
    asset = service.upload(data, 'native-dates.xlsx')
    assert asset['status'] == 'usable'
    stored = service.store.get('asset', asset['id'])
    observation = next(c for c in stored['profile']['sheets'][0]['cells_sample'] if c['address'] == 'B2')
    assert observation['value'].startswith('2026-01-05')
    assert observation['value_type'] == 'datetime'
    rows = transaction_rows(service.store.read_blob(asset['digest']), stored['profile'])
    assert rows[0]['date'] == '2026-01-05'
    assert rows[0]['_locator'] == 'sheet=Transactions;row=2'


def test_native_excel_timestamp_is_not_silently_truncated(service):
    with pytest.raises(DomainError) as result:
        service.upload(workbook_bytes(datetime(2026, 3, 31, 23, 59)), 'timestamp.xlsx')
    assert result.value.code == 'INPUT_DRIFT'
    assert 'timestamp' in result.value.message


def test_csv_multiline_records_keep_physical_source_locations():
    data = (b'transaction_id,date,region,status,amount,currency\n'
            b'"first\ntransaction",2026-01-01,North,posted,30,EUR\n'
            b'second,2025-01-01,North,posted,20,EUR\n')
    columns, rows = rows_from_csv(data)
    assert rows[0]['_locator'] == 'csv:lines=2-3'
    assert rows[1]['_line'] == 4


@pytest.mark.parametrize('extension', ['xlsx', 'docx'])
def test_zip_without_required_office_parts_returns_format_error(tmp_path, extension):
    content = BytesIO()
    with ZipFile(content, 'w') as archive:
        archive.writestr('hello.txt', 'This is a ZIP but not an Office document.')
    with TestClient(create_app(tmp_path, start_worker=False)) as client:
        response = client.post('/api/assets', files={'file': (f'malformed.{extension}', content.getvalue())})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'FORMAT_INVALID'


def test_accepting_editorial_revision_is_valid_and_preserves_review_history(service):
    initial = snapshot_dict(fixture_snapshot())
    service.store.insert('snapshot', initial)
    revised = service.revise(initial['id'], 1, 'commentary', 'Management context is under review.', 'Clarify context')
    accepted = service.accept(revised['id'], revised['revision'])
    assert validate_stored_snapshot(accepted).status == 'accepted'
    assert accepted['parent_id'] == revised['id']
    assert accepted['revision'] == revised['revision'] + 1
    assert accepted['facts'] == initial['facts']
    assert service.store.get('snapshot', revised['id']) == revised
    assert service.store.get('snapshot', initial['id']) == initial
    assert accepted['metadata']['human_acceptance']['reviewed_findings']
    assert not any(f['severity'] in ('review', 'block') for f in accepted['findings'])


def test_numeric_block_cannot_be_exported_even_as_compatible_draft(service):
    original = snapshot_dict(fixture_snapshot())
    service.store.insert('snapshot', original)
    blocked = service.revise(original['id'], 1, 'commentary', 'Revenue was 1000000 euros.', 'Bad numeric prose')
    try:
        job = service.request_export(blocked['id'], 'pdf', 'compatible', 'blocked-report-export')
    except DomainError as error:
        assert error.code in {'REPORT_BLOCKED', 'SNAPSHOT_BLOCKED'}
    else:
        Worker(service).run_one()
        assert service.store.job(job['id'])['status'] == 'blocked'
    assert service.store.list('export') == []


def pinned_request_fixture(service):
    """Create trusted catalog state directly, avoiding unrelated renderer evaluation."""
    created = service.create_type('Release pinning test')
    report_type, program = created['report_type'], created['program']
    program['state'] = 'published'
    service.store.insert('release', program)
    report_type['active_program_id'] = program['id']
    service.store.update('report_type', report_type['id'], report_type)
    asset = service.upload((ROOT / 'fixtures' / 'transactions.csv').read_bytes(), 'transactions.csv')
    return report_type, program, asset


def test_run_idempotency_reuses_original_pin_after_active_release_changes(service):
    report_type, original, asset = pinned_request_fixture(service)
    period = default_period().model_dump(mode='json')
    first = service.request_run(report_type['id'], asset['id'], period, 'logical-request')
    successor = copy.deepcopy(original)
    successor.update(id=uid('program'), version='2.0.0', digest='b' * 64)
    service.store.insert('release', successor)
    report_type['active_program_id'] = successor['id']
    service.store.update('report_type', report_type['id'], report_type)
    retried = service.request_run(report_type['id'], asset['id'], period, 'logical-request')
    assert retried['id'] == first['id']
    assert retried['payload']['program_id'] == original['id']
    fresh = service.request_run(report_type['id'], asset['id'], period, 'new-logical-request')
    assert fresh['payload']['program_id'] == successor['id']
    changed = copy.deepcopy(period)
    changed['label'] = 'Different declared request'
    with pytest.raises(DomainError) as result:
        service.request_run(report_type['id'], asset['id'], changed, 'logical-request')
    assert result.value.code == 'IDEMPOTENCY_CONFLICT'


def test_stale_worker_publish_rolls_back_all_records_and_result(service):
    queued = service.store.enqueue('generation', 'test', 'stale', {})
    expired = service.store.claim(lease_seconds=-1)
    current = service.store.claim()
    with pytest.raises(DomainError) as result:
        service.store.finish(queued['id'], expired['token'], result={'snapshot_id': 'stale_snapshot'},
                             records=[('snapshot', {'id': 'stale_snapshot'})])
    assert result.value.code == 'LEASE_LOST'
    assert service.store.list('snapshot') == []
    assert service.store.job(queued['id'])['result'] is None
    assert service.store.job(queued['id'])['token'] == current['token']
