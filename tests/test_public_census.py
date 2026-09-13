"""Census parser tests use only the May/June authoring periods, never holdouts."""
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from foundry.errors import DomainError
from foundry.ingestion import inspect_asset
from foundry.public_census import extract_static_xlsx, inspect_report, inspect_report_bytes, inspect_source

ROOT = Path(__file__).resolve().parents[1]
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def original(month, role):
    assert month in (5, 6), 'July/August are reserved for later evaluation.'
    suffix = 'xlsx' if role == 'source' else 'pdf'
    paths = [ROOT / 'output/public-corpus-cache' / f'census-marts-2025-{month:02}-{role}.{suffix}',
             ROOT / 'output/public-corpus-research/census' / f"{'rs' if role == 'source' else 'adv'}25{month:02}.{suffix}"]
    for path in paths:
        if path.exists():
            return path.read_bytes()
    pytest.skip('Original May/June public corpus cache is required; tests never download artifacts.')


def edit_archive(data, updates=None, additions=None):
    target = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(target, 'w', ZIP_DEFLATED) as result:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if updates and entry.filename in updates:
                content = updates[entry.filename](content)
            result.writestr(entry, content)
        for name, content in (additions or {}).items():
            result.writestr(name, content)
    return target.getvalue()


def edit_cell(data, sheet_number, address, value, *, formula=None, cache=None):
    def update(content):
        root = ET.fromstring(content)
        cell = root.find(f".//{S}c[@r='{address}']")
        assert cell is not None, address
        cell.clear()
        cell.set('r', address)
        if formula is not None:
            ET.SubElement(cell, S + 'f').text = formula
            if cache is not None:
                ET.SubElement(cell, S + 'v').text = str(cache)
        elif value is not None:
            if isinstance(value, str):
                cell.set('t', 'inlineStr')
                ET.SubElement(ET.SubElement(cell, S + 'is'), S + 't').text = value
            else:
                ET.SubElement(cell, S + 'v').text = str(value)
        return ET.tostring(root)
    return edit_archive(data, {f'xl/worksheets/sheet{sheet_number}.xml': update})


@pytest.mark.parametrize('month,vintage,total,prior,headline,rates', [
    (5, '2025-06-17', '715417', '721983', '715400.0', ['-0.9', '3.3', '4.5', '-0.9', '3.0', '8.3', '5.3']),
    (6, '2025-07-17', '720106', '715541', '720100.0', ['0.6', '3.9', '4.1', '0.6', '3.5', '4.5', '6.6']),
])
def test_real_authoring_pairs_have_independent_values_vintages_and_precision(month, vintage, total, prior, headline, rates):
    source_bytes, report_bytes = original(month, 'source'), original(month, 'report')
    source, report = inspect_source(source_bytes), inspect_report_bytes(report_bytes)
    period = f'2025-{month:02}'
    assert source['period'] == report['report_period'] == period
    assert source['vintage'] == report['vintage'] == vintage
    assert source['issues'] == report['issues'] == []
    assert len(source['observations']) == 28 and len(report['observations']) == 35
    assert source['source_digest'] == hashlib.sha256(source_bytes).hexdigest()
    assert report['asset_digest'] == hashlib.sha256(report_bytes).hexdigest()
    by_source = {(o['metric_id'], o['period']): o for o in source['observations']}
    assert by_source[('census.sales_usd_million', period)]['value'] == total
    assert by_source[('census.sales_usd_million', f'2025-{month - 1:02}')]['value'] == prior
    narrative = [o for o in report['observations'] if o['method'] == 'published_report_narrative']
    assert narrative[0]['value'] == headline
    assert narrative[0]['unit'] == 'usd_million' and narrative[0]['display_decimals'] == -2
    assert [o['value'] for o in narrative[1:]] == rates
    assert all(o['unit'] == 'percent_points' and o['display_decimals'] == 1 for o in narrative[1:])
    assert all(o['locator'] and o['source_digest'] == source['source_digest'] for o in source['observations'])
    assert all(o['status'] == 'known' for o in source['observations'])
    assert sum(o.get('method') == 'change_from_published_levels' for o in source['observations']) == 6
    rolling = by_source[('census.rolling_three_month_year_on_year_pct', period)]
    assert rolling['independent_recomputation_available'] is False and rolling['method'] == 'published_rate'
    assert len(report['regions']) == 7
    assert all(r['status'] != 'mapped' for r in report['regions'])  # partial observations do not certify whole pages
    json.dumps(source, allow_nan=False)
    json.dumps(report, allow_nan=False)


def test_static_mode_retains_external_provenance_without_opening_target_and_generic_gate_stays_strict(monkeypatch):
    data = original(5, 'source')
    with pytest.raises(DomainError) as rejected:
        inspect_asset(data, 'source.xlsx')
    assert rejected.value.code in {'ACTIVE_CONTENT', 'EXTERNAL_RESOURCE'}
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Static workbook extraction must not open a path or use a socket')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr('builtins.open', forbidden)
    static = extract_static_xlsx(data)
    assert static['external_resolution'] == static['formula_evaluation'] == 'never'
    assert len(static['external_relationships']) == 1
    relation = static['external_relationships'][0]
    assert relation['target'] == 'file:///A:\\ADVDEL01.xls' and relation['resolved'] is False
    assert relation['part'] == 'xl/externalLinks/_rels/externalLink1.xml.rels'
    assert static['source_digest'] == hashlib.sha256(data).hexdigest()
    observed = next(c for c in static['cells'] if c['sheet'] == 'Table 1.' and c['address'] == 'J12')
    assert observed['value'] == observed['raw_xml_value'] == '715417'


@pytest.mark.parametrize('value,status', [(None, 'missing'), ('(S)', 'withheld'), ('(NA)', 'undefined'), ('(*)', 'missing'),
                                         ('not a number', 'undefined'), ('7,15417', 'undefined')])
def test_missing_suppressed_or_invalid_source_values_never_become_zero(value, status):
    data = edit_cell(original(5, 'source'), 1, 'J12', value)
    result = inspect_source(data)
    observation = next(o for o in result['observations'] if o['metric_id'] == 'census.sales_headline_usd_million')
    assert observation['value'] is None and observation['status'] == status
    assert result['issues']
    assert all(i['severity'] == 'block' for i in result['issues'])
    change = next(o for o in result['observations'] if o['metric_id'] == 'census.month_on_month_pct')
    assert change['value'] is None and change['status'] == status


def test_formula_cache_is_preserved_but_cannot_supply_values(monkeypatch):
    data = edit_cell(original(5, 'source'), 1, 'J12', None,
                     formula='WEBSERVICE("https://invalid.example/private")', cache=715417)
    monkeypatch.setattr(socket.socket, 'connect', lambda *_args, **_kwargs: pytest.fail('Unexpected network access'))
    static = extract_static_xlsx(data)
    cell = next(c for c in static['cells'] if c['sheet'] == 'Table 1.' and c['address'] == 'J12')
    assert cell['formula'].startswith('=WEBSERVICE(')
    assert cell['cached_value'] == '715417' and cell['cached_value_trusted'] is False
    assert cell['value'] is None and cell['status'] == 'undefined'
    result = inspect_source(data)
    assert result['issues']
    assert next(o for o in result['observations'] if o['metric_id'] == 'census.sales_headline_usd_million')['value'] is None


@pytest.mark.parametrize('sheet,cell,value', [
    (1, 'A4', 'Values are in billions of dollars'), (2, 'A3', 'Estimates are currency levels'),
    (1, 'J6', 'Not Adjusted'), (1, 'A76', 'Adjusted for price changes'),
    (1, 'J8', 'Jun.3'), (1, 'K8', 'Mar.'), (1, 'M7', 2023),
    (2, 'C8', 'Jun. 2025 Advance'), (1, 'J9', '(r)'), (1, 'A64', 455),
    (2, 'A51', 455), (1, 'B17', 'Wholesale'),
    (2, 'A59', 'Source: U.S. Census Bureau, Advance Monthly Retail Trade Survey, July 17, 2025.'),
])
def test_units_basis_period_vintage_and_category_drift_block(sheet, cell, value):
    with pytest.raises(DomainError) as failure:
        inspect_source(edit_cell(original(5, 'source'), sheet, cell, value))
    assert failure.value.code == 'PUBLIC_SOURCE_DRIFT'


def test_comparison_change_and_zero_denominator_are_explicit_reconciliation_issues():
    changed = inspect_source(edit_cell(original(5, 'source'), 1, 'K12', 700000))
    mom = next(o for o in changed['observations'] if o['metric_id'] == 'census.month_on_month_pct')
    assert mom['value'] == '2.2' and mom['published_value'] == '-0.9'
    assert any(i['code'] == 'PUBLIC_SOURCE_RECONCILIATION' for i in changed['issues'])
    assert all(i['severity'] == 'block' for i in changed['issues'])
    zero = inspect_source(edit_cell(original(5, 'source'), 1, 'K12', 0))
    mom = next(o for o in zero['observations'] if o['metric_id'] == 'census.month_on_month_pct')
    assert mom['status'] == 'undefined' and mom['value'] is None and zero['issues']


def test_coherently_updated_percentages_cannot_legitimize_negative_sales():
    from foundry.public_reports import prepare
    data = edit_cell(original(5, 'source'), 1, 'J12', -100)
    # Both rates genuinely round to -100.0 for the unchanged prior levels.
    # This specifically avoids relying on a stale published-rate contradiction.
    data = edit_cell(data, 2, 'C15', -100.0)
    data = edit_cell(data, 2, 'D15', -100.0)
    result = inspect_source(data)
    assert any(i['code'] == 'PUBLIC_VALUE_INVALID' and i['severity'] == 'block' for i in result['issues'])
    headline = next(o for o in result['observations'] if o['metric_id'] == 'census.sales_headline_usd_million')
    assert headline['value'] is None and headline['status'] == 'undefined'
    period = {'label': 'May 2025', 'start': '2025-05-01', 'end_exclusive': '2025-06-01',
              'comparison': {'start': '2025-04-01', 'end_exclusive': '2025-05-01'},
              'timezone': 'UTC', 'as_of': '2025-06-17T23:59:59Z'}
    with pytest.raises(DomainError) as failure:
        prepare(result, period, {'id': 'source', 'filename': 'negative.xlsx', 'digest': result['source_digest']}, family='census_marts')
    assert failure.value.code == 'SOURCE_RECONCILIATION_REQUIRED'


@pytest.mark.parametrize('cell', ['K12', 'J17', 'M64', 'N67'])
def test_nonnegative_domain_applies_to_each_category_and_comparison_period(cell):
    result = inspect_source(edit_cell(original(5, 'source'), 1, cell, -1))
    assert any(i['code'] == 'PUBLIC_VALUE_INVALID' and i['locator'] == f'sheet=Table 1.;cell={cell}' for i in result['issues'])


@pytest.mark.parametrize('part,body,code', [
    ('../escape.xml', b'<x/>', 'ARCHIVE_INVALID'),
    ('xl/vbaProject.bin', b'macro', 'ACTIVE_CONTENT'),
    ('xl/embeddings/object.bin', b'object', 'ACTIVE_CONTENT'),
])
def test_static_mode_does_not_weaken_other_zip_protections(part, body, code):
    with pytest.raises(DomainError) as rejected:
        extract_static_xlsx(edit_archive(original(5, 'source'), additions={part: body}))
    assert rejected.value.code == code


def report_asset():
    data = original(5, 'report')
    return {'id': 'may-report', 'digest': hashlib.sha256(data).hexdigest(), **inspect_asset(data, 'report.pdf')}


def test_report_parsing_is_independent_and_preserves_every_original_region(monkeypatch):
    asset = report_asset()
    saved = copy.deepcopy(asset)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Report parsing must not read source data')
    monkeypatch.setattr('foundry.public_census.inspect_source', forbidden)
    monkeypatch.setattr('foundry.public_census.extract_static_xlsx', forbidden)
    result = inspect_report(asset)
    assert not result['issues'] and asset == saved
    assert [(r['id'], r['text'], r['locator']) for r in result['regions']] == [
        (r['id'], r['text'], r['locator']) for r in asset['profile']['regions']]


@pytest.mark.parametrize('page,old,new,code', [
    (0, 'down 0.9 percent', 'up 0.9 percent', 'PUBLIC_REPORT_CONTRADICTION'),
    (0, 'were $715.4 billion', 'were $999.4 billion', 'PUBLIC_REPORT_CONTRADICTION'),
    (5, 'May 2025 Advance', 'June 2025 Advance', 'PUBLIC_REPORT_PERIOD'),
    (5, 'June 17, 2025', 'July 17, 2025', 'PUBLIC_REPORT_VINTAGE'),
    (4, 'millions of dollars', 'billions of dollars', 'PUBLIC_REPORT_UNITS'),
])
def test_report_profile_mutations_detect_internal_disagreement(page, old, new, code):
    asset = report_asset()
    region = asset['profile']['regions'][page]
    assert old in region['text']
    region['text'] = region['text'].replace(old, new)
    result = inspect_report(asset)
    assert any(issue['code'] == code for issue in result['issues'])
    assert all(i['severity'] == 'block' for i in result['issues'])


def test_missing_or_ambiguous_report_regions_are_explicit():
    asset = report_asset()
    asset['profile']['regions'].pop(5)
    assert any(i['code'] == 'PUBLIC_REPORT_TABLE' for i in inspect_report(asset)['issues'])
    asset = report_asset()
    asset['profile']['regions'].append(copy.deepcopy(asset['profile']['regions'][0]))
    result = inspect_report(asset)
    assert not result['observations'] and result['issues'][0]['code'] == 'PUBLIC_REPORT_IDENTITY'


@pytest.mark.parametrize('vintage', ['April 17, 2025', 'May 31, 2025'])
def test_consistently_backdated_source_cannot_publish_a_future_or_unfinished_month(vintage):
    data = edit_archive(original(5, 'source'), {'xl/sharedStrings.xml':
        lambda content: content.replace(b'June 17, 2025', vintage.encode())})
    with pytest.raises(DomainError) as failure:
        inspect_source(data)
    assert failure.value.code == 'PUBLIC_SOURCE_DRIFT' and 'follow its reference month' in failure.value.message


@pytest.mark.parametrize('vintage', ['April 17, 2025', 'May 31, 2025'])
def test_consistently_backdated_report_is_independently_rejected(vintage):
    asset = report_asset()
    for region in asset['profile']['regions']:
        region['text'] = region['text'].replace('June 17, 2025', vintage).replace('JUNE 17, 2025', vintage.upper())
    result = inspect_report(asset)
    assert not result['observations']
    assert any(i['code'] == 'PUBLIC_REPORT_VINTAGE' and i['severity'] == 'block' for i in result['issues'])
    assert len(result['regions']) == len(asset['profile']['regions'])
