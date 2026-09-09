"""Behavioral acceptance tests for successor candidates and pinned history.

These tests use real lifecycle transitions. Exporter smoke work inside program
evaluation is replaced by a small file because actual render correctness has
its own independent suite. Snapshot-export preservation tests use real PDFs.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foundry.api import create_app
from foundry.errors import DomainError
from foundry.jobs import Worker
from foundry.runtime import default_period
from foundry.service import ROOT, Service, validate_stored_snapshot
from foundry.storage import Store, uid


@pytest.fixture
def service(tmp_path):
    return Service(Store(tmp_path))


def _smoke_export(snapshot, format, output_dir, **kwargs):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / f"evaluation.{format}"
    file.write_bytes(b"Lifecycle-only export smoke fixture. " * 8)
    return {"path": str(file)}


def _ready(service, program, monkeypatch):
    for decision in program["decisions"]:
        program = service.resolve(program["id"], decision["id"], decision["alternatives"][0]["value"], program["digest"])
    with monkeypatch.context() as patch:
        patch.setattr("foundry.exporters.export_snapshot", _smoke_export)
        program = service.evaluate(program["id"], program["digest"])
    assert program["evaluation"]["passed"]
    return program


def _publish(service, program, monkeypatch):
    program = _ready(service, program, monkeypatch)
    return service.publish(program["id"], program["digest"])


def _initial_release(service, monkeypatch):
    created = service.create_type("Versioned revenue")
    return created["report_type"], _publish(service, created["program"], monkeypatch)


def _source(service):
    return service.upload((ROOT / "fixtures" / "transactions.csv").read_bytes(), "transactions.csv")


def _period():
    return default_period().model_dump(mode="json")


def _simulate_restarted_runtime(monkeypatch):
    import foundry.service as module
    # Keep actual file hashes intact so package assembly remains a real check.
    # A changed process identity exercises the runtime pin independently of a
    # particular arithmetic implementation change.
    changed = copy.deepcopy(module.code_identity())
    changed["test_runtime_build"] = "successor-runtime"
    monkeypatch.setattr(module, "code_identity", lambda: copy.deepcopy(changed))
    monkeypatch.setattr(module, "PROCESS_CODE_IDENTITY", copy.deepcopy(changed))
    return changed


def test_successor_requires_new_review_without_changing_active_release(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    frozen = copy.deepcopy(service.store.get("release", first["id"]))
    old_package = service.store.read_blob(first["package_artifact_digest"])
    second = service.create_candidate(first["id"], first["digest"], "Review the next version")
    assert second["report_type_id"] == report_type["id"]
    assert second["id"] != first["id"] and second["version"] == "1.1.0"
    assert second["state"] == "candidate"
    assert second["lineage"]["parent_program_id"] == first["id"]
    assert second["lineage"]["parent_program_digest"] == first["digest"]
    assert second["lineage"]["reason"] == "Review the next version"
    assert second["policy"] == first["policy"]
    assert second["input_contract"] == first["input_contract"]
    assert second.get("evaluation") is None
    assert not second.get("approval") and not second.get("package_artifact_digest")
    assert not second.get("published_at")
    assert all(item["status"] == "implemented" for item in second["coverage"])
    for current, prior in zip(second["decisions"], first["decisions"]):
        assert current["resolution"] is None
        assert current["prior_resolution"] == prior["resolution"]
        assert current["inherited_from"]
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == first["id"]
    with pytest.raises(DomainError):
        service.publish(second["id"], second["digest"])
    assert service.store.get("release", first["id"]) == frozen
    assert service.store.read_blob(first["package_artifact_digest"]) == old_package


def test_identical_candidate_request_reuses_candidate_different_reason_conflicts(service, monkeypatch):
    _, first = _initial_release(service, monkeypatch)
    one = service.create_candidate(first["id"], first["digest"], "Review refreshed code")
    repeated = service.create_candidate(first["id"], first["digest"], "  Review refreshed code  ")
    assert repeated["id"] == one["id"]
    with pytest.raises(DomainError) as error:
        service.create_candidate(first["id"], first["digest"], "A separate change")
    assert error.value.code == "CANDIDATE_EXISTS"
    assert len([p for p in service.store.list("program") if p["state"] == "candidate"]) == 1


def test_stale_parent_digest_cannot_create_a_successor(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    before = service.store.list("program")
    with pytest.raises(DomainError) as error:
        service.create_candidate(first["id"], "0" * 64, "Wrong historical identity")
    assert error.value.code == "VERSION_CONFLICT"
    assert service.store.list("program") == before
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == first["id"]


def test_publication_switches_active_pointer_and_retains_old_release(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    original_release = copy.deepcopy(service.store.get("release", first["id"]))
    second = service.create_candidate(first["id"], first["digest"], "Publish a reviewed successor")
    second = _publish(service, second, monkeypatch)
    assert second["state"] == "published"
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == second["id"]
    assert service.store.get("release", first["id"]) == original_release
    assert service.store.get("release", second["id"])["approval"]["digest"] == second["digest"]
    assert {r["id"] for r in service.store.list("release")} == {first["id"], second["id"]}
    with pytest.raises(DomainError):
        service.create_candidate(first["id"], first["digest"], "An obsolete branch")
    with pytest.raises(DomainError):
        service.discard_candidate(second["id"], second["digest"], "Cannot discard a release")
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == second["id"]


def test_discard_retains_history_and_never_reuses_version_number(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    second = service.create_candidate(first["id"], first["digest"], "Explore a candidate")
    with pytest.raises(DomainError) as stale:
        service.discard_candidate(second["id"], "0" * 64, "Stale discard")
    assert stale.value.code == "VERSION_CONFLICT"
    discarded = service.discard_candidate(second["id"], second["digest"], "Defer this change")
    assert discarded["state"] == "discarded"
    assert service.store.get("program", second["id"]) == discarded
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == first["id"]
    assert all(r["id"] != second["id"] for r in service.store.list("release"))
    with pytest.raises(DomainError):
        service.evaluate(discarded["id"], discarded["digest"])
    with pytest.raises(DomainError):
        service.publish(discarded["id"], discarded["digest"])
    third = service.create_candidate(first["id"], first["digest"], "A fresh candidate")
    assert third["id"] != second["id"] and third["version"] == "1.2.0"
    assert len(service.store.list("program")) == 3


def test_publication_cas_rejects_a_candidate_based_on_an_obsolete_active_release(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    candidate = _ready(service, service.create_candidate(first["id"], first["digest"], "Waiting for review"), monkeypatch)
    # Simulate a competing catalog publication while this reviewed candidate
    # waits. The service must compare its original base inside the final txn.
    competing = copy.deepcopy(first)
    competing.update(id=uid("program"), version="2.0.0")
    service.store.insert("release", competing)
    active = service.store.get("report_type", report_type["id"])
    active["active_program_id"] = competing["id"]
    service.store.update("report_type", active["id"], active)
    with pytest.raises(DomainError) as error:
        service.publish(candidate["id"], candidate["digest"])
    assert error.value.status_code == 409
    assert service.store.get("report_type", active["id"])["active_program_id"] == competing["id"]
    assert service.store.get("program", candidate["id"])["state"] == "candidate"
    assert not any(r["id"] == candidate["id"] for r in service.store.list("release"))


def test_failed_publication_rolls_back_release_candidate_and_active_pointer(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    candidate = _ready(service, service.create_candidate(first["id"], first["digest"], "Publication transaction"), monkeypatch)
    original_audit = service.store.audit
    def fail_audit(subject, action, data, db=None):
        if subject == candidate["id"] and action == "published":
            raise RuntimeError("Injected catalog failure")
        return original_audit(subject, action, data, db)
    monkeypatch.setattr(service.store, "audit", fail_audit)
    with pytest.raises(RuntimeError, match="Injected"):
        service.publish(candidate["id"], candidate["digest"])
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == first["id"]
    assert service.store.get("program", candidate["id"]) == candidate
    assert not any(r["id"] == candidate["id"] for r in service.store.list("release"))


def test_queued_runs_keep_old_release_while_new_requests_use_successor(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    source = _source(service)
    queued = service.request_run(report_type["id"], source["id"], _period(), "before-publication")
    second = _publish(service, service.create_candidate(first["id"], first["digest"], "Same runtime new review"), monkeypatch)
    repeated = service.request_run(report_type["id"], source["id"], _period(), "before-publication")
    fresh = service.request_run(report_type["id"], source["id"], _period(), "after-publication")
    assert repeated["id"] == queued["id"]
    assert repeated["payload"]["program_id"] == first["id"]
    assert fresh["payload"]["program_id"] == second["id"]
    worker = Worker(service)
    worker.run_one()
    worker.run_one()
    old_snapshot = service.store.get("snapshot", service.store.job(queued["id"])["result"]["snapshot_id"])
    new_snapshot = service.store.get("snapshot", service.store.job(fresh["id"])["result"]["snapshot_id"])
    assert old_snapshot["program"]["id"] == first["id"]
    assert old_snapshot["program"]["digest"] == first["digest"]
    assert new_snapshot["program"]["id"] == second["id"]
    assert old_snapshot["facts"] == new_snapshot["facts"]


def test_disk_code_drift_requires_restart_before_candidate_mutation(service, monkeypatch):
    import foundry.service as module
    report_type, first = _initial_release(service, monkeypatch)
    installed = copy.deepcopy(module.code_identity())
    installed["test_runtime_build"] = "changed-on-disk-only"
    monkeypatch.setattr(module, "code_identity", lambda: copy.deepcopy(installed))
    with pytest.raises(DomainError) as error:
        service.create_candidate(first["id"], first["digest"], "Must restart first")
    assert error.value.code == "RUNTIME_RESTART_REQUIRED"
    assert len(service.store.list("program")) == 1
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == first["id"]


def test_runtime_drift_blocks_old_jobs_but_old_snapshot_export_survives(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    source = _source(service)
    worker = Worker(service)
    original_job = service.request_run(report_type["id"], source["id"], _period(), "materialized-before-update")
    worker.run_one()
    original = service.store.get("snapshot", service.store.job(original_job["id"])["result"]["snapshot_id"])
    pinned_job = service.request_run(report_type["id"], source["id"], _period(), "queued-before-update")
    changed_identity = _simulate_restarted_runtime(monkeypatch)
    candidate = service.create_candidate(first["id"], first["digest"], "Evaluate newly installed runtime")
    assert candidate["code_identity"] == changed_identity
    successor = _publish(service, candidate, monkeypatch)
    worker.run_one()
    blocked = service.store.job(pinned_job["id"])
    assert blocked["status"] == "blocked" and blocked["error"]["code"] == "CODE_CHANGED"
    assert blocked["payload"]["program_id"] == first["id"] and blocked["result"] is None
    assert service.store.get("snapshot", original["id"]) == original
    validate_stored_snapshot(original)
    assert service.store.get("release", first["id"])["package_artifact_digest"]
    fresh = service.request_run(report_type["id"], source["id"], _period(), "new-runtime-request")
    worker.run_one()
    new_snapshot = service.store.get("snapshot", service.store.job(fresh["id"])["result"]["snapshot_id"])
    assert new_snapshot["program"]["id"] == successor["id"]
    def no_prepare(*args, **kwargs):
        raise AssertionError("Export re-entered the reporting runtime")
    monkeypatch.setattr("foundry.runtime.prepare", no_prepare)
    export_job = service.request_export(original["id"], "pdf", "compatible", "old-snapshot-after-update")
    worker.run_one()
    finished = service.store.job(export_job["id"])
    assert finished["status"] == "completed", finished
    exported = service.store.get("export", finished["result"]["export_id"])
    assert exported["snapshot_digest"] == original["digest"]
    assert service.store.read_blob(exported["digest"]).startswith(b"%PDF-")


def test_api_successor_review_discard_and_replacement(tmp_path, monkeypatch):
    app = create_app(tmp_path, start_worker=False)
    service = app.state.service
    with TestClient(app) as client:
        created = client.post("/api/report-types", json={"name": "API version history"}).json()
        first = _publish(service, created["program"], monkeypatch)
        original_package = client.get(f"/api/programs/{first['id']}/package")
        assert original_package.status_code == 200
        assert original_package.json()["program_digest"] == first["digest"]
        body = {"expected_digest": first["digest"], "reason": "Review a successor"}
        response = client.post(f"/api/programs/{first['id']}/candidates", json=body)
        assert response.status_code == 201, response.text
        candidate = response.json()
        assert client.get(f"/api/programs/{candidate['id']}/package").status_code in {404, 409}
        repeated = client.post(f"/api/programs/{first['id']}/candidates", json=body)
        assert repeated.status_code == 201 and repeated.json()["id"] == candidate["id"]
        invalid = client.post(f"/api/programs/{first['id']}/candidates", json={**body, "unapproved": True})
        assert invalid.status_code == 422
        retired = client.post(f"/api/programs/{candidate['id']}/discard", json={
            "expected_digest": candidate["digest"], "reason": "A different change is needed"})
        assert retired.status_code == 200 and retired.json()["state"] == "discarded"
        replacement = client.post(f"/api/programs/{first['id']}/candidates", json={**body, "reason": "Replacement change"})
        assert replacement.status_code == 201
        assert replacement.json()["version"] == "1.2.0"
        assert client.get(f"/api/programs/{candidate['id']}").json()["state"] == "discarded"
        assert client.get("/api/bootstrap").json()["report_types"][0]["active_program_id"] == first["id"]
        published = _publish(service, replacement.json(), monkeypatch)
        new_package = client.get(f"/api/programs/{published['id']}/package")
        assert new_package.status_code == 200
        assert new_package.json()["program_digest"] == published["digest"]
        assert client.get(f"/api/programs/{first['id']}/package").content == original_package.content
        assert new_package.content != original_package.content


def test_candidate_code_refresh_invalidates_prior_decisions_and_evaluation(service, monkeypatch):
    report_type, first = _initial_release(service, monkeypatch)
    candidate = _ready(service, service.create_candidate(first["id"], first["digest"], "Before a runtime update"), monkeypatch)
    prior_digest = candidate["digest"]
    changed = _simulate_restarted_runtime(monkeypatch)
    with pytest.raises(DomainError) as result:
        service.evaluate(candidate["id"], prior_digest)
    assert result.value.code == "CODE_CHANGED"
    refreshed = service.store.get("program", candidate["id"])
    assert refreshed["digest"] != prior_digest
    assert refreshed["code_identity"] == changed
    assert refreshed["evaluation"] is None
    assert all(item["resolution"] is None for item in refreshed["decisions"])
    assert all(item["status"] == "implemented" for item in refreshed["coverage"])
    assert service.store.get("report_type", report_type["id"])["active_program_id"] == first["id"]
    with pytest.raises(DomainError) as stale:
        service.publish(refreshed["id"], prior_digest)
    assert stale.value.code == "VERSION_CONFLICT"
    released = _publish(service, refreshed, monkeypatch)
    assert released["approval"]["digest"] == released["digest"] != prior_digest
    assert released["evaluation"]["digest"] == released["digest"]


def test_evaluation_cannot_commit_after_candidate_changes_during_checks(service, monkeypatch):
    _, first = _initial_release(service, monkeypatch)
    candidate = service.create_candidate(first["id"], first["digest"], "Concurrent evaluation")
    for item in candidate["decisions"]:
        candidate = service.resolve(candidate["id"], item["id"], item["alternatives"][0]["value"], candidate["digest"])
    before_digest = candidate["digest"]
    changed = False
    def racing_export(snapshot, format, output_dir, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            latest = service.store.get("program", candidate["id"])
            choice = latest["decisions"][0]
            service.resolve(latest["id"], choice["id"], choice["resolution"], latest["digest"])
        return _smoke_export(snapshot, format, output_dir, **kwargs)
    monkeypatch.setattr("foundry.exporters.export_snapshot", racing_export)
    with pytest.raises(DomainError) as result:
        service.evaluate(candidate["id"], before_digest)
    assert result.value.code == "VERSION_CONFLICT"
    latest = service.store.get("program", candidate["id"])
    assert latest["digest"] != before_digest and latest["evaluation"] is None
    assert all(item["status"] == "implemented" for item in latest["coverage"])


def test_initial_candidate_cannot_be_discarded_and_strand_its_report_type(service):
    created = service.create_type("Initial candidate required")
    program = created["program"]
    with pytest.raises(DomainError) as result:
        service.discard_candidate(program["id"], program["digest"], "Would leave no usable program")
    assert result.value.code == "INITIAL_CANDIDATE_REQUIRED"
    assert service.store.get("program", program["id"]) == program
    assert service.store.get("report_type", created["report_type"]["id"])["active_program_id"] is None


def test_parallel_successor_requests_create_only_one_open_candidate(service, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    report_type, first = _initial_release(service, monkeypatch)
    barrier = Barrier(2)
    def request(reason):
        barrier.wait(timeout=5)
        try:
            return service.create_candidate(first["id"], first["digest"], reason)
        except DomainError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(request, reason) for reason in ["Concurrent change A", "Concurrent change B"]]
        results = [future.result(timeout=15) for future in futures]
    winners = [item for item in results if isinstance(item, dict)]
    conflicts = [item for item in results if isinstance(item, DomainError)]
    assert len(winners) == 1 and len(conflicts) == 1
    assert conflicts[0].code == "CANDIDATE_EXISTS"
    assert winners[0]["version"] == "1.1.0"
    stored = [p for p in service.store.list("program") if p["report_type_id"] == report_type["id"]]
    assert len(stored) == 2 and len([p for p in stored if p["state"] == "candidate"]) == 1


def test_program_get_is_coherent_when_publication_occurs_between_catalog_reads(tmp_path, monkeypatch):
    app = create_app(tmp_path, start_worker=False)
    service = app.state.service
    report_type, first = _initial_release(service, monkeypatch)
    candidate = _ready(service, service.create_candidate(first["id"], first["digest"], "Publish while a reader is open"), monkeypatch)
    original_get = service.store.get
    inject_publication = True
    publications = []
    def interleaved_get(kind, id, db=None):
        nonlocal inject_publication
        record = original_get(kind, id, db)
        if inject_publication and kind == "program" and id == candidate["id"] and db is not None:
            # The response has read the old candidate. Commit publication on a
            # separate connection before it reads the report type's pointer.
            # Clear first because publishing also reads this same program.
            inject_publication = False
            publications.append(service.publish(candidate["id"], candidate["digest"]))
        return record
    monkeypatch.setattr(service.store, "get", interleaved_get)
    with TestClient(app) as client:
        response = client.get(f"/api/programs/{candidate['id']}")
    assert response.status_code == 200, response.text
    assert len(publications) == 1 and publications[0]["state"] == "published"
    observed = response.json()
    assert observed["state"] == "candidate"
    assert observed["lifecycle_status"] == "candidate"
    assert observed["active_program_id"] == first["id"]
    assert original_get("program", candidate["id"])["state"] == "published"
    assert original_get("report_type", report_type["id"])["active_program_id"] == candidate["id"]
