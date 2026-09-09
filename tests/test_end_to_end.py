from __future__ import annotations
from fastapi.testclient import TestClient
from foundry.api import create_app
from foundry.cli import seed_demo
from foundry.runtime import default_period
from foundry.service import ROOT, validate_stored_snapshot


def test_native_review_and_all_export_paths(tmp_path, monkeypatch):
    app = create_app(tmp_path, start_worker=False)
    service = app.state.service
    result = seed_demo(service)
    assert result['job']['status'] == 'completed'
    initial_id = result['job']['result']['snapshot_id']
    with TestClient(app) as client:
        original = client.get(f'/api/report-snapshots/{initial_id}').json()
        assert original['status'] == 'review_required'
        assert original['facts']['revenue.current']['value'] == '1200.00'
        changed = client.post(f'/api/report-snapshots/{initial_id}/revisions', json={
            'expected_revision': 1, 'node_id': 'commentary',
            'text': 'Management has reviewed the regional scope of this reporting period.',
            'reason': 'Add reviewed editorial context.'})
        assert changed.status_code == 201, changed.text
        edited = changed.json()
        accepted_response = client.post(f"/api/report-snapshots/{edited['id']}/accept", json={'expected_revision': 2})
        assert accepted_response.status_code == 200, accepted_response.text
        accepted = accepted_response.json()
        assert accepted['status'] == 'accepted'
        assert accepted['metadata']['human_acceptance']['reviewed_findings']
        validate_stored_snapshot(accepted)
        assert client.get(f'/api/report-snapshots/{initial_id}').json() == original
        # Exporting cannot re-enter business preparation or generate different prose.
        def forbidden(*args, **kwargs):
            raise AssertionError('Export attempted to re-run the reporting program')
        monkeypatch.setattr('foundry.runtime.prepare', forbidden)
        for fmt in ('docx', 'xlsx', 'pdf', 'pptx'):
            response = client.post('/api/exports', json={'snapshot_id': accepted['id'], 'format': fmt,
                'policy': 'compatible', 'idempotency_key': f'export-{fmt}'})
            assert response.status_code == 202, response.text
            job = response.json()
            app.state.worker.run_one()
            final = client.get(f"/api/jobs/{job['id']}").json()
            assert final['status'] == 'completed', final
            export_id = final['result']['export_id']
            body = client.get(f'/api/exports/{export_id}/download')
            assert body.status_code == 200 and len(body.content) > 1000
            manifest = client.get(f'/api/exports/{export_id}/manifest').json()
            assert manifest['snapshot_digest'] == accepted['digest']
            again = client.post('/api/exports', json={'snapshot_id': accepted['id'], 'format': fmt,
                'policy': 'compatible', 'idempotency_key': f'export-{fmt}'}).json()
            assert again['id'] == job['id']
        strict = client.post('/api/exports', json={'snapshot_id': accepted['id'], 'format': 'xlsx',
            'policy': 'strict', 'idempotency_key': 'strict-export'}).json()
        app.state.worker.run_one()
        final = client.get(f"/api/jobs/{strict['id']}").json()
        assert final['status'] == 'blocked'
        assert final['error']['code'] == 'native_certification_pending'
        audit = client.get(f"/api/report-snapshots/{accepted['id']}/audit").json()
        assert audit['snapshot']['digest'] == accepted['digest']
        assert audit['program']['package_artifact_digest']
        assert 'transaction_id,date' not in str(audit)  # package/source identities, no raw source bytes


def test_missing_comparison_becomes_persisted_blocked_job(tmp_path):
    app = create_app(tmp_path, start_worker=False)
    service = app.state.service
    result = seed_demo(service)
    rows = (ROOT / 'fixtures' / 'transactions.csv').read_text().splitlines()
    data = '\n'.join([rows[0]] + [line for line in rows[1:] if ',2025-' not in line]).encode()
    asset = service.upload(data, 'missing-comparison.csv')
    job = service.request_run(result['report_type']['id'], asset['id'], default_period().model_dump(mode='json'), 'missing-comparison')
    app.state.worker.run_one()
    final = service.store.job(job['id'])
    assert final['status'] == 'blocked'
    assert final['error']['code'] == 'PERIOD_INCOMPLETE'
    assert final['result'] is None
