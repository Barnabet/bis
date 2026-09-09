"""Independent observations of a small, explicit historical report profile.

This module reads inspected target regions only. It never calls preparation,
queries source rows, infers locale, executes document text, or creates expected
values from candidate output. Unrecognized regions remain visible for review.
"""
from __future__ import annotations

import copy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import re
import unicodedata

from .errors import DomainError

NUMBER = r"[+\-−]?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d+)?"
MONEY = rf"[+\-−]?€(?:0|[1-9]\d*|[1-9]\d{{0,2}}(?:,\d{{3}})+)(?:\.\d{{1,2}})?"
REGION = r"[A-Za-z][A-Za-z '&\-]{0,99}"
DISCLOSURE = "This report describes posted revenue movements. The source data does not establish the causes of those movements."


def _region_identity(value):
    label = " ".join(unicodedata.normalize("NFKC", value).split())
    key = label.casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    if not slug or slug != key:
        slug = (slug[:50] or "region") + "_" + hashlib.sha256(key.encode()).hexdigest()[:8]
    return key.title(), slug


def _numeric(value, unit):
    token = str(value).strip().replace("−", "-")
    if unit == "EUR":
        token = re.sub(r"\s+EUR$", "", token)
        token = token.replace("€", "", 1)
    elif unit == "ratio":
        if not token.endswith("%"):
            raise ValueError("Percentage observations require an explicit percent sign")
        token = token[:-1]
    if not re.fullmatch(NUMBER, token):
        raise ValueError("Only explicit English decimal-point and comma-grouping notation is supported")
    decimals = len(token.rsplit(".", 1)[1]) if "." in token else 0
    if decimals > (2 if unit == "EUR" else 4):
        raise ValueError("The displayed precision exceeds this observation profile")
    number = Decimal(token.replace(",", ""))
    return format(number / 100 if unit == "ratio" else number, "f"), decimals


def _column(value):
    header = " ".join(str(value).strip().casefold().split())
    if header == "region":
        return "region", "region"
    if header in {"current (eur)", "current revenue (eur)", "current period (eur)"} or re.fullmatch(r"q[1-4] \d{4} \(eur\)", header):
        return "current", "EUR"
    if header in {"comparison (eur)", "comparison revenue (eur)", "comparison period (eur)", "prior (eur)"}:
        return "comparison", "EUR"
    if header in {"change (eur)", "revenue change (eur)"}:
        return "change", "EUR"
    if header in {"growth", "growth (%)", "growth (percent)"}:
        return "growth", "ratio"
    return None


def inspect_target(asset: dict) -> dict:
    """Extract independently located values and retain every supplied region."""
    if (not isinstance(asset, dict) or not isinstance(asset.get("id"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("digest", "")))):
        raise DomainError("TARGET_IDENTITY_INVALID", "A historical target requires its original asset identity and digest.")
    source_regions = asset.get("profile", {}).get("regions", [])
    observations, regions, issues = [], [], []

    def add(region, fact_id, value, *, unit="region", display=None, decimals=None, method="explicit_label"):
        observation = {"id": f"{asset['id']}:{region['id']}:{len(observations)+1}", "fact_id": fact_id,
                       "value": value, "locator": region["locator"], "method": method, "region_id": region["id"], "unit": unit}
        if display is not None:
            observation["display"] = display
        if decimals is not None:
            observation["display_decimals"] = decimals
        observations.append(observation)
        region["observation_ids"].append(observation["id"])

    def numeric(region, fact_id, display, unit, method="explicit_label"):
        value, decimals = _numeric(display, unit)
        add(region, fact_id, value, unit=unit, display=display, decimals=decimals, method=method)

    def table(region):
        rows = region.get("rows")
        if not isinstance(rows, list) or len(rows) < 2 or not all(isinstance(row, list) for row in rows):
            raise ValueError("A complete regional table with a header and data rows is required")
        columns = [_column(cell) for cell in rows[0]]
        if any(column is None for column in columns):
            raise ValueError("The table has a column outside the explicit regional EUR profile")
        identifiers = [column[0] for column in columns]
        if len(set(identifiers)) != len(identifiers) or not {"region", "current", "comparison"} <= set(identifiers):
            raise ValueError("The table must explicitly identify one region, current EUR and comparison EUR column")
        labels, values = [], []
        region_index = identifiers.index("region")
        for row_index, row in enumerate(rows[1:], start=2):
            if len(row) != len(columns) or not isinstance(row[region_index], str) or not re.fullmatch(REGION, row[region_index].strip()):
                raise ValueError("The table has an unsupported row or region label")
            label, slug = _region_identity(row[region_index])
            if label in labels or label.casefold() in {"total", "grand total", "subtotal"}:
                raise ValueError("Repeated regions or total rows need explicit target mapping")
            labels.append(label)
            for column_index, (field, unit) in enumerate(columns):
                if field == "region":
                    continue
                value, decimals = _numeric(row[column_index], unit)
                values.append((f"region.{slug}.{field}", value, unit, str(row[column_index]), decimals, row_index, column_index+1))
        for fact_id, value, unit, display, decimals, row_index, column_index in values:
            add(region, fact_id, value, unit=unit, display=display, decimals=decimals, method="native_table_cell")
            observations[-1]["locator"] += f"/row[{row_index}]/column[{column_index}]"
        add(region, "regional_totals.region_order", labels, unit="region_order", method="native_table_membership_and_order")
        return "regional_table", "Regional values and ordered membership were extracted from explicit table cells."

    def paragraph(region):
        text = region.get("text", "").strip()
        label_pattern = r"(Current revenue|Comparison revenue|Revenue change)(?: \(EUR\))?:\s*(.+)"
        match = re.fullmatch(label_pattern, text)
        if match:
            fact_id = {"Current revenue": "revenue.current", "Comparison revenue": "revenue.comparison", "Revenue change": "revenue.change"}[match[1]]
            # A currency symbol/code or an explicit EUR label prevents unit guessing.
            if "(EUR)" not in text and "€" not in match[2] and not match[2].endswith(" EUR"):
                raise ValueError("A revenue label must explicitly declare EUR")
            numeric(region, fact_id, match[2], "EUR")
            return "summary", "An explicit EUR total or change was observed."
        match = re.fullmatch(r"(?:Growth|Revenue growth):\s*(.+)", text)
        if match:
            numeric(region, "revenue.growth", match[1], "ratio")
            return "summary", "An explicit displayed percentage was observed."
        match = re.fullmatch(rf"(?:Selected region|Highlighted region|Driver region):\s*({REGION})\.?", text)
        if match:
            label, _ = _region_identity(match[1])
            add(region, "driver.region", label, display=match[1], method="explicit_driver_label")
            return "summary", "The selected region is observed; its selection rule is not inferred from the label alone."
        prefix = rf"Posted revenue reached (?P<current>{MONEY})\. Growth against the comparison period was (?P<growth>{NUMBER}%)\. "
        suffix = rf", against a total change of (?P<change>{MONEY})\."
        variants = [
            ("largest_absolute_change", rf"(?P<driver>{REGION}) recorded the largest absolute regional movement, (?P<driver_change>{MONEY})"),
            ("largest_percentage_change", rf"(?P<driver>{REGION}) recorded the largest absolute percentage revenue movement, (?P<driver_growth>{NUMBER}%), with a revenue change of (?P<driver_change>{MONEY})"),
            ("largest_current_revenue", rf"(?P<driver>{REGION}) had the highest current-period regional revenue, (?P<driver_current>{MONEY}), with a revenue change of (?P<driver_change>{MONEY})"),
        ]
        for selection, middle in variants:
            match = re.fullmatch(prefix + middle + suffix, text)
            if match:
                for group, fact_id, unit in [("current", "revenue.current", "EUR"), ("growth", "revenue.growth", "ratio"),
                                              ("change", "revenue.change", "EUR"), ("driver_change", "driver.change", "EUR"),
                                              ("driver_growth", "driver.growth", "ratio"), ("driver_current", "driver.current", "EUR")]:
                    if group in match.groupdict():
                        numeric(region, fact_id, match[group], unit, "exact_supported_summary_pattern")
                add(region, "driver.region", _region_identity(match["driver"])[0], method="explicit_summary_selection")
                add(region, "policy.selection", selection, unit="policy", method="explicit_selection_wording")
                return "summary", "The supported full summary wording and its displayed values were observed."
        if text == DISCLOSURE:
            add(region, "node.commentary.text", text, unit="literal_text", display=text, method="exact_literal_text")
            return "commentary", "The registered exact disclosure text was observed."
        if text in {"Quarterly revenue", "Regional performance", "Quarter in review", "Editorial context"} or re.fullmatch(r"Quarterly revenue [·-] Q[1-4] \d{4}", text):
            return "summary" if text != "Regional performance" else "regional_table", "A supported report heading was observed; historical layout is not certified."
        raise ValueError("This region is outside the explicit table/label/summary observation profile")

    for index, raw in enumerate(source_regions):
        region = copy.deepcopy(raw)
        region.setdefault("id", f"region{index+1}")
        region.setdefault("locator", f"asset:{asset['id']}/region[{index+1}]")
        region.update(component_id=None, status="needs_decision", observation_ids=[])
        start = len(observations)
        try:
            if region.get("kind") == "table":
                component, reason = table(region)
            elif region.get("kind") in {"paragraph", "text"}:
                component, reason = paragraph(region)
            else:
                raise ValueError("This region kind needs explicit interpretation or an approved scope decision")
            region.update(component_id=component, status="mapped", reason=reason)
        except (ValueError, TypeError) as error:
            del observations[start:]
            region["observation_ids"] = []
            region["reason"] = str(error)
            issues.append({"code": "TARGET_REGION_UNRESOLVED", "severity": "review", "region_id": region["id"],
                           "locator": region["locator"], "message": str(error)})
        regions.append(region)
    if not regions:
        issues.append({"code": "TARGET_REGIONS_MISSING", "severity": "review", "message": "The target has no complete structural region inventory."})
    if not observations:
        issues.append({"code": "TARGET_OBSERVATIONS_MISSING", "severity": "review", "message": "No supported independent numeric or selection observations were extracted."})
    return {"asset_id": asset["id"], "asset_digest": asset["digest"], "observations": observations, "regions": regions, "issues": issues}


def compare_snapshot(snapshot, inspection: dict) -> dict:
    """Compare only independent target observations, using their display precision."""
    data = snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else snapshot
    checks = []
    for observation in inspection.get("observations", []):
        fid, expected = observation["fact_id"], observation["value"]
        actual, passed = None, False
        if fid == "regional_totals.region_order":
            actual = [row["region"] for row in data.get("datasets", {}).get("regional_totals", {}).get("rows", [])]
            passed = actual == expected
        elif fid == "policy.selection":
            actual = data.get("metadata", {}).get("reporting_policy", {}).get("selection", "largest_absolute_change")
            passed = actual == expected
        elif fid == "node.commentary.text":
            node = next((node for node in data.get("nodes", []) if node["id"] == "commentary" and node["kind"] == "rich_text"), None)
            if node is not None:
                try:
                    actual = "".join(run["text"] if run["type"] == "text" else data["facts"][run["fact_id"]]["display"] for run in node["runs"])
                except (KeyError, TypeError):
                    actual = None
            passed = actual == expected
        else:
            fact = data.get("facts", {}).get(fid)
            if fact is not None:
                actual = fact["value"]
                if observation.get("unit") in {"EUR", "ratio"} and actual is not None:
                    try:
                        places = observation.get("display_decimals", 2) + (2 if observation["unit"] == "ratio" else 0)
                        quantum = Decimal(1).scaleb(-places)
                        passed = Decimal(actual).quantize(quantum, rounding=ROUND_HALF_UP) == Decimal(expected).quantize(quantum, rounding=ROUND_HALF_UP)
                    except (ValueError, ArithmeticError, TypeError):
                        passed = False
                else:
                    passed = actual == expected
        checks.append({"observation_id": observation["id"], "fact_id": fid, "expected": expected, "actual": actual,
                       "passed": bool(passed), "locator": observation["locator"], "method": observation["method"]})
    if not checks:
        checks.append({"fact_id": None, "expected": "At least one independent target observation", "actual": None,
                       "passed": False, "locator": f"asset:{inspection.get('asset_id', 'unknown')}", "method": "observation_coverage"})
    return {"passed": all(check["passed"] for check in checks), "checks": checks,
            "observation_count": len(inspection.get("observations", []))}


__all__ = ["inspect_target", "compare_snapshot"]
