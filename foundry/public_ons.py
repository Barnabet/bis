"""Bounded, data-only ONS retail-series and independent bulletin observations.

The registered scope is seven published aggregate headline series. It does not
reconstruct survey microdata, estimate causes, execute document text, or infer
an index reference year from a coincidentally equal annual value.
"""
from __future__ import annotations

import copy
import csv
from datetime import date, datetime
from decimal import Decimal
import hashlib
from io import StringIO
import re

from .errors import DomainError

PARSER_VERSION = 1
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 5_000
MAX_COLUMNS = 1_000
MAX_CELLS = 1_000_000
MAX_REPORT_TEXT = 3_000_000
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
MONTH_NUMBER = {name.casefold(): index for index, name in enumerate(MONTHS, 1)}
MONTH_PATTERN = "(?:" + "|".join(MONTHS) + ")"
NUM = r"[+\-−]?(?:0|[1-9]\d{0,17})(?:\.\d{1,12})?"
UNSIGNED = r"(?:0|[1-9]\d{0,17})(?:\.\d{1,12})?"
METADATA_ROWS = ("Title", "CDID", "PreUnit", "Unit", "Release Date", "Next release", "Important Notes")

# Explicit CDID+definition+unit registration avoids treating a similarly named
# NSA, fuel-excluding or value series as the headline volume statistic.
SERIES = {
    "J5EC": ("RSI:Month on prev month % change:All Business All retail inc fuel VOL SA", "%", "Retail volume: month on previous month", "volume", "monthly_change", "including_fuel"),
    "J5EG": ("RSI:Rolling 3mnth on prev 3mnth %change:All Business All retail inc fuel VOL SA", "%", "Retail volume: three months on previous three months", "volume", "three_month_change", "including_fuel"),
    "J5EB": ("RSI:All retail inc fuel:All Business:VOL SA:% change on same month a year ago", "%", "Retail volume: same month a year earlier", "volume", "annual_change", "including_fuel"),
    "J5EH": ("RSI:All retail inc fuel:All Business:VOL SA:Rolling 3m on same 3m a year ago %", "%", "Retail volume: three months on same three months a year earlier", "volume", "three_month_annual_change", "including_fuel"),
    "KP8P": ("RSI:Internet:Month on prev month %change:All Business All retail ex fuel VAL SA", "%", "Online retail value: month on previous month", "value", "monthly_change", "excluding_fuel"),
    "KP8H": ("RSI:Internet:All retail ex fuelAll Business:VAL SA:% change month a year ago", "%", "Online retail value: same month a year earlier", "value", "annual_change", "excluding_fuel"),
    "MS6Y": ("RSI: Internet: All Retailing excl auto fuel: All Bus: SA: proportion of retail", "", "Online share of retail spending", "value", "share", "excluding_fuel"),
}


def _fail(code, message):
    raise DomainError(code, message)


def _normalize_text(value):
    return " ".join(value.split())


def _period(label):
    if re.fullmatch(r"\d{4}", label):
        return label, "year"
    if re.fullmatch(r"\d{4} Q[1-4]", label):
        return label.replace(" ", "-"), "quarter"
    match = re.fullmatch(r"(\d{4}) ([A-Z]{3})", label)
    if match:
        months = {month[:3].upper(): index for index, month in enumerate(MONTHS, 1)}
        if match[2] in months:
            return f"{match[1]}-{months[match[2]]:02}", "month"
    _fail("ONS_PERIOD_INVALID", "ONS data rows require an explicit annual, quarterly or monthly period label.")


def _value(token):
    if token == "":
        return None, "missing", 0
    if not re.fullmatch(NUM, token):
        _fail("ONS_VALUE_INVALID", "ONS data cells must contain bounded decimal values or explicit blanks.")
    token = token.replace("−", "-")
    return format(Decimal(token), "f"), "known", len(token.partition(".")[2])


def _definition(cdid):
    _, _, definition, measure, statistic, population = SERIES[cdid]
    return definition, {"adjustment": "seasonally_adjusted", "measure": measure,
                        "statistic": statistic, "population": population,
                        "geography": "Great Britain", "grain": "month"}


def inspect_source(data: bytes) -> dict:
    """Inspect exact vintage CSV bytes; return only registered monthly metrics."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        _fail("ONS_INPUT_LIMIT", "Supply a nonempty ONS CSV no larger than 20 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DomainError("ONS_INPUT_ENCODING", "ONS CSV must use UTF-8 encoding.") from exc
    if "\x00" in text:
        _fail("ONS_INPUT_ENCODING", "ONS CSV contains null bytes.")
    rows, lines = [], []
    try:
        reader = csv.reader(StringIO(text), strict=True)
        while True:
            start = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            if len(rows) >= MAX_ROWS or len(row) > MAX_COLUMNS:
                _fail("ONS_INPUT_LIMIT", "ONS CSV exceeds the bounded row or column limit.")
            if not row or any(len(cell) > 2_000 for cell in row):
                _fail("ONS_INPUT_LIMIT", "ONS CSV has an empty row or an oversized cell.")
            rows.append(row)
            lines.append((start, reader.line_num))
    except csv.Error as exc:
        raise DomainError("ONS_INPUT_PARSE", "ONS CSV could not be parsed.") from exc
    if len(rows) <= len(METADATA_ROWS) or len(rows[0]) < 2:
        _fail("ONS_HEADER_INVALID", "ONS CSV requires its seven metadata rows and period data.")
    width = len(rows[0])
    if len(rows) * width > MAX_CELLS:
        _fail("ONS_INPUT_LIMIT", "ONS CSV exceeds the bounded cell limit.")
    if any(len(row) != width for row in rows):
        _fail("ONS_HEADER_INVALID", "ONS CSV rows must match the metadata width.")
    if tuple(row[0] for row in rows[:7]) != METADATA_ROWS:
        _fail("ONS_HEADER_INVALID", "ONS CSV metadata labels or their order have changed.")
    cdids = rows[1][1:]
    if len(set(cdids)) != len(cdids) or any(not re.fullmatch(r"[A-Z0-9]{4}", cdid) for cdid in cdids):
        _fail("ONS_CDID_INVALID", "ONS CDIDs must be unique four-character identifiers.")
    if any(not title.strip() for title in rows[0][1:]):
        _fail("ONS_HEADER_INVALID", "ONS series titles must be nonempty.")
    indices = {cdid: index + 1 for index, cdid in enumerate(cdids)}
    if set(SERIES) - set(cdids):
        _fail("ONS_SERIES_MISSING", "ONS CSV is missing a registered headline series.")
    for cdid, (title, unit, *_) in SERIES.items():
        index = indices[cdid]
        if (_normalize_text(rows[0][index]) != _normalize_text(title)
                or rows[2][index] != "" or rows[3][index] != unit):
            _fail("ONS_SERIES_DRIFT", f"The published definition or unit for {cdid} has changed.")
    releases = set(rows[4][1:])
    if len(releases) != 1:
        _fail("ONS_VINTAGE_INVALID", "All ONS series must have one common release date.")
    release = releases.pop()
    try:
        if not re.fullmatch(r"\d{2}-\d{2}-\d{4}", release):
            raise ValueError
        vintage_date = datetime.strptime(release, "%d-%m-%Y").date()
    except ValueError as exc:
        raise DomainError("ONS_VINTAGE_INVALID", "ONS Release Date must use DD-MM-YYYY.") from exc
    observations, periods, seen, previous, grain_counts = [], [], set(), {}, {}
    for row_index, row in enumerate(rows[7:], 7):
        period, grain = _period(row[0])
        if (grain, period) in seen or period <= previous.get(grain, ""):
            _fail("ONS_PERIOD_INVALID", "ONS period labels must be unique and chronological within each grain.")
        seen.add((grain, period))
        previous[grain] = period
        grain_counts[grain] = grain_counts.get(grain, 0) + 1
        periods.append({"period": period, "grain": grain, "source_label": row[0], "row": row_index + 1})
        # Validate every value, even outside the registered metric projection.
        values = [_value(cell) for cell in row[1:]]
        if grain != "month":
            continue
        for cdid in SERIES:
            index = indices[cdid]
            value, status, decimals = values[index - 1]
            definition, dimensions = _definition(cdid)
            start, end = lines[row_index]
            observations.append({"metric_id": f"ons.{cdid}", "period": period, "value": value,
                                 "status": status, "unit": "percent_points", "display_decimals": decimals,
                                 "locator": f"csv:lines={start}-{end};column={index+1};cdid={cdid}",
                                 "definition": definition, "dimensions": dimensions})
    latest = previous.get("month")
    if latest is None or latest >= vintage_date.strftime("%Y-%m"):
        _fail("ONS_VINTAGE_INVALID", "ONS CSV requires monthly data preceding its publication month.")
    metadata = {
        "dataset_id": "DRSI", "source_level": "published_aggregate_estimates", "raw_microdata": False,
        "period_grains": grain_counts, "period_inventory": periods,
        "series_count": len(cdids), "registered_series": list(SERIES),
        "unregistered_series": [cdid for cdid in cdids if cdid not in SERIES],
        "series": {cdid: {"title": rows[0][indices[cdid]], "pre_unit": rows[2][indices[cdid]],
                          "unit": rows[3][indices[cdid]], "release_date": rows[4][indices[cdid]],
                          "next_release": rows[5][indices[cdid]], "notes": rows[6][indices[cdid]]}
                   for cdid in cdids},
        "index_reference_year": None,
        "index_reference_note": "CSV index metadata declares base=100 without naming its reference year. No year was inferred.",
        "unit_note": "percent_points preserves published percentage-number values, not fractional ratios. MS6Y is a percentage share despite blank native Unit metadata.",
        "coverage": "Only seven registered monthly headline series are normalized. Annual and quarterly rows, other series and original definitions remain inventoried.",
    }
    return {"family": "ons_retail", "parser_version": PARSER_VERSION,
            "source_digest": hashlib.sha256(data).hexdigest(), "period": latest,
            "vintage": vintage_date.isoformat(), "observations": observations, "metadata": metadata, "issues": []}


def _named_period(month, year):
    return f"{int(year):04}-{MONTH_NUMBER[month.casefold()]:02}"


def _signed(number, direction):
    value, _, decimals = _value(number)
    negative = direction.casefold() in {"fell", "fallen", "fall", "decline", "decreased", "decrease"}
    result = -Decimal(value) if negative else Decimal(value)
    return format(result, "f"), decimals


def inspect_report(asset: dict) -> dict:
    """Observe only explicit bulletin wording, independently of all source data."""
    if (not isinstance(asset, dict) or not isinstance(asset.get("id"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("digest", "")))):
        _fail("ONS_TARGET_IDENTITY_INVALID", "An ONS target requires its original asset identity and digest.")
    raw_regions = asset.get("profile", {}).get("regions", [])
    if not isinstance(raw_regions, list) or len(raw_regions) > 500:
        _fail("ONS_REPORT_LIMIT", "ONS report regions exceed the bounded inventory.")
    if any(not isinstance(region, dict) or not isinstance(region.get("text", ""), str) for region in raw_regions):
        _fail("ONS_REPORT_INVALID", "ONS report regions must contain literal text.")
    if sum(len(region.get("text", "")) for region in raw_regions) > MAX_REPORT_TEXT:
        _fail("ONS_REPORT_LIMIT", "ONS report text exceeds the bounded inspection limit.")
    regions = copy.deepcopy(raw_regions)
    texts = [_normalize_text(region.get("text", "")) for region in regions]
    headings, releases, notices = set(), set(), []
    narrative_page_count = None
    for text in texts:
        for match in re.finditer(rf"Retail sales, Great Britain:\s*({MONTH_PATTERN}) (\d{{4}})", text):
            headings.add(_named_period(match[1], match[2]))
        for match in re.finditer(rf"Release date:\s*(\d{{1,2}}) ({MONTH_PATTERN}) (\d{{4}})", text):
            try:
                releases.add(date(int(match[3]), MONTH_NUMBER[match[2].casefold()], int(match[1])).isoformat())
            except ValueError:
                _fail("ONS_REPORT_VINTAGE_INVALID", "The report publication date is invalid.")
        if narrative_page_count is None:
            match = re.search(r"Page 1 of (\d+)", text)
            if match:
                narrative_page_count = int(match[1])
        for match in re.finditer(rf"Notice (\d{{1,2}} {MONTH_PATTERN} \d{{4}})(.*?)(?=Page \d+ of|$)", text):
            notices.append({"date_label": match[1], "text": match[2].strip()})
    # The June cover notice refers to a different bulletin. Its title must not
    # redefine the actual report period; the first located cover title owns it.
    cover = texts[0] if texts else ""
    title = re.search(rf"Statistical bulletin Retail sales, Great Britain:\s*({MONTH_PATTERN}) (\d{{4}})", cover)
    if title:
        report_period = _named_period(title[1], title[2])
    elif len(headings) == 1:
        report_period = next(iter(headings))
    else:
        _fail("ONS_REPORT_PERIOD_INVALID", "The ONS report period is missing or ambiguous.")
    if len(releases) != 1:
        _fail("ONS_REPORT_VINTAGE_INVALID", "The ONS report requires one explicit publication date.")
    vintage = next(iter(releases))
    if report_period >= vintage[:7]:
        _fail("ONS_REPORT_VINTAGE_INVALID", "The report period must precede its publication month.")
    observations, issues, observed_keys = [], [], {}

    def add(region, text, match, cdid, number, direction="rose", *, period=None):
        value, decimals = _signed(number, direction)
        period = period or report_period
        definition, dimensions = _definition(cdid)
        key = (cdid, period)
        prior = observed_keys.get(key)
        if prior is not None and Decimal(prior) != Decimal(value):
            issues.append({"code": "ONS_REPORT_CONFLICT", "severity": "block", "metric_id": f"ons.{cdid}",
                           "period": period, "locator": region["locator"],
                           "message": "Explicit report statements disagree for the same metric and period."})
        observed_keys[key] = value
        observation = {"id": f"{asset['id']}:{len(observations)+1}", "metric_id": f"ons.{cdid}",
                       "period": period, "value": value, "status": "known", "unit": "percent_points",
                       "display_decimals": decimals, "definition": definition, "dimensions": dimensions,
                       "locator": f"{region['locator']};normalized_text_chars={match.start()}-{match.end()}",
                       "region_id": region["id"], "method": "explicit_ons_bulletin_wording",
                       "display": number + "%", "evidence_text": text[match.start():match.end()]}
        observations.append(observation)
        region["observation_ids"].append(observation["id"])

    direction = r"(?P<direction>rose|fell)"
    date_pattern = rf"(?P<month>{MONTH_PATTERN}) (?P<year>\d{{4}})"
    volume_month = re.compile(rf"(?:Sales volumes {direction} by|Retail sales volumes(?: \(quantity bought\))? are estimated to have (?P<estimated>risen|fallen) by) (?P<number>{UNSIGNED})% (?:over the month during|during|in) {date_pattern}")
    volume_year = re.compile(rf"Sales volumes {direction} by (?P<number>{UNSIGNED})% over the year to {date_pattern}")
    volume_quarter = re.compile(rf"Sales volumes {direction} by (?P<number>{UNSIGNED})% in the three months to {date_pattern}")
    quarter_phrase = re.compile(rf"there was a (?P<number>{UNSIGNED})% (?P<direction>rise|fall) across the three months to {date_pattern}", re.IGNORECASE)
    quarter_annual = re.compile(rf"Sales volumes {direction} by (?P<number>{UNSIGNED})%, compared with the three months to {date_pattern}")
    quarter_annual_context = re.compile(rf"There was a (?P<number>{UNSIGNED})% (?P<direction>rise|fall) compared with the same period last year")
    compound_annual = re.compile(rf"Sales volumes (?:rose|fell) by {UNSIGNED}% over the month during (?P<anchor_month>{MONTH_PATTERN}) (?P<anchor_year>\d{{4}}), following a {UNSIGNED}% (?:rise|fall) in {MONTH_PATTERN}, and (?P<direction>rose|fell) by (?P<number>{UNSIGNED})% over the year to {date_pattern}")
    reverse_quarter_annual = re.compile(rf"[Ww]hen comparing with the three months to {date_pattern}, sales volumes (?P<direction>rose|fell) by (?P<number>{UNSIGNED})%")
    named_quarter_annual = re.compile(rf"[Ww]hen compared with Quarter (?P<quarter>[1-4]) (?P<year>\d{{4}}), sales volumes (?P<direction>rose|fell) by (?P<number>{UNSIGNED})%")
    online = re.compile(rf"The amount spent online, known as [\"“]online spending values[\"”], (?P<direction>rose|fell) by (?P<monthly>{UNSIGNED})% over the month to {date_pattern},? and by (?P<annual>{UNSIGNED})% when comparing (?P<current_month>{MONTH_PATTERN}) (?P<current_year>\d{{4}}) with (?P<previous_month>{MONTH_PATTERN}) (?P<previous_year>\d{{4}})")
    online_monthly_series = re.compile(rf"(?:Considering|With) the monthly series, sales values (?P<direction>rose|fell) by (?P<monthly>{UNSIGNED})% over the month to {date_pattern},? and by (?P<annual>{UNSIGNED})% when comparing (?P<current_month>{MONTH_PATTERN}) (?P<current_year>\d{{4}}) with (?P<previous_month>{MONTH_PATTERN}) (?P<previous_year>\d{{4}})")
    share = re.compile(rf"the proportion of sales made online (?:rose|fell|increased|decreased|showed little change, (?:falling|rising)) from (?P<previous>{UNSIGNED})% in (?P<previous_month>{MONTH_PATTERN}) (?P<previous_year>\d{{4}}) to (?P<number>{UNSIGNED})% in {date_pattern}")
    for index, (region, text) in enumerate(zip(regions, texts), 1):
        region.setdefault("id", f"region{index}")
        region.setdefault("locator", f"asset:{asset['id']}/region[{index}]")
        region.update(status="needs_decision", observation_ids=[])
        physical_page = re.search(r"(?:^|;)page=(\d+)", region["locator"])
        is_appendix = bool(narrative_page_count and physical_page and int(physical_page[1]) > narrative_page_count)
        if is_appendix:
            region["coverage_kind"] = "statistical_appendix"
        elif region.get("kind") not in {"page", "paragraph", "text"}:
            region["coverage_kind"] = "unsupported_structure"
        else:
            region["coverage_kind"] = "narrative_and_layout"
            # Only an explicitly headed total-retail section or Overview can
            # supply aggregate volume figures; sector pages remain uncovered.
            total_section = bool(re.search(r"(?:\d+ \. (?:Overview|Retail sales in)|^Sales volumes )", text))
            if total_section:
                for pattern, cdid in [(volume_month, "J5EC"), (volume_year, "J5EB"),
                                      (volume_quarter, "J5EG"), (quarter_phrase, "J5EG")]:
                    for match in pattern.finditer(text):
                        period = _named_period(match["month"], match["year"])
                        if period == report_period:
                            verb = match.groupdict().get("direction") or match.groupdict().get("estimated")
                            add(region, text, match, cdid, match["number"], verb, period=period)
                previous_year_period = f"{int(report_period[:4])-1}{report_period[4:]}"
                for match in quarter_annual.finditer(text):
                    if _named_period(match["month"], match["year"]) == previous_year_period:
                        add(region, text, match, "J5EH", match["number"], match["direction"])
                for match in compound_annual.finditer(text):
                    if (_named_period(match["month"], match["year"]) == report_period
                            and _named_period(match["anchor_month"], match["anchor_year"]) == report_period):
                        add(region, text, match, "J5EB", match["number"], match["direction"])
                if any(obs["metric_id"] == "ons.J5EG" and obs["region_id"] == region["id"] for obs in observations):
                    for match in quarter_annual_context.finditer(text):
                        add(region, text, match, "J5EH", match["number"], match["direction"])
                    for match in reverse_quarter_annual.finditer(text):
                        if _named_period(match["month"], match["year"]) == previous_year_period:
                            add(region, text, match, "J5EH", match["number"], match["direction"])
                    for match in named_quarter_annual.finditer(text):
                        quarter = (int(report_period[5:]) - 1) // 3 + 1
                        if (int(report_period[5:]) % 3 == 0 and int(match["quarter"]) == quarter
                                and int(match["year"]) == int(report_period[:4]) - 1):
                            add(region, text, match, "J5EH", match["number"], match["direction"])
            if re.search(r"\d+ \. Online retail values", text):
                for match in [*online.finditer(text), *online_monthly_series.finditer(text)]:
                    period = _named_period(match["month"], match["year"])
                    same_current = _named_period(match["current_month"], match["current_year"]) == period
                    prior = _named_period(match["previous_month"], match["previous_year"])
                    if period == report_period and same_current and prior == f"{int(period[:4])-1}{period[4:]}":
                        add(region, text, match, "KP8P", match["monthly"], match["direction"])
                        add(region, text, match, "KP8H", match["annual"], match["direction"])
                for match in share.finditer(text):
                    if _named_period(match["month"], match["year"]) == report_period:
                        add(region, text, match, "MS6Y", match["number"])
        if region["observation_ids"]:
            region["status"] = "partially_mapped"
        region["reason"] = "Only located registered numeric claims are observed. Other prose, anecdotes, charts, tables, notices and exact layout remain outside this parser's coverage."
    missing = [f"ons.{cdid}" for cdid in SERIES if (cdid, report_period) not in observed_keys]
    if missing:
        issues.append({"code": "ONS_REPORT_OBSERVATIONS_MISSING", "severity": "block", "metric_ids": missing,
                       "message": "The bulletin does not explicitly match every registered headline observation pattern."})
    issues.append({"code": "ONS_REPORT_PARTIAL_COVERAGE", "severity": "review",
                   "message": "The seven-metric numerical scope does not certify all narrative claims, retailer anecdotes, revision explanations, statistical tables, charts or layout."})
    return {"asset_id": asset["id"], "asset_digest": asset["digest"], "family": "ons_retail",
            "parser_version": PARSER_VERSION, "report_period": report_period, "vintage": vintage,
            "observations": observations, "regions": regions, "issues": issues,
            "metadata": {"narrative_page_count": narrative_page_count, "notices": notices,
                         "scope": "seven_registered_headline_metrics", "publication_date_is_notice_date": False}}


__all__ = ["inspect_source", "inspect_report"]
