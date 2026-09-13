"""Application-owned lifecycle. No model or uploaded code controls publication."""
from __future__ import annotations
import copy
from pathlib import Path
import platform
import re
import tempfile
from .storage import Store, digest, canonical, now, uid
from .errors import DomainError
from .ingestion import inspect_asset, transaction_rows
from .authoring import AuthoringMixin

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
    fields = {k: program[k] for k in ('code_identity', 'policy', 'decisions', 'input_contract', 'version')}
    # Preserve the identities of releases created before lineage was introduced.
    if 'lineage' in program:
        fields['lineage'] = program['lineage']
    if 'learning' in program:
        fields['learning'] = program['learning']
    return digest(fields)


# Disk hashes alone cannot describe modules already imported by a running worker.
# A restart is required before newly installed code can be evaluated or executed.
PROCESS_CODE_IDENTITY = code_identity()


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


class Service(AuthoringMixin):
    def __init__(self, store: Store):
        self.store = store

    def _installed_code_identity(self):
        installed = code_identity()
        if installed != PROCESS_CODE_IDENTITY:
            raise DomainError('RUNTIME_RESTART_REQUIRED',
                              'Backend files changed while this process was running. Restart the server or worker before continuing.', 409)
        return installed

    @staticmethod
    def _reason(reason):
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise DomainError('REASON_REQUIRED', 'Provide a reason between 1 and 1000 characters.')
        return reason.strip()

    def upload(self, data, filename, demo=False, public_family=None):
        if public_family:
            from .public_reports import inspect_upload
            inspected = inspect_upload(data, filename, public_family)
        else:
            inspected = inspect_asset(data, filename, render_sink=self.store.put_blob)
        sha = self.store.put_blob(data)
        record = {'id': uid('asset'), **inspected, 'digest': sha, 'created_at': now(), 'demo': demo}
        self.store.insert('asset', record)
        self.store.audit(record['id'], 'uploaded', {'digest': sha, 'filename': record['filename']})
        return self.asset_view(record['id'])

    @staticmethod
    def _declare_image_support(program):
        if program['policy']['adapter'] != 'quarterly-revenue-v1':
            return
        program['input_contract']['optional_image'] = {
            'role': 'report_image', 'formats': ['png', 'jpg', 'jpeg'], 'max_count': 1,
            'max_bytes': 20 * 1024 * 1024, 'max_pixels': 16_000_000, 'max_edge_px': 8192,
            'render_format': 'image/png', 'alt_text_required_unless_decorative': True,
        }
        program['policy']['image_handling'] = 'frozen_sanitized_png_with_user_description'
        if not any(c['id'] == 'report_image' for c in program['coverage']):
            program['coverage'].append({'id': 'report_image', 'label': 'Optional image with frozen provenance',
                                        'kind': 'image', 'status': 'implemented'})

    def image_preview(self, asset_id):
        from .images import verify_render_image
        asset = self._guard_asset(self.store.get('asset', asset_id))
        image = asset['profile'].get('image')
        if 'report_image' not in asset['profile'].get('eligible_roles', []) or not image:
            raise DomainError('IMAGE_REQUIRED', 'This source is not a supported report image.', 422)
        return verify_render_image(self.store.read_blob(image['render_digest']), image['render_digest'],
                                   image['width_px'], image['height_px'])

    def snapshot_image(self, snapshot_id, node_id):
        from .contracts import Image
        from .images import verify_render_image
        snapshot = validate_stored_snapshot(self.store.get('snapshot', snapshot_id))
        node = next((n for n in snapshot.nodes if n.id == node_id and isinstance(n, Image)), None)
        if node is None or not node.render_digest:
            raise DomainError('IMAGE_UNAVAILABLE', 'This report has no frozen image for that component.', 404)
        return verify_render_image(self.store.read_blob(node.render_digest), node.render_digest,
                                   node.width_px, node.height_px)

    def _bind_image(self, binding):
        from .contracts import ImageBinding
        from pydantic import ValidationError
        try:
            binding = ImageBinding.model_validate(binding).model_dump(mode='json')
        except ValidationError as exc:
            raise DomainError('IMAGE_BINDING_INVALID', 'Choose an image and describe it, or explicitly mark it decorative.') from exc
        asset = self.store.get('asset', binding['asset_id'])
        info = asset['profile'].get('image')
        if 'report_image' not in asset['profile'].get('eligible_roles', []) or not info:
            raise DomainError('IMAGE_REQUIRED', 'The selected source is not an inspected PNG or JPEG image.')
        self.store.read_blob(asset['digest'])
        self.image_preview(asset['id'])
        return binding, {**binding, 'source_digest': asset['digest'],
                         **{k: info[k] for k in ('render_digest', 'media_type', 'width_px', 'height_px')}}

    def create_type(self, name, description='', demo=False, family='quarterly-revenue-v1'):
        type_id, program_id = uid('type'), uid('program')
        report_type = {'id': type_id, 'name': name, 'description': description, 'active_program_id': None,
                       'created_at': now(), 'demo': demo}
        program = {
            'id': program_id, 'report_type_id': type_id, 'name': f'{name} reporting program', 'version': '1.0.0',
            'state': 'candidate', 'created_at': now(), 'demo': demo, 'code_identity': self._installed_code_identity(),
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
        if family != 'quarterly-revenue-v1':
            from .public_reports import configure_program
            configure_program(program, family)
        self._declare_image_support(program)
        program['digest'] = program_digest(program)
        with self.store.transaction() as db:
            self.store.insert('report_type', report_type, db)
            self.store.insert('program', program, db)
            self.store.audit(type_id, 'report_type_created', {'program_id': program_id}, db)
        return {'report_type': report_type, 'program': program}

    def create_candidate(self, id, expected_digest, reason):
        reason = self._reason(reason)
        installed = self._installed_code_identity()
        with self.store.transaction() as db:
            parent = self.store.get('program', id, db)
            if parent['state'] != 'published':
                raise DomainError('PROGRAM_UNPUBLISHED', 'Create an update from the active published release.', 409)
            if parent['digest'] != expected_digest:
                raise DomainError('VERSION_CONFLICT', 'The base release differs from the version you reviewed.', 409)
            report_type = self.store.get('report_type', parent['report_type_id'], db)
            if report_type['active_program_id'] != id:
                raise DomainError('ACTIVE_RELEASE_CHANGED', 'This release is no longer active. Open the active release to create an update.', 409)
            # Copy the immutable release rather than an incidental UI representation.
            parent = self.store.get('release', id, db)
            if parent['digest'] != expected_digest or program_digest(parent) != expected_digest:
                raise DomainError('PROGRAM_INTEGRITY', 'The frozen base release does not match its recorded identity.', 409)
            versions = [p for p in self.store.list('program', db) if p['report_type_id'] == report_type['id']]
            existing = next((p for p in versions if p['state'] == 'candidate'), None)
            if existing:
                lineage = existing.get('lineage', {})
                if (lineage.get('parent_program_id') == id and
                        lineage.get('parent_program_digest') == expected_digest and lineage.get('reason') == reason):
                    return existing
                raise DomainError('CANDIDATE_EXISTS', 'This report type already has an open update. Open or discard it before creating another.',
                                  409, {'candidate_id': existing['id']})
            numbers = []
            for p in versions:
                if not re.fullmatch(r'\d+\.\d+\.\d+', p['version']):
                    raise DomainError('VERSION_INVALID', 'An existing program has an unsupported version.', 409)
                numbers.append(tuple(int(part) for part in p['version'].split('.')))
            major, minor, _ = max(numbers)
            candidate = copy.deepcopy(parent)
            for field in ('published_at', 'approval', 'package_artifact_digest', 'discard'):
                candidate.pop(field, None)
            candidate.update(id=uid('program'), version=f'{major}.{minor + 1}.0', state='candidate',
                             created_at=now(), code_identity=installed, evaluation=None,
                             lineage={'parent_program_id': id, 'parent_program_digest': expected_digest, 'reason': reason})
            self._declare_image_support(candidate)
            for decision in candidate['decisions']:
                decision['prior_resolution'] = decision['resolution']
                decision['inherited_from'] = {'program_id': id, 'program_digest': expected_digest,
                                              'resolved_at': decision.get('resolved_at')}
                decision['resolution'] = None
                decision.pop('resolved_at', None)
                decision.pop('actor', None)
            for component in candidate['coverage']:
                component['status'] = 'implemented'
            candidate['digest'] = program_digest(candidate)
            self.store.insert('program', candidate, db)
            self.store.audit(candidate['id'], 'candidate_created', {'lineage': candidate['lineage'], 'version': candidate['version'],
                                                                  'actor': 'local_user'}, db)
            self.store.audit(report_type['id'], 'program_update_created', {'program_id': candidate['id'], 'parent_program_id': id}, db)
        return candidate

    def discard_candidate(self, id, expected_digest, reason):
        reason = self._reason(reason)
        with self.store.transaction() as db:
            program = self._candidate(id, expected_digest, db)
            if not program.get('lineage', {}).get('parent_program_id'):
                raise DomainError('INITIAL_CANDIDATE_REQUIRED', 'This report type needs its first candidate. Resolve or refresh it before publication.', 409)
            program['state'] = 'discarded'
            program['discard'] = {'reason': reason, 'actor': 'local_user', 'at': now()}
            self.store.update('program', id, program, db)
            self.store.audit(id, 'candidate_discarded', program['discard'], db)
        return program

    def _candidate(self, id, expected_digest, db):
        program = self.store.get('program', id, db)
        if program['state'] != 'candidate':
            raise DomainError('PROGRAM_IMMUTABLE', 'Only open candidates can be changed. Published and discarded versions are retained.', 409)
        if program['digest'] != expected_digest:
            raise DomainError('VERSION_CONFLICT', 'This candidate changed. Refresh before continuing.', 409)
        if program_digest(program) != program['digest']:
            raise DomainError('PROGRAM_INTEGRITY', 'Candidate content does not match its recorded identity.', 409)
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
            if decision_id == 'selection':
                program['policy']['selection'] = resolution
            program['evaluation'] = None
            for component in program['coverage']:
                component['status'] = 'implemented'
            program['digest'] = program_digest(program)
            self.store.update('program', id, program, db)
            self.store.audit(id, 'policy_resolved', {'decision_id': decision_id, 'resolution': resolution}, db)
        return program

    def evaluate(self, id, expected_digest):
        installed = self._installed_code_identity()
        with self.store.transaction() as db:
            program = self._candidate(id, expected_digest, db)
        if program['code_identity'] != installed:
            # Never carry an old evaluation or approvals across installed code changes.
            with self.store.transaction() as db:
                p = self._candidate(id, expected_digest, db)
                p['code_identity'] = installed
                p['evaluation'] = None
                self._declare_image_support(p)
                for component in p['coverage']:
                    component['status'] = 'implemented'
                for decision in p['decisions']:
                    if decision['resolution']:
                        decision['prior_resolution'] = decision['resolution']
                    decision['resolution'] = None
                    decision.pop('resolved_at', None)
                    decision.pop('actor', None)
                p['digest'] = program_digest(p)
                self.store.update('program', id, p, db)
                self.store.audit(id, 'candidate_code_refreshed', {'previous_digest': expected_digest, 'digest': p['digest']}, db)
            raise DomainError('CODE_CHANGED', 'Installed code changed. The candidate was refreshed; review its policy decisions and evaluate again.', 409)
        from .public_reports import family_of, evaluate_program
        if family_of(program):
            return evaluate_program(self, program)
        from .runtime import prepare, default_period
        from .contracts import Snapshot
        basis = self._evaluation_basis(program)
        fixture = (ROOT / 'fixtures' / 'transactions.csv').read_bytes()
        from .ingestion import rows_from_csv
        _, rows = rows_from_csv(fixture)
        source = {'id': 'fixture_transactions', 'digest': digest(fixture), 'filename': 'transactions.csv'}
        from .images import normalize_image
        image_fixture = (ROOT / 'fixtures' / 'report-image.png').read_bytes()
        image_bytes, image_profile = normalize_image(image_fixture, 'png')
        image_source = {'id': 'fixture_report_image', 'digest': digest(image_fixture), 'filename': 'report-image.png'}
        image_metadata = {k: image_profile[k] for k in ('width_px', 'height_px', 'render_digest', 'media_type')}
        image_metadata.update(asset_id=image_source['id'], alt_text='Report Foundry wordmark with three green bars.', decorative=False)
        snapshot = prepare(rows, default_period(), source, program={k: program[k] for k in ('id', 'version', 'digest')},
                           image_asset=image_source, image_metadata=image_metadata,
                           reporting_policy={'selection': program['policy']['selection']})
        checks = []
        def check(name, passed, detail):
            checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
        facts = snapshot.facts
        from decimal import Decimal
        check('Independent current total', Decimal(facts['revenue.current'].value) == Decimal('1200'), 'Expected EUR 1,200.00 from protected synthetic observations.')
        check('Independent comparison total', Decimal(facts['revenue.comparison'].value) == Decimal('1000'), 'Expected EUR 1,000.00; cancelled/out-of-period rows excluded.')
        expected_driver = {'largest_absolute_change': 'North', 'largest_current_revenue': 'North', 'largest_percentage_change': 'West'}[program['policy']['selection']]
        check('Independent growth and driver', Decimal(facts['revenue.growth'].value) == Decimal('.2') and facts['driver.region'].value == expected_driver,
              f'Expected 20.0% and {expected_driver} under the selected policy, independent of display order.')
        Snapshot.model_validate(snapshot.model_dump())
        check('Native graph and complete views', len(snapshot.views) == 3, 'Fact lineage, dataset types and all three coverage maps validate.')
        image_node = next(n for n in snapshot.nodes if n.kind == 'image')
        check('Frozen image identity and complete coverage',
              image_node.render_digest == digest(image_bytes) and all(image_node.id in v.node_ids for v in snapshot.views),
              'The supplied PNG and its original source identity are bound to every view; image content is not computed evidence.')
        reversed_snapshot = prepare(list(reversed(rows)), default_period(), source,
                                    reporting_policy={'selection': program['policy']['selection']})
        check('Input order invariance', reversed_snapshot.facts['revenue.current'].value == facts['revenue.current'].value and reversed_snapshot.facts['driver.region'].value == facts['driver.region'].value, 'Shuffled transactions preserve totals and selected driver.')
        # Structural render smoke checks are independent of candidate approval.
        from .exporters import export_snapshot
        def resolve_fixture_image(sha):
            if sha != image_profile['render_digest']:
                raise DomainError('IMAGE_INTEGRITY', 'Evaluation requested an unbound image.', 409)
            return image_bytes
        try:
            with tempfile.TemporaryDirectory(prefix='foundry-evaluate-') as folder:
                for format in ('docx', 'xlsx', 'pdf', 'pptx'):
                    output = export_snapshot(snapshot.model_dump(mode='json'), format, Path(folder) / format, policy='compatible',
                                             asset_resolver=resolve_fixture_image)
                    check(f'{format.upper()} export structure', Path(output['path']).is_file() and Path(output['path']).stat().st_size > 100,
                          'Rendered from one frozen snapshot. Native application certification and human visual review are separate.')
        except Exception as exc:
            check('Export capability smoke test', False, str(exc)[:500])
        historical = self._evaluate_examples(program)
        checks.extend(historical['checks'])
        if self._evaluation_basis(program) != basis:
            raise DomainError('EVALUATION_BASIS_CHANGED', 'Evidence changed while evaluation was running; evaluate again.', 409)
        evaluation = {'digest': expected_digest, 'basis_digest': basis, 'passed': all(c['passed'] for c in checks), 'checks': checks,
                      'created_at': now(), 'corpus': 'paired_historical_examples' if program.get('learning') else 'synthetic_development',
                      'holdout_count': historical['holdout_count'], 'reconstruction_count': historical['reconstruction_count'],
                      'image_fixture_digest': digest(image_fixture), 'image_render_digest': digest(image_bytes)}
        with self.store.transaction() as db:
            self._installed_code_identity()
            current = self._candidate(id, expected_digest, db)
            if self._evaluation_basis(current) != basis:
                raise DomainError('EVALUATION_BASIS_CHANGED', 'Evaluation evidence changed during the checks; run evaluation again.', 409)
            current['evaluation'] = evaluation
            for c in current['coverage']:
                c['status'] = 'verified' if evaluation['passed'] else 'implemented'
            self.store.update('program', id, current, db)
            self.store.audit(id, 'evaluated', evaluation, db)
        return current

    def publish(self, id, expected_digest, actor='local_user'):
        with self.store.transaction() as db:
            program = self._candidate(id, expected_digest, db)
            if program['code_identity'] != self._installed_code_identity():
                raise DomainError('CODE_CHANGED', 'Code changed after evaluation. Evaluate a new candidate digest.', 409)
            rt = self.store.get('report_type', program['report_type_id'], db)
            parent_id = program.get('lineage', {}).get('parent_program_id')
            if rt['active_program_id'] != parent_id:
                raise DomainError('ACTIVE_RELEASE_CHANGED', 'The active release changed after this candidate was created. Create an update from the active release.', 409)
            if parent_id:
                parent = self.store.get('release', parent_id, db)
                if parent['digest'] != program['lineage']['parent_program_digest']:
                    raise DomainError('PROGRAM_INTEGRITY', 'The candidate base no longer matches its frozen release.', 409)
            missing = [d['id'] for d in program['decisions'] if not d['resolution']]
            if missing:
                raise DomainError('POLICY_UNRESOLVED', 'Resolve the reporting policy decisions before publication.', 409, missing)
            evaluation = program.get('evaluation')
            if not evaluation or not evaluation['passed'] or evaluation['digest'] != expected_digest:
                raise DomainError('EVALUATION_REQUIRED', 'This exact candidate must pass independent evaluation before publication.', 409)
            if evaluation.get('basis_digest') != self._evaluation_basis(program):
                raise DomainError('EVALUATION_BASIS_CHANGED', 'The evaluated examples or reference fixtures changed. Evaluate the exact current basis before publishing.', 409)
            if any(c['status'] != 'verified' for c in program['coverage']):
                raise DomainError('COVERAGE_INCOMPLETE', 'Required components are not verified.', 409)
            package_files = {}
            for name, expected in program['code_identity']['files'].items():
                content = (ROOT / name).read_bytes()
                if digest(content) != expected:
                    raise DomainError('CODE_CHANGED', 'A package file changed during publication.', 409)
                package_files[name] = content.decode('utf-8')
            package = {'schema_version': '1.0', 'program_digest': expected_digest, 'files': package_files,
                       'program_version': program['version'], 'code_identity': program['code_identity'],
                       'input_contract': program['input_contract'], 'lineage': program.get('lineage'),
                       'policy': program['policy'], 'decisions': program['decisions']}
            if program.get('learning'):
                package['learning'] = program['learning']
            self._installed_code_identity()
            program['package_artifact_digest'] = self.store.put_blob(canonical(package))
            program['state'] = 'published'
            program['published_at'] = now()
            program['approval'] = {'actor': actor, 'at': now(), 'digest': expected_digest, 'profile': 'compatible_provisional'}
            self.store.insert('release', copy.deepcopy(program), db)
            self.store.update('program', id, program, db)
            rt['active_program_id'] = id
            self.store.update('report_type', rt['id'], rt, db)
            self.store.audit(id, 'published', program['approval'], db)
            self.store.audit(rt['id'], 'active_release_changed', {'previous_program_id': parent_id, 'program_id': id,
                                                                 'digest': expected_digest, 'actor': actor}, db)
        return program

    def request_run(self, report_type_id, asset_id, period, idempotency_key, image=None):
        report_type = self.store.get('report_type', report_type_id)
        if not report_type['active_program_id']:
            raise DomainError('PROGRAM_UNPUBLISHED', 'Evaluate and publish this report type before generating a period.', 409)
        program = self.store.get('release', report_type['active_program_id'])
        asset = self._guard_asset(self.store.get('asset', asset_id))
        if program['input_contract']['role'] not in asset['profile']['eligible_roles']:
            raise DomainError('INPUT_DRIFT', 'Bind a source inspected for this reporting program’s input role.')
        payload = {'report_type_id': report_type_id, 'program_id': program['id'], 'program_digest': program['digest'],
                   'asset_id': asset_id, 'source_digest': asset['digest'], 'period': period}
        original_request = {'report_type_id': report_type_id, 'asset_id': asset_id, 'period': period}
        if image is not None:
            if not program['input_contract'].get('optional_image'):
                raise DomainError('IMAGE_PROGRAM_UNSUPPORTED', 'Publish an updated program that supports report images before binding one.', 409)
            original_request['image'], payload['image'] = self._bind_image(image)
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

    def execute_generation(self, job, stage):
        from .runtime import prepare, RuntimeBlocked
        payload = job['payload']
        stage('Resolving frozen program')
        program = self.store.get('release', payload['program_id'])
        if program['digest'] != payload['program_digest'] or program['code_identity'] != self._installed_code_identity():
            raise DomainError('CODE_CHANGED', 'The installed runtime differs from the pinned release. Publish a new evaluated candidate.', 409)
        stage('Validating immutable source')
        asset = self._guard_asset(self.store.get('asset', payload['asset_id']))
        if asset['digest'] != payload['source_digest']:
            raise DomainError('SOURCE_INTEGRITY', 'The transaction source differs from the frozen request.', 409)
        from .public_reports import family_of, source_data, prepare as prepare_public
        family = family_of(program)
        rows = (source_data(self.store.read_blob(asset['digest']), asset, family) if family else
                transaction_rows(self.store.read_blob(asset['digest']), asset['profile']))
        image_asset, image_metadata = None, None
        if payload.get('image'):
            stage('Verifying frozen report image')
            bound = payload['image']
            image_asset = self.store.get('asset', bound['asset_id'])
            if image_asset['digest'] != bound['source_digest']:
                raise DomainError('IMAGE_INTEGRITY', 'The image source differs from the frozen request.', 409)
            self.store.read_blob(bound['source_digest'])
            from .images import verify_render_image
            verify_render_image(self.store.read_blob(bound['render_digest']), bound['render_digest'],
                                bound['width_px'], bound['height_px'])
            image_metadata = {k: bound[k] for k in ('asset_id', 'alt_text', 'decorative', 'render_digest',
                                                   'media_type', 'width_px', 'height_px')}
        stage('Preparing facts and shared data')
        runner = (lambda *a, **kw: prepare_public(*a, family=family, **kw)) if family else prepare
        snapshot = runner(rows, payload['period'], source_ref(asset), program={k: program[k] for k in ('id', 'version', 'digest')},
                           report_type_id=payload['report_type_id'], image_asset=source_ref(image_asset) if image_asset else None,
                           image_metadata=image_metadata, reporting_policy={'selection': program['policy']['selection']})
        self._installed_code_identity()
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
        self._installed_code_identity()
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
            output = export_snapshot(model.model_dump(mode='json'), payload['format'], Path(folder), policy=payload['policy'],
                                     asset_resolver=self.store.read_blob)
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

    def _program_view(self, program, report_type, installed, parent=None):
        result = copy.deepcopy(program)
        result['active_program_id'] = report_type['active_program_id']
        result['lifecycle_status'] = ('active' if program['id'] == report_type['active_program_id'] else
                                      'historical' if program['state'] == 'published' else program['state'])
        result['runtime_status'] = ('restart_required' if installed != PROCESS_CODE_IDENTITY else
                                    'current' if program['code_identity'] == installed else 'code_changed')
        result['change_summary'] = None
        if parent:
            before = parent['code_identity']['files']
            after = program['code_identity']['files']
            result['change_summary'] = {
                'added_files': sorted(set(after) - set(before)),
                'removed_files': sorted(set(before) - set(after)),
                'changed_files': sorted(name for name in set(before) & set(after) if before[name] != after[name]),
                'python_changed': parent['code_identity']['python'] != program['code_identity']['python'],
                'policy_changed': parent['policy'] != program['policy'] or parent['input_contract'] != program['input_contract'],
                'decision_review_required': any(not d['resolution'] for d in program['decisions']),
            }
        return result

    def program_view(self, id):
        installed = code_identity()
        with self.store.connect() as db:
            db.execute('BEGIN')
            program = self.store.get('program', id, db)
            report_type = self.store.get('report_type', program['report_type_id'], db)
            parent_id = program.get('lineage', {}).get('parent_program_id')
            parent = self.store.get('release', parent_id, db) if parent_id else None
            return self._program_view(program, report_type, installed, parent)

    def bootstrap(self):
        from .model_provider import status as model_status
        installed = code_identity()
        with self.store.connect() as db:
            # One read transaction keeps active pointers and release labels consistent.
            db.execute('BEGIN')
            report_types = self.store.list('report_type', db)
            by_type = {t['id']: t for t in report_types}
            releases = {p['id']: p for p in self.store.list('release', db)}
            programs = [self._program_view(p, by_type[p['report_type_id']], installed,
                                           releases.get(p.get('lineage', {}).get('parent_program_id')))
                        for p in self.store.list('program', db)]
        return {'report_types': report_types, 'programs': programs,
                'snapshots': self.store.list('snapshot'), 'assets': [self.asset_view(a['id']) for a in self.store.list('asset')], 'jobs': self.store.jobs(),
                'historical_target_asset_ids': [e['report_asset_id'] for e in self.store.list('example')],
                'capabilities': {'formats': ['docx', 'xlsx', 'pdf', 'pptx'], 'learning': 'bounded_regional_policy_search', 'model': model_status(),
                    'runtime': 'trusted_regional_revenue', 'native_pivot': 'structural_verified_target_certification_pending',
                    'deployment': 'single_user_local', 'uploads': ['csv', 'xlsx', 'docx', 'pdf', 'png', 'jpg', 'jpeg'],
                    'images': {'formats': ['png', 'jpg', 'jpeg'], 'max_per_report': 1, 'frozen_png_export': True}}, 'demo': True}
