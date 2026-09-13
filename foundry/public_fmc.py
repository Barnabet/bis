"""Fail-closed FMC freight admission and independently supplied reconciliation.

This reads static annual workbooks and selects one quarter. It does not OCR
image reports, infer their totals, resolve external resources, or certify a
report. Published report observations must cross a separate explicit boundary.
"""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
import hashlib
import re
import unicodedata

from .errors import DomainError
from .public_census import extract_static_xlsx

FAMILY = 'fmc_freight'
TABLES = {'US Ports': 'Port Name', 'Ocean Carriers': 'Carrier Name'}
METRICS = [
    ('laden_exports', 'Laden Exports', 'containers_as_published'),
    ('empty_exports', 'Empty Exports', 'containers_as_published'),
    ('laden_imports', 'Laden Imports', 'containers_as_published'),
    ('empty_imports', 'Empty Imports', 'containers_as_published'),
    ('export_tonnage', 'Export Tonnage', 'tonnage_as_published'),
    ('import_tonnage', 'Import Tonnage', 'tonnage_as_published'),
]
UNITS = {metric: unit for metric, _, unit in METRICS} | {
    'container_total': 'containers_as_published', 'tonnage_total': 'tonnage_as_published'}


def _issue(code, message, **details):
    return {'code': code, 'severity': 'block', 'message': message, **details}


def _identity(label):
    return ' '.join(unicodedata.normalize('NFKC', label).split()).casefold()


def _integer(value):
    if value is None or isinstance(value, bool):
        raise ValueError('A known nonnegative integer is required.')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('A known nonnegative integer is required.') from exc
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError('A known nonnegative integer is required.')
    return number


def _total(values):
    return str(sum((Decimal(v) for v in values), Decimal(0))) if all(v is not None for v in values) else None


def inspect_source(data: bytes, period='2025-Q1') -> dict:
    """Validate all annual rows, then expose only the requested quarter's values."""
    if not isinstance(period, str) or not re.fullmatch(r'\d{4}-Q[1-4]', period):
        raise DomainError('FMC_PERIOD_INVALID', 'Select an explicit YYYY-Q1 through YYYY-Q4 period.')
    static = extract_static_xlsx(data)
    if [s['name'] for s in static['sheets']] != ['Info', 'US Ports', 'Ocean Carriers']:
        raise DomainError('FMC_SOURCE_DRIFT', 'The published Info, US Ports and Ocean Carriers worksheets are required.')
    cells = {(c['sheet'], c['address']): c for c in static['cells']}
    def cell(sheet, address):
        return cells.get((sheet, address), {'raw_value': None, 'value': None, 'status': 'missing',
                                           'formula': None, 'locator': f'sheet={sheet};cell={address}'})
    def raw(sheet, address):
        return cell(sheet, address)['raw_value']

    title = str(raw('Info', 'A1'))
    if 'Federal Maritime' not in title or 'Containerized Freight Statistics' not in title:
        raise DomainError('FMC_SOURCE_DRIFT', 'The workbook does not identify the FMC containerized freight series.')
    scope = ' '.join(str(raw('Info', 'A2')).split())
    match = re.fullmatch(r'Aggregated Data for Quarter 1, 2, 3, & 4 of Calendar Year (\d{4})', scope)
    if not match:
        raise DomainError('FMC_SOURCE_DRIFT', 'The workbook must explicitly declare its annual four-quarter scope.')
    year = match[1]
    if period[:4] != year:
        raise DomainError('FMC_PERIOD_MISMATCH', 'The requested quarter does not belong to the workbook calendar year.')
    if raw('Info', 'A3') != 'Cargo Metrics by Laden/Empty Containers, Import/Export, & Tonnage':
        raise DomainError('FMC_SOURCE_DRIFT', 'Cargo metric labels or their published units changed.')
    selected, totals, observations, issues = {}, {}, [], []
    source_counts, selected_counts = {}, {}
    valid_periods = {f'{year}-Q{q}' for q in range(1, 5)}
    for sheet in static['sheets'][1:]:
        name = sheet['name']
        expected_headers = ['Quarter, Year', TABLES[name], *[label for _, label, _ in METRICS]]
        actual_headers = [raw(name, chr(65 + index) + '1') for index in range(sheet['columns'])]
        if actual_headers != expected_headers:
            raise DomainError('FMC_SOURCE_DRIFT', 'Freight headers must preserve quarter, entity and six cargo measures.',
                              details={'sheet': name, 'expected': expected_headers, 'actual': actual_headers})
        selected[name], seen, seen_periods = [], set(), set()
        source_counts[name] = sheet['rows'] - 1
        for row in range(2, sheet['rows'] + 1):
            row_locator = f'sheet={name};row={row}'
            quarter = raw(name, f'A{row}')
            quarter_match = re.fullmatch(r'Q([1-4]) (\d{4})', str(quarter))
            row_period = f'{quarter_match[2]}-Q{quarter_match[1]}' if quarter_match else None
            if row_period not in valid_periods:
                issues.append(_issue('FMC_ROW_PERIOD_INVALID', 'The row quarter/year is invalid or outside the declared workbook year.',
                                     locator=f'sheet={name};cell=A{row}', actual=quarter))
            else:
                seen_periods.add(row_period)
            entity = raw(name, f'B{row}')
            entity_key = _identity(entity) if isinstance(entity, str) else ''
            if not entity_key or entity_key in {'total', 'grand total', 'subtotal'}:
                issues.append(_issue('FMC_ENTITY_INVALID', 'A nonempty individual port or carrier identity is required; total rows are not source records.',
                                     locator=f'sheet={name};cell=B{row}', actual=entity))
            key = (row_period, entity_key)
            if key in seen:
                issues.append(_issue('FMC_DUPLICATE_ENTITY', 'An entity occurs more than once within one quarter and table.',
                                     locator=row_locator, entity=entity, period=row_period))
            seen.add(key)
            values, locators = {}, {}
            for index, (metric, _, _) in enumerate(METRICS, 2):
                source = cell(name, f'{chr(65 + index)}{row}')
                locators[metric] = source['locator']
                try:
                    if source['status'] != 'known' or source['formula'] is not None:
                        raise ValueError('Missing, nonnumeric and formula-dependent counts are not usable.')
                    values[metric] = str(_integer(source['value']))
                except ValueError as exc:
                    values[metric] = None
                    issues.append(_issue('FMC_VALUE_UNAVAILABLE', str(exc), locator=source['locator'],
                                         status=source['status'], raw_value=source['raw_value']))
            values['container_total'] = _total([values[m] for m, _, _ in METRICS[:4]])
            values['tonnage_total'] = _total([values[m] for m, _, _ in METRICS[4:]])
            if row_period == period:
                selected[name].append({'period': row_period, 'table': name, 'entity': entity,
                                       'entity_id': hashlib.sha256(entity_key.encode()).hexdigest()[:20],
                                       'source_row': row, 'locator': row_locator, 'values': values,
                                       'source_locators': locators, 'source_digest': static['source_digest']})
        if seen_periods != valid_periods:
            issues.append(_issue('FMC_PERIOD_INCOMPLETE', 'The annual worksheet does not contain each of its four declared quarters.',
                                 table=name, missing_periods=sorted(valid_periods - seen_periods)))
        selected_counts[name] = len(selected[name])
        if not selected[name]:
            issues.append(_issue('FMC_PERIOD_INCOMPLETE', 'The selected quarter has no records in a required table.', table=name, period=period))
        totals[name] = {}
        for metric, unit in UNITS.items():
            value = _total([r['values'][metric] for r in selected[name]]) if selected[name] else None
            totals[name][metric] = value
            locators = [r['locator'] for r in selected[name]]
            observations.append({'metric_id': 'fmc.' + metric, 'table': name, 'entity': 'Total', 'period': period,
                                 'value': value, 'status': 'known' if value is not None else 'missing',
                                 'unit': unit, 'display_decimals': 0, 'locator': f'sheet={name};quarter={period};aggregation=sum',
                                 'source_locators': locators, 'source_digest': static['source_digest'],
                                 'definition': 'Sum of the disjoint published entity rows in this table and quarter; the two table views must not be added together.'})
    for metric in UNITS:
        ports, carriers = totals['US Ports'][metric], totals['Ocean Carriers'][metric]
        if ports is not None and carriers is not None and Decimal(ports) != Decimal(carriers):
            issues.append(_issue('FMC_CROSS_TABLE_DISCREPANCY', 'Port and carrier aggregations do not reconcile; no rounding tolerance is assumed.',
                                 metric_id='fmc.' + metric, period=period, port_sum=ports, carrier_sum=carriers,
                                 difference=str(Decimal(ports) - Decimal(carriers))))
    issues.extend([
        _issue('FMC_REPORT_OBSERVATIONS_REQUIRED', 'The PDF tables are images. Static workbook totals alone do not certify their printed report values; independent located report observations are required.'),
        _issue('FMC_TONNAGE_UNIT_UNRESOLVED', 'The workbook declares tonnage but not the ton standard. Metric or short tons must not be inferred.'),
    ])
    return {'family': FAMILY, 'parser_version': 1, 'source_digest': static['source_digest'], 'period': period,
            'vintage': None, 'observations': observations, 'rows': selected, 'totals': totals, 'issues': issues,
            'metadata': {'source_calendar_year': year, 'source_row_counts': source_counts, 'selected_row_counts': selected_counts,
                         'source_size_bytes': static['byte_count'], 'all_source_rows_checked': True,
                         'all_source_rows_valid': not any(i['code'] in {'FMC_ROW_PERIOD_INVALID', 'FMC_ENTITY_INVALID',
                             'FMC_DUPLICATE_ENTITY', 'FMC_VALUE_UNAVAILABLE', 'FMC_PERIOD_INCOMPLETE'} for i in issues),
                         'source_periods_declared': sorted(valid_periods),
                         'units': {'container_columns': 'containers_as_published', 'tonnage_columns': 'tonnage_as_published'},
                         'unit_scope': 'Official reporting scope uses TEUs, but the workbook labels the measures as containers. The precise ton standard is not supplied.',
                         'data_level': 'quarterly_port_and_carrier_aggregates_not_individual_shipments',
                         'external_relationships': static['external_relationships'],
                         'formula_evaluation': 'never', 'external_resolution': 'never',
                         'report_certification': 'blocked', 'report_ocr_performed': False,
                         'vintage_limitation': 'No publication date is asserted from workbook modification metadata.'}}


def reconcile_report(normalized: dict, report_observations: list[dict]) -> dict:
    """Compare supplied report evidence without promoting it to runtime OCR truth.

    Each observation supplies table, entity (``Total`` or an exact source name),
    metric_id, period, value, unit, locator, source_digest and extraction method.
    This function never derives the expected report value from source totals.
    Source/OCR/unit scope blocks remain even when supplied controls match.
    """
    if normalized.get('family') != FAMILY:
        raise DomainError('FMC_FAMILY_MISMATCH', 'Reconciliation requires normalized FMC freight data.')
    result = {'checks': [], 'issues': copy.deepcopy(normalized.get('issues', [])), 'reconciliation_findings': [],
              'period': normalized['period'], 'source_digest': normalized['source_digest'],
              'report_certification': 'blocked', 'report_ocr_performed': False,
              'evidence_scope': 'independently_supplied_report_controls_only'}
    if not isinstance(report_observations, list) or not report_observations:
        result['issues'].append(_issue('FMC_REPORT_CONTROLS_MISSING', 'Supply independently located report observations.'))
        return result
    seen, printed_groups = set(), {}
    for observation in report_observations:
        try:
            table, entity, metric_id = observation['table'], observation['entity'], observation['metric_id']
            if not all(isinstance(v, str) for v in (table, entity, metric_id)):
                raise ValueError('Table, entity and metric identities must be strings.')
            metric = metric_id.removeprefix('fmc.')
            if table not in TABLES or metric_id != 'fmc.' + metric or metric not in UNITS:
                raise ValueError('Unknown table or metric identity.')
            if observation['period'] != normalized['period']:
                raise ValueError('The report observation period differs from the selected source quarter.')
            if observation['unit'] != UNITS[metric]:
                raise ValueError('The report observation unit differs from the explicit published measure.')
            if not isinstance(observation.get('locator'), str) or not observation['locator'].strip():
                raise ValueError('A physical report locator is required.')
            if not re.fullmatch(r'[0-9a-f]{64}', str(observation.get('source_digest', ''))):
                raise ValueError('The original report digest is required.')
            if not isinstance(observation.get('method'), str) or not observation['method'].strip():
                raise ValueError('The independent report extraction method must be declared.')
            key = (table, entity, metric)
            if key in seen:
                raise ValueError('Duplicate report control identity.')
            seen.add(key)
            printed = _integer(observation['value'])
            if entity == 'Total':
                source = normalized['totals'][table][metric]
                locator = f'sheet={table};quarter={normalized["period"]};aggregation=sum'
            else:
                rows = [r for r in normalized['rows'][table] if r['entity'] == entity]
                if len(rows) != 1:
                    raise ValueError('The report entity is absent or ambiguous in this selected quarter.')
                source = rows[0]['values'][metric]
                locator = rows[0]['source_locators'].get(metric, rows[0]['locator'])
            actual = _integer(source)
            check = {'metric_id': metric_id, 'table': table, 'entity': entity, 'period': normalized['period'],
                     'unit': UNITS[metric], 'source_value': str(actual), 'report_value': str(printed),
                     'source_locator': locator, 'report_locator': observation['locator'],
                     'report_digest': observation['source_digest'], 'report_method': observation['method'],
                     'difference': str(actual - printed), 'passed': actual == printed}
            result['checks'].append(check)
            if actual != printed:
                finding = _issue('FMC_REPORT_DISCREPANCY', 'The source aggregation and printed report control differ; no tolerance is assumed.', **check)
                result['issues'].append(finding)
                result['reconciliation_findings'].append(finding)
            printed_groups.setdefault((table, entity, observation['source_digest']), {})[metric] = observation
        except (ValueError, KeyError, TypeError) as exc:
            result['issues'].append(_issue('FMC_REPORT_CONTROL_INVALID', str(exc), observation=copy.deepcopy(observation)))
    for (table, entity, report_digest), group in printed_groups.items():
        for parts, total in [([m for m, _, _ in METRICS[:4]], 'container_total'),
                             ([m for m, _, _ in METRICS[4:]], 'tonnage_total')]:
            if all(metric in group for metric in [*parts, total]):
                categories = sum((_integer(group[m]['value']) for m in parts), Decimal(0))
                grand = _integer(group[total]['value'])
                if categories != grand:
                    finding = _issue('FMC_REPORT_INTERNAL_DISCREPANCY', 'Printed category values do not sum to the printed total.',
                                     table=table, entity=entity, period=normalized['period'], metric_id='fmc.' + total,
                                     report_digest=report_digest, category_sum=str(categories), printed_total=str(grand),
                                     difference=str(categories - grand), locators=[group[m]['locator'] for m in [*parts, total]])
                    result['issues'].append(finding)
                    result['reconciliation_findings'].append(finding)
    return result
