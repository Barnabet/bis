#!/usr/bin/env python3
"""Opt-in public headline workflows using original cached data and reports.

Two development pairs per family enter authoring. Later reports are inspected
only by this evaluator after the draft and optional commentary have been frozen.
These public answers were previously researched: this is a scoped evaluation,
not an untouched holdout. Mutations prove that output depends on supplied data.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
from uuid import uuid4
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate_live_model import Report, sanitized, sha256, require
from validate_evolution import job, retry, receipt

MODEL = 'claude-opus-5'
MAX_CALLS = 10  # two policy calls and four commentary jobs, each allowing one repair
FORMATS = ('docx', 'xlsx', 'pdf', 'pptx')
BLOCK_CODES = {
    'census_marts': {'missing_value': 'SOURCE_RECONCILIATION_REQUIRED',
                     'contradictory_published_rate': 'SOURCE_RECONCILIATION_REQUIRED',
                     'coherent_negative_level': 'SOURCE_RECONCILIATION_REQUIRED'},
    'ons_retail': {'missing_value': 'REQUIRED_OBSERVATION_MISSING', 'duplicate_period': 'ONS_PERIOD_INVALID'},
}


class Audit:
    def __init__(self, report, live):
        self.report, self.live, self.phase = report, live, None
        self.requests, self.forbidden, self.allowed_examples = [], [], set()

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
        if not self.live or self.phase is None or self.count >= MAX_CALLS:
            raise DomainError('UNEXPECTED_MODEL_CALL', 'Model dispatch is forbidden in this validation stage.')
        request = json.loads(body)
        require(request['model'] == MODEL and request['store'] is False and request['tools'] == [], 'Unexpected model request configuration')
        payload = json.loads(request['input'][0]['content'][0]['text'])
        if self.phase.endswith('/learning'):
            require(set(payload) == {'requirements', 'hypotheses', 'coverage'}, 'Learning scope changed')
            for token in self.forbidden:
                require(token not in body.decode(), 'Later-period asset identity leaked to model authoring')
            require(all(c['id'].split(':', 1)[0] in self.allowed_examples for c in payload['coverage']), 'Unauthorized historical region entered model context')
            require(all(c['example_id'] in self.allowed_examples for h in payload['hypotheses'] for c in h['checks']), 'Unauthorized historical observation entered model context')
        else:
            require(payload['qualitative_evidence'] == [], 'Historical report leaked into commentary evidence')
            require(not any(k in payload for k in ('expected', 'report', 'source_rows')), 'Commentary scope changed')
        number = self.count + 1
        self.requests.append({'sha256': sha256(body), 'body': request})
        entry = {'number': number, 'phase': self.phase, 'model': MODEL, 'request_sha256': sha256(body),
                 'request': self.report.artifact(f'requests/{number:02d}.json', sanitized(request)), 'headers_recorded': False}
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
            self.report.save()


def period_for(case):
    start = date.fromisoformat(case['period'] + '-01')
    return {'label': case['period'], 'start': start.isoformat(),
            'end_exclusive': (start.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat(),
            'comparison': {'start': (start - timedelta(days=1)).replace(day=1).isoformat(), 'end_exclusive': start.isoformat()},
            'timezone': 'UTC', 'as_of': case['release_date'] + 'T23:59:59Z'}


def xlsx_change(data, replacements):
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    output = BytesIO()
    with ZipFile(BytesIO(data)) as src, ZipFile(output, 'w') as dst:
        for name in src.namelist():
            raw = src.read(name)
            if name in replacements:
                root = ET.fromstring(raw)
                for address, value in replacements[name].items():
                    cell = root.find(f'.//s:c[@r="{address}"]', ns)
                    require(cell is not None, f'Mutation cell missing: {address}')
                    for child in list(cell): cell.remove(child)
                    cell.attrib.pop('t', None)
                    if value is not None:
                        ET.SubElement(cell, '{' + ns['s'] + '}v').text = str(value)
                raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            dst.writestr(name, raw)
    return output.getvalue()


def mutations(family, data):
    """Expected mutation values are computed here, independently of the runtime."""
    if family == 'ons_retail':
        rows = list(csv.reader(StringIO(data.decode('utf-8-sig'))))
        column = rows[1].index('J5EC')
        last = max(i for i, r in enumerate(rows) if len(r[0]) == 8 and r[0][4] == ' ')
        def encode(items):
            stream = StringIO(); csv.writer(stream).writerows(items); return stream.getvalue().encode()
        changed = copy.deepcopy(rows)
        changed[last][column] = str(Decimal(changed[last][column]) + Decimal('1.3'))
        yield 'changed_value', encode(changed), {'ons.J5EC': changed[last][column]}
        reordered = [[r[0], *reversed(r[1:])] for r in rows]
        yield 'column_order', encode(reordered), {}
        missing = copy.deepcopy(rows); missing[last][column] = ''
        yield 'missing_value', encode(missing), None
        duplicate = copy.deepcopy(rows); duplicate.append(copy.deepcopy(rows[last]))
        yield 'duplicate_period', encode(duplicate), None
    else:
        from openpyxl import load_workbook
        book = load_workbook(BytesIO(data), data_only=True, keep_links=False)
        sheet = book['Table 1.']; current = Decimal(str(sheet['J12'].value)) + 1372
        monthly = ((current / Decimal(str(sheet['K12'].value)) - 1) * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)
        annual = ((current / Decimal(str(sheet['M12'].value)) - 1) * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)
        negative_monthly = ((Decimal('-100') / Decimal(str(sheet['K12'].value)) - 1) * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)
        negative_annual = ((Decimal('-100') / Decimal(str(sheet['M12'].value)) - 1) * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)
        book.close()
        changed = xlsx_change(data, {'xl/worksheets/sheet1.xml': {'J12': current}, 'xl/worksheets/sheet2.xml': {'C15': monthly, 'D15': annual}})
        yield 'changed_value', changed, {'census.sales_headline_usd_million': str(current), 'census.month_on_month_pct': str(monthly), 'census.year_on_year_pct': str(annual)}
        yield 'missing_value', xlsx_change(data, {'xl/worksheets/sheet1.xml': {'J12': None}}), None
        yield 'contradictory_published_rate', xlsx_change(data, {'xl/worksheets/sheet2.xml': {'C15': '99.9'}}), None
        yield 'coherent_negative_level', xlsx_change(data, {'xl/worksheets/sheet1.xml': {'J12': '-100'},
            'xl/worksheets/sheet2.xml': {'C15': negative_monthly, 'D15': negative_annual}}), None


def run_family(corpus, assets, blobs, service, worker, report, audit):
    from foundry.public_reports import inspect_target, compare_snapshot
    from foundry.errors import DomainError
    family = corpus['id']
    report.stage(f'{family}: authoring from the first two public pairs')
    created = service.create_type(corpus['title'] + ' · headlines', family=family)
    program = created['program']
    authoring_manifest = []
    for case in corpus['cases'][:2]:
        target_meta, source_meta = assets[case['report_asset']], assets[case['data_assets'][0]]
        target = service.upload(blobs[target_meta['id']], target_meta['filename'], public_family=family)
        source = service.upload(blobs[source_meta['id']], source_meta['filename'], public_family=family)
        pair = service.add_example(program['report_type_id'], target['id'], [source['id']], period_for(case), 'authoring', label=case['id'])
        audit.allowed_examples.add(pair['id'])
        authoring_manifest.append({'example_id': pair['id'], 'period': case['period'], 'report_sha256': target['digest'], 'source_sha256': source['digest']})
    report.artifact(f'{family}/authoring-manifest.json', authoring_manifest)
    requirements = 'Reconstruct only the registered headline statistics from these public report/source pairs. Preserve release vintage, units and explicit source locators. Leave all unmapped historical material visible for a scope review. Never infer unsupported explanations.'
    request = lambda: service.request_learning(program['id'], program['digest'], requirements, 'openai' if audit.live else 'deterministic', family + '/learn')
    done = job(service, worker, request(), report, audit, family + '/learning' if audit.live else None)
    retry(service, worker, request, done, audit, report, family + ' learning')
    program = service.store.get('program', program['id'])
    report.artifact(f'{family}/learning.json', program['learning'])
    report.check(family + ' historical headline hypothesis supported', all(h['supported'] for h in program['learning']['hypotheses']))
    if audit.live: receipt(report, program['learning']['model_receipt'], family + ' authoring')
    # Test-only approvals describe the limited experiment, never accept reports.
    for region in program['learning']['coverage']:
        if region['status'] != 'mapped':
            program = service.review_coverage(program['id'], program['digest'], region['id'], 'out_of_scope',
                'Validation experiment explicitly reconstructs registered headlines only. All other text, appendix figures, uncertainty, imagery and original layout remain excluded and unverified.')
    for decision in program['decisions']:
        program = service.resolve(program['id'], decision['id'], decision['alternatives'][0]['value'], program['digest'])
    report.stage(f'{family}: evaluating the exact candidate and native exports')
    program = service.evaluate(program['id'], program['digest'])
    report.artifact(f'{family}/evaluation.json', program['evaluation'])
    report.check(family + ' exact candidate evaluation passed', program['evaluation']['passed'])
    program = service.publish(program['id'], program['digest'], actor='public_validation_fixture_scope')
    report.summary['programs'].append({k: program[k] for k in ('id', 'version', 'digest', 'report_type_id', 'policy')})
    for case in corpus['cases'][2:]:
        result = {'case_id': case['id'], 'status': 'running', 'mutations': [], 'exports': []}
        report.summary['cases'].append(result); report.save()
        report.stage(f"{case['id']}: source-only generation and later-report evaluation")
        source_meta = assets[case['data_assets'][0]]
        raw = blobs[source_meta['id']]
        source = service.upload(raw, source_meta['filename'], public_family=family)
        period = period_for(case)
        request_run = lambda: service.request_run(program['report_type_id'], source['id'], period, case['id'])
        generated = job(service, worker, request_run(), report, audit)
        retry(service, worker, request_run, generated, audit, report, case['id'] + ' generation')
        snapshot = service.store.get('snapshot', generated['result']['snapshot_id'])
        original_facts = copy.deepcopy(snapshot['facts'])
        if audit.live:
            objective = 'Write a concise factual commentary using the required fact placeholders and the supplied published values. Describe the figures without inventing explanations, calculations, rankings or other claims. Keep the wording subject to review.'
            request_compose = lambda: service.request_composition(snapshot['id'], snapshot['revision'], [], objective, case['id'] + '/commentary')
            composed = job(service, worker, request_compose(), report, audit, case['id'] + '/composition')
            snapshot = service.store.get('snapshot', composed['result']['snapshot_id'])
            require(snapshot['facts'] == original_facts, 'Commentary changed a frozen fact')
            result['composition_receipt'] = snapshot['metadata']['composition']['receipt']
            receipt(report, result['composition_receipt'], case['id'] + ' commentary')
        require(snapshot['status'] == 'review_required', 'A generated report was automatically accepted')
        report.artifact(f"{case['id']}/snapshot.json", snapshot)
        # Historical answers enter the evaluator only after output is frozen.
        target_meta = assets[case['report_asset']]
        target = service.upload(blobs[target_meta['id']], target_meta['filename'], public_family=family)
        inspection = inspect_target(target, family)
        compared = compare_snapshot(snapshot, inspection)
        result.update(comparison=compared, scope='Registered headlines only; original report regions remain outside this draft.', snapshot_id=snapshot['id'])
        report.artifact(f"{case['id']}/independent-report-observations.json", inspection)
        report.check(case['id'] + ' independently located headline comparison', compared['passed'])
        for name, mutated, expected in mutations(family, raw):
            entry = {'name': name, 'source_sha256': sha256(mutated)}
            result['mutations'].append(entry)
            before_counts = (audit.count, len(service.store.list('snapshot')), len(service.store.list('export')))
            expected_code = BLOCK_CODES[family].get(name)
            try:
                altered = service.upload(mutated, source_meta['filename'], public_family=family)
                requested = service.request_run(program['report_type_id'], altered['id'], period, case['id'] + '/' + name)
                worker.run_one()
                finished = service.store.job(requested['id'])
                entry['job_status'] = finished['status']
                if finished['status'] != 'completed':
                    code = (finished.get('error') or {}).get('code')
                    entry.update(passed=expected is None and finished['status'] == 'blocked' and code == expected_code, code=code)
                else:
                    changed = service.store.get('snapshot', finished['result']['snapshot_id'])
                    entry['passed'] = expected is not None
                    if expected is not None:
                        for fid, value in expected.items():
                            entry['passed'] &= Decimal(changed['facts'][fid]['value']) == Decimal(value)
                        if name == 'column_order':
                            entry['passed'] &= {k: v['value'] for k, v in changed['facts'].items()} == {k: v['value'] for k, v in original_facts.items()}
                        else:
                            entry['passed'] &= not compare_snapshot(changed, inspection)['passed']
                        require(changed['status'] == 'review_required', 'Mutation output was autoaccepted')
            except DomainError as exc:
                entry.update(passed=expected is None and exc.code == expected_code, code=exc.code)
            after_counts = (audit.count, len(service.store.list('snapshot')), len(service.store.list('export')))
            require(after_counts[0] == before_counts[0], 'Mutation dispatched a model request')
            if expected is None:
                entry['passed'] &= before_counts == after_counts
                entry['no_snapshot_or_export_created'] = before_counts == after_counts
            report.check(case['id'] + ' mutation ' + name, entry['passed'])
        for name, changed_period in [('wrong_window', {**period, 'start': period['start'][:8] + '02'}),
                                     ('before_release', {**period, 'as_of': period['start'] + 'T00:00:00Z'})]:
            before_counts = (audit.count, len(service.store.list('snapshot')), len(service.store.list('export')))
            requested = service.request_run(program['report_type_id'], source['id'], changed_period, case['id'] + '/' + name)
            worker.run_one(); finished = service.store.job(requested['id'])
            code = (finished.get('error') or {}).get('code')
            expected_code = 'PERIOD_GRAIN_MISMATCH' if name == 'wrong_window' else 'SOURCE_VINTAGE_MISMATCH'
            after_counts = (audit.count, len(service.store.list('snapshot')), len(service.store.list('export')))
            entry = {'name': name, 'passed': finished['status'] == 'blocked' and code == expected_code and before_counts == after_counts,
                     'code': code, 'no_snapshot_or_export_created': before_counts == after_counts}
            result['mutations'].append(entry)
            report.check(case['id'] + ' boundary ' + name, entry['passed'])
        for fmt in FORMATS:
            exported = job(service, worker, service.request_export(snapshot['id'], fmt, 'compatible', case['id'] + '/' + fmt), report, audit)
            result['exports'].append({'format': fmt, 'result': exported['result']})
        result['status'] = 'passed'; report.save()


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    mode = arg.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline', action='store_true'); mode.add_argument('--run-live', action='store_true')
    options = arg.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6]
    folder = ROOT / 'output' / 'public-workflow-validation' / stamp
    folder.mkdir(parents=True)
    report = Report(folder, folder / 'workspace')
    report.summary.update(synthetic_only=False, scope='Two registered public headline families; four later-period drafts. FMC reconciliation remains blocked. Test-only scope approvals; no report acceptance.',
        untouched_holdout=False, previous_research_exposure=True, limits={'logical_model_jobs': 6, 'outbound_responses_calls': MAX_CALLS}, programs=[], cases=[], failures=[])
    from foundry.service import Service, code_identity
    from foundry.storage import Store
    from foundry.jobs import Worker
    from foundry.model_provider import status
    identity = code_identity()
    manifest_bytes = (ROOT / 'fixtures/public-corpus/manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    assets = {a['id']: a for a in manifest['assets']}
    blobs = {id: (ROOT / 'output/public-corpus-cache' / a['cache_filename']).read_bytes() for id, a in assets.items()}
    for id, raw in blobs.items(): require(sha256(raw) == assets[id]['sha256'] and len(raw) == assets[id]['size_bytes'], 'Original public source integrity mismatch')
    report.summary.update(code_identity=identity, manifest_sha256=sha256(manifest_bytes), validator_sha256=sha256(Path(__file__).read_bytes()), original_assets_verified=len(blobs))
    if options.run_live:
        configuration = status()
        require(configuration['configured'] and configuration['provider'] == 'cliproxyapi' and configuration['model'] == MODEL, 'Configure exact claude-opus-5 on local CLIProxyAPI')
        report.summary['model_configuration'] = configuration
    service = Service(Store(folder / 'workspace')); worker = Worker(service)
    with Audit(report, options.run_live) as audit:
        audit.forbidden = [a[k] for c in manifest['corpora'][:2] for case in c['cases'][2:] for id in [case['report_asset'], *case['data_assets']] for a in [assets[id]] for k in ('id', 'sha256')]
        for corpus in manifest['corpora'][:2]:
            try:
                run_family(corpus, assets, blobs, service, worker, report, audit)
            except Exception as exc:
                report.summary['failures'].append({'family': corpus['id'], 'code': getattr(exc, 'code', type(exc).__name__), 'message': str(exc)[:1000]})
                report.save()
        try:
            from foundry.public_fmc import inspect_source, reconcile_report
            corpus = manifest['corpora'][2]
            report.summary['fmc'] = []
            for case in corpus['cases']:
                quarter = case['period'][-2:] + ' ' + case['period'][:4]
                curated = next(r for r in corpus['source_reconciliation'] if r['quarter'] == quarter)
                observations = []
                for table, page in [('US Ports', 1), ('Ocean Carriers', 3)]:
                    for metrics, values, unit, observed_page in [
                        (['laden_exports', 'empty_exports', 'laden_imports', 'empty_imports', 'container_total'], curated['pdf_printed_container_totals'], 'containers_as_published', page),
                        (['export_tonnage', 'import_tonnage', 'tonnage_total'], curated['pdf_printed_tonnage_totals'], 'tonnage_as_published', page + 1)]:
                        for metric, value in zip(metrics, values):
                            observations.append({'table': table, 'entity': 'Total', 'metric_id': 'fmc.' + metric, 'period': case['period'],
                                'value': str(value), 'unit': unit, 'locator': f'page={observed_page};row=Total;column={metric}',
                                'source_digest': assets[case['report_asset']]['sha256'], 'method': 'independently_curated_manifest_control_not_runtime_ocr'})
                source = inspect_source(blobs[case['data_assets'][0]], case['period'])
                reconciled = reconcile_report(source, observations)
                all_selected = all(row['period'] == case['period'] for rows in source['rows'].values() for row in rows)
                result = {'case_id': case['id'], 'source_digest': source['source_digest'], 'quarter_isolation': all_selected,
                          'report_certification': reconciled['report_certification'], 'runtime_ocr_performed': False,
                          'checks': reconciled['checks'], 'issues': reconciled['issues'], 'reconciliation_findings': reconciled['reconciliation_findings']}
                report.summary['fmc'].append(result)
                report.artifact(f"{case['id']}/reconciliation.json", result)
                report.check(case['id'] + ' preserves quarter isolation and unresolved report block',
                             all_selected and result['report_certification'] == 'blocked' and bool(result['reconciliation_findings']))
        except Exception as exc:
            report.summary['failures'].append({'family': 'fmc_freight', 'code': getattr(exc, 'code', type(exc).__name__), 'message': str(exc)[:1000]})
        final_checks = [('Runtime code unchanged during experiment', code_identity() == identity),
                        ('No report accepted', all(s['status'] != 'accepted' for s in service.store.list('snapshot'))),
                        ('Four later-period cases completed', len(report.summary['cases']) == 4 and all(c['status'] == 'passed' for c in report.summary['cases'])),
                        ('Original bytes unchanged', all(sha256((ROOT / 'output/public-corpus-cache' / a['cache_filename']).read_bytes()) == a['sha256'] for a in assets.values()))]
        for name, passed in final_checks:
            report.summary['checks'].append({'name': name, 'passed': passed})
            if not passed:
                report.summary['failures'].append({'code': 'FINAL_CHECK_FAILED', 'message': name})
        report.summary.update(outbound_calls=audit.count, status='passed' if not report.summary['failures'] else 'failed', finished_at=datetime.now(timezone.utc).isoformat())
        report.save()
    print(json.dumps({'status': report.summary['status'], 'summary': str(folder / 'summary.json'), 'outbound_calls': report.summary['outbound_calls'], 'failures': report.summary['failures']}, indent=2))
    return 0 if report.summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
