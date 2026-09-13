"""Independent June/July ONS examples and bounded parser failure behavior."""
import copy
import csv
import hashlib
from io import StringIO
import json

import pytest

from foundry.errors import DomainError
from foundry.public_ons import inspect_report, inspect_source


# Literal definitions and expectations transcribed from June/July release
# sources. These tests do not import the parser's series registry or any oracle.
CDIDS = ["J5EC", "J5EG", "J5EB", "J5EH", "KP8P", "KP8H", "MS6Y"]
TITLES = [
    "RSI:Month on prev month % change:All Business All retail inc fuel VOL SA",
    "RSI:Rolling 3mnth on prev 3mnth %change:All Business All retail inc fuel VOL SA",
    "RSI:All retail inc fuel:All Business:VOL SA:% change on same month a year ago",
    "RSI:All retail inc fuel:All Business:VOL SA:Rolling 3m on same 3m a year ago %",
    "RSI:Internet:Month on prev month %change:All Business All retail ex fuel VAL SA",
    "RSI:Internet:All retail ex fuelAll Business:VAL SA:% change month a year ago",
    "RSI: Internet: All Retailing excl auto fuel: All Bus: SA: proportion of retail",
]
EXPECTED_JUNE = {"ons.J5EC": "0.9", "ons.J5EG": "0.2", "ons.J5EB": "1.7", "ons.J5EH": "1.8",
                 "ons.KP8P": "2.3", "ons.KP8H": "4.5", "ons.MS6Y": "27.8"}
EXPECTED_JULY = {"ons.J5EC": "0.6", "ons.J5EG": "-0.6", "ons.J5EB": "1.1", "ons.J5EH": "0.4",
                 "ons.KP8P": "2.0", "ons.KP8H": "3.7", "ons.MS6Y": "27.8"}


def source_rows():
    return [
        ["Title", *TITLES], ["CDID", *CDIDS], ["PreUnit", *([""] * 7)],
        ["Unit", "%", "%", "%", "%", "%", "%", ""],
        ["Release Date", *(["25-07-2025"] * 7)],
        ["Next release", *(["22 August 2025"] * 7)], ["Important Notes", *([""] * 7)],
        ["2024", "1.0", "", "", "", "", "", ""],
        ["2025 Q1", "", "", "", "", "", "", ""],
        ["2025 MAY", "-2.8", "1.0", "-1.1", "1.7", "-0.3", "-2.0", "27.4"],
        ["2025 JUN", "0.9", "0.2", "1.7", "1.8", "2.3", "4.5", "27.8"],
    ]


def encode(rows):
    stream = StringIO(newline="")
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode()


def report_asset(*, july=False):
    if july:
        pages = [
            "Page 1 of 13\nNext release: 19 September 2025\nRelease date: 5 September 2025\n"
            "Statistical bulletin\nRetail sales, Great Britain: July 2025\nNotice\n5 September 2025\n"
            "The release was delayed because of a calendar adjustment error.",
            "Page 3 of 13\n1 . Overview\nRetail sales volumes are estimated to have risen by 0.6% in July 2025, "
            "following an increase of 0.3% in June 2025. Retailers attributed this to new products and good weather.",
            "Page 9 of 13\n3 . Retail sales in July\nSales volumes fell by 0.6% in the three months to July 2025, "
            "compared with the three months to April 2025. Sales volumes rose by 0.4%, compared with the three "
            "months to July 2024. Sales volumes rose by 0.6% over the month during July 2025, following a 0.3% "
            "rise in June. Sales volumes rose by 1.1% over the year to July 2025.",
            "Page 11 of 13\n5 . Online retail values\nThe amount spent online, known as “online spending values”, "
            "rose by 2.0% over the month to July 2025 and by 3.7% when comparing July 2025 with July 2024. "
            "As a result, the proportion of sales made online rose from 27.5% in June 2025 to 27.8% in July 2025.",
        ]
        locations = [1, 3, 9, 11]
    else:
        pages = [
            "Page 1 of 8\nNext release: 5 September 2025\nRelease date: 25 July 2025\nStatistical bulletin\n"
            "Retail sales, Great Britain: June 2025\nNotice\n19 August 2025\nThe Retail Sales, Great Britain: "
            "July 2025 release is being postponed to Friday 5 September.",
            "Page 3 of 8\n1 . Overview\nRetail sales volumes (quantity bought) are estimated to have risen by "
            "0.9% in June 2025, following a fall of 2.8% in May 2025. Food store retailers reported good weather.",
            "Page 4 of 8\n2 . Retail sales in June\nSales volumes rose by 0.9% during June 2025, following a "
            "2.8% fall in May. Sales volumes rose by 1.7% over the year to June 2025. More broadly, there was a "
            "0.2% rise across the three months to June 2025 (Quarter 2), when compared with the three months to "
            "March 2025 (Quarter 1). There was a 1.8% rise compared with the same period last year.",
            "Page 6 of 8\n4 . Online retail values\nThe amount spent online, known as \"online spending values\", "
            "rose by 2.3% over the month to June 2025, and by 4.5% when comparing June 2025 with June 2024. "
            "As a result, the proportion of sales made online rose from 27.4% in May 2025 to 27.8% in June 2025.",
        ]
        locations = [1, 3, 4, 6]
    return {"id": "historical-ons", "digest": hashlib.sha256("\n".join(pages).encode()).hexdigest(),
            "profile": {"regions": [{"id": f"page{n}", "kind": "page", "locator": f"page={n}", "text": text}
                                    for n, text in zip(locations, pages)]}}


def values(result, period):
    return {o["metric_id"]: o["value"] for o in result["observations"] if o["period"] == period}


def test_source_keeps_cdids_vintage_grains_definitions_and_exact_percent_numbers():
    data = encode(source_rows())
    result = inspect_source(data)
    assert result["family"] == "ons_retail" and result["parser_version"] == 1
    assert result["source_digest"] == hashlib.sha256(data).hexdigest()
    assert result["period"] == "2025-06" and result["vintage"] == "2025-07-25"
    assert values(result, "2025-06") == EXPECTED_JUNE
    assert values(result, "2025-05")["ons.J5EC"] == "-2.8"
    assert result["metadata"]["period_grains"] == {"year": 1, "quarter": 1, "month": 2}
    assert len(result["observations"]) == 14
    assert result["metadata"]["index_reference_year"] is None
    assert all(o["unit"] == "percent_points" and o["status"] == "known" for o in result["observations"])
    assert all(o["display_decimals"] == 1 and "column=" in o["locator"] for o in result["observations"])
    assert not result["issues"]
    json.dumps(result, allow_nan=False)


def test_source_joins_by_cdid_when_columns_reordered():
    rows = source_rows()
    order = [0, 7, 3, 1, 6, 2, 5, 4]
    result = inspect_source(encode([[row[i] for i in order] for row in rows]))
    assert values(result, "2025-06") == EXPECTED_JUNE
    observed = next(o for o in result["observations"] if o["metric_id"] == "ons.MS6Y")
    assert ";column=2;cdid=MS6Y" in observed["locator"]


def test_blank_is_missing_zero_is_known_and_unsupported_series_stays_in_inventory():
    rows = source_rows()
    rows[-1][1], rows[-1][2] = "", "0.0"
    for row, value in zip(rows, ["Unregistered aggregate", "ZZZZ", "", "%", "25-07-2025", "22 August 2025", "", "", "", "1.0", "2.0"]):
        row.append(value)
    result = inspect_source(encode(rows))
    current = {o["metric_id"]: o for o in result["observations"] if o["period"] == "2025-06"}
    assert current["ons.J5EC"]["value"] is None and current["ons.J5EC"]["status"] == "missing"
    assert current["ons.J5EG"]["value"] == "0.0" and current["ons.J5EG"]["status"] == "known"
    assert result["metadata"]["unregistered_series"] == ["ZZZZ"]
    assert not any(o["metric_id"] == "ons.ZZZZ" for o in result["observations"])


@pytest.mark.parametrize("kind,code", [
    ("duplicate_cdid", "ONS_CDID_INVALID"), ("missing_cdid", "ONS_SERIES_MISSING"),
    ("changed_definition", "ONS_SERIES_DRIFT"), ("changed_unit", "ONS_SERIES_DRIFT"),
    ("mixed_vintage", "ONS_VINTAGE_INVALID"), ("invalid_vintage", "ONS_VINTAGE_INVALID"),
    ("future_data", "ONS_VINTAGE_INVALID"), ("duplicate_period", "ONS_PERIOD_INVALID"),
    ("reverse_period", "ONS_PERIOD_INVALID"), ("unknown_period", "ONS_PERIOD_INVALID"),
    ("ragged", "ONS_HEADER_INVALID"), ("metadata_order", "ONS_HEADER_INVALID"),
])
def test_source_refuses_ambiguous_or_changed_contract(kind, code):
    rows = source_rows()
    if kind == "duplicate_cdid": rows[1][2] = rows[1][1]
    elif kind == "missing_cdid":
        for row in rows: row.pop()
    elif kind == "changed_definition": rows[0][1] = rows[0][1].replace("VOL SA", "VOL NSA")
    elif kind == "changed_unit": rows[3][1] = "GBP"
    elif kind == "mixed_vintage": rows[4][2] = "05-09-2025"
    elif kind == "invalid_vintage": rows[4][1:] = ["31-02-2025"] * 7
    elif kind == "future_data": rows[-1][0] = "2025 JUL"
    elif kind == "duplicate_period": rows[-1][0] = rows[-2][0]
    elif kind == "reverse_period": rows[-1][0] = "2025 APR"
    elif kind == "unknown_period": rows[-1][0] = "2025 summer"
    elif kind == "ragged": rows[-1].pop()
    elif kind == "metadata_order": rows[2], rows[3] = rows[3], rows[2]
    with pytest.raises(DomainError) as error:
        inspect_source(encode(rows))
    assert error.value.code == code


@pytest.mark.parametrize("token", ["=1+1", "NaN", "Infinity", "1e4", "..", "1,200", "Not defined", "9" * 100])
def test_source_never_evaluates_or_silently_coerces_non_decimal_data(token):
    rows = source_rows()
    rows[-1][1] = token
    with pytest.raises(DomainError, match="bounded decimal"):
        inspect_source(encode(rows))


@pytest.mark.parametrize("data", [b"", b"\xff", b"Title\x00,Value", b"\"unterminated"])
def test_source_rejects_invalid_raw_bytes(data):
    with pytest.raises(DomainError):
        inspect_source(data)


@pytest.mark.parametrize("july,period,vintage,expected", [
    (False, "2025-06", "2025-07-25", EXPECTED_JUNE),
    (True, "2025-07", "2025-09-05", EXPECTED_JULY),
])
def test_report_independently_extracts_located_headlines_and_keeps_unsupported_prose(july, period, vintage, expected, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Target observation must not read or calculate from data sources")
    monkeypatch.setattr("foundry.public_ons.inspect_source", forbidden)
    asset = report_asset(july=july)
    original = copy.deepcopy(asset)
    result = inspect_report(asset)
    assert asset == original
    assert result["report_period"] == period and result["vintage"] == vintage
    assert values(result, period) == expected
    assert len(result["observations"]) == 8
    assert [r["text"] for r in result["regions"]] == [r["text"] for r in asset["profile"]["regions"]]
    assert all(o["evidence_text"] and "normalized_text_chars=" in o["locator"] for o in result["observations"])
    assert {issue["code"] for issue in result["issues"]} == {"ONS_REPORT_PARTIAL_COVERAGE"}
    assert {r["status"] for r in result["regions"]} == {"needs_decision", "partially_mapped"}
    json.dumps(result, allow_nan=False)


def test_cover_notice_does_not_replace_publication_date_or_report_period():
    result = inspect_report(report_asset())
    assert result["report_period"] == "2025-06" and result["vintage"] == "2025-07-25"
    assert result["metadata"]["notices"][0]["date_label"] == "19 August 2025"


def test_changed_or_missing_wording_remains_unobserved_instead_of_copying_expected_value():
    asset = report_asset()
    asset["profile"]["regions"][-1]["text"] = "Page 6 of 8 4 . Online retail values Amount changed substantially."
    result = inspect_report(asset)
    assert not any(o["metric_id"].startswith("ons.KP") or o["metric_id"] == "ons.MS6Y" for o in result["observations"])
    issue = next(i for i in result["issues"] if i["code"] == "ONS_REPORT_OBSERVATIONS_MISSING")
    assert issue["severity"] == "block"
    assert set(issue["metric_ids"]) == {"ons.KP8P", "ons.KP8H", "ons.MS6Y"}


def test_conflicting_duplicate_claims_are_flagged():
    asset = report_asset()
    asset["profile"]["regions"][1]["text"] = asset["profile"]["regions"][1]["text"].replace("0.9%", "9.9%")
    result = inspect_report(asset)
    assert any(i["code"] == "ONS_REPORT_CONFLICT" and i["metric_id"] == "ons.J5EC" for i in result["issues"])
    assert next(i for i in result["issues"] if i["code"] == "ONS_REPORT_CONFLICT")["severity"] == "block"
    assert {o["value"] for o in result["observations"] if o["metric_id"] == "ons.J5EC"} == {"9.9", "0.9"}


def test_sector_claims_and_appendix_text_cannot_supply_headline_metrics():
    asset = report_asset()
    asset["profile"]["regions"].extend([
        {"id": "sector", "kind": "page", "locator": "page=5", "text": "Page 5 of 8 3 . Retail sector volumes Sales volumes rose by 99.9% during June 2025."},
        {"id": "appendix", "kind": "page", "locator": "page=9", "text": "2 . Retail sales in June Sales volumes rose by 99.9% during June 2025."},
    ])
    result = inspect_report(asset)
    assert not any(o["value"] == "99.9" for o in result["observations"])
    appendix = next(r for r in result["regions"] if r["id"] == "appendix")
    assert appendix["coverage_kind"] == "statistical_appendix" and appendix["status"] == "needs_decision"


def test_reporting_year_and_population_are_not_guessed_for_unmatched_online_claims():
    asset = report_asset()
    asset["profile"]["regions"][-1]["text"] = asset["profile"]["regions"][-1]["text"].replace("with June 2024", "with May 2024")
    result = inspect_report(asset)
    assert not any(o["metric_id"].startswith("ons.KP") for o in result["observations"])


def test_invalid_report_identity_or_ambiguous_publication_is_rejected():
    with pytest.raises(DomainError):
        inspect_report({"id": "bad", "digest": "not-a-hash"})
    asset = report_asset()
    asset["profile"]["regions"][0]["text"] += " Release date: 26 July 2025"
    with pytest.raises(DomainError) as error:
        inspect_report(asset)
    assert error.value.code == "ONS_REPORT_VINTAGE_INVALID"


def later_development_asset(september=False):
    """Later wording became development evidence after initial 2/7 failures."""
    month, release = ("September", "24 October") if september else ("August", "19 September")
    total = (
        "Sales volumes rose by 0.9% in the three months to September 2025 (Quarter 3) compared with the "
        "three months to June 2025 (Quarter 2). When compared with Quarter 3 2024, sales volumes rose by 1.0% "
        "Sales volumes rose by 0.5% over the month during September 2025, following a 0.6% rise in August, "
        "and rose by 1.5% over the year to September 2025."
        if september else
        "Sales volumes fell by 0.1% in the three months to August 2025, compared with the three months to May 2025. "
        "However, when comparing with the three months to August 2024, sales volumes rose by 0.8%. "
        "Sales volumes rose by 0.5% over the month during August 2025, following a 0.5% rise in July, "
        "and rose by 0.7% over the year to August 2025."
    )
    online = (
        "The amount spent online, known as “online spending values”, rose by 3.5% when comparing Quarter 3 "
        "(July to Sept) 2025 with Quarter 2 (Apr to June) 2025, and by 5.0% when comparing with Quarter 3 2024. "
        "With the monthly series, sales values rose by 1.4% over the month to September 2025, and by 5.6% "
        "when comparing September 2025 with September 2024. As a result, the proportion of sales made online "
        "increased from 27.8% in August 2025 to 28.0% in September 2025."
        if september else
        "The amount spent online, known as \"online spending values\", rose by 2.0% when comparing the three "
        "months to August 2025 with the three months to May 2025, and by 3.4% when comparing with the three "
        "months to August 2024. Considering the monthly series, sales values rose by 0.4% over the month to "
        "August 2025, and by 4.7% when comparing August 2025 with August 2024. As a result, the proportion of "
        "sales made online showed little change, falling from 27.7% in July 2025 to 27.6% in August 2025."
    )
    texts = [f"Page 1 of 3 Release date: {release} 2025 Statistical bulletin Retail sales, Great Britain: {month} 2025",
             f"Page 2 of 3 2 . Retail sales in {month} {total}", f"Page 3 of 3 4 . Online retail values {online}"]
    return {"id": "later-development", "digest": hashlib.sha256("\n".join(texts).encode()).hexdigest(),
            "profile": {"regions": [{"id": f"page{i+1}", "kind": "page", "locator": f"page={i+1}", "text": text}
                                    for i, text in enumerate(texts)]}}


@pytest.mark.parametrize("september,period,expected", [
    (False, "2025-08", {"ons.J5EC": "0.5", "ons.J5EG": "-0.1", "ons.J5EB": "0.7", "ons.J5EH": "0.8", "ons.KP8P": "0.4", "ons.KP8H": "4.7", "ons.MS6Y": "27.6"}),
    (True, "2025-09", {"ons.J5EC": "0.5", "ons.J5EG": "0.9", "ons.J5EB": "1.5", "ons.J5EH": "1.0", "ons.KP8P": "1.4", "ons.KP8H": "5.6", "ons.MS6Y": "28.0"}),
])
def test_exposed_later_wording_reconstructs_all_seven_from_narrative_only(september, period, expected):
    result = inspect_report(later_development_asset(september))
    assert values(result, period) == expected
    assert len(result["observations"]) == 7
    assert not any(i["severity"] == "block" for i in result["issues"])
    assert any(i["code"] == "ONS_REPORT_PARTIAL_COVERAGE" for i in result["issues"])


def test_later_online_monthly_values_do_not_use_neighboring_quarterly_values():
    asset = later_development_asset()
    asset["profile"]["regions"][-1]["text"] = asset["profile"]["regions"][-1]["text"].replace("rose by 2.0%", "rose by 99.0%")
    result = inspect_report(asset)
    assert values(result, "2025-08")["ons.KP8P"] == "0.4"
    assert not any(o["value"] == "99.0" for o in result["observations"])


def test_wrong_named_quarter_or_comparison_year_remains_blocked():
    for changed in ["Quarter 2 2024", "Quarter 3 2023"]:
        asset = later_development_asset(True)
        asset["profile"]["regions"][1]["text"] = asset["profile"]["regions"][1]["text"].replace("Quarter 3 2024", changed)
        result = inspect_report(asset)
        assert "ons.J5EH" not in values(result, "2025-09")
        assert any(i["severity"] == "block" for i in result["issues"])
