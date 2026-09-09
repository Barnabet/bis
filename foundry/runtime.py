"""Deterministic quarterly revenue program and explicit native revisions.

This module executes a trusted manually authored policy. It does not infer policy,
call a model, fetch sources, mutate a release, or perform exports.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from uuid import uuid4

from .contracts import FactRun, Finding, Period, Program, Snapshot, SourceAsset

SOURCE_COLUMNS = {"transaction_id", "date", "region", "status", "amount", "currency"}
DISCLOSURE = "This report describes posted revenue movements. The source data does not establish the causes of those movements."
POLICY_VERSION = "quarterly-revenue/1.0.0"
SELECTION_OPTIONS = [
    {"value": "largest_absolute_change", "label": "Largest absolute revenue change"},
    {"value": "largest_percentage_change", "label": "Largest absolute percentage change"},
    {"value": "largest_current_revenue", "label": "Largest current-period revenue"},
]


def validate_reporting_policy(reporting_policy=None):
    if reporting_policy is None:
        return {"selection": "largest_absolute_change"}
    if (not isinstance(reporting_policy, dict) or set(reporting_policy) != {"selection"}
            or not isinstance(reporting_policy["selection"], str)
            or reporting_policy["selection"] not in {option["value"] for option in SELECTION_OPTIONS}):
        _fail("REPORTING_POLICY_INVALID", "This registered adapter requires one supported selection policy.")
    return dict(reporting_policy)


class RuntimeBlocked(ValueError):
    def __init__(self, findings: list[Finding]):
        self.findings = findings
        super().__init__("; ".join(f.message for f in findings))


def canonical_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def default_period() -> Period:
    return Period.model_validate({
        "label": "Q1 2026", "start": "2026-01-01", "end_exclusive": "2026-04-01",
        "comparison": {"start": "2025-01-01", "end_exclusive": "2025-04-01"},
        "timezone": "Europe/Paris", "as_of": "2026-04-03T12:00:00+02:00",
    })


def default_program() -> Program:
    directory = Path(__file__).parent
    payload = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ("runtime.py", "contracts.py")}
    payload["policy"] = POLICY_VERSION
    return Program(id="quarterly-revenue", version="1.0.0", digest=canonical_digest(payload))


def _finding(code, message, *, severity="block", component="source_binding", phase="preparing", evidence=None, repair="source"):
    return Finding(id=f"{code.lower()}.{component}", phase=phase, severity=severity, code=code,
                   component_id=component, evidence_refs=evidence or [], message=message, repair_class=repair)


def _fail(code, message, line=None):
    location = f"csv:line={line}" if isinstance(line, int) else line
    raise RuntimeBlocked([_finding(code, message, evidence=[location] if location else [])])


def _raw(number: Decimal) -> str:
    return format(number, "f")


def _money(number: Decimal, signed=False) -> str:
    rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    prefix = "+" if signed and rounded > 0 else "−" if rounded < 0 else ""
    return f"{prefix}€{abs(rounded):,.2f}"


def _percent(number: Decimal | None, signed=False) -> str:
    if number is None:
        return "Not defined"
    value = (number * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{'+' if signed and value > 0 else ''}{value:.1f}%"


def _region(raw: str):
    display = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not display or len(display) > 100:
        raise ValueError("Region must contain 1–100 characters")
    key = display.casefold()
    label = key.title()
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    if not slug or slug != key:
        slug = (slug[:50] or "region") + "_" + hashlib.sha256(key.encode()).hexdigest()[:8]
    return key, label, slug


def _parse_rows(rows):
    parsed, seen = [], set()
    if not isinstance(rows, list) or not rows:
        _fail("INPUT_MISSING", "The bound transaction source contains no records.")
    for index, row in enumerate(rows, start=2):
        if not isinstance(row, dict) or set(row) - {"_line", "_locator"} != SOURCE_COLUMNS:
            _fail("INPUT_DRIFT", "Transaction columns must be transaction_id, date, region, status, amount, currency.", index)
        line = row.get("_line", index)
        if not isinstance(line, int) or isinstance(line, bool) or line < 2:
            _fail("INPUT_DRIFT", "Source row locators must be positive CSV line numbers.", index)
        locator = row.get("_locator")
        if locator is not None and (not isinstance(locator, str) or not locator.strip() or len(locator) > 500):
            _fail("INPUT_DRIFT", "A supplied source locator must be a nonempty format-specific string of at most 500 characters.", index)
        location = locator or line
        if any(not isinstance(row[column], str) for column in SOURCE_COLUMNS):
            _fail("INPUT_DRIFT", "Source fields must retain their declared text values.", location)
        transaction_id = row["transaction_id"].strip()
        if not transaction_id or transaction_id in seen:
            _fail("INPUT_DRIFT", "Transaction identifiers must be nonempty and unique.", location)
        seen.add(transaction_id)
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
                raise ValueError("date")
            day = date.fromisoformat(row["date"])
        except ValueError:
            _fail("INPUT_DRIFT", "Transaction dates must be real ISO local business dates (YYYY-MM-DD).", location)
        status = row["status"].strip().casefold()
        if status not in {"posted", "cancelled"}:
            _fail("INPUT_DRIFT", "Transaction status must be posted or cancelled.", location)
        if row["currency"].strip() != "EUR":
            _fail("INPUT_DRIFT", "This published program accepts EUR only; currency conversion is not declared.", location)
        amount_text = row["amount"].strip()
        try:
            if not re.fullmatch(r"\d+(?:\.\d{1,2})?", amount_text) or len(amount_text) > 18:
                raise InvalidOperation
            amount = Decimal(amount_text)
            if not amount.is_finite() or amount < 0:
                raise InvalidOperation
        except InvalidOperation:
            _fail("INPUT_DRIFT", "Amounts must be finite nonnegative decimal currency values with at most two fractional digits and 18 characters.", location)
        try:
            key, label, slug = _region(row["region"])
        except ValueError as exc:
            _fail("INPUT_DRIFT", str(exc), location)
        parsed.append({"date": day, "status": status, "amount": amount, "key": key, "label": label, "slug": slug,
                       "line": line, "locator": locator, "record_index": index})
    return parsed


def prepare(rows, period, source_asset, program=None, *, snapshot_id=None,
            report_type_id="quarterly-revenue", revision=1, parent_id=None,
            created_at=None, source_snapshot_digest=None, image_asset=None, image_metadata=None,
            reporting_policy=None) -> Snapshot:
    """Compute one report from already bound CSV rows and explicit source metadata."""
    period = Period.model_validate(period)
    source_asset = SourceAsset.model_validate(source_asset)
    policy = validate_reporting_policy(reporting_policy)
    explicit_program = program is not None
    program = Program.model_validate(program) if explicit_program else default_program()
    if not explicit_program and policy["selection"] != "largest_absolute_change":
        program = program.model_copy(update={"digest": canonical_digest({"adapter": program.digest, "reporting_policy": policy})})
    image_asset = SourceAsset.model_validate(image_asset) if image_asset is not None else None
    if image_metadata and image_asset is None:
        _fail('REFERENCE_INVALID', 'A report image requires its original bound source asset.')
    parsed = _parse_rows(rows)
    windows = {"current": period, "comparison": period.comparison}
    included = {name: [r for r in parsed if r["status"] == "posted" and window.start <= r["date"] < window.end_exclusive]
                for name, window in windows.items()}
    for name, records in included.items():
        if not records:
            _fail("PERIOD_INCOMPLETE", f"The {name} window contains no posted records; this source cannot establish a complete zero-activity period.")
    keys = sorted({r["key"] for records in included.values() for r in records})
    profiles = {r["key"]: (r["label"], r["slug"]) for r in parsed}
    facts, totals = {}, {}

    def source_ref(records):
        if any(r["locator"] for r in records):
            return [{"asset_id": source_asset.id, "artifact_sha256": source_asset.digest, "locator": locator}
                    for locator in sorted({r["locator"] or f"csv:line={r['line']}" for r in records})]
        lines = sorted({r["line"] for r in records})
        return [{"asset_id": source_asset.id, "artifact_sha256": source_asset.digest,
                 "locator": "csv:lines=" + ",".join(str(line) for line in lines) + ";columns=date,region,status,amount,currency"}]

    def fact(fid, value, definition, scope, *, unit="EUR", inputs=None, sources=None, display=None, kind="number"):
        facts[fid] = {"id": fid, "kind": kind, "value": _raw(value) if isinstance(value, Decimal) else value,
                      "unit": unit, "display": display if display is not None else _money(value),
                      "status": "undefined" if value is None else "known", "definition": definition,
                      "scope": scope, "inputs": inputs or [], "sources": sources or []}

    with localcontext() as context:
        context.prec = 40
        aggregates = {name: {key: sum((r["amount"] for r in records if r["key"] == key), Decimal(0)) for key in keys}
                      for name, records in included.items()}
        for name, records in included.items():
            window = windows[name]
            scope = f"Posted EUR transactions; {window.start} inclusive to {window.end_exclusive} exclusive; local business dates in {period.timezone}."
            for key in keys:
                label, slug = profiles[key]
                selected = [r for r in records if r["key"] == key]
                # Absence within a nonempty assumed-complete source is an approved zero rule.
                provenance_records = selected if selected else records
                definition = f"Sum of posted revenue in {label}."
                if not selected:
                    definition += " No regional records in this assumed-complete, nonempty period; approved zero policy applied."
                fact(f"region.{slug}.{name}", aggregates[name][key], definition, scope, sources=source_ref(provenance_records))
            totals[name] = sum(aggregates[name].values(), Decimal(0))
            fact(f"revenue.{name}", totals[name], f"Total posted revenue for the {name} window.", scope,
                 inputs=[f"region.{profiles[key][1]}.{name}" for key in keys])
        change = totals["current"] - totals["comparison"]
        growth = change / totals["comparison"] if totals["comparison"] else None
        comparison_scope = f"{period.label}: explicit current window against {period.comparison.start} to {period.comparison.end_exclusive} (exclusive)."
        fact("revenue.change", change, "Current posted revenue minus comparison posted revenue.", comparison_scope,
             inputs=["revenue.current", "revenue.comparison"], display=_money(change, True))
        fact("revenue.growth", growth, "Revenue change divided by comparison revenue; undefined when the denominator is zero.", comparison_scope,
             unit="ratio", inputs=["revenue.change", "revenue.comparison"], display=_percent(growth))
        regional_rows, pivot_rows = [], []
        movements, ratios = {}, {}
        for key in keys:
            label, slug = profiles[key]
            current, comparison = aggregates["current"][key], aggregates["comparison"][key]
            movement = current - comparison
            ratio = movement / comparison if comparison else None
            movements[key] = movement
            ratios[key] = ratio
            fact(f"region.{slug}.change", movement, f"Current minus comparison posted revenue for {label}.", comparison_scope,
                 inputs=[f"region.{slug}.current", f"region.{slug}.comparison"], display=_money(movement, True))
            fact(f"region.{slug}.growth", ratio, f"Revenue movement divided by comparison revenue for {label}; zero denominator is undefined.", comparison_scope,
                 unit="ratio", inputs=[f"region.{slug}.change", f"region.{slug}.comparison"], display=_percent(ratio))
            regional_rows.append({"region": label, "current": _raw(current), "comparison": _raw(comparison),
                                  "change": _raw(movement), "growth": _raw(ratio) if ratio is not None else None})
            pivot_rows.extend({"region": label, "period": name, "revenue": _raw(aggregates[name][key])} for name in ("current", "comparison"))
        selection = policy["selection"]
        if selection == "largest_percentage_change":
            ranked = [key for key in keys if ratios[key] is not None]
            if not ranked:
                _fail("SELECTION_UNDEFINED", "No region has a defined comparison ratio for the approved percentage selection policy.")
            driver_key = sorted(ranked, key=lambda key: (-abs(ratios[key]), key))[0]
            driver_definition = "Region with the largest absolute percentage revenue movement; undefined ratios are excluded and normalized region key breaks ties."
            driver_inputs = [f"region.{profiles[key][1]}.growth" for key in keys]
        elif selection == "largest_current_revenue":
            driver_key = sorted(keys, key=lambda key: (-aggregates["current"][key], key))[0]
            driver_definition = "Region with the largest current-period posted revenue; normalized region key breaks ties."
            driver_inputs = [f"region.{profiles[key][1]}.current" for key in keys]
        else:
            driver_key = sorted(keys, key=lambda key: (-abs(movements[key]), key))[0]
            driver_definition = "Region with the largest absolute revenue movement; normalized region key breaks ties."
            driver_inputs = [f"region.{profiles[key][1]}.change" for key in keys]
        driver_label, driver_slug = profiles[driver_key]
        fact("driver.region", driver_label, driver_definition, comparison_scope,
             kind="text", unit="region", display=driver_label, inputs=driver_inputs)
        fact("driver.change", movements[driver_key], "Revenue movement of the selected driver region.", comparison_scope,
             inputs=["driver.region", f"region.{driver_slug}.change"], display=_money(movements[driver_key], True))
        if selection == "largest_percentage_change":
            fact("driver.growth", ratios[driver_key], "Percentage revenue movement of the selected driver region.", comparison_scope,
                 unit="ratio", inputs=["driver.region", f"region.{driver_slug}.growth"], display=_percent(ratios[driver_key], True))
        elif selection == "largest_current_revenue":
            fact("driver.current", aggregates["current"][driver_key], "Current-period revenue of the selected driver region.", comparison_scope,
                 inputs=["driver.region", f"region.{driver_slug}.current"])

    def text(value):
        return {"type": "text", "text": value}

    def ref(value):
        return {"type": "fact", "fact_id": value}

    summary_runs = [text("Posted revenue reached "), ref("revenue.current"), text(". ")]
    if growth is None:
        summary_runs.extend([text("Relative growth is "), ref("revenue.growth"), text(" because comparison revenue is zero. ")])
    else:
        summary_runs.extend([text("Growth against the comparison period was "), ref("revenue.growth"), text(". ")])
    if selection == "largest_percentage_change":
        summary_runs.extend([ref("driver.region"), text(" recorded the largest absolute percentage revenue movement, "), ref("driver.growth"),
                             text(", with a revenue change of "), ref("driver.change")])
    elif selection == "largest_current_revenue":
        summary_runs.extend([ref("driver.region"), text(" had the highest current-period regional revenue, "), ref("driver.current"),
                             text(", with a revenue change of "), ref("driver.change")])
    else:
        summary_runs.extend([ref("driver.region"), text(" recorded the largest absolute regional movement, "), ref("driver.change")])
    summary_runs.extend([text(", against a total change of "), ref("revenue.change"), text(".")])
    nodes = [
        {"id": "summary", "kind": "rich_text", "title": "Quarter in review", "runs": summary_runs, "editable": False, "mode": "computed"},
        {"id": "commentary", "kind": "rich_text", "title": "Editorial context", "runs": [text(DISCLOSURE)], "editable": True, "mode": "literal"},
        {"id": "regional_table", "kind": "table", "title": "Regional performance", "dataset_id": "regional_totals"},
        {"id": "regional_chart", "kind": "chart", "title": "Revenue by region", "dataset_id": "regional_totals", "chart_type": "bar",
         "category_column": "region", "series": [{"column_id": "current", "label": period.label}, {"column_id": "comparison", "label": "Comparison period"}], "axis_unit": "EUR"},
        {"id": "regional_pivot", "kind": "pivot", "title": "Revenue analysis", "dataset_id": "pivot_source", "materialized_dataset_id": "regional_totals",
         "row_dimensions": ["region"], "column_dimensions": ["period"], "measures": [{"column_id": "revenue", "aggregation": "sum"}], "native_required_in": ["grid"]},
    ]
    assets = [source_asset.model_dump()]
    image_id = None
    if image_asset:
        if image_asset.id == source_asset.id:
            _fail("REFERENCE_INVALID", "The image and transaction source must have distinct asset IDs.")
        assets.append(image_asset.model_dump())
        image_id = 'report_image' if image_metadata else 'report_mark'
        if image_metadata:
            from .contracts import Image
            bound_image = Image.model_validate({'id': image_id, 'kind': 'image', 'title': 'Report image',
                                                **image_metadata, 'asset_id': image_asset.id})
            nodes.append(bound_image.model_dump())
        else:
            # Legacy native-contract fixture: valid as a reference, blocked by
            # exporters until a frozen render derivative has been supplied.
            nodes.append({"id": image_id, "kind": "image", "title": "Report identity", "asset_id": image_asset.id,
                          "alt_text": "Report Foundry brand mark", "width_px": 160, "height_px": 160, "decorative": True})
    leaf_ids = [node["id"] for node in nodes]
    nodes.insert(0, {"id": "root", "kind": "section", "title": "Quarterly revenue", "children": leaf_ids})
    views = []
    recipes = {
        "flow": {"page_size": "A4", "margin_mm": 18, "font": "Calibri", "body_pt": 10, "paragraph_indent_pt": 18,
                 "paragraph_space_after_pt": 7, "heading_indent_pt": 0, "table_overflow": "repeat_headers", "pivot_representation": "static_allowed"},
        "grid": {"sheets": [{"name": "Overview", "node_ids": ["summary", "commentary", "regional_table"]},
                              {"name": "Analysis", "node_ids": ["regional_pivot", "regional_chart"]}]
                             + ([{'name': 'Images', 'node_ids': [image_id]}] if image_id else []),
                 "placement": "after_previous_region", "pivot_representation": "native_required", "pivot_source_scope": "approved_aggregates_only"},
        "canvas": {"aspect_ratio": "16:9", "overflow": "block", "slides": [
            {"title": "Quarter in review", "node_ids": ["summary", "commentary", "regional_table"]},
            {"title": "Regional performance", "node_ids": ["regional_chart", "regional_pivot"]}]
            + ([{'title': 'Report image', 'node_ids': [image_id]}] if image_id else []), "pivot_representation": "static_allowed"},
    }
    for vid, family, title in (("document", "flow", "Document"), ("workbook", "grid", "Workbook"), ("presentation", "canvas", "Presentation")):
        views.append({"id": vid, "family": family, "title": title, "node_ids": leaf_ids,
                      "coverage": {"scope": "complete", "required_node_ids": leaf_ids, "omitted_node_ids": []}, "recipe": recipes[family]})
    findings = []
    if image_metadata and not image_metadata.get('decorative', False):
        findings.append(_finding('IMAGE_REVIEW_REQUIRED', 'Review the supplied image and its description. Image content is not used to compute report facts.',
                                 severity='review', component=image_id, repair='human_review',
                                 evidence=[f'asset:{image_asset.id}', f'sha256:{image_asset.digest}']))
    if growth is None:
        findings.append(_finding("UNDEFINED_COMPARISON", "Relative growth is undefined because comparison revenue is zero; the absolute movement remains valid.",
                                 severity="warn", component="summary", repair="none"))
    source_payload = [{"id": a["id"], "digest": a["digest"]} for a in assets]
    if image_metadata:
        source_payload = {'assets': source_payload, 'image': image_metadata}
    return Snapshot.model_validate({
        "schema_version": "1.0", "id": snapshot_id or f"snapshot_{uuid4().hex}", "revision": revision, "parent_id": parent_id,
        "title": f"Quarterly revenue · {period.label}", "report_type_id": report_type_id, "program": program.model_dump(),
        "period": period.model_dump(), "source_snapshot_digest": source_snapshot_digest or canonical_digest(source_payload),
        "source_assets": assets, "facts": facts, "datasets": {
            "regional_totals": {"id": "regional_totals", "columns": [
                {"id": "region", "label": "Region", "type": "text", "unit": ""},
                {"id": "current", "label": period.label, "type": "decimal", "unit": "EUR"},
                {"id": "comparison", "label": "Comparison", "type": "decimal", "unit": "EUR"},
                {"id": "change", "label": "Change", "type": "decimal", "unit": "EUR"},
                {"id": "growth", "label": "Growth", "type": "decimal", "unit": "ratio"}], "rows": regional_rows},
            "pivot_source": {"id": "pivot_source", "columns": [
                {"id": "region", "label": "Region", "type": "text", "unit": ""},
                {"id": "period", "label": "Period", "type": "text", "unit": ""},
                {"id": "revenue", "label": "Revenue", "type": "decimal", "unit": "EUR"}], "rows": pivot_rows}},
        "nodes": nodes, "views": views, "findings": findings,
        "metadata": {"runtime": POLICY_VERSION, "authorship": "manually_authored", "reporting_policy": policy,
                     "normalization": "Unicode NFKC, collapsed whitespace, casefold; deterministic title case display",
                     "completeness": "Assumed complete inside each nonempty posted period; not independently certified.",
                     "cutoff_semantics": "as_of identifies the bound immutable snapshot; these date-only records cannot reconstruct historical revisions.",
                     "pivot_disclosure": "Region/period revenue aggregates only; transaction identifiers are excluded.",
                     "input_rows": len(parsed), "current_rows": len(included["current"]), "comparison_rows": len(included["comparison"]),
                     "excluded_rows": len(parsed) - len({r["record_index"] for records in included.values() for r in records}),
                     "composition": "Deterministic fact-bound prose; no language model or semantic truth certification."},
        "status": "review_required" if any(f.severity == 'review' for f in findings) else "accepted",
        "created_at": created_at or datetime.now(timezone.utc),
    })


def render_runs(runs, facts) -> str:
    """Resolve persisted spans without composing, recalculating or accessing sources."""
    output = []
    for run in runs:
        if isinstance(run, dict):
            kind, payload = run["type"], run
        else:
            kind, payload = run.type, run.model_dump()
        if kind == "text":
            output.append(payload["text"])
        elif kind == "fact":
            fact = facts[payload["fact_id"]]
            output.append(fact["display"] if isinstance(fact, dict) else fact.display)
        else:
            raise ValueError("Unsupported rich-text run")
    return "".join(output)


def validate_commentary(text: str, node_id="commentary") -> list[Finding]:
    """Conservative checks. No claim that passing these proves semantic support."""
    findings = []
    if not isinstance(text, str) or not text.strip():
        return [_finding("REQUIRED_CONTENT_MISSING", "Editorial context must not be empty.", component=node_id, phase="revision", repair="narrative")]
    if len(text.split()) > 150:
        findings.append(_finding("WORD_LIMIT", "Editorial context exceeds its 150-word limit.", component=node_id, phase="revision", repair="narrative"))
    if re.search(r"\d|[%€$£]", text):
        findings.append(_finding("NUMERIC_LITERAL", "Edited commentary contains numeric text outside the fact registry. Use the computed facts or submit a source correction.",
                                 component=node_id, phase="revision", repair="narrative"))
    if re.search(r"\b(caused(?:\s+by)?|due\s+to|because|driven\s+by|result(?:ed|ing)\s+from|thanks\s+to|led\s+to|twice|doubled|halved|most|largest)\b", text, re.I):
        findings.append(_finding("UNSUPPORTED_CLAIM", "This edit contains causal or quantitative interpretation that the transaction source alone does not establish. Review its evidence before acceptance.",
                                 severity="review", component=node_id, phase="revision", repair="evidence"))
    return findings


def revise_commentary(snapshot, text, *, expected_revision, snapshot_id=None, created_at=None) -> Snapshot:
    snapshot = Snapshot.model_validate(snapshot)
    if expected_revision != snapshot.revision:
        raise ValueError("Revision conflict: the supplied expected revision is stale")
    data = snapshot.model_dump(mode="json")
    node = next((n for n in data["nodes"] if n["id"] == "commentary"), None)
    if node is None or node["kind"] != "rich_text" or not node["editable"]:
        raise ValueError("This snapshot does not permit editorial-context edits")
    findings = validate_commentary(text)
    node.update(runs=[{"type": "text", "text": text}], mode="composed")
    data["findings"] = [f for f in data["findings"] if f["component_id"] != "commentary"] + [f.model_dump() for f in findings]
    # An arbitrary human edit still needs explicit acceptance; keyword checks are not a semantic oracle.
    if not findings:
        data["findings"].append(_finding("EDITORIAL_REVIEW_REQUIRED", "Editorial context was changed for this revision. Review the new wording before acceptance.",
                                        severity="review", component="commentary", phase="revision", repair="review").model_dump())
    data.update(id=snapshot_id or f"snapshot_{uuid4().hex}", revision=snapshot.revision + 1,
                parent_id=snapshot.id, created_at=created_at or datetime.now(timezone.utc),
                status="blocked" if any(f["severity"] == "block" for f in data["findings"]) else "review_required")
    data["metadata"]["revision_scope"] = "this_period_content"
    return Snapshot.model_validate(data)


def fixture_rows():
    path = Path(__file__).resolve().parent.parent / "fixtures" / "transactions.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def fixture_snapshot() -> Snapshot:
    path = Path(__file__).resolve().parent.parent / "fixtures" / "transactions.csv"
    asset = SourceAsset(id="fixture_transactions", digest=hashlib.sha256(path.read_bytes()).hexdigest(), filename=path.name)
    return prepare(fixture_rows(), default_period(), asset, snapshot_id="snapshot_fixture_q1_2026",
                   created_at="2026-04-03T12:00:00+02:00")
