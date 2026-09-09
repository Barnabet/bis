"""Independent observations and adversarial boundary/behavior checks for the core."""

import copy
import hashlib
import json
import random
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from foundry.contracts import Period, Snapshot
from foundry.runtime import (
    DISCLOSURE, RuntimeBlocked, default_period, default_program, fixture_rows,
    fixture_snapshot, prepare, render_runs, revise_commentary, validate_commentary,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())


def generate(rows=None, **kwargs):
    rows = fixture_rows() if rows is None else rows
    artifact_bytes = json.dumps(rows, sort_keys=True).encode()
    return prepare(rows, kwargs.pop("period", default_period()),
                   {"id": "transactions", "digest": hashlib.sha256(artifact_bytes).hexdigest(), "filename": "transactions.csv"},
                   snapshot_id="test_snapshot", created_at="2026-04-03T12:00:00+02:00", **kwargs)


def observe(snapshot):
    for fact_id, field in (("revenue.current", "current"), ("revenue.comparison", "comparison"),
                           ("revenue.change", "change"), ("revenue.growth", "growth"), ("driver.change", "driver_change")):
        assert Decimal(snapshot.facts[fact_id].value) == Decimal(EXPECTED[field])
    assert snapshot.facts["revenue.growth"].display == EXPECTED["growth_display"]
    assert snapshot.facts["driver.region"].value == EXPECTED["driver"]
    rows = snapshot.datasets["regional_totals"].rows
    assert [r["region"] for r in rows] == EXPECTED["region_order"]
    for row in rows:
        for field in ("current", "comparison", "change"):
            assert Decimal(row[field]) == Decimal(EXPECTED["regions"][row["region"]][field])


def test_independent_fixture_observations():
    snapshot = fixture_snapshot()
    observe(snapshot)
    assert snapshot.metadata["input_rows"] == EXPECTED["source_rows"]
    assert snapshot.metadata["excluded_rows"] == EXPECTED["excluded_rows"]
    assert snapshot.status == "accepted"
    assert "20.0%" in render_runs(snapshot.nodes[1].runs, snapshot.facts)


def test_oracle_detects_plausible_wrong_formula_and_wrong_driver():
    snapshot = fixture_snapshot().model_dump(mode="json")
    for field, bad_value in (("revenue.growth", "0.1666666667"), ("driver.region", "South"), ("revenue.change", "-200")):
        changed = copy.deepcopy(snapshot)
        changed["facts"][field]["value"] = bad_value
        with pytest.raises(AssertionError):
            observe(Snapshot.model_validate(changed))


def test_round_trip_and_unknown_fields_rejected():
    snapshot = fixture_snapshot()
    assert Snapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    data = snapshot.model_dump(mode="json")
    data["approved_by_model"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        Snapshot.model_validate(data)


def test_permutation_preserves_values_order_selection_and_provenance():
    rows = [{**row, "_line": i} for i, row in enumerate(fixture_rows(), start=2)]
    baseline = generate(rows)
    random.Random(7).shuffle(rows)
    shuffled = generate(rows)
    # Input identity changes because this test serializes order; semantic results remain stable.
    assert baseline.datasets == shuffled.datasets
    assert {key: (f.value, f.display, f.inputs) for key, f in baseline.facts.items()} == {
        key: (f.value, f.display, f.inputs) for key, f in shuffled.facts.items()}
    assert baseline.facts["region.north.current"].sources[0].locator == shuffled.facts["region.north.current"].sources[0].locator


def test_period_boundary_and_cancelled_transactions_are_excluded():
    rows = fixture_rows()
    for row in rows:
        if row["transaction_id"] in {"TX-2026-CANCELLED", "TX-2026-APRIL"}:
            row["amount"] = "999999999.99"
    observe(generate(rows))
    rows.append({"transaction_id": "start-boundary", "date": "2026-01-01", "region": "North", "status": "posted", "amount": "1.01", "currency": "EUR"})
    assert generate(rows).facts["revenue.current"].value == "1201.01"


def test_changing_period_uses_raw_inputs_instead_of_historical_output():
    period = default_period().model_dump(mode="json")
    period.update(label="Q1 2025", start="2025-01-01", end_exclusive="2025-04-01",
                  comparison={"start": "2026-01-01", "end_exclusive": "2026-04-01"})
    snapshot = generate(period=period)
    assert snapshot.facts["revenue.current"].value == "1000.00"
    assert snapshot.facts["revenue.change"].value == "-200.00"
    assert snapshot.facts["revenue.growth"].display == "-16.7%"


def test_new_region_and_approved_absence_zero_policy():
    rows = fixture_rows() + [{"transaction_id": "new-region", "date": "2026-01-01", "region": "Central", "status": "posted", "amount": "200.00", "currency": "EUR"}]
    snapshot = generate(rows)
    assert snapshot.facts["region.central.comparison"].value == "0"
    assert "approved zero policy" in snapshot.facts["region.central.comparison"].definition
    assert snapshot.facts["region.central.growth"].value is None
    assert snapshot.facts["driver.region"].value == "Central"
    assert snapshot.datasets["regional_totals"].rows[0]["region"] == "Central"


def test_zero_comparison_is_undefined_not_zero_or_infinity():
    rows = fixture_rows()
    for row in rows:
        if row["date"].startswith("2025"):
            row["amount"] = "0.00"
    snapshot = generate(rows)
    assert snapshot.facts["revenue.growth"].value is None
    assert snapshot.facts["revenue.growth"].status == "undefined"
    assert snapshot.facts["revenue.growth"].display == "Not defined"
    assert snapshot.findings[0].code == "UNDEFINED_COMPARISON"
    assert snapshot.status == "accepted"


def test_negative_movements_rank_by_magnitude():
    rows = fixture_rows()
    for row in rows:
        if row["date"].startswith("2026") and row["region"] == "North" and row["status"] == "posted":
            row["amount"] = "0.00"
    snapshot = generate(rows)
    assert snapshot.facts["driver.region"].value == "North"
    assert snapshot.facts["driver.change"].value == "-400.00"
    assert snapshot.facts["revenue.change"].value == "-300.00"


def test_ties_use_normalized_region_key_and_labels_are_stable():
    rows = [
        {"transaction_id": "prior-n", "date": "2025-01-01", "region": "north", "status": "posted", "amount": "100", "currency": "EUR"},
        {"transaction_id": "prior-e", "date": "2025-01-01", "region": " EAST ", "status": "posted", "amount": "100", "currency": "EUR"},
        {"transaction_id": "current-n", "date": "2026-01-01", "region": "Ｎｏｒｔｈ", "status": "posted", "amount": "150", "currency": "EUR"},
        {"transaction_id": "current-e", "date": "2026-01-01", "region": "east", "status": "posted", "amount": "150", "currency": "EUR"},
    ]
    snapshot = generate(rows)
    assert snapshot.facts["driver.region"].value == "East"
    assert len(snapshot.datasets["regional_totals"].rows) == 2


@pytest.mark.parametrize("field,value", [
    ("amount", "NaN"), ("amount", "Infinity"), ("amount", "-1"), ("amount", ""),
    ("amount", "1.001"), ("amount", "1e3"), ("amount", "1,000.00"),
    ("date", "2026-02-30"), ("date", "2026-01-01T00:00:00Z"),
    ("currency", "USD"), ("status", "pending"), ("region", "   "),
])
def test_bad_source_fields_block_with_location(field, value):
    rows = fixture_rows()
    rows[0][field] = value
    with pytest.raises(RuntimeBlocked) as result:
        generate(rows)
    assert result.value.findings[0].code == "INPUT_DRIFT"
    assert result.value.findings[0].evidence_refs == ["csv:line=2"]


def test_missing_columns_duplicate_ids_and_empty_inputs_block():
    rows = fixture_rows()
    rows[0]["net_amount"] = rows[0].pop("amount")
    with pytest.raises(RuntimeBlocked):
        generate(rows)
    rows = fixture_rows()
    rows[1]["transaction_id"] = rows[0]["transaction_id"]
    with pytest.raises(RuntimeBlocked):
        generate(rows)
    with pytest.raises(RuntimeBlocked, match="no records"):
        generate([])


@pytest.mark.parametrize("missing_prefix", ["2025", "2026"])
def test_missing_required_period_does_not_fabricate_zero(missing_prefix):
    rows = [r for r in fixture_rows() if not r["date"].startswith(missing_prefix)]
    with pytest.raises(RuntimeBlocked) as result:
        generate(rows)
    assert result.value.findings[0].code == "PERIOD_INCOMPLETE"


@pytest.mark.parametrize("patch", [
    {"end_exclusive": "2026-01-01"}, {"timezone": "Mars/Olympus"}, {"as_of": "2026-04-01T00:00:00"},
    {"comparison": {"start": "2025-04-01", "end_exclusive": "2025-01-01"}},
])
def test_invalid_period_contract(patch):
    period = default_period().model_dump(mode="json")
    period.update(patch)
    with pytest.raises(ValidationError):
        Period.model_validate(period)


def test_every_direct_source_locator_identifies_included_rows():
    snapshot = fixture_snapshot()
    locators = [source.locator for fact in snapshot.facts.values() for source in fact.sources]
    assert locators
    for locator in locators:
        lines = [int(line) for line in locator.split("=", 1)[1].split(";", 1)[0].split(",")]
        assert all(2 <= line <= 11 for line in lines)


def test_native_spreadsheet_locators_are_preserved_without_fake_csv_coordinates():
    rows = [{**row, "_locator": f"sheet=Transactions;row={i}"} for i, row in enumerate(fixture_rows(), start=2)]
    snapshot = generate(rows)
    sources = snapshot.facts["region.north.current"].sources
    assert {source.locator for source in sources} == {"sheet=Transactions;row=7", "sheet=Transactions;row=8"}
    rows[0]["amount"] = "broken"
    with pytest.raises(RuntimeBlocked) as result:
        generate(rows)
    assert result.value.findings[0].evidence_refs == ["sheet=Transactions;row=2"]


@pytest.mark.parametrize("mutation", ["unknown_fact", "numeric_bypass", "cycle", "source_digest", "nan", "decimal_syntax", "missing_value", "table_shape", "view_coverage", "content_cycle", "orphan", "bad_pivot"])
def test_snapshot_boundary_rejects_structural_corruption(mutation):
    data = fixture_snapshot().model_dump(mode="json")
    if mutation == "unknown_fact":
        data["nodes"][1]["runs"].append({"type": "fact", "fact_id": "secret.unknown"})
    elif mutation == "numeric_bypass":
        data["nodes"][1]["runs"].append({"type": "text", "text": "Revenue was 9 million."})
    elif mutation == "cycle":
        data["facts"]["revenue.current"]["inputs"] = ["revenue.change"]
    elif mutation == "source_digest":
        data["facts"]["region.north.current"]["sources"][0]["artifact_sha256"] = "0" * 64
    elif mutation == "nan":
        data["facts"]["revenue.current"]["value"] = "NaN"
    elif mutation == "decimal_syntax":
        data["facts"]["revenue.current"]["value"] = "1_200"
    elif mutation == "missing_value":
        data["facts"]["revenue.current"]["value"] = None
    elif mutation == "table_shape":
        del data["datasets"]["regional_totals"]["rows"][0]["region"]
    elif mutation == "view_coverage":
        data["views"][0]["node_ids"].pop()
    elif mutation == "content_cycle":
        data["nodes"][0]["children"].append("root")
    elif mutation == "orphan":
        data["nodes"][0]["children"].remove("commentary")
    elif mutation == "bad_pivot":
        data["nodes"][-1]["measures"][0]["column_id"] = "region"
    with pytest.raises(ValidationError):
        Snapshot.model_validate(data)


def test_pivot_embeds_only_approved_aggregates():
    dataset = fixture_snapshot().datasets["pivot_source"]
    assert {c.id for c in dataset.columns} == {"region", "period", "revenue"}
    assert len(dataset.rows) == 8
    assert "transaction_id" not in dataset.model_dump_json()


def test_program_identity_tracks_content_and_override_is_explicit():
    program = default_program()
    assert len(program.digest) == 64
    snapshot = generate(program={"id": "published_revenue", "version": "v2", "digest": "a" * 64})
    assert snapshot.program.digest == "a" * 64


def test_replay_does_not_modify_package_files():
    paths = [Path(__file__).resolve().parent.parent / "foundry" / name for name in ("contracts.py", "runtime.py")]
    before = [path.read_bytes() for path in paths]
    first, second = generate(), generate()
    assert first == second
    assert [path.read_bytes() for path in paths] == before


def test_source_changes_invalidate_snapshot_identity_and_facts():
    first = generate()
    rows = fixture_rows()
    rows[5]["amount"] = "301.00"
    second = generate(rows)
    assert second.source_snapshot_digest != first.source_snapshot_digest
    assert second.facts["revenue.current"].value == "1201.00"


def test_commentary_revision_preserves_original_and_computed_facts():
    original = fixture_snapshot()
    original_json = original.model_dump_json()
    revised = revise_commentary(original, "Management context awaits review.", expected_revision=1)
    assert revised.revision == 2 and revised.parent_id == original.id
    assert revised.id != original.id
    assert revised.facts == original.facts and revised.datasets == original.datasets
    assert revised.program == original.program
    assert revised.status == "review_required"
    assert original.model_dump_json() == original_json
    with pytest.raises(ValueError, match="conflict"):
        revise_commentary(original, "Other text.", expected_revision=2)


def test_numeric_bypass_is_blocked_and_causality_needs_review():
    original = fixture_snapshot()
    blocked = revise_commentary(original, "Revenue reached €9000.", expected_revision=1)
    assert blocked.status == "blocked"
    assert any(f.code == "NUMERIC_LITERAL" for f in blocked.findings)
    causal = revise_commentary(original, "A marketing campaign caused the increase.", expected_revision=1)
    assert causal.status == "review_required"
    assert any(f.code == "UNSUPPORTED_CLAIM" for f in causal.findings)
    assert validate_commentary(DISCLOSURE) == []


def test_keyword_checks_do_not_claim_semantic_proof():
    text = "The campaign transformed regional performance."
    assert validate_commentary(text) == []
    revised = revise_commentary(fixture_snapshot(), text, expected_revision=1)
    assert revised.status == "review_required"
    assert any(f.code == "EDITORIAL_REVIEW_REQUIRED" for f in revised.findings)


def test_image_references_real_bound_asset_and_is_covered_in_all_views():
    snapshot = generate(image_asset={"id": "brand_asset", "digest": "a" * 64, "filename": "brand.png"})
    assert snapshot.nodes[-1].kind == "image"
    assert all("report_mark" in view.coverage.required_node_ids for view in snapshot.views)
