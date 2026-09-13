"""Adversarial historical-to-future lifecycles through the real local service.

These tests exercise deterministic reconstruction and real release evaluation.
They make no model calls and do not claim model quality. Invalid sources must
never become an apparently successful zero-valued report or an export.
"""
from __future__ import annotations

import copy
import csv
from io import BytesIO, StringIO
import json
import shutil

from docx import Document
import pytest

from foundry.errors import DomainError
from foundry.jobs import Worker
from foundry.service import ROOT, Service, validate_stored_snapshot
from foundry.storage import Store


HISTORICAL = ROOT / "fixtures" / "learning"
COLUMNS = ["transaction_id", "date", "region", "status", "amount", "currency"]
SELECTIONS = ["largest_absolute_change", "largest_percentage_change", "largest_current_revenue"]
NEXT_PERIOD = {
    "label": "Q2 2026",
    "start": "2026-04-01",
    "end_exclusive": "2026-07-01",
    "comparison": {"start": "2025-04-01", "end_exclusive": "2025-07-01"},
    "timezone": "Europe/Paris",
    "as_of": "2026-07-03T12:00:00+02:00",
}


def _source(rows, columns=COLUMNS):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _row(identity, day, amount, region="North", status="posted", currency="EUR"):
    return dict(zip(COLUMNS, [identity, day, region, status, amount, currency]))


def _future_rows():
    # Independently declared new period: current 650, comparison 500, delta 150.
    return [
        _row("new-north", "2026-04-01", "400.00"),
        _row("new-south", "2026-06-30", "250.00", "South"),
        _row("prior-north", "2025-04-01", "200.00"),
        _row("prior-south", "2025-06-30", "300.00", "South"),
    ]


def _finish(service, job):
    assert Worker(service).run_one()
    completed = service.store.job(job["id"])
    assert completed["status"] not in {"queued", "running"}
    return completed


def _pair(service, report_type_id, name, replacements=None, label=""):
    directory = HISTORICAL / name
    report_bytes = (directory / "report.docx").read_bytes()
    if replacements:
        document = Document(BytesIO(report_bytes))
        for old, new in replacements.items():
            paragraphs = [p for p in document.paragraphs if p.text == old]
            assert len(paragraphs) == 1
            paragraphs[0].text = new
        output = BytesIO()
        document.save(output)
        report_bytes = output.getvalue()
    report = service.upload(report_bytes, f"{name}-{label or 'original'}.docx")
    source = service.upload((directory / "transactions.csv").read_bytes(), f"{name}.csv")
    period = json.loads((directory / "period.json").read_text())
    return service.add_example(report_type_id, report["id"], [source["id"]], period, "authoring")


def _learn(service, program):
    job = service.request_learning(program["id"], program["digest"], "", "deterministic", "historical-learning")
    completed = _finish(service, job)
    assert completed["status"] == "completed", completed.get("error")
    assert service.store.list("model_call") == []
    return service.store.get("program", program["id"]), completed


def _review(service, program, selection="largest_absolute_change"):
    for decision in program["decisions"]:
        value = selection if decision["id"] == "selection" else decision["alternatives"][0]["value"]
        program = service.resolve(program["id"], decision["id"], value, program["digest"])
    return program


@pytest.fixture(scope="module")
def released_template(tmp_path_factory):
    """A real learned/evaluated release; never insert a fabricated release row."""
    directory = tmp_path_factory.mktemp("evolution-release")
    service = Service(Store(directory))
    created = service.create_type("Adversarial future-period validation")
    report_type, program = created["report_type"], created["program"]
    for name in ("ambiguous", "discriminating"):
        _pair(service, report_type["id"], name)
    learned, _ = _learn(service, program)
    assert [h["value"] for h in learned["learning"]["hypotheses"] if h["supported"]] == ["largest_absolute_change"]
    reviewed = _review(service, learned)
    evaluated = service.evaluate(reviewed["id"], reviewed["digest"])
    assert evaluated["evaluation"]["passed"], evaluated["evaluation"]
    assert evaluated["evaluation"]["reconstruction_count"] == 2
    released = service.publish(evaluated["id"], evaluated["digest"], actor="synthetic_test_reviewer")
    assert released["state"] == "published"
    assert service.store.list("snapshot") == service.store.list("export") == []
    return directory, report_type["id"]


@pytest.fixture
def released_service(released_template, tmp_path):
    directory, report_type_id = released_template
    target = tmp_path / "isolated-release"
    shutil.copytree(directory, target)
    return Service(Store(target)), report_type_id


def _assert_no_output(service):
    assert service.store.list("snapshot") == []
    assert service.store.list("export") == []
    assert service.store.list("model_call") == []
    assert not any(j["kind"] == "export" for j in service.store.jobs())


def _blocked_run(service, report_type_id, rows, code="INPUT_DRIFT", period=None):
    data = _source(rows)
    asset = service.upload(data, "unseen-period.csv")
    assert "transactions" in asset["profile"]["eligible_roles"]
    requested = service.request_run(report_type_id, asset["id"], period or NEXT_PERIOD, "invalid-future-run")
    completed = _finish(service, requested)
    assert completed["status"] == "blocked", completed
    assert completed["error"]["code"] == code, completed
    assert completed["result"] is None
    assert service.store.read_blob(asset["digest"]) == data
    # Retry is the same durable failure, not another chance to create a report.
    retried = service.request_run(report_type_id, asset["id"], period or NEXT_PERIOD, "invalid-future-run")
    assert retried["id"] == completed["id"] and retried["status"] == "blocked"
    assert Worker(service).run_one() is False
    _assert_no_output(service)
    return completed


@pytest.mark.parametrize("target_failure", ["contradictory_selection", "wrong_total"])
def test_inconsistent_historical_corpus_cannot_be_published_under_any_policy(tmp_path, target_failure):
    service = Service(Store(tmp_path))
    created = service.create_type("Historical contradiction gate")
    report_type, program = created["report_type"], created["program"]
    original = _pair(service, report_type["id"], "discriminating")
    replacements = ({"Selected region: South": "Selected region: East"}
                    if target_failure == "contradictory_selection"
                    else {"Current revenue (EUR): 1,600.00": "Current revenue (EUR): 1,999.00"})
    changed = _pair(service, report_type["id"], "discriminating", replacements, target_failure)
    assert original["report_asset_id"] != changed["report_asset_id"]
    learned, job = _learn(service, program)
    assert all(not hypothesis["supported"] for hypothesis in learned["learning"]["hypotheses"])
    assert all(decision["resolution"] is None for decision in learned["decisions"])
    assert job["result"] is not None  # Analysis succeeds while publication remains unavailable.
    for selection in SELECTIONS:
        reviewed = _review(service, learned, selection)
        evaluated = service.evaluate(reviewed["id"], reviewed["digest"])
        assert evaluated["evaluation"]["passed"] is False
        failures = [c for c in evaluated["evaluation"]["checks"]
                    if c["name"].startswith("Historical reconstruction") and not c["passed"]]
        assert failures
        if target_failure == "wrong_total":
            discrepancy = next(d for c in failures for d in c["discrepancies"]
                               if d.get("fact_id") == "revenue.current" and not d["passed"])
            assert discrepancy["expected"] == "1999.00" and discrepancy["actual"] == "1600.00"
        with pytest.raises(DomainError) as error:
            service.publish(evaluated["id"], evaluated["digest"])
        assert error.value.code == "EVALUATION_REQUIRED"
        learned = evaluated
    assert service.store.list("release") == []
    assert service.store.get("report_type", report_type["id"])["active_program_id"] is None
    source = service.upload(_source(_future_rows()), "next.csv")
    with pytest.raises(DomainError) as error:
        service.request_run(report_type["id"], source["id"], NEXT_PERIOD, "cannot-run-unpublished")
    assert error.value.code == "PROGRAM_UNPUBLISHED"
    _assert_no_output(service)


def test_ambiguous_corpus_remains_unresolved_through_evaluation_and_publication(tmp_path):
    service = Service(Store(tmp_path))
    created = service.create_type("Ambiguous historical corpus")
    _pair(service, created["report_type"]["id"], "ambiguous")
    learned, _ = _learn(service, created["program"])
    assert {h["value"] for h in learned["learning"]["hypotheses"] if h["supported"]} == set(SELECTIONS)
    evaluated = service.evaluate(learned["id"], learned["digest"])
    assert evaluated["evaluation"]["passed"] is False
    assert all(d["resolution"] is None for d in evaluated["decisions"])
    unresolved = next(c for c in evaluated["evaluation"]["checks"] if c["name"] == "Executable selection decision")
    assert unresolved["passed"] is False
    with pytest.raises(DomainError) as error:
        service.publish(evaluated["id"], evaluated["digest"])
    assert error.value.code == "POLICY_UNRESOLVED"
    assert service.store.list("release") == []
    _assert_no_output(service)


@pytest.mark.parametrize("change", [
    "missing_amount", "nonfinite_amount", "localized_amount", "excess_precision",
    "currency_mismatch", "impossible_date", "timestamp_date", "unknown_status",
    "duplicate_id_same_row", "duplicate_id_conflicting_row", "cancelled_invalid_amount",
    "outside_window_invalid_currency",
])
def test_invalid_unseen_period_data_becomes_durable_block_without_report(released_service, change):
    service, report_type_id = released_service
    rows = _future_rows()
    if change == "missing_amount":
        rows[0]["amount"] = ""
    elif change == "nonfinite_amount":
        rows[0]["amount"] = "NaN"
    elif change == "localized_amount":
        rows[0]["amount"] = "400,00"
    elif change == "excess_precision":
        rows[0]["amount"] = "400.001"
    elif change == "currency_mismatch":
        rows[0]["currency"] = "USD"
    elif change == "impossible_date":
        rows[0]["date"] = "2026-04-31"
    elif change == "timestamp_date":
        rows[0]["date"] = "2026-04-01T00:00:00+02:00"
    elif change == "unknown_status":
        rows[0]["status"] = "pending"
    elif change.startswith("duplicate_id"):
        rows.append(copy.deepcopy(rows[0]))
        if change == "duplicate_id_conflicting_row":
            rows[-1].update(amount="9999.00", region="Conflicting Region", date="2025-06-15")
    elif change == "cancelled_invalid_amount":
        rows.append(_row("cancelled-invalid", "2026-05-01", "", status="cancelled"))
    elif change == "outside_window_invalid_currency":
        rows.append(_row("outside-invalid", "2020-01-01", "500", currency="USD"))
    completed = _blocked_run(service, report_type_id, rows)
    assert completed["error"]["details"][0]["evidence_refs"]


@pytest.mark.parametrize("absence", ["current", "comparison", "comparison_cancelled", "both"])
def test_missing_whole_period_cannot_be_inferred_as_zero(released_service, absence):
    service, report_type_id = released_service
    rows = _future_rows()
    if absence == "current":
        rows = [row for row in rows if row["date"].startswith("2025")]
    elif absence == "comparison":
        rows = [row for row in rows if row["date"].startswith("2026")]
    elif absence == "comparison_cancelled":
        for row in rows:
            if row["date"].startswith("2025"):
                row["status"] = "cancelled"
    else:
        rows = [_row("irrelevant-record", "2020-01-01", "999999")]
    _blocked_run(service, report_type_id, rows, "PERIOD_INCOMPLETE")


@pytest.mark.parametrize("drift", ["renamed_amount", "missing_amount", "unexpected_column"])
def test_schema_drift_is_catalogued_but_cannot_enter_generation(released_service, drift):
    service, report_type_id = released_service
    rows = _future_rows()
    columns = COLUMNS.copy()
    if drift == "renamed_amount":
        columns[columns.index("amount")] = "net_amount"
        for row in rows:
            row["net_amount"] = row.pop("amount")
    elif drift == "missing_amount":
        columns.remove("amount")
        for row in rows:
            row.pop("amount")
    else:
        columns.append("amount_includes_tax")
        for row in rows:
            row["amount_includes_tax"] = "true"
    asset = service.upload(_source(rows, columns), "schema-changed.csv")
    assert "transactions" not in asset["profile"]["eligible_roles"]
    assert asset["profile"]["warnings"]
    jobs_before = service.store.jobs()
    with pytest.raises(DomainError) as error:
        service.request_run(report_type_id, asset["id"], NEXT_PERIOD, "schema-drift")
    assert error.value.code == "INPUT_DRIFT"
    assert service.store.jobs() == jobs_before
    _assert_no_output(service)


def test_header_only_source_blocks_and_empty_upload_is_rejected(released_service):
    service, report_type_id = released_service
    _blocked_run(service, report_type_id, [], "INPUT_MISSING")
    assets_before = service.store.list("asset")
    with pytest.raises(DomainError) as error:
        service.upload(b"", "empty.csv")
    assert error.value.code == "UPLOAD_LIMIT"
    assert service.store.list("asset") == assets_before
    _assert_no_output(service)


def test_explicit_period_windows_control_inclusive_start_exclusive_end_and_reversal(released_service):
    service, report_type_id = released_service
    rows = _future_rows() + [
        _row("before-current", "2026-03-31", "800000"),
        _row("after-current", "2026-07-01", "900000"),
        _row("before-comparison", "2025-03-31", "700000"),
        _row("after-comparison", "2025-07-01", "600000"),
        _row("cancelled-current", "2026-04-01", "999999", status="cancelled"),
    ]
    asset = service.upload(_source(rows), "explicit-boundaries.csv")
    original = _finish(service, service.request_run(report_type_id, asset["id"], NEXT_PERIOD, "forward"))
    assert original["status"] == "completed", original
    snapshot = service.store.get("snapshot", original["result"]["snapshot_id"])
    validate_stored_snapshot(snapshot)
    assert snapshot["facts"]["revenue.current"]["value"] == "650.00"
    assert snapshot["facts"]["revenue.comparison"]["value"] == "500.00"
    assert snapshot["facts"]["revenue.change"]["value"] == "150.00"
    assert snapshot["facts"]["revenue.growth"]["display"] == "30.0%"
    assert snapshot["facts"]["driver.region"]["value"] == "North"
    assert snapshot["metadata"]["input_rows"] == 9 and snapshot["metadata"]["excluded_rows"] == 5
    assert snapshot["status"] == "review_required"
    reverse = copy.deepcopy(NEXT_PERIOD)
    reverse.update(label="Explicit reversed comparison", start="2025-04-01", end_exclusive="2025-07-01",
                   comparison={"start": "2026-04-01", "end_exclusive": "2026-07-01"})
    reversed_job = _finish(service, service.request_run(report_type_id, asset["id"], reverse, "reversed"))
    assert reversed_job["status"] == "completed", reversed_job
    reversed_snapshot = service.store.get("snapshot", reversed_job["result"]["snapshot_id"])
    assert reversed_snapshot["facts"]["revenue.current"]["value"] == "500.00"
    assert reversed_snapshot["facts"]["revenue.comparison"]["value"] == "650.00"
    assert reversed_snapshot["facts"]["revenue.change"]["value"] == "-150.00"
    assert reversed_snapshot["facts"]["revenue.growth"]["display"] == "-23.1%"
    assert service.store.get("snapshot", snapshot["id"]) == snapshot
    assert service.store.list("model_call") == []


def test_corrected_source_requires_fresh_run_and_preserves_failed_history(released_service):
    service, report_type_id = released_service
    rows = _future_rows()
    rows[0]["amount"] = ""
    failed = _blocked_run(service, report_type_id, rows)
    corrected = service.upload(_source(_future_rows()), "corrected-period.csv")
    with pytest.raises(DomainError) as error:
        service.request_run(report_type_id, corrected["id"], NEXT_PERIOD, "invalid-future-run")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    successful = _finish(service, service.request_run(report_type_id, corrected["id"], NEXT_PERIOD, "corrected-future-run"))
    assert successful["status"] == "completed", successful
    snapshot = service.store.get("snapshot", successful["result"]["snapshot_id"])
    assert snapshot["facts"]["revenue.current"]["value"] == "650.00"
    assert service.store.job(failed["id"]) == failed
    assert len(service.store.list("snapshot")) == 1 and service.store.list("export") == []


def test_undefined_percentage_policy_blocks_instead_of_falling_back_to_absolute_change(tmp_path):
    service = Service(Store(tmp_path))
    created = service.create_type("Explicit percentage policy boundary")
    # This corpus admits all three policies. Percentage selection is a recorded
    # reviewer decision, not a claim that ambiguous evidence uniquely implies it.
    _pair(service, created["report_type"]["id"], "ambiguous")
    learned, _ = _learn(service, created["program"])
    assert len([h for h in learned["learning"]["hypotheses"] if h["supported"]]) == 3
    reviewed = _review(service, learned, "largest_percentage_change")
    evaluated = service.evaluate(reviewed["id"], reviewed["digest"])
    assert evaluated["evaluation"]["passed"], evaluated["evaluation"]
    released = service.publish(evaluated["id"], evaluated["digest"], actor="synthetic_test_reviewer")
    rows = _future_rows()
    for row in rows:
        if row["date"].startswith("2025"):
            row["amount"] = "0.00"
    _blocked_run(service, created["report_type"]["id"], rows, "SELECTION_UNDEFINED")
    assert service.store.get("release", released["id"]) == released
    assert released["policy"]["selection"] == "largest_percentage_change"


def test_regional_absence_is_explicit_assumed_zero_not_proven_data_completeness(released_service):
    service, report_type_id = released_service
    rows = _future_rows()
    rows = [row for row in rows if row["transaction_id"] != "prior-south"]
    asset = service.upload(_source(rows), "region-absent-in-comparison.csv")
    completed = _finish(service, service.request_run(report_type_id, asset["id"], NEXT_PERIOD, "regional-absence"))
    assert completed["status"] == "completed", completed
    snapshot = service.store.get("snapshot", completed["result"]["snapshot_id"])
    prior_south = snapshot["facts"]["region.south.comparison"]
    assert prior_south["value"] == "0"
    assert "approved zero policy" in prior_south["definition"]
    assert prior_south["sources"]  # Points to the nonempty assumed-complete period.
    assert snapshot["facts"]["region.south.growth"]["value"] is None
    assert snapshot["facts"]["region.south.growth"]["status"] == "undefined"
    assert snapshot["facts"]["driver.region"]["value"] == "South"
    assert snapshot["metadata"]["completeness"] == "Assumed complete inside each nonempty posted period; not independently certified."
    assert snapshot["status"] == "review_required"
    assert service.store.list("model_call") == []
