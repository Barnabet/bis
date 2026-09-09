"""Bounded reconstruction across three registered revenue selection policies.

This is an enumerable hypothesis test, not autonomous program synthesis. It
cannot execute uploaded code, patch the application, access a model, publish a
release, or fetch reserved examples. Target observations have a separate owner.
"""
from __future__ import annotations

from .errors import DomainError
from .observations import inspect_target, compare_snapshot
from .runtime import prepare, RuntimeBlocked, SELECTION_OPTIONS


def analyze_examples(cases: list[dict]) -> dict:
    """Return candidate-policy discrepancies and a complete target-region ledger.

    The host must supply already authorized source rows and immutable target
    inspections. Corpus restrictions are checked before any example executes.
    """
    if not isinstance(cases, list) or not cases:
        raise DomainError("LEARNING_EXAMPLES_REQUIRED", "Attach at least one authoring or development example before learning.")
    if len(cases) > 50:
        raise DomainError("LEARNING_LIMIT", "This local learning profile supports at most 50 examples per investigation.")
    for case in cases:
        if not isinstance(case, dict):
            raise DomainError("LEARNING_CASE_INVALID", "Learning examples must be structured case records.")
        if case.get("corpus_role") == "reserved":
            raise DomainError("RESERVED_EXAMPLE_DENIED", "Reserved examples are unavailable to the learning controller.", 403)
        if case.get("corpus_role") not in {"authoring", "development"}:
            raise DomainError("LEARNING_CASE_INVALID", "Each learning example needs an explicit authoring or development corpus role.")
        if not {"id", "period", "report_asset", "source_asset", "rows"} <= set(case):
            raise DomainError("LEARNING_CASE_INVALID", "A learning example requires target, source, period and inspected rows.")
        if not isinstance(case["id"], str) or not case["id"]:
            raise DomainError("LEARNING_CASE_INVALID", "Every learning example needs a stable identity.")
        for name in ("report_asset", "source_asset"):
            asset = case[name]
            if not isinstance(asset, dict) or not {"id", "digest", "filename"} <= set(asset):
                raise DomainError("LEARNING_CASE_INVALID", "A learning binding requires original asset metadata.")
    if len({case["id"] for case in cases}) != len(cases):
        raise DomainError("LEARNING_CASE_INVALID", "A learning investigation cannot repeat an example identity.")
    bound, coverage, assumptions = [], [], []
    for case in cases:
        inspection = case.get("inspection") or inspect_target(case["report_asset"])
        if (inspection.get("asset_id") != case["report_asset"]["id"]
                or inspection.get("asset_digest") != case["report_asset"]["digest"]):
            raise DomainError("TARGET_IDENTITY_INVALID", "The target inspection does not match this example's immutable report.", 409)
        bound.append((case, inspection))
        for region in inspection.get("regions", []):
            text = region.get("text", "")
            if not text and region.get("rows"):
                text = "\n".join(" | ".join(str(cell) for cell in row) for row in region["rows"])
            coverage.append({"id": f"{case['id']}:{region['id']}", "example_id": case["id"], "region_id": region["id"],
                             "locator": region["locator"], "kind": region.get("kind", "unknown"), "text": text,
                             "component_id": region.get("component_id"), "status": region["status"], "reason": region["reason"]})
        if not any(observation["fact_id"] == "driver.region" for observation in inspection.get("observations", [])):
            assumptions.append(f"Example {case['id']} contains no observed selected region; its numeric totals cannot distinguish the selection policies.")
    hypotheses = []
    for option in SELECTION_OPTIONS:
        checks = []
        for case, inspection in bound:
            try:
                source = {key: case["source_asset"][key] for key in ("id", "digest", "filename")}
                snapshot = prepare(case["rows"], case["period"], source, reporting_policy={"selection": option["value"]})
                result = compare_snapshot(snapshot, inspection)
                checks.extend({"example_id": case["id"], **check} for check in result["checks"])
            except RuntimeBlocked as error:
                checks.append({"example_id": case["id"], "expected": "The example must execute under this policy",
                               "actual": "; ".join(finding.message for finding in error.findings), "passed": False,
                               "locator": f"asset:{case['source_asset']['id']}", "code": error.findings[0].code})
        hypotheses.append({**option, "supported": bool(checks) and all(check["passed"] for check in checks), "checks": checks})
    supported = [hypothesis["value"] for hypothesis in hypotheses if hypothesis["supported"]]
    if len(supported) > 1:
        assumptions.append("Several registered selection policies reproduce the supplied observations. A distinguishing example or explicit policy decision is required.")
    elif not supported:
        assumptions.append("No registered selection policy reproduces all supplied observations. Investigate contradictory targets, source bindings or unsupported reporting rules; do not choose a best-fitting rule silently.")
    if any(item["status"] == "needs_decision" for item in coverage):
        assumptions.append("Unresolved historical regions require an explicit mapping or scope decision before claiming complete reconstruction.")
    limitations = [
        "Only three registered Python selection policies are investigated; this is not arbitrary report learning or generated-code execution.",
        "The fixed source contract includes posted EUR transactions, explicit comparison windows, normalized region ties, and an assumed complete nonempty-period zero policy.",
        "Target extraction supports explicit English EUR/percentage labels, a regional table and recognized summary wording; unknown regions remain reviewable.",
        "Mapped observations do not certify visual fidelity, semantics of unrecognized prose, or native Office behavior.",
        "These authoring/development examples are exposed evidence, not a protected holdout evaluation.",
    ]
    return {"hypotheses": hypotheses, "coverage": coverage, "assumptions": assumptions, "limitations": limitations}


__all__ = ["analyze_examples", "SELECTION_OPTIONS"]
