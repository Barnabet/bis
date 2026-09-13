"""Native public-report boundaries independent of publisher regression answers."""
import copy
from decimal import Decimal

import pytest

from foundry.composition import validate_proposal
from foundry.errors import DomainError
from foundry.public_reports import prepare, compare_snapshot, configure_program, inspect_upload
from foundry.storage import digest


def inputs():
    metrics = ['ons.J5EC', 'ons.J5EG', 'ons.J5EB', 'ons.J5EH', 'ons.KP8P', 'ons.KP8H', 'ons.MS6Y']
    normalized = {'family': 'ons_retail', 'source_digest': digest(b'independent-test-source'),
                  'period': '2025-06', 'vintage': '2025-07-25', 'issues': [],
                  'observations': [{'metric_id': metric, 'period': '2025-06', 'value': str(Decimal(i) / 10),
                                    'status': 'known', 'unit': 'percent_points', 'display_decimals': 1,
                                    'locator': f'csv:row=11;column={i+2}', 'definition': 'Independent test measure'}
                                   for i, metric in enumerate(metrics)]}
    period = {'label': 'June', 'start': '2025-06-01', 'end_exclusive': '2025-07-01',
              'comparison': {'start': '2025-05-01', 'end_exclusive': '2025-06-01'},
              'timezone': 'UTC', 'as_of': '2025-07-25T12:00:00Z'}
    asset = {'id': 'independent_source', 'digest': normalized['source_digest'], 'filename': 'values.csv'}
    return normalized, period, asset


def test_native_facts_keep_scale_identity_views_and_review():
    normalized, period, asset = inputs()
    snapshot = prepare(normalized, period, asset, family='ons_retail')
    assert snapshot.facts['ons.J5EG'].display == '0.1%'
    assert snapshot.facts['ons.J5EG'].value == '0.1'
    assert snapshot.facts['ons.J5EG'].sources[0].artifact_sha256 == asset['digest']
    assert snapshot.status == 'review_required'
    assert len(snapshot.views) == 3
    assert all(set(v.coverage.required_node_ids) == {'summary', 'commentary', 'headline_table', 'headline_chart'} for v in snapshot.views)
    assert snapshot.datasets['headlines'].columns[1].type == 'fact'


@pytest.mark.parametrize('change,code', [
    ('wrong_month', 'SOURCE_PERIOD_MISMATCH'), ('wrong_grain', 'PERIOD_GRAIN_MISMATCH'),
    ('wrong_comparison', 'PERIOD_GRAIN_MISMATCH'), ('early_cutoff', 'SOURCE_VINTAGE_MISMATCH'), ('impossible_release', 'SOURCE_VINTAGE_MISMATCH'),
    ('wrong_digest', 'SOURCE_INTEGRITY'), ('wrong_family', 'SOURCE_INTEGRITY'),
    ('missing', 'REQUIRED_OBSERVATION_MISSING'), ('withheld', 'REQUIRED_OBSERVATION_MISSING'),
    ('unit', 'UNIT_MISMATCH'), ('conflict', 'SOURCE_RECONCILIATION_REQUIRED'),
    ('duplicate', 'SOURCE_AMBIGUOUS'), ('policy', 'POLICY_INVALID'),
])
def test_invalid_public_bindings_fail_closed(change, code):
    data, period, asset = inputs()
    policy = None
    if change == 'wrong_month': data['period'] = '2025-05'
    if change == 'wrong_grain': period['start'] = '2025-06-02'
    if change == 'wrong_comparison': period['comparison']['start'] = '2024-06-01'
    if change == 'early_cutoff': period['as_of'] = '2025-07-24T23:59:59Z'
    if change == 'impossible_release': data['vintage'] = '2025-05-17'
    if change == 'wrong_digest': data['source_digest'] = digest(b'other')
    if change == 'wrong_family': data['family'] = 'census_marts'
    if change in {'missing', 'withheld'}: data['observations'][0].update(value=None, status=change)
    if change == 'unit': data['observations'][0]['unit'] = 'GBP'
    if change == 'conflict': data['issues'].append({'severity': 'block', 'code': 'CONFLICT'})
    if change == 'duplicate': data['observations'].append(copy.deepcopy(data['observations'][0]))
    if change == 'policy': policy = {'selection': 'invented_policy'}
    with pytest.raises(DomainError) as error:
        prepare(data, period, asset, family='ons_retail', reporting_policy=policy)
    assert error.value.code == code


def test_independent_comparer_checks_every_headline_units_and_vintage():
    data, period, asset = inputs()
    snapshot = prepare(data, period, asset, family='ons_retail')
    observations = copy.deepcopy(data['observations'])
    target = {'asset_id': 'target', 'vintage': data['vintage'], 'observations': observations}
    assert compare_snapshot(snapshot, target)['passed']
    for field, value in [('value', '9.9'), ('unit', 'ratio'), ('period', '2025-05')]:
        altered = copy.deepcopy(target)
        altered['observations'][0][field] = value
        assert not compare_snapshot(snapshot, altered)['passed']
    target['observations'].pop()
    assert not compare_snapshot(snapshot, target)['passed']


@pytest.mark.parametrize('metric,value', [('ons.MS6Y', '-0.1'), ('ons.MS6Y', '100.1'), ('ons.J5EC', '-100.1')])
def test_public_measure_domain_is_enforced(metric, value):
    data, period, asset = inputs()
    next(o for o in data['observations'] if o['metric_id'] == metric)['value'] = value
    with pytest.raises(DomainError) as error:
        prepare(data, period, asset, family='ons_retail')
    assert error.value.code == 'PUBLIC_VALUE_INVALID'


def test_composition_uses_registered_public_required_facts():
    snapshot = prepare(*inputs(), family='ons_retail')
    output = {'paragraphs': [{'template': 'The supplied release records monthly volume movement of {{ons.J5EC}} and rolling movement of {{ons.J5EG}}. These published figures remain subject to review.', 'evidence_refs': []}]}
    result = validate_proposal(snapshot, [], output)
    assert not any(f['severity'] == 'block' for f in result['findings'])
    assert any(f['code'] == 'COMPOSITION_REVIEW_REQUIRED' for f in result['findings'])
    output['paragraphs'][0]['template'] = 'The supplied release records a monthly movement of {{ons.J5EC}}. These figures remain subject to review.'
    assert any(f['code'] == 'REQUIRED_FACT_MISSING' for f in validate_proposal(snapshot, [], output)['findings'])


def test_registered_scope_is_digest_covered_and_unknown_families_rejected():
    program = {}
    configure_program(program, 'ons_retail')
    assert program['policy']['adapter'] == 'ons_retail'
    assert program['input_contract']['role'] == 'public_source:ons_retail'
    assert not any(c['kind'] == 'pivot' for c in program['coverage'])
    with pytest.raises(DomainError, match='registered'):
        configure_program({}, 'unknown')
    with pytest.raises(DomainError):
        inspect_upload(b'wrong', 'file.xlsx', 'ons_retail')


def test_public_lifecycle_requires_examples_coverage_evaluation_and_review(tmp_path):
    # The fixture helper is literal independent June report/source material.
    from test_public_ons import source_rows, encode, report_asset
    from io import BytesIO
    import textwrap
    from reportlab.pdfgen import canvas
    from foundry.service import Service
    from foundry.storage import Store
    from foundry.jobs import Worker
    service = Service(Store(tmp_path / 'workspace'))
    worker = Worker(service)
    created = service.create_type('Public test', family='ons_retail')
    program = created['program']
    with pytest.raises(DomainError) as error:
        service.publish(program['id'], program['digest'])
    assert error.value.code == 'POLICY_UNRESOLVED'
    empty = service.evaluate(program['id'], program['digest'])
    assert not empty['evaluation']['passed']
    source = service.upload(encode(source_rows()), 'ons.csv', public_family='ons_retail')
    output = BytesIO(); pdf = canvas.Canvas(output)
    for region in report_asset()['profile']['regions']:
        y = 800
        for line in textwrap.wrap(region['text'], 100):
            pdf.drawString(40, y, line); y -= 14
        pdf.showPage()
    pdf.save()
    target = service.upload(output.getvalue(), 'historical.pdf', public_family='ons_retail')
    period = inputs()[1]
    example = service.add_example(program['report_type_id'], target['id'], [source['id']], period, 'authoring')
    request = service.request_learning(program['id'], program['digest'], 'Headlines only', 'deterministic', 'learning')
    assert worker.run_one()
    assert service.store.job(request['id'])['status'] == 'completed'
    program = service.store.get('program', program['id'])
    assert program['learning']['hypotheses'][0]['supported']
    assert all(d['resolution'] is None for d in program['decisions'])
    for decision in program['decisions']:
        program = service.resolve(program['id'], decision['id'], decision['alternatives'][0]['value'], program['digest'])
    unresolved = service.evaluate(program['id'], program['digest'])
    assert not unresolved['evaluation']['passed']
    with pytest.raises(DomainError) as error:
        service.publish(program['id'], program['digest'])
    assert error.value.code == 'EVALUATION_REQUIRED'
    for region in program['learning']['coverage']:
        if region['status'] != 'mapped':
            program = service.review_coverage(program['id'], program['digest'], region['id'], 'out_of_scope', 'Explicit fixture scope: registered headline numbers only; prose and layout remain unverified.')
    program = service.evaluate(program['id'], program['digest'])
    assert program['evaluation']['passed'], program['evaluation']
    program = service.publish(program['id'], program['digest'], actor='test_fixture_review')
    run = service.request_run(program['report_type_id'], source['id'], period, 'run')
    assert worker.run_one()
    finished = service.store.job(run['id'])
    assert finished['status'] == 'completed', finished
    snapshot = service.store.get('snapshot', finished['result']['snapshot_id'])
    assert snapshot['status'] == 'review_required'
    assert snapshot['facts']['ons.J5EC']['value'] == '0.9'
    alias = service.upload(encode(source_rows()), 'alias.csv', public_family='ons_retail')
    with pytest.raises(DomainError) as error:
        service.add_example(program['report_type_id'], target['id'], [alias['id']], period, 'reserved')
    assert error.value.code in {'EXAMPLE_EXISTS', 'CORPUS_OVERLAP'}
    revenue = service.create_type('Revenue default')
    assert revenue['program']['policy']['adapter'] == 'quarterly-revenue-v1'
    with pytest.raises(DomainError):
        service.add_example(revenue['program']['report_type_id'], target['id'], [source['id']], period, 'authoring')
