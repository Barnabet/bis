"""Application-owned lifecycle. No model or uploaded code controls publication."""
from __future__ import annotations
import copy
from pathlib import Path
import platform
import tempfile
from .storage import Store, digest, canonical, now, uid
from .errors import DomainError
from .ingestion import inspect_asset, transaction_rows

ROOT = Path(__file__).resolve().parent.parent


def source_ref(asset):
    return {k: asset[k] for k in ('id', 'digest', 'filename')}


def code_identity():
    files = {}
    for path in sorted((ROOT / 'foundry').rglob('*.py')):
        if '__pycache__' not in path.parts:
            files[str(path.relative_to(ROOT))] = digest(path.read_bytes())
    for name in ('pyproject.toml', 'uv.lock'):
        path = ROOT / name
        if path.exists():
            files[name] = digest(path.read_bytes())
    return {'files': files, 'python': f'{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}'}


def program_digest(program):
    return digest({k: program[k] for k in ('code_identity', 'policy', 'decisions', 'input_contract', 'version')})


def snapshot_dict(model):
    result = model.model_dump(mode='json') if hasattr(model, 'model_dump') else copy.deepcopy(model)
    result.pop('digest', None)
    result['digest'] = digest(result)
    return result


def validate_stored_snapshot(record):
    from .contracts import Snapshot
    raw = {k: v for k, v in record.items() if k != 'digest'}
    if digest(raw) != record['digest']:
        raise DomainError('SNAPSHOT_INTEGRITY', 'Snapshot content no longer matches its frozen digest.', 409)
    return Snapshot.model_validate(raw)


class Service:
    def __init__(self, store: Store):
        self.store = store

    def upload(self, data, filename, demo=False):
        inspected = inspect_asset(data, filename)
        sha = self.store.put_blob(data)
        record = {'id': uid('asset'), **inspected, 'digest': sha, 'created_at': now(), 'demo': demo}
        self.store.insert('asset', record)
        self.store.audit(record['id'], 'uploaded', {'digest': sha, 'filename': record['filename']})
        return record

    def create_type(self, name, description='', demo=False):
        type_id, program_id = uid('type'), uid('program')
        report_type = {'id': type_id, 'name': name, 'description': description, 'active_program_id': None,
                       'created_at': now(), 'demo': demo}
        program = {
            'id': program_id, 'report_type_id': type_id, 'name': f'{name} reporting program', 'version': '1.0.0',
            'state': 'candidate', 'created_at': now(), 'demo': demo, 'code_identity': code_identity(),
            'authoring_mode': 'manually_authored_reference',
            'policy': {'adapter': 'quarterly-revenue-v1', 'selection': 'largest_absolute_change',
                       'tie_break': 'normalized_region_key', 'currency': 'EUR', 'missing_region': 'zero_within_nonempty_period',
                       'cutoff': 'immutable_snapshot_metadata', 'prose': 'computed_and_reviewed_editorial',
                       'fidelity': 'compatible', 'evidence_scope': 'synthetic_regression_no_holdouts'},
            'input_contract': {'role': 'transactions', 'formats': ['csv', 'xlsx'],
                'columns': ['transaction_id', 'date', 'region', 'status', 'amount', 'currency'],
                'notes': 'One immutable value-only transaction dataset. Posted EUR transactions; explicit current and comparison intervals.'},
            'coverage': [{'id': id, 'label': label, 'kind': kind, 'status': 'implemented'} for id, label, kind in [
                ('summary', 'Fact-linked movement summary', 'computed'), ('commentary', 'Editorial commentary', 'literal'),
                ('regional_table', 'Regional revenue table', 'table'), ('regional_chart', 'Regional comparison chart', 'chart'),
                ('regional_pivot', 'Region and period pivot', 'pivot')]],
            'decisions': [
                {'id': 'selection', 'question': 'Which regional movement should the summary discuss?',
                 'alternatives': [{'value': 'largest_absolute_change', 'label': 'Largest absolute revenue change',
                                   'consequence': 'Rank the magnitude of EUR changes; use the region key to break ties.'}], 'resolution': None},
                {'id': 'completeness', 'question': 'May absent regions count as zero inside a nonempty supplied period?',
                 'alternatives': [{'value': 'assumed_complete', 'label': 'Accept the complete-export assumption',
                                   'consequence': 'Missing whole periods still block. Source completeness remains a disclosed assumption.'}], 'resolution': None},
                {'id': 'template', 'question': 'Approve the built-in compatible presentation profile for this report type?',
                 'alternatives': [{'value': 'compatible_reviewed', 'label': 'Approve compatible presentations',
                                   'consequence': 'Static chart/pivot representations are disclosed. Strict native pivot certification remains blocked.'}], 'resolution': None}
            ],
            'evaluation': None,
            'limitations': ['Trusted regional revenue adapter only; automated report learning is not implemented.',
                           'Synthetic regression fixtures; no held-out customer evaluation.',
                           'Native Excel pivot interaction requires certification in the intended spreadsheet application.',
                           'Single-user local runtime; no production multi-tenant sandbox.']
        }
        program['digest'] = program_digest(program)
        with self.store.transaction() as db:
            self.store.insert('report_type', report_type, db)
            self.store.insert('program', program, db)
            self.store.audit(type_id, 'report_type_created', {'program_id': program_id}, db)
        return {'report_type': report_type, 'program': program}

    def _candidate(self, id, expected_digest, db):
        program = self.store.get('program', id, db)
        if program['state'] != 'candidate':
            raise DomainError('PROGRAM_IMMUTABLE', 'Published programs are frozen; create a new candidate.', 409)
        if program['digest'] != expected_digest:
            raise DomainError('VERSION_CONFLICT', 'This candidate changed. Refresh before continuing.', 409)
        return program

    def resolve(self, id, decision_id, resolution, expected_digest):
        with self.store.transaction() as db:
            program = self._candidate(id, expected_digest, db)
            decision = next((d for d in program['decisions'] if d['id'] == decision_id), None)
            if not decision or resolution not in [a['value'] for a in decision['alternatives']]:
                raise DomainError('DECISION_INVALID', 'Choose a supported policy resolution.')
            decision['resolution'] = resolution
            decision['resolved_at'] = now()
            decision['actor'] = 'local_user'
            program['evaluation'] = None
            program['digest'] = program_digest(program)
            self.store.update('program', id, program, db)
            self.store.audit(id, 'policy_resolved', {'decision_id': decision_id, 'resolution': resolution}, db)
        return program

    def evaluate(self, id, expected_digest):
        program = self.store.get('program', id)
        if program['digest'] != expected_digest:
            raise DomainError('VERSION_CONFLICT', 'The candidate changed before evaluation.', 409)
        if program['code_identity'] != code_identity():
            if program['state'] == 'candidate':
                # Refresh registered code only as a new candidate digest; caller must review it.
                with self.store.transaction() as db:
                    p = self._candidate(id, expected_digest, db)
                    p['code_identity'] = code_identity()
                    p['evaluation'] = None
                    p['digest'] = program_digest(p)
                    self.store.update('program', id, p, db)
                raise DomainError('CODE_CHANGED', 'Registered code changed; candidate refreshed. Review and run evaluation again.', 409)
            raise DomainError('CODE_CHANGED', 'The published runtime no longer matches installed code.', 409)
        from .runtime import prepare, default_period
        from .contracts import Snapshot
        fixture = (ROOT / 'fixtures' / 'transactions.csv').read_bytes()
        from .ingestion import rows_from_csv
        _, rows = rows_from_csv(fixture)
        source = {'id': 'fixture_transactions', 'digest': digest(fixture), 'filename': 'transactions.csv'}
        snapshot = prepare(rows, default_period(), source, program={k: program[k] for k in ('id', 'version', 'digest')})
        checks = []
        def check(name, passed, detail):
            checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
        facts = snapshot.facts
        from decimal import Decimal
        check('Independent current total', Decimal(facts['revenue.current'].value) == Decimal('1200'), 'Expected EUR 1,200.00 from protected synthetic observations.')
        check('Independent comparison total', Decimal(facts['revenue.comparison'].value) == Decimal('1000'), 'Expected EUR 1,000.00; cancelled/out-of-period rows excluded.')
        check('Independent growth and driver', Decimal(facts['revenue.growth'].value) == Decimal('.2') and facts['driver.region'].value == 'North', 'Expected 20.0% and North, independent of display order.')
        Snapshot.model_validate(snapshot.model_dump())
        check('Native graph and complete views', len(snapshot.views) == 3, 'Fact lineage, dataset types and all three coverage maps validate.')
        reversed_snapshot = prepare(list(reversed(rows)), default_period(), source)
        check('Input order invariance', reversed_snapshot.facts['revenue.current'].value == facts['revenue.current'].value and reversed_snapshot.facts['driver.region'].value == facts['driver.region'].value, 'Shuffled transactions preserve totals and selected driver.')
        # Structural render smoke checks are independent of candidate approval.
        from .exporters import export_snapshot
        try:
            with tempfile.TemporaryDirectory(prefix='foundry-evaluate-') as folder:
                for format in ('docx', 'xlsx', 'pdf', 'pptx'):
                    output = export_snapshot(snapshot.model_dump(mode='json'), format, Path(folder) / format, policy='compatible')
                    check(f'{format.upper()} export structure', Path(output['path']).is_file() and Path(output['path']).stat().st_size > 100,
                          'Rendered from one frozen snapshot. Native application certification and human visual review are separate.')
        except Exception as exc:
            check('Export capability smoke test', False, str(exc)[:500])
        evaluation = {'digest': expected_digest, 'passed': all(c['passed'] for c in checks), 'checks': checks,
                      'created_at': now(), 'corpus': 'synthetic_development', 'holdout_count': 0}
        with self.store.transaction() as db:
            current = self._candidate(id, expected_digest, db)
            current['evaluation'] = evaluation
            for c in current['coverage']:
                c['status'] = 'verified' if evaluation['passed'] else 'implemented'
            self.store.update('program', id, current, db)
            self.store.audit(id, 'evaluated', evaluation, db)
        return current

    def publish(self, id, expected_digest, actor='local_user'):
        with self.store.transaction() as db:
            program = self._candidate(id, expected_digest, db)
            if program['code_identity'] != code_identity():
                raise DomainError('CODE_CHANGED', 'Code changed after evaluation. Evaluate a new candidate digest.', 409)
            missing = [d['id'] for d in program['decisions'] if not d['resolution']]
            if missing:
                raise DomainError('POLICY_UNRESOLVED', 'Resolve the reporting policy decisions before publication.', 409, missing)
            evaluation = program.get('evaluation')
            if not evaluation or not evaluation['passed'] or evaluation['digest'] != expected_digest:
                raise DomainError('EVALUATION_REQUIRED', 'This exact candidate must pass independent evaluation before publication.', 409)
            if any(c['status'] != 'verified' for c in program['coverage']):
                raise DomainError('COVERAGE_INCOMPLETE', 'Required components are not verified.', 409)
            package_files = {}
            for name, expected in program['code_identity']['files'].items():
                content = (ROOT / name).read_bytes()
                if digest(content) != expected:
                    raise DomainError('CODE_CHANGED', 'A package file changed during publication.', 409)
                package_files[name] = content.decode('utf-8')
            package = {'schema_version': '1.0', 'program_digest': expected_digest, 'files': package_files,
                       'policy': program['policy'], 'decisions': program['decisions']}
            program['package_artifact_digest'] = self.store.put_blob(canonical(package))
            program['state'] = 'published'
            program['published_at'] = now()
            program['approval'] = {'actor': actor, 'at': now(), 'digest': expected_digest, 'profile': 'compatible_provisional'}
            self.store.insert('release', copy.deepcopy(program), db)
            self.store.update('program', id, program, db)
            rt = self.store.get('report_type', program['report_type_id'], db)
            rt['active_program_id'] = id
            self.store.update('report_type', rt['id'], rt, db)
            self.store.audit(id, 'published', program['approval'], db)
        return program

    def request_run(self, report_type_id, asset_id, period, idempotency_key):
        report_type = self.store.get('report_type', report_type_id)
        if not report_type['active_program_id']:
            raise DomainError('PROGRAM_UNPUBLISHED', 'Evaluate and publish this report type before generating a period.', 409)
        program = self.store.get('release', report_type['active_program_id'])
        asset = self.store.get('asset', asset_id)
        if 'transactions' not in asset['profile']['eligible_roles']:
            raise DomainError('INPUT_DRIFT', 'Bind a supported transaction source.')
        payload = {'report_type_id': report_type_id, 'program_id': program['id'], 'program_digest': program['digest'],
                   'asset_id': asset_id, 'source_digest': asset['digest'], 'period': period}
        original_request = {'report_type_id': report_type_id, 'asset_id': asset_id, 'period': period}
        return self.store.enqueue('generation', f'run:{report_type_id}', idempotency_key, payload, request_identity=original_request)

    def request_export(self, snapshot_id, format, policy, idempotency_key):
        record = self.store.get('snapshot', snapshot_id)
        validate_stored_snapshot(record)
        return self.store.enqueue('export', f'export:{snapshot_id}', idempotency_key,
                                  {'snapshot_id': snapshot_id, 'snapshot_digest': record['digest'], 'format': format, 'policy': policy})

    def revise(self, id, expected_revision, node_id, text, reason):
        from .runtime import revise_commentary
        record = self.store.get('snapshot', id)
        model = validate_stored_snapshot(record)
        if record['revision'] != expected_revision:
            raise DomainError('VERSION_CONFLICT', 'This revision changed. Refresh the report.', 409)
        node = next((n for n in model.nodes if n.id == node_id), None)
        if node_id != 'commentary' or not getattr(node, 'editable', False):
            raise DomainError('COMPUTED_FACT_LOCKED', 'Computed content must be changed through a source correction and a new run.', 409)
        revised = revise_commentary(model, text, expected_revision=expected_revision)
        raw = revised.model_dump(mode='json')
        raw['metadata'].update({'revision_reason': reason, 'edited_by': 'local_user', 'edit_scope': 'this_period_content'})
        data = snapshot_dict(raw)
        with self.store.transaction() as db:
            # One child per base: concurrent edits must rebase on the winner.
            children = db.execute("SELECT data FROM entities WHERE kind='snapshot'").fetchall()
            if any(__import__('json').loads(c[0]).get('parent_id') == id for c in children):
                raise DomainError('VERSION_CONFLICT', 'A newer revision already exists. Open it before editing.', 409)
            self.store.insert('snapshot', data, db)
            self.store.audit(id, 'revised', {'new_snapshot_id': data['id'], 'reason': reason, 'node_id': node_id}, db)
            self.store.audit(data['id'], 'revision_created', {'parent_id': id, 'reason': reason, 'scope': 'this_period_content'}, db)
        return data

    def accept(self, id, expected_revision):
        record = self.store.get('snapshot', id)
        model = validate_stored_snapshot(record)
        if record['revision'] != expected_revision:
            raise DomainError('VERSION_CONFLICT', 'Refresh the report revision before accepting.', 409)
        if record['status'] == 'accepted':
            return record
        if any(f.severity == 'block' for f in model.findings):
            raise DomainError('REPORT_BLOCKED', 'Required content issues must be corrected before acceptance.', 409)
        data = model.model_dump(mode='json')
        data.update(id=uid('snapshot'), parent_id=id, revision=record['revision'] + 1, status='accepted', created_at=now())
        data['metadata']['human_acceptance'] = {'actor': 'local_user', 'at': now(), 'original_findings_preserved': True,
                                               'reviewed_findings': [f for f in data['findings'] if f['severity'] == 'review']}
        data['findings'] = [f for f in data['findings'] if f['severity'] != 'review']
        from .contracts import Snapshot
        data = snapshot_dict(Snapshot.model_validate(data))
        with self.store.transaction() as db:
            import json
            children = db.execute("SELECT data FROM entities WHERE kind='snapshot'").fetchall()
            if any(json.loads(c[0]).get('parent_id') == id for c in children):
                raise DomainError('VERSION_CONFLICT', 'A newer revision already exists. Review it before accepting.', 409)
            self.store.insert('snapshot', data, db)
            self.store.audit(data['id'], 'human_accepted', {'parent_id': id, 'original_findings_preserved': True}, db)
        return data

    def add_example(self, report_type_id, report_asset_id, source_asset_ids, period, corpus_role):
        self.store.get('report_type', report_type_id)
        self.store.get('asset', report_asset_id)
        for asset_id in source_asset_ids:
            self.store.get('asset', asset_id)
        example = {'id': uid('example'), 'report_type_id': report_type_id, 'report_asset_id': report_asset_id,
                   'source_asset_ids': source_asset_ids, 'period': period, 'corpus_role': corpus_role,
                   'state': 'inspected', 'learning_status': 'not_implemented', 'created_at': now()}
        self.store.insert('example', example)
        return example

    def execute_generation(self, job, stage):
        from .runtime import prepare, RuntimeBlocked
        payload = job['payload']
        stage('Resolving frozen program')
        program = self.store.get('release', payload['program_id'])
        if program['digest'] != payload['program_digest'] or program['code_identity'] != code_identity():
            raise DomainError('CODE_CHANGED', 'The installed runtime differs from the pinned release. Publish a new evaluated candidate.', 409)
        stage('Validating immutable source')
        asset = self.store.get('asset', payload['asset_id'])
        rows = transaction_rows(self.store.read_blob(asset['digest']), asset['profile'])
        stage('Preparing facts and shared data')
        snapshot = prepare(rows, payload['period'], source_ref(asset), program={k: program[k] for k in ('id', 'version', 'digest')},
                           report_type_id=payload['report_type_id'])
        report_type = self.store.get('report_type', payload['report_type_id'])
        raw = snapshot.model_dump(mode='json')
        raw['title'] = report_type['name']
        raw['metadata'].update({'demo': bool(asset.get('demo')), 'generation_job_id': job['id'], 'authoring_mode': program['authoring_mode']})
        raw['status'] = 'review_required'
        stage('Validating references and view coverage')
        from .contracts import Snapshot
        snapshot = Snapshot.model_validate(raw)
        data = snapshot_dict(snapshot)
        self.store.put_blob(canonical(data))
        stage('Freezing native report')
        self.store.finish(job['id'], job['token'], result={'snapshot_id': data['id']}, records=[('snapshot', data)])

    def execute_export(self, job, stage):
        from .exporters import export_snapshot
        payload = job['payload']
        stage('Resolving frozen report')
        record = self.store.get('snapshot', payload['snapshot_id'])
        model = validate_stored_snapshot(record)
        if record['status'] == 'blocked' or any(f.severity == 'block' for f in model.findings):
            raise DomainError('REPORT_BLOCKED', 'Correct blocking report findings before exporting this revision.', 409)
        if record['digest'] != payload['snapshot_digest']:
            raise DomainError('SNAPSHOT_INTEGRITY', 'Export snapshot digest differs from its request.', 409)
        stage('Planning coverage and fidelity')
        with tempfile.TemporaryDirectory(prefix='foundry-export-', dir=self.store.root) as folder:
            stage(f'Rendering {payload["format"].upper()}')
            output = export_snapshot(model.model_dump(mode='json'), payload['format'], Path(folder), policy=payload['policy'])
            stage('Verifying and storing artifact')
            path = Path(output['path']).resolve()
            if not path.is_relative_to(Path(folder).resolve()) or path.is_symlink():
                raise DomainError('EXPORT_BOUNDARY', 'Renderer returned a path outside its output directory.', 500)
            data = path.read_bytes()
            sha = self.store.put_blob(data)
            export = {'id': uid('export'), 'snapshot_id': record['id'], 'snapshot_digest': record['digest'],
                      'format': payload['format'], 'filename': output.get('filename', path.name),
                      'media_type': output['media_type'], 'digest': sha, 'size': len(data),
                      'status': 'draft' if record['status'] != 'accepted' else 'ready',
                      'manifest': output['manifest'], 'created_at': now()}
            export['manifest']['report_status'] = record['status']
            export['manifest']['snapshot_digest'] = record['digest']
            if payload['format'] == 'pdf':
                export['preview_digest'] = sha
                export['preview_origin'] = 'native_flow_pdf'
            else:
                import os, shutil
                if os.environ.get('FOUNDRY_SOFFICE') or shutil.which('soffice'):
                    try:
                        from .exporters.preview import render_office_preview
                        stage('Rendering exact Office preview')
                        preview = render_office_preview(path, Path(folder) / 'precision-preview')
                        preview_path = Path(preview['path']).resolve()
                        if not preview_path.is_relative_to(Path(folder).resolve()):
                            raise DomainError('EXPORT_BOUNDARY', 'Preview escaped its output directory.', 500)
                        preview_sha = self.store.put_blob(preview_path.read_bytes())
                        export['preview_digest'] = preview_sha
                        export['preview_origin'] = 'office_artifact_pdf'
                        export['manifest']['precision_preview'] = {k: v for k, v in preview.items() if k != 'path'}
                    except Exception as exc:
                        export['manifest'].setdefault('warnings', []).append({
                            'code': 'PRECISION_PREVIEW_UNAVAILABLE',
                            'message': 'The Office export is available; its precision preview could not be rendered.',
                            'detail': str(exc)[:300]})
                else:
                    export['manifest'].setdefault('warnings', []).append({
                        'code': 'PRECISION_PREVIEW_UNAVAILABLE',
                        'message': 'Configure FOUNDRY_SOFFICE to enable PDF previews of the actual Office file.'})
            self.store.finish(job['id'], job['token'], result={'export_id': export['id']}, records=[('export', export)])

    def bootstrap(self):
        return {'report_types': self.store.list('report_type'), 'programs': self.store.list('program'),
                'snapshots': self.store.list('snapshot'), 'assets': self.store.list('asset'), 'jobs': self.store.jobs(),
                'capabilities': {'formats': ['docx', 'xlsx', 'pdf', 'pptx'], 'learning': False,
                    'runtime': 'trusted_regional_revenue', 'native_pivot': 'structural_verified_target_certification_pending',
                    'deployment': 'single_user_local', 'uploads': ['csv', 'xlsx', 'docx', 'pdf']}, 'demo': True}
