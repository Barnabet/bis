#!/usr/bin/env python3
"""Capture the current ingestion capability against frozen public report/data pairs.

Uses cached original bytes by default; --fetch explicitly permits downloading
the official URLs in fixtures/public-corpus/manifest.json. Hash mismatches fail
and never silently refresh the benchmark. This is an admission baseline, not
an end-to-end report-generation score. No model requests are permitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT / 'fixtures' / 'public-corpus' / 'manifest.json'
CACHE = ROOT / 'output' / 'public-corpus-cache'
LIMIT = 20 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def benchmark_identity():
    return {name: sha256((ROOT / 'scripts' / name).read_bytes())
            for name in ('validate_public_corpus.py', 'public_corpus_checks.py')}


def original_bytes(asset, fetch, hosts):
    filename = asset['cache_filename']
    if Path(filename).name != filename:
        raise ValueError('Cache filenames must not contain directories')
    path = CACHE / filename
    if path.exists():
        if path.stat().st_size > LIMIT:
            raise ValueError('Cached artifact exceeds the fixed input limit')
        data = path.read_bytes()
    elif fetch:
        url = urlparse(asset['url'])
        if url.scheme != 'https' or url.hostname not in hosts or url.username or url.password:
            raise ValueError('Download URL is outside the manifest official-host allowlist')
        class OfficialRedirects(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                redirected = urlparse(urljoin(req.full_url, newurl))
                if (redirected.scheme != 'https' or redirected.hostname not in hosts
                        or redirected.username or redirected.password):
                    raise ValueError('Download redirected outside the official-host allowlist')
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        request = Request(asset['url'], headers={'User-Agent': 'ReportFoundryPublicCorpusValidation/1.0'})
        with build_opener(OfficialRedirects()).open(request, timeout=30) as response:
            final = urlparse(response.url)
            if final.scheme != 'https' or final.hostname not in hosts:
                raise ValueError('Download redirected outside the official-host allowlist')
            data = response.read(LIMIT + 1)
    else:
        raise FileNotFoundError('Original artifact is absent; use --fetch to retrieve the recorded official URL')
    if len(data) > LIMIT or not data:
        raise ValueError('Original artifact is empty or exceeds the fixed input limit')
    if sha256(data) != asset['sha256']:
        raise ValueError('Original artifact hash changed; a new vintage requires an explicit new benchmark record')
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return data, path


def inspect_original(asset, data):
    from foundry.errors import DomainError
    from foundry.ingestion import inspect_asset
    from foundry.observations import inspect_target
    try:
        inspected = inspect_asset(data, asset['filename'])
        profile = inspected['profile']
        result = {'status': inspected['status'], 'eligible_roles': profile['eligible_roles'],
                  'parser': profile.get('parser'), 'warnings': profile.get('warnings', []),
                  'row_count': profile.get('row_count'), 'page_count': profile.get('page_count')}
        if asset['role'] == 'report' and 'historical_target' in profile['eligible_roles']:
            target = inspect_target({'id': asset['id'], 'digest': asset['sha256'], **inspected})
            result['target_observations'] = {
                'observation_count': len(target['observations']),
                'mapped_regions': sum(r['status'] == 'mapped' for r in target['regions']),
                'unresolved_regions': sum(r['status'] != 'mapped' for r in target['regions']),
                'issues': target['issues'],
            }
        return result
    except DomainError as exc:
        return {'status': 'admission_rejected', 'code': exc.code, 'message': exc.message,
                'eligible_roles': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='Permit missing official-URL downloads, with exact SHA256 verification')
    args = parser.parse_args()
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6]
    directory = ROOT / 'output' / 'public-corpus-validation' / stamp
    directory.mkdir(parents=True)
    from foundry.service import code_identity
    from foundry import model_provider
    from public_corpus_checks import source_value_checks
    identity = code_identity()
    validator_identity = benchmark_identity()
    attempts = []

    def forbid(*_args, **_kwargs):
        attempts.append('unexpected_model_dispatch')
        raise AssertionError('Public-source admission checks must not request a model')

    model_provider.OpenAIProvider.generate = forbid
    model_provider._responses_transport = forbid
    model_provider._https_transport = forbid
    summary = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
               'manifest_sha256': sha256(manifest_bytes), 'code_identity': identity,
               'benchmark_identity': validator_identity,
               'scope': 'Independent public-source controls and original-byte admission capability; no learning or generation.',
               'assets': [], 'cases': [], 'model_dispatch_attempts': attempts}

    def save():
        (directory / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    save()
    for asset in manifest['assets']:
        record = {'id': asset['id'], 'role': asset['role'], 'url': asset['url'], 'sha256': asset['sha256']}
        try:
            data, path = original_bytes(asset, args.fetch, set(manifest['official_hosts']))
            record.update(artifact_status='verified', path=str(path), size=len(data),
                          inspection=inspect_original(asset, data))
        except Exception as exc:
            record.update(artifact_status='failed', error_type=type(exc).__name__, message=str(exc))
        summary['assets'].append(record)
        save()
    indexed = {a['id']: a for a in summary['assets']}
    for corpus in manifest['corpora']:
        for case in corpus['cases']:
            report = indexed[case['report_asset']]
            sources = [indexed[key] for key in case['data_assets']]
            report_info = report.get('inspection', {})
            supported_sources = [s['id'] for s in sources if 'transactions' in s.get('inspection', {}).get('eligible_roles', [])]
            observations = report_info.get('target_observations', {})
            verified = all(a['artifact_status'] == 'verified' for a in [report, *sources])
            source_checks = (source_value_checks(corpus, case, Path(sources[0]['path'])) if verified
                             else {'checks': [], 'errors': [{'message': 'Original bytes could not be verified'}],
                                   'reconciliation_findings': []})
            summary['cases'].append({
                'id': case['id'], 'corpus': corpus['id'], 'period': case['period'],
                'original_bytes_verified': verified,
                'report_admitted_as_historical_target': 'historical_target' in report_info.get('eligible_roles', []),
                'mapped_report_regions': observations.get('mapped_regions', 0),
                'unresolved_report_regions': observations.get('unresolved_regions'),
                'transaction_eligible_sources': supported_sources,
                'end_to_end_status': 'not_run_requires_reviewed_domain_adapter',
                'required_capabilities': corpus['required_capabilities'],
                'source_value_checks': source_checks,
            })
            save()
    controls = [check for case in summary['cases'] for check in case['source_value_checks']['checks']]
    expected_controls = sum(len(case['verified_source_checks']) for corpus in manifest['corpora'] for case in corpus['cases'])
    for asset in summary['assets']:
        if asset['artifact_status'] == 'verified':
            asset['unchanged_after_checks'] = sha256(Path(asset['path']).read_bytes()) == asset['sha256']
    summary['counts'] = {'corpora': len(manifest['corpora']), 'period_pairs': len(summary['cases']),
        'artifacts': len(summary['assets']),
        'verified_artifacts': sum(a['artifact_status'] == 'verified' for a in summary['assets']),
        'transaction_eligible_periods': sum(bool(c['transaction_eligible_sources']) for c in summary['cases']),
        'report_numeric_controls': sum(c['kind'] == 'report_numeric_control' for c in controls),
        'expected_report_numeric_controls': expected_controls,
        'passed_report_numeric_controls': sum(c['kind'] == 'report_numeric_control' and c['passed'] for c in controls),
        'independent_arithmetic_checks': sum(c['kind'] == 'independent_arithmetic' for c in controls),
        'passed_independent_arithmetic_checks': sum(c['kind'] == 'independent_arithmetic' and c['passed'] for c in controls),
        'source_reconciliation_findings': sum(len(c['source_value_checks']['reconciliation_findings']) for c in summary['cases']),
        'end_to_end_generation_runs': 0, 'model_calls': 0}
    complete = (all(a['artifact_status'] == 'verified' and a['unchanged_after_checks'] for a in summary['assets'])
                and all(not c['source_value_checks']['errors'] for c in summary['cases'])
                and sum(c['kind'] == 'report_numeric_control' for c in controls) == expected_controls)
    unchanged = (identity == code_identity() and validator_identity == benchmark_identity()
                 and manifest_bytes == MANIFEST.read_bytes())
    summary.update(status='completed_admission_baseline' if complete and unchanged and not attempts else 'failed',
                   finished_at=datetime.now(timezone.utc).isoformat(), inputs_and_code_unchanged=unchanged)
    save()
    print('Public-corpus admission evidence:', directory / 'summary.json')
    print(json.dumps(summary['counts'], sort_keys=True))
    return 0 if summary['status'] == 'completed_admission_baseline' else 1


if __name__ == '__main__':
    raise SystemExit(main())
