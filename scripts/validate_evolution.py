#!/usr/bin/env python3
"""Run the fixed 3-corpus / 12-future-period reporting experiment.

Use --offline for deterministic pipeline/export checks, or --run-live to add
three genuine CLIProxyAPI learning calls and twelve commentary jobs using exact
claude-opus-5 (27 outbound calls maximum including bounded repair). Expected
reports are frozen before authoring and never registered as learning examples.
Every run creates a separate workspace under ignored output/evolution-validation.
No report is accepted. Failures remain recorded while independent cases continue.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate_live_model import Report, sha256, sanitized, require, cache_replay
from evolution_checks import snapshot_errors, export_errors, read_rows, write_rows

LIMIT = 27
MODEL = 'claude-opus-5'
FORMATS = ('docx', 'xlsx', 'pdf', 'pptx')
REQUIREMENTS = ('Use the historical report/source pairs to propose the supported regional selection policy. '
                'The reporting scope is posted revenue with explicit current and comparison intervals. '
                'Preserve ambiguity and contradictions; leave consequential decisions unresolved.')
OBJECTIVE = ('Write concise factual commentary of at most ninety words using the supplied fact placeholders. '
             'Include revenue.current, revenue.comparison, revenue.change, revenue.growth and driver.region. '
             'Describe the values and selected region without adding explanations or interpretations.')


def now():
    return datetime.now(timezone.utc).isoformat()


class Audit:
    """Real transport observer with a deny-by-default dispatch stage."""
    def __init__(self, report, live, canaries):
        self.report, self.live, self.canaries = report, live, canaries
        self.phase = None
        self.requests = []
        self.network_allowed = True
        self.forbidden_attempts = 0

    @property
    def count(self):
        return len(self.requests)

    def __enter__(self):
        from foundry import model_provider
        self.original = model_provider._responses_transport
        model_provider._responses_transport = self.call
        return self

    def __exit__(self, *_):
        from foundry import model_provider
        model_provider._responses_transport = self.original

    def call(self, body, headers, **options):
        from foundry.errors import DomainError
        if not self.live or not self.phase or not self.network_allowed:
            self.forbidden_attempts += 1
            raise DomainError('UNEXPECTED_MODEL_CALL', 'This experiment stage forbids model dispatch.')
        if self.count >= LIMIT:
            raise DomainError('LIVE_CALL_BUDGET', 'The fixed experiment model-call ceiling was reached.')
        packet = json.loads(body)
        require(packet['model'] == MODEL, 'A different model was requested')
        require(packet['tools'] == [] and packet['store'] is False, 'Unexpected provider request options')
        payload = json.loads(packet['input'][0]['content'][0]['text'])
        if self.phase.endswith('/learning'):
            require(set(payload) == {'requirements', 'hypotheses', 'coverage'}, 'Learning scope changed')
            for canary in self.canaries:
                require(canary.casefold() not in body.decode().casefold(), 'Future region leaked into authoring request')
        else:
            require(set(payload) <= {'objective', 'facts', 'required_fact_ids', 'qualitative_evidence', 'max_words', 'repair_errors'},
                    'Unexpected composition inputs')
            require(payload['qualitative_evidence'] == [], 'Future expected report leaked into composition evidence')
        number = self.count + 1
        entry = {'number': number, 'phase': self.phase, 'started_at': now(), 'model': MODEL,
                 'request_sha256': sha256(body), 'headers_recorded': False, 'status': 'dispatched',
                 'request': self.report.artifact(f'requests/{number:02d}.json', sanitized(packet))}
        self.requests.append({'sha256': sha256(body), 'body': packet})
        self.report.summary['transport_calls'].append(entry)
        self.report.save()
        try:
            raw = self.original(body, headers, **options)
            entry.update(status='response_received', response_sha256=sha256(raw), response_bytes=len(raw))
            return raw
        except Exception as exc:
            entry.update(status='failed', error_code=getattr(exc, 'code', type(exc).__name__))
            raise
        finally:
            entry['finished_at'] = now()
            self.report.save()


def job(service, worker, requested, report, audit, phase=None):
    report.summary["stage"] = f"{requested['kind']}: {phase or requested['id']}"
    report.save()
    before = audit.count
    audit.phase = phase
    try:
        require(worker.run_one(), 'Worker did not claim the fresh job')
    finally:
        audit.phase = None
    result = service.store.job(requested['id'])
    report.summary['jobs'].append({k: result.get(k) for k in ('id', 'kind', 'status', 'stage', 'result', 'error', 'steps')})
    report.save()
    if phase is None:
        require(audit.count == before, 'A deterministic job dispatched a model request')
    require(result['status'] == 'completed', f"{result['kind']} failed: {(result.get('error') or {}).get('code', result['status'])}")
    return result


def receipt(report, item, label):
    report.check(label + ' exact model receipt', item['provider'] == 'cliproxyapi' and
                 item['requested_model'] == item['model'] == MODEL and item['protocol'] == 'responses')


def retry(service, worker, request, original, audit, report, label):
    before = audit.count, len(service.store.list('model_call'))
    again = request()
    report.check(label + ' idempotent completed retry', again['id'] == original['id'] and again['result'] == original['result']
                 and not worker.run_one() and before == (audit.count, len(service.store.list('model_call'))))


def mutations(rows, expected, period):
    yield 'reversed_rows', list(reversed(copy.deepcopy(rows))), copy.deepcopy(expected)
    split = copy.deepcopy(rows)
    index = next(i for i, row in enumerate(split) if row['status'] == 'posted' and period['start'] <= row['date'] < period['end_exclusive'])
    first, second = copy.deepcopy(split[index]), copy.deepcopy(split[index])
    cents = int(Decimal(first['amount']) * 100)
    first.update(transaction_id=first['transaction_id'] + '-split-a', amount=str(Decimal(cents // 2) / 100))
    second.update(transaction_id=second['transaction_id'] + '-split-b', amount=str(Decimal(cents - cents // 2) / 100))
    split[index:index + 1] = [first, second]
    yield 'split_transaction', split, copy.deepcopy(expected)
    scaled, answer = copy.deepcopy(rows), copy.deepcopy(expected)
    for row in scaled:
        if row['status'] == 'posted' and any(window['start'] <= row['date'] < window['end_exclusive'] for window in (period, period['comparison'])):
            row['amount'] = str(Decimal(row['amount']) * 2)
    for section in [answer['totals'], answer['driver'], *answer['regions']]:
        for field in ('current', 'comparison', 'change'):
            if field in section:
                section[field] = str(Decimal(section[field]) * 2)
    yield 'positive_scale', scaled, answer
    perturbed = copy.deepcopy(rows)
    count = 0
    for row in perturbed:
        if row['status'] == 'cancelled' or not any(window['start'] <= row['date'] < window['end_exclusive'] for window in (period, period['comparison'])):
            row['amount'] = '9999999.99'
            count += 1
    require(count > 0, 'The excluded-record mutation needs an excluded source row')
    yield 'excluded_amounts', perturbed, copy.deepcopy(expected)


def run_future(service, worker, report, audit, corpus, case, frozen, program):
    from foundry.ingestion import inspect_asset
    from foundry.observations import inspect_target, compare_snapshot
    from foundry.runtime import render_runs
    label = corpus['id'] + '/' + case['id']
    report.stage('Checking future period ' + label)
    record = {'id': label, 'status': 'running', 'checks': [], 'exports': [], 'mutations': []}
    report.summary['periods'].append(record)
    report.save()
    try:
        period = json.loads((frozen / case['period']).read_text())
        expected = json.loads((frozen / case['expected']).read_text())
        data = (frozen / case['source']).read_bytes()
        rows = read_rows(data)
        source = service.upload(data, case['id'] + '.csv', demo=True)
        request = lambda: service.request_run(program['report_type_id'], source['id'], period, label + '/generation')
        generated = job(service, worker, request(), report, audit)
        snapshot = service.store.get('snapshot', generated['result']['snapshot_id'])
        record.update(source=source['id'], generated=report.artifact(label + '/generated.json', snapshot))
        errors = snapshot_errors(snapshot, expected, corpus['expected_selection'], source, rows)
        record['checks'].append({'check': 'independent_complete_numeric_oracle', 'errors': errors})
        require(not errors, 'Independent next-period oracle failed: ' + ', '.join(errors))
        target_data = (frozen / case['report']).read_bytes()
        target = {'id': 'expected_' + case['id'], 'digest': sha256(target_data), **inspect_asset(target_data, 'expected.docx')}
        inspection = inspect_target(target)
        comparison = compare_snapshot(snapshot, inspection)
        record['expected_report_comparison'] = comparison
        require(not inspection['issues'] and all(r['status'] == 'mapped' for r in inspection['regions']) and comparison['passed'],
                'The independent full expected DOCX did not match the generated report')
        require(snapshot['program'] == {k: program[k] for k in ('id', 'version', 'digest')}, 'Future run changed the learned release')
        require(snapshot['status'] == 'review_required', 'Generated report was automatically accepted')
        retry(service, worker, request, generated, audit, report, label)
        for name, variant_rows, variant_expected in mutations(rows, expected, period):
            variant_asset = service.upload(write_rows(variant_rows), case['id'] + '-' + name + '.csv', demo=True)
            done = job(service, worker, service.request_run(program['report_type_id'], variant_asset['id'], period, label + '/' + name), report, audit)
            changed = service.store.get('snapshot', done['result']['snapshot_id'])
            errors = snapshot_errors(changed, variant_expected, corpus['expected_selection'], variant_asset, variant_rows)
            record['mutations'].append({'name': name, 'snapshot_id': changed['id'], 'errors': errors})
            report.save()
            require(not errors, name + ' changed an independently specified answer or provenance: ' + ', '.join(errors))
        if audit.live:
            report.stage('Live commentary ' + label)
            parent = copy.deepcopy(snapshot)
            request_compose = lambda: service.request_composition(parent['id'], parent['revision'], [], OBJECTIVE, label + '/commentary')
            composed_job = job(service, worker, request_compose(), report, audit, label + '/composition')
            snapshot = service.store.get('snapshot', composed_job['result']['snapshot_id'])
            composition = snapshot['metadata']['composition']
            require(snapshot['facts'] == parent['facts'] and snapshot['datasets'] == parent['datasets'] and
                    snapshot['views'] == parent['views'] and snapshot['program'] == parent['program'] and
                    [n for n in snapshot['nodes'] if n['id'] != 'commentary'] == [n for n in parent['nodes'] if n['id'] != 'commentary'],
                    'Commentary changed frozen report content')
            require(snapshot['status'] == 'review_required' and snapshot['revision'] == 2 and snapshot['parent_id'] == parent['id'],
                    'Commentary failed to create a separate review-required revision')
            require(snapshot['source_assets'] == parent['source_assets'] and not composition['evidence'] and not composition['evidence_refs'],
                    'Unrequested evidence entered commentary')
            node = next(n for n in snapshot['nodes'] if n['id'] == 'commentary')
            used = {r['fact_id'] for r in node['runs'] if r['type'] == 'fact'}
            require({'revenue.current', 'revenue.comparison', 'revenue.change', 'revenue.growth', 'driver.region'} <= used,
                    'Commentary omitted a requested core fact')
            record['commentary'] = {'text': render_runs(node['runs'], snapshot['facts']), 'composition': composition,
                                    'semantic_review': 'pending_agent_review'}
            for attempt in composition['attempts']:
                receipt(report, attempt['receipt'], label + f" attempt {attempt['attempt']}")
            retry(service, worker, request_compose, composed_job, audit, report, label + ' commentary')
            cache_replay(service, report, audit, composed_job, snapshot)
            record['cache_replay'] = copy.deepcopy(report.summary['cache_replay'])
        record['final_snapshot'] = report.artifact(label + '/final.json', snapshot)
        before_export = audit.count, copy.deepcopy(service.store.list('model_call')), copy.deepcopy(service.store.list('snapshot'))
        for fmt in FORMATS:
            item = {'format': fmt, 'status': 'running'}
            record['exports'].append(item)
            try:
                done = job(service, worker, service.request_export(snapshot['id'], fmt, 'compatible', label + '/' + fmt), report, audit)
                export = service.store.get('export', done['result']['export_id'])
                artifact = report.artifact(label + '/exports/report.' + fmt, service.store.read_blob(export['digest']))
                item.update(record=export, artifact=artifact)
                errors = export_errors(Path(artifact['path']), fmt, snapshot, expected)
                require(not errors, 'Independent export readback failed: ' + ', '.join(errors))
                require(export['snapshot_digest'] == snapshot['digest'] and export['status'] == 'draft', 'Export draft binding changed')
                require({m['node_id'] for m in export['manifest']['components']} == {n['id'] for n in snapshot['nodes'] if n['kind'] != 'section'},
                        'Export omitted a required node')
                require(before_export == (audit.count, service.store.list('model_call'), service.store.list('snapshot')),
                        'Export invoked a model or modified a captured record')
                if export.get('preview_digest'):
                    item['preview'] = report.artifact(label + '/exports/' + fmt + '-preview.pdf', service.store.read_blob(export['preview_digest']))
                item['status'] = 'passed'
            except Exception as exc:
                item.update(status='failed', error=safe_error(exc))
            report.save()
        require(all(e['status'] == 'passed' for e in record['exports']), 'One or more export formats failed')
        record['status'] = 'passed'
    except Exception as exc:
        record.update(status='failed', error=safe_error(exc))
    report.save()


def safe_error(exc):
    return {'type': type(exc).__name__, 'code': getattr(exc, 'code', None),
            'message': str(exc) if isinstance(exc, (AssertionError, KeyError)) else getattr(exc, 'message', 'Inspect the stored job record.')}


def run_corpus(service, worker, report, audit, corpus, frozen, number):
    report.stage('Learning corpus ' + corpus['id'])
    item = {'id': corpus['id'], 'status': 'running'}
    report.summary['corpora'].append(item)
    try:
        created = service.create_type(f'Evolution corpus {chr(65 + number)}', 'Synthetic independently authored corpus.', demo=True)
        program = created['program']
        for index, historical in enumerate(corpus['history']):
            report_asset = service.upload((frozen / historical['report']).read_bytes(), f'historical-{index}.docx', demo=True)
            source_asset = service.upload((frozen / historical['source']).read_bytes(), f'historical-{index}.csv', demo=True)
            service.add_example(created['report_type']['id'], report_asset['id'], [source_asset['id']],
                                json.loads((frozen / historical['period']).read_text()), 'authoring' if index == 0 else 'development',
                                f'Historical pair {index + 1}', 'Synthetic historical observation; no future expected report registered.')
        initial_digest = program['digest']
        request = lambda: service.request_learning(program['id'], initial_digest, REQUIREMENTS,
                                                   'openai' if audit.live else 'deterministic', corpus['id'] + '/learning')
        completed = job(service, worker, request(), report, audit, corpus['id'] + '/learning' if audit.live else None)
        program = service.store.get('program', program['id'])
        learning = program['learning']
        item['learning'] = learning
        require({h['value'] for h in learning['hypotheses'] if h['supported']} == {corpus['expected_selection']},
                'Historical corpus did not uniquely identify its declared policy')
        require(all(d['resolution'] is None for d in program['decisions']) and program['state'] == 'candidate' and program['evaluation'] is None,
                'Learning auto-approved or published the candidate')
        if audit.live:
            receipt(report, learning['model_receipt'], corpus['id'] + ' learning')
            require(learning['model_proposal']['selection'] == corpus['expected_selection'], 'Live proposal chose the wrong policy')
            selection = learning['model_proposal']['selection']
        else:
            selection = next(h['value'] for h in learning['hypotheses'] if h['supported'])
        retry(service, worker, request, completed, audit, report, corpus['id'] + ' learning')
        require(all(r['status'] == 'mapped' for r in learning['coverage']), 'Historical content was silently excluded')
        choices = {'selection': selection, 'completeness': 'assumed_complete', 'template': 'compatible_reviewed',
                   'requirements': 'supported_scope_reviewed'}
        item['scripted_fixture_review'] = choices
        for decision in list(program['decisions']):
            program = service.resolve(program['id'], decision['id'], choices[decision['id']], program['digest'])
        program = service.evaluate(program['id'], program['digest'])
        require(program['evaluation']['passed'] and program['evaluation']['reconstruction_count'] == 2 and program['evaluation']['holdout_count'] == 0,
                'Historical publication evaluation failed or future cases entered evaluation')
        program = service.publish(program['id'], program['digest'], actor='synthetic_evolution_validation')
        original = copy.deepcopy(service.store.get('release', program['id']))
        item['release'] = {k: program[k] for k in ('id', 'version', 'digest')}
        item['evaluation'] = program['evaluation']
        for case in corpus['future']:
            run_future(service, worker, report, audit, corpus, case, frozen, program)
            require(service.store.get('release', program['id']) == original and
                    service.store.get('report_type', created['report_type']['id'])['active_program_id'] == program['id'],
                    'Future period mutated the reviewed release')
        item['status'] = 'passed' if all(p['status'] == 'passed' for p in report.summary['periods'] if p['id'].startswith(corpus['id'] + '/')) else 'failed'
    except Exception as exc:
        item.update(status='failed', error=safe_error(exc))
    report.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline', action='store_true')
    mode.add_argument('--run-live', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output_root = ROOT / 'output' / 'evolution-validation'
    output = (args.output or output_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])).resolve()
    if not output.is_relative_to(output_root.resolve()) or output == output_root.resolve() or output.exists():
        parser.error('Choose a new directory under output/evolution-validation; existing evidence is never overwritten.')
    output.mkdir(parents=True)
    report = Report(output, output / 'workspace')
    report.summary.update(experiment='three-corpus-twelve-future-period-v1', mode='live' if args.run_live else 'offline',
                          limits={'logical_model_jobs': 15, 'outbound_responses_calls': LIMIT},
                          scope='One regional-revenue family; three registered policies; automatic drafts after scripted fixture publication.',
                          corpora=[], periods=[], human_acceptance='not_performed')
    try:
        from foundry import model_provider
        from foundry.service import Service, code_identity
        from foundry.storage import Store
        from foundry.jobs import Worker
        frozen = output / 'frozen-fixtures'
        shutil.copytree(ROOT / 'fixtures' / 'evolution', frozen)
        frozen_hashes = {str(p.relative_to(frozen)): sha256(p.read_bytes()) for p in sorted(frozen.rglob('*')) if p.is_file()}
        report.summary['frozen_fixture_hashes'] = frozen_hashes
        report.summary['fixture_frozen_at'] = now()
        report.summary['code_identity'] = code_identity()
        manifest = json.loads((frozen / 'manifest.json').read_text())
        require(len(manifest['corpora']) == 3 and all(len(c['history']) == 2 and len(c['future']) == 4 for c in manifest['corpora']),
                'The fixed experimental matrix changed')
        if args.run_live:
            config = model_provider.status()
            report.summary['model_status'] = config
            require(config['configured'] and config['provider'] == 'cliproxyapi' and config['model'] == MODEL and config['protocol'] == 'responses',
                    'Configure the local CLIProxyAPI and exact claude-opus-5 model')
        report.save()
        service = Service(Store(output / 'workspace'))
        worker = Worker(service)
        with Audit(report, args.run_live, [c['future_canary'] for c in manifest['corpora']]) as audit:
            for number, corpus in enumerate(manifest['corpora']):
                run_corpus(service, worker, report, audit, corpus, frozen, number)
            report.summary['counts'] = {'corpora': len(report.summary['corpora']), 'future_periods': len(report.summary['periods']),
                'passed_periods': sum(p['status'] == 'passed' for p in report.summary['periods']),
                'metamorphic_variants': sum(len(p['mutations']) for p in report.summary['periods']),
                'passed_exports': sum(e['status'] == 'passed' for p in report.summary['periods'] for e in p['exports']),
                'transport_calls': audit.count, 'forbidden_model_attempts': audit.forbidden_attempts,
                'persisted_model_calls': len(service.store.list('model_call'))}
            require(audit.forbidden_attempts == 0 and audit.count <= LIMIT, 'Model scope/call-budget check failed')
        require(frozen_hashes == {str(p.relative_to(frozen)): sha256(p.read_bytes()) for p in sorted(frozen.rglob('*')) if p.is_file()},
                'Frozen expected answers or sources changed during the experiment')
        require(code_identity() == report.summary['code_identity'], 'Application code changed during the experiment')
        require(len(report.summary['periods']) == 12 and all(c['status'] == 'passed' for c in report.summary['corpora']),
                'The matrix contains failed or unexecuted periods')
        report.summary.update(status='passed_pending_agent_review' if args.run_live else 'passed_offline', finished_at=now())
        report.save()
        print('Complete results:', output / 'summary.json')
        return 0
    except Exception as exc:
        report.summary.update(status='failed', error=safe_error(exc), finished_at=now())
        report.save()
        print('Retained results:', output / 'summary.json', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
