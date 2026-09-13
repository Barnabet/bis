"""FMC diagnostics: Q1/Q2 development only, with no OCR/generation claims."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from foundry.errors import DomainError
from foundry.public_fmc import inspect_source, reconcile_report

ROOT = Path(__file__).resolve().parents[1]
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def original():
    for path in [ROOT / 'output/public-corpus-cache/fmc-cfs-2025-source.xlsx',
                 ROOT / 'output/public-corpus-research/transport/CFS_2025_Data.xlsx']:
        if path.exists():
            return path.read_bytes()
    pytest.skip('The frozen original FMC workbook cache is required; tests never download artifacts.')


def edit_cell(data, sheet, address, value):
    result = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(result, 'w', ZIP_DEFLATED) as target:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if entry.filename == f'xl/worksheets/sheet{sheet}.xml':
                root = ET.fromstring(content)
                cell = root.find(f".//{S}c[@r='{address}']")
                assert cell is not None
                cell.clear(); cell.set('r', address)
                if isinstance(value, str):
                    cell.set('t', 'inlineStr')
                    ET.SubElement(ET.SubElement(cell, S + 'is'), S + 't').text = value
                elif value is not None:
                    ET.SubElement(cell, S + 'v').text = str(value)
                content = ET.tostring(root)
            target.writestr(entry, content)
    return result.getvalue()


@pytest.mark.parametrize('quarter,port_count,port_containers,carrier_containers,tonnage', [
    (1, 37, '13883563', '13883561', '109183990'),
    (2, 36, '12980936', '12980935', '111384019'),
])
def test_real_development_quarters_are_selected_without_full_year_leakage(quarter, port_count, port_containers, carrier_containers, tonnage):
    data = original()
    normalized = inspect_source(data, f'2025-Q{quarter}')
    assert normalized['source_digest'] == hashlib.sha256(data).hexdigest()
    assert normalized['metadata']['selected_row_counts'] == {'US Ports': port_count, 'Ocean Carriers': 29}
    assert normalized['metadata']['source_row_counts'] == {'US Ports': 147, 'Ocean Carriers': 116}
    assert normalized['metadata']['all_source_rows_checked'] and normalized['metadata']['all_source_rows_valid']
    assert all(r['period'] == f'2025-Q{quarter}' for rows in normalized['rows'].values() for r in rows)
    assert all(o['period'] == f'2025-Q{quarter}' for o in normalized['observations'])
    assert normalized['totals']['US Ports']['container_total'] == port_containers
    assert normalized['totals']['Ocean Carriers']['container_total'] == carrier_containers
    assert normalized['totals']['US Ports']['tonnage_total'] == normalized['totals']['Ocean Carriers']['tonnage_total'] == tonnage
    assert all(issue['severity'] == 'block' for issue in normalized['issues'])
    assert {'FMC_CROSS_TABLE_DISCREPANCY', 'FMC_REPORT_OBSERVATIONS_REQUIRED', 'FMC_TONNAGE_UNIT_UNRESOLVED'} <= {i['code'] for i in normalized['issues']}
    assert normalized['metadata']['report_ocr_performed'] is False and normalized['metadata']['report_certification'] == 'blocked'
    assert normalized['vintage'] is None
    json.dumps(normalized, allow_nan=False)


@pytest.mark.parametrize('period', ['2025', '2025-Q5', 'Q1 2025', '2024-Q1', None])
def test_missing_or_wrong_quarter_is_not_silently_rebound(period):
    with pytest.raises(DomainError):
        inspect_source(original(), period)


@pytest.mark.parametrize('sheet,cell,value,code', [
    (2, 'A2', 'Q2 2024', 'FMC_ROW_PERIOD_INVALID'),
    (2, 'B2', '', 'FMC_ENTITY_INVALID'),
    (2, 'B3', 'Anchorage, Alaska', 'FMC_DUPLICATE_ENTITY'),
    (2, 'C2', None, 'FMC_VALUE_UNAVAILABLE'),
    (2, 'C2', -1, 'FMC_VALUE_UNAVAILABLE'),
    (2, 'C2', 1.25, 'FMC_VALUE_UNAVAILABLE'),
    (2, 'C2', 'unknown', 'FMC_VALUE_UNAVAILABLE'),
    (2, 'C39', 'unknown', 'FMC_VALUE_UNAVAILABLE'),  # another development quarter still validated
])
def test_all_rows_are_validated_and_missing_counts_do_not_become_zero(sheet, cell, value, code):
    result = inspect_source(edit_cell(original(), sheet, cell, value), '2025-Q1')
    assert any(i['code'] == code and i['severity'] == 'block' for i in result['issues'])
    assert result['metadata']['all_source_rows_valid'] is False
    if cell == 'C2':
        assert result['totals']['US Ports']['laden_exports'] is None
        assert result['totals']['US Ports']['container_total'] is None


@pytest.mark.parametrize('sheet,cell,value', [(1, 'A2', 'Unspecified period'), (1, 'A3', 'Amounts in USD'),
                                             (2, 'C1', 'TEU Revenue'), (3, 'B1', 'Port Name')])
def test_scope_unit_or_entity_header_drift_fails(sheet, cell, value):
    with pytest.raises(DomainError) as failure:
        inspect_source(edit_cell(original(), sheet, cell, value))
    assert failure.value.code == 'FMC_SOURCE_DRIFT'


# These are independently visually transcribed Q1 report controls, not values
# obtained from normalized source output. This is curated test evidence, not OCR.
Q1_PUBLISHED = {'laden_exports': '3477686', 'empty_exports': '3719786', 'laden_imports': '6438387',
                'empty_imports': '247691', 'container_total': '13883549',
                'export_tonnage': '42065857', 'import_tonnage': '67118133', 'tonnage_total': '109183990'}
Q1_REPORT_DIGEST = 'b88b995d7d377da5b1a6f2d6afc07940818e4c8c150ead96c8904df76dcde831'


def controls():
    return [{'table': table, 'entity': 'Total', 'metric_id': 'fmc.' + metric, 'period': '2025-Q1',
             'value': value, 'unit': 'tonnage_as_published' if 'tonnage' in metric else 'containers_as_published',
             'locator': f'page={page};row=Total;column={metric}', 'source_digest': Q1_REPORT_DIGEST,
             'method': 'independently_visually_curated_test_control'}
            for table, page in [('US Ports', 1), ('Ocean Carriers', 3)] for metric, value in Q1_PUBLISHED.items()]


def test_independent_curated_controls_expose_discrepancies_without_ocr_success_claim():
    normalized = inspect_source(original())
    saved = deepcopy(normalized)
    result = reconcile_report(normalized, controls())
    assert normalized == saved
    assert len(result['checks']) == 16
    assert sum(c['passed'] for c in result['checks']) == 6  # six tonnage controls, ten differing container controls
    assert {c['difference'] for c in result['checks'] if c['metric_id'] == 'fmc.container_total'} == {'14', '12'}
    assert sum(i['code'] == 'FMC_REPORT_DISCREPANCY' for i in result['reconciliation_findings']) == 10
    assert sum(i['code'] == 'FMC_REPORT_INTERNAL_DISCREPANCY' for i in result['reconciliation_findings']) == 2
    assert all(i['severity'] == 'block' for i in result['issues'])
    assert result['report_certification'] == 'blocked' and result['report_ocr_performed'] is False
    assert any(i['code'] == 'FMC_REPORT_OBSERVATIONS_REQUIRED' for i in result['issues'])
    json.dumps(result, allow_nan=False)


def test_individual_port_controls_use_selected_row_identity_and_subtotals():
    normalized = inspect_source(original())
    supplied = [{'table': 'US Ports', 'entity': 'Los Angeles, California', 'metric_id': 'fmc.container_total',
                 'period': '2025-Q1', 'value': '2139760', 'unit': 'containers_as_published',
                 'source_digest': Q1_REPORT_DIGEST, 'locator': 'page=1;row=Los Angeles;column=Total',
                 'method': 'independently_visually_curated_test_control'}]
    result = reconcile_report(normalized, supplied)
    assert result['checks'][0]['passed'] is True
    supplied[0]['value'] = '2139761'
    result = reconcile_report(normalized, supplied)
    assert result['checks'][0]['passed'] is False and result['reconciliation_findings']


@pytest.mark.parametrize('field,value', [('period', '2025-Q2'), ('unit', 'EUR'), ('source_digest', ''),
                                        ('locator', ''), ('entity', 'Atlantis'), ('metric_id', None), ('value', 'NaN')])
def test_report_control_identity_and_numeric_validation_fail_closed(field, value):
    supplied = controls()[:1]
    supplied[0][field] = value
    result = reconcile_report(inspect_source(original()), supplied)
    assert not result['checks']
    assert any(i['code'] == 'FMC_REPORT_CONTROL_INVALID' and i['severity'] == 'block' for i in result['issues'])


def test_duplicate_and_missing_report_controls_do_not_certify_report():
    normalized = inspect_source(original())
    duplicate = controls()[:1] * 2
    result = reconcile_report(normalized, duplicate)
    assert any(i['code'] == 'FMC_REPORT_CONTROL_INVALID' for i in result['issues'])
    result = reconcile_report(normalized, [])
    assert not result['checks'] and result['report_certification'] == 'blocked'
