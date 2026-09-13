"""Registered public-statistics adapters; no benchmark answers or model calculations.

These profiles reconstruct explicitly scoped headline facts. The original report's
remaining regions stay in the coverage ledger and require a separate scope review.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import tempfile

from .contracts import Period, Snapshot
from .errors import DomainError
from .storage import digest, now, uid

FAMILIES = {
    'census_marts': {
        'name': 'Census monthly retail headlines', 'formats': ['xlsx'],
        'metrics': [
            ('census.sales_headline_usd_million', 'Retail and food services sales'),
            ('census.month_on_month_pct', 'Sales: monthly change'),
            ('census.year_on_year_pct', 'Sales: annual change'),
            ('census.rolling_three_month_year_on_year_pct', 'Sales: rolling annual change'),
            ('census.retail_month_on_month_pct', 'Retail: monthly change'),
            ('census.retail_year_on_year_pct', 'Retail: annual change'),
            ('census.nonstore_year_on_year_pct', 'Nonstore: annual change'),
            ('census.food_services_year_on_year_pct', 'Food services: annual change'),
        ],
        'required': ['census.sales_headline_usd_million', 'census.month_on_month_pct'],
        'scope': 'Seasonally adjusted published retail headlines in USD millions and displayed percentage changes. Overlapping categories are never summed. Workbook revisions stay bound to their release vintage.',
    },
    'ons_retail': {
        'name': 'ONS monthly retail headlines', 'formats': ['csv'],
        'metrics': [('ons.J5EC', 'Volume: monthly change'), ('ons.J5EG', 'Volume: rolling change'),
                    ('ons.J5EB', 'Volume: annual change'), ('ons.J5EH', 'Volume: rolling annual change'),
                    ('ons.KP8P', 'Online value: monthly change'), ('ons.KP8H', 'Online value: annual change'),
                    ('ons.MS6Y', 'Online share of retail')],
        'required': ['ons.J5EC', 'ons.J5EG'],
        'scope': 'Seven registered CDID headline series, using monthly observations from one release vintage. Percentage figures retain their published scale. Index-level rebasing and retailer anecdotes are outside this profile.',
    },
}
SELECTION = {'value': 'published_vintage_headlines', 'label': 'Published headline series from the bound vintage'}


def family_of(program):
    adapter = program.get('policy', {}).get('adapter', 'quarterly-revenue-v1')
    if adapter == 'quarterly-revenue-v1':
        return None
    if adapter not in FAMILIES:
        raise DomainError('ADAPTER_UNSUPPORTED', 'The program requires an unregistered reporting adapter.')
    return adapter


def config(family):
    if family not in FAMILIES:
        raise DomainError('ADAPTER_UNSUPPORTED', 'Choose a registered public reporting family.')
    return FAMILIES[family]


def parser(family):
    config(family)
    if family == 'census_marts':
        from . import public_census
        return public_census
    from . import public_ons
    return public_ons


def configure_program(program, family):
    cfg = config(family)
    program.update(
        authoring_mode='registered_public_headline_profile',
        policy={'adapter': family, 'selection': SELECTION['value'], 'fidelity': 'compatible',
                'scope': cfg['scope'], 'evidence_scope': 'paired_public_reports_scoped_headlines',
                'cutoff': 'release_date_not_after_as_of_date', 'cutoff_precision': 'calendar_day_intraday_unverified',
                'prose': 'fact_bound_review_required'},
        input_contract={'role': f'public_source:{family}', 'formats': cfg['formats'], 'columns': [],
                        'notes': cfg['scope'], 'period_grain': 'month', 'original_bytes_required': True},
        coverage=[{'id': id, 'label': label, 'kind': kind, 'status': 'implemented'} for id, label, kind in [
            ('summary', 'Located headline facts', 'computed'), ('commentary', 'Reviewed editorial context', 'literal'),
            ('headline_table', 'Headline values with exact units', 'table'), ('headline_chart', 'Published percentage figures', 'chart')]],
        decisions=[{'id': id, 'question': question, 'alternatives': [alternative], 'resolution': None}
                   for id, question, alternative in [
            ('selection', 'Use the registered headline series from the bound release vintage?',
             {**SELECTION, 'consequence': cfg['scope']}),
            ('scope', 'Approve headline reconstruction and review the remaining historical regions separately?',
             {'value': 'headlines_only_reviewed', 'label': 'Approve the headline scope',
              'consequence': 'Full report prose, uncertainty, appendix tables and exact layout are not reconstructed. Unmapped regions remain in the coverage ledger.'}),
            ('template', 'Approve compatible document, workbook and presentation views?',
             {'value': 'compatible_reviewed', 'label': 'Approve compatible views',
              'consequence': 'Native artifacts represent the scoped headline draft; they do not copy the publisher’s layout.'})]],
        limitations=[cfg['scope'], 'A registered field mapping is investigated, not arbitrary report or code synthesis.',
                     'Public examples are exposed evidence; later-period checks are not untouched statistical holdouts.',
                     'Every generated report requires review. Unmapped historical regions and exact visual fidelity remain separate.',
                     'Release dates are checked at calendar-day precision; intraday publication availability is not verified.'])


def inspect_upload(data, filename, family):
    from .ingestion import MAX_BYTES, MIME, inspect_asset
    import unicodedata
    cfg = config(family)
    if not data or len(data) > MAX_BYTES:
        raise DomainError('UPLOAD_LIMIT', 'Supply a nonempty file no larger than 20 MB.')
    filename = unicodedata.normalize('NFC', Path(filename.replace('\\', '/')).name)[:200]
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext == 'pdf':
        asset = inspect_asset(data, filename, pdf_page_limit=120)
        asset['profile']['public_family'] = family
        asset['profile']['warnings'].append('Public headline inspection preserves all pages; mapped numbers do not establish complete report reconstruction.')
        return asset
    if ext not in cfg['formats']:
        raise DomainError('INPUT_DRIFT', 'This file format does not match the selected public reporting family.')
    normalized = parser(family).inspect_source(data)
    blocks = [issue for issue in normalized.get('issues', []) if issue.get('severity') == 'block']
    profile = {'format': ext, 'public_family': family, 'parser': f'{family}/static-v1',
               'eligible_roles': [f'public_source:{family}'], 'row_count': len(normalized['observations']),
               'columns': [], 'regions': [], 'period': normalized['period'], 'vintage': normalized['vintage'],
               'normalized_digest': digest(normalized), 'metadata': normalized.get('metadata', {}),
               'warnings': [cfg['scope'], 'Original source bytes retained; no formulas or external links are evaluated.']
                           + [f"{issue['code']}: {issue['message']}" for issue in blocks],
               'issues': normalized.get('issues', [])}
    return {'filename': filename, 'media_type': MIME[ext], 'size': len(data), 'profile': profile, 'status': 'blocked' if blocks else 'usable'}


def source_data(data, asset, family):
    if f'public_source:{family}' not in asset['profile'].get('eligible_roles', []):
        raise DomainError('INPUT_DRIFT', 'Bind a source inspected for this exact reporting family.')
    if digest(data) != asset['digest']:
        raise DomainError('SOURCE_INTEGRITY', 'The original source bytes differ from their recorded identity.', 409)
    normalized = parser(family).inspect_source(data)
    if digest(normalized) != asset['profile'].get('normalized_digest'):
        raise DomainError('SOURCE_INTERPRETATION_CHANGED', 'Source interpretation changed. Reimport the original with the current adapter.', 409)
    return normalized


def inspect_target(asset, family):
    if 'historical_target' not in asset['profile'].get('eligible_roles', []):
        raise DomainError('EXAMPLE_BINDING_INVALID', 'Use a text-bearing historical PDF target.')
    declared = asset['profile'].get('public_family')
    if declared and declared != family:
        raise DomainError('EXAMPLE_BINDING_INVALID', 'The historical target was inspected for another family.')
    return parser(family).inspect_report(asset)


def _validate_period(normalized, period):
    p = Period.model_validate(period)
    month = p.start.strftime('%Y-%m')
    following = (p.start.replace(day=28) + timedelta(days=4)).replace(day=1)
    previous = (p.start - timedelta(days=1)).replace(day=1)
    if (p.start.day != 1 or p.end_exclusive != following or p.comparison.start != previous
            or p.comparison.end_exclusive != p.start):
        raise DomainError('PERIOD_GRAIN_MISMATCH', 'Use an exact calendar month and the immediately preceding calendar month for this profile.')
    if month != normalized['period']:
        raise DomainError('SOURCE_PERIOD_MISMATCH', 'The requested month differs from the bound source release’s reference month.')
    if (not normalized.get('vintage') or date.fromisoformat(normalized['vintage']) < following
            or date.fromisoformat(normalized['vintage']) > p.as_of.date()):
        raise DomainError('SOURCE_VINTAGE_MISMATCH', 'The source release must follow the reference month and be dated on or before the requested as-of date.')
    return p


def prepare(normalized, period, source_asset, *, family, program=None, report_type_id='public_report', reporting_policy=None, **unused):
    cfg = config(family)
    if normalized.get('family') != family or normalized.get('source_digest') != source_asset['digest']:
        raise DomainError('SOURCE_INTEGRITY', 'The normalized observations are not bound to this source and family.', 409)
    if reporting_policy and reporting_policy.get('selection') != SELECTION['value']:
        raise DomainError('POLICY_INVALID', 'Only the registered vintage headline mapping is implemented.')
    if any(i.get('severity') == 'block' for i in normalized.get('issues', [])):
        raise DomainError('SOURCE_RECONCILIATION_REQUIRED', 'Source findings must be resolved before preparing the report.', 422, normalized['issues'])
    p = _validate_period(normalized, period)
    selected = {}
    for obs in normalized['observations']:
        if obs['period'] == normalized['period']:
            key = obs['metric_id']
            if key in selected:
                raise DomainError('SOURCE_AMBIGUOUS', 'More than one source observation maps to a metric and period.')
            selected[key] = obs
    facts, rows, chart_rows = {}, [], []
    scope = f"Reference month {normalized['period']}; source release {normalized['vintage']}. {cfg['scope']}"
    for fid, label in cfg['metrics']:
        obs = selected.get(fid)
        if obs is None or obs['status'] != 'known' or obs['value'] is None:
            raise DomainError('REQUIRED_OBSERVATION_MISSING', f'The source does not supply a known value for {fid}; suppression and absence are never zero-filled.')
        value = Decimal(obs['value'])
        if not value.is_finite() or obs['unit'] not in {'usd_million', 'percent_points'}:
            raise DomainError('UNIT_MISMATCH', 'Public headline values require finite numbers and explicit supported units.')
        if (obs['unit'] == 'usd_million' and value < 0
                or fid == 'ons.MS6Y' and not 0 <= value <= 100
                or obs['unit'] == 'percent_points' and fid != 'ons.MS6Y' and value < -100):
            raise DomainError('PUBLIC_VALUE_INVALID', 'A published headline is outside its measure’s domain: nonnegative sales, share within zero to one hundred, or a growth rate no lower than minus one hundred.')
        places = obs.get('display_decimals', 1)
        rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        display = f'{rounded:,.{max(0, places)}f}' + ('%' if obs['unit'] == 'percent_points' else ' USD million')
        locators = obs.get('source_locators') or [obs['locator']]
        if not all(isinstance(loc, str) and loc for loc in locators):
            locators = [obs['locator']]
        facts[fid] = {'id': fid, 'kind': 'number', 'value': obs['value'], 'unit': obs['unit'], 'display': display,
                      'status': obs['status'], 'definition': obs.get('definition') or label, 'scope': scope,
                      'sources': [{'asset_id': source_asset['id'], 'artifact_sha256': source_asset['digest'], 'locator': loc} for loc in locators]}
        rows.append({'metric': label, 'value': fid})
        if obs['unit'] == 'percent_points':
            chart_rows.append({'metric': label, 'value': obs['value']})
    period_locator = ('sheet=Table 1.;cells=J7:J8' if family == 'census_marts'
                      else selected['ons.J5EC']['locator'].split(';column=')[0] + ';column=1')
    vintage_locator = ('sheet=Table 1.;cell=A85|sheet=Table 2.;cell=A59|sheet=Table 3.;cell=A42'
                       if family == 'census_marts' else 'csv:row=5;columns=all series;metadata=Release Date')
    for fid, value, unit, label, locator in [
        ('source.reference_month', normalized['period'], 'month', 'Reference month', period_locator),
        ('source.release_date', normalized['vintage'], 'date', 'Release date', vintage_locator)]:
        facts[fid] = {'id': fid, 'kind': 'text', 'value': value, 'unit': unit, 'display': value,
                      'status': 'known', 'definition': label + ' from the bound original source.', 'scope': scope,
                      'sources': [{'asset_id': source_asset['id'], 'artifact_sha256': source_asset['digest'],
                                   'locator': locator}]}
    summary = [{'type': 'text', 'text': 'Reference month '}, {'type': 'fact', 'fact_id': 'source.reference_month'},
               {'type': 'text', 'text': '; release '}, {'type': 'fact', 'fact_id': 'source.release_date'}, {'type': 'text', 'text': '. '}]
    for fid, label in cfg['metrics'][:2]:
        summary.extend([{'type': 'text', 'text': label + ': '}, {'type': 'fact', 'fact_id': fid}, {'type': 'text', 'text': '. '}])
    summary.append({'type': 'text', 'text': 'Headline draft only. Uncertainty, appendix tables, explanations and original layout are excluded.'})
    nodes = [
        {'id': 'summary', 'kind': 'rich_text', 'title': 'Published headlines', 'runs': summary, 'mode': 'computed', 'editable': False},
        {'id': 'commentary', 'kind': 'rich_text', 'title': 'Editorial context', 'runs': [{'type': 'text', 'text': 'This draft presents the registered headline figures from the supplied release. Review the source vintage, scope and wording before acceptance.'}], 'mode': 'literal', 'editable': True},
        {'id': 'headline_table', 'kind': 'table', 'title': 'Headline measures', 'dataset_id': 'headlines'},
        {'id': 'headline_chart', 'kind': 'chart', 'title': 'Published percentage figures', 'dataset_id': 'headline_rates',
         'chart_type': 'bar', 'category_column': 'metric', 'series': [{'column_id': 'value', 'label': 'Published figure'}], 'axis_unit': 'Published figure (%)'},
    ]
    leaf = [n['id'] for n in nodes]
    nodes.insert(0, {'id': 'root', 'kind': 'section', 'title': cfg['name'], 'children': leaf})
    recipes = {'flow': {'page_size': 'A4', 'margin_mm': 18, 'font': 'Calibri', 'body_pt': 10, 'table_overflow': 'repeat_headers'},
               'grid': {'sheets': [{'name': 'Overview', 'node_ids': leaf}], 'placement': 'after_previous_region'},
               'canvas': {'aspect_ratio': '16:9', 'overflow': 'block', 'slides': [
                   {'title': 'Published headlines', 'node_ids': leaf[:3]}, {'title': 'Published percentage figures', 'node_ids': [leaf[3]]}]}}
    views = [{'id': id, 'family': kind, 'title': label, 'node_ids': leaf,
              'coverage': {'scope': 'complete', 'required_node_ids': leaf, 'omitted_node_ids': []}, 'recipe': recipes[kind]}
             for id, kind, label in [('document', 'flow', 'Document'), ('workbook', 'grid', 'Workbook'), ('presentation', 'canvas', 'Presentation')]]
    return Snapshot.model_validate({'schema_version': '1.0', 'id': uid('snapshot'), 'revision': 1, 'parent_id': None,
        'title': f"{cfg['name']} · {normalized['period']}", 'report_type_id': report_type_id,
        'program': program or {'id': 'public_reference', 'version': '1.0.0', 'digest': digest({'family': family, 'mapping': cfg})},
        'period': p.model_dump(mode='json'), 'source_snapshot_digest': digest({'source': source_asset['digest'], 'normalized': digest(normalized), 'period': normalized['period']}),
        'source_assets': [source_asset], 'facts': facts,
        'datasets': {'headlines': {'id': 'headlines', 'columns': [{'id': 'metric', 'label': 'Measure', 'type': 'text'}, {'id': 'value', 'label': 'Published value', 'type': 'fact'}], 'rows': rows},
                     'headline_rates': {'id': 'headline_rates', 'columns': [{'id': 'metric', 'label': 'Measure', 'type': 'text'}, {'id': 'value', 'label': 'Published figure (%)', 'type': 'decimal', 'unit': 'percent_points'}], 'rows': chart_rows}},
        'nodes': nodes, 'views': views, 'findings': [{'id': 'public.scope_review', 'phase': 'preparation', 'severity': 'review',
            'code': 'PUBLIC_SCOPE_REVIEW_REQUIRED', 'component_id': 'summary', 'evidence_refs': [],
            'message': 'Review the headline scope and source vintage. Uncertainty, appendices, explanations and original layout are not reconstructed.', 'repair_class': 'human_review'}],
        'metadata': {'adapter': family, 'reporting_policy': reporting_policy or {'selection': SELECTION['value']},
                     'source_vintage': normalized['vintage'], 'normalized_source_digest': digest(normalized),
                     'cutoff_precision': 'calendar_day_intraday_unverified',
                     'scope': cfg['scope'], 'source_metadata': normalized.get('metadata', {}),
                     'composition': 'Deterministic located facts; optional model commentary remains subject to review.'},
        'status': 'review_required', 'created_at': now()})


def compare_snapshot(snapshot, inspection):
    data = snapshot.model_dump(mode='json') if hasattr(snapshot, 'model_dump') else snapshot
    checks = []
    for index, obs in enumerate(inspection.get('observations', [])):
        fid = obs['metric_id']
        # Source-level report appendix observations outside the declared headline
        # contract stay visible but cannot be claimed as reconstructed.
        if fid not in data['facts']:
            continue
        actual = data['facts'][fid]
        passed = (actual['unit'] == obs['unit'] and actual['status'] == obs.get('status', 'known')
                  and obs['period'] == data['period']['start'][:7])
        try:
            q = Decimal(1).scaleb(-obs.get('display_decimals', 1))
            passed = passed and Decimal(actual['value']).quantize(q, rounding=ROUND_HALF_UP) == Decimal(obs['value']).quantize(q, rounding=ROUND_HALF_UP)
        except (ArithmeticError, TypeError, ValueError):
            passed = False
        checks.append({'observation_id': obs.get('id', str(index)), 'fact_id': fid, 'expected': obs['value'],
                       'actual': actual['value'], 'passed': bool(passed), 'locator': obs['locator'], 'method': 'independent_report_text'})
    observed = {c['fact_id'] for c in checks}
    expected_metrics = {metric for metric, _ in config(data['metadata']['adapter'])['metrics']}
    missing = sorted(expected_metrics - observed)
    checks.append({'passed': not missing, 'fact_id': None, 'expected': 'Independent observations for every declared headline',
                   'actual': missing, 'locator': f"asset:{inspection.get('asset_id', 'unknown')}", 'method': 'headline_coverage'})
    issues = [i for i in inspection.get('issues', []) if i.get('severity') == 'block']
    if issues:
        checks.append({'passed': False, 'detail': 'The target has contradictory or invalid headline observations.', 'issues': issues})
    if inspection.get('vintage') != data['metadata']['source_vintage']:
        checks.append({'passed': False, 'detail': 'Source and report release vintages differ.'})
    return {'passed': bool(observed) and all(c['passed'] for c in checks), 'checks': checks, 'observation_count': len(observed)}


def analyze_examples(cases, family):
    checks, coverage = [], []
    for case in cases:
        if case['corpus_role'] not in {'authoring', 'development'}:
            raise DomainError('RESERVED_EVIDENCE', 'Reserved targets cannot enter authoring.', 403)
        inspection = case['inspection']
        if inspection['asset_digest'] != case['report_asset']['digest']:
            raise DomainError('EXAMPLE_INTEGRITY', 'Historical inspection identity differs from its source.', 409)
        for region in inspection['regions']:
            coverage.append({**copy.deepcopy(region), 'id': f"{case['id']}:{region['id']}", 'region_id': region['id'],
                             'example_id': case['id'], 'reason': region.get('reason', 'Original report region requires a scope decision.')})
        try:
            snapshot = prepare(case['rows'], case['period'], {k: case['source_asset'][k] for k in ('id', 'digest', 'filename')}, family=family)
            compared = compare_snapshot(snapshot, inspection)
            checks.extend({'example_id': case['id'], **c} for c in compared['checks'])
        except DomainError as error:
            checks.append({'example_id': case['id'], 'passed': False, 'detail': str(error), 'code': error.code})
    return {'hypotheses': [{**SELECTION, 'supported': bool(checks) and all(c['passed'] for c in checks), 'checks': checks}],
            'coverage': coverage, 'assumptions': ['Only the registered headline mapping is implemented; model interpretation cannot add new computations.',
                'Every unmapped report region requires explicit review and remains excluded from reconstruction claims.'],
            'limitations': [config(family)['scope'], 'Later public examples are exposed evaluation data, not untouched holdouts.']}


def model_coverage(coverage):
    """Compact the permitted region ledger, retaining identity and unresolved status."""
    return [{k: c.get(k) for k in ('id', 'locator', 'kind', 'status', 'component_id')}
            | {'reason': c.get('reason', '')[:180], 'text_excerpt': c.get('text', '')[:100], 'text_digest': digest(c.get('text', ''))}
            for c in coverage]


def evaluate_program(service, program):
    """Use paired reports as independent oracles, then render the scoped graph."""
    family = family_of(program)
    basis = service._evaluation_basis(program)
    historical = service._evaluate_examples(program)
    checks = list(historical['checks'])
    learning = program.get('learning')
    checks.append({'name': 'Paired public examples required', 'passed': bool(learning and historical['reconstruction_count']),
                   'detail': 'Publication requires independently located report headlines, source vintage checks and explicit coverage review.'})
    if learning:
        from .exporters import export_snapshot
        entry = next((e for e in learning['corpus'] if e['role'] != 'reserved'), None)
        if entry:
            try:
                case = service._case(entry)
                snapshot = prepare(case['rows'], case['period'], {k: case['source_asset'][k] for k in ('id', 'digest', 'filename')}, family=family)
                checks.append({'name': 'Native graph and review gate', 'passed': snapshot.status == 'review_required' and len(snapshot.views) == 3,
                               'detail': 'Typed facts, source locators and complete scoped views validate; report acceptance stays separate.'})
                with tempfile.TemporaryDirectory(prefix='foundry-public-evaluate-') as folder:
                    for fmt in ('docx', 'xlsx', 'pdf', 'pptx'):
                        result = export_snapshot(snapshot.model_dump(mode='json'), fmt, Path(folder) / fmt, policy='compatible')
                        checks.append({'name': f'{fmt.upper()} public export structure', 'passed': Path(result['path']).stat().st_size > 100,
                                       'detail': 'Rendered from the frozen scoped snapshot; exact publisher layout is not certified.'})
            except Exception as exc:
                checks.append({'name': 'Public native export and preparation', 'passed': False, 'detail': str(exc)[:700]})
    evaluation = {'digest': program['digest'], 'basis_digest': basis, 'passed': all(c['passed'] for c in checks),
                  'checks': checks, 'created_at': now(), 'corpus': 'paired_public_headline_examples',
                  'holdout_count': historical['holdout_count'], 'reconstruction_count': historical['reconstruction_count']}
    with service.store.transaction() as db:
        service._installed_code_identity()
        current = service._candidate(program['id'], program['digest'], db)
        if service._evaluation_basis(current) != basis:
            raise DomainError('EVALUATION_BASIS_CHANGED', 'Evidence changed during evaluation.', 409)
        current['evaluation'] = evaluation
        for component in current['coverage']:
            component['status'] = 'verified' if evaluation['passed'] else 'implemented'
        service.store.update('program', current['id'], current, db)
        service.store.audit(current['id'], 'evaluated', evaluation, db)
    return current
