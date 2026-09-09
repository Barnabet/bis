from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
import os
import re
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .contracts import Period, ImageBinding
from .storage import Store, canonical
from .service import Service
from .errors import DomainError
from .jobs import Worker

ROOT = Path(__file__).resolve().parent.parent


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class CreateType(Input):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=1000)

class Evaluate(Input):
    expected_digest: str = Field(pattern=r'^[a-f0-9]{64}$')

class Decision(Evaluate):
    decision_id: str = Field(min_length=1, max_length=100)
    resolution: str = Field(min_length=1, max_length=100)

class CandidateMutation(Evaluate):
    reason: str = Field(min_length=1, max_length=1000)

class Run(Input):
    report_type_id: str
    asset_id: str
    period: Period
    idempotency_key: str = Field(min_length=1, max_length=200)
    image: ImageBinding | None = None

class Export(Input):
    snapshot_id: str
    format: Literal['docx', 'xlsx', 'pdf', 'pptx']
    policy: Literal['compatible', 'strict'] = 'compatible'
    idempotency_key: str = Field(min_length=1, max_length=200)

class Revision(Input):
    expected_revision: int = Field(ge=1)
    node_id: str
    text: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=500)

class Accept(Input):
    expected_revision: int = Field(ge=1)

class Example(Input):
    report_asset_id: str
    source_asset_ids: list[str] = Field(min_length=1, max_length=20)
    period: Period
    corpus_role: Literal['authoring', 'development', 'reserved']


def create_app(data_dir=None, start_worker=True):
    store = Store(data_dir or os.environ.get('FOUNDRY_DATA_DIR', ROOT / '.foundry'))
    service = Service(store)
    worker = Worker(service)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        worker.close()

    app = FastAPI(title='Report Foundry', version='0.1.0', lifespan=lifespan)
    app.state.service, app.state.worker = service, worker

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        host = request.headers.get('host', '').split(':')[0].strip('[]')
        if host not in ('127.0.0.1', 'localhost', '::1', 'testserver'):
            return JSONResponse({'error': {'code': 'LOCAL_ONLY', 'message': 'This installation only serves loopback requests.'}}, status_code=403)
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            parsed = urlparse(origin)
            # Vite's development proxy preserves its loopback Origin.
            if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
                return JSONResponse({'error': {'code': 'ORIGIN_DENIED', 'message': 'Cross-origin writes are not allowed.'}}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({'error': exc.as_dict()}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        errors = [{'field': '.'.join(str(s) for s in e['loc']), 'message': e['msg']} for e in exc.errors()]
        return JSONResponse({'error': {'code': 'REQUEST_INVALID', 'message': 'Check the request fields.', 'details': errors}}, status_code=422)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'mode': 'single_user_local', 'version': '0.1.0'}

    @app.get('/api/bootstrap')
    def bootstrap():
        return service.bootstrap()

    @app.post('/api/report-types', status_code=201)
    def create_type(body: CreateType):
        return service.create_type(body.name, body.description)

    @app.post('/api/assets', status_code=201)
    async def upload(file: UploadFile = File(...)):
        from .ingestion import MAX_BYTES
        data = await file.read(MAX_BYTES + 1)
        return service.upload(data, file.filename or 'upload')

    @app.get('/api/assets/{id}')
    def asset(id: str):
        return store.get('asset', id)

    @app.get('/api/assets/{id}/download')
    def download_asset(id: str):
        a = store.get('asset', id)
        data = store.read_blob(a['digest'])
        return download(data, a['filename'], a['media_type'])

    @app.get('/api/assets/{id}/preview')
    def image_preview(id: str):
        return Response(service.image_preview(id), media_type='image/png')

    @app.post('/api/report-types/{id}/examples', status_code=201)
    def example(id: str, body: Example):
        return service.add_example(id, body.report_asset_id, body.source_asset_ids, body.period.model_dump(mode='json'), body.corpus_role)

    @app.get('/api/programs/{id}')
    def program(id: str):
        return service.program_view(id)

    @app.get('/api/programs/{id}/package')
    def program_package(id: str):
        release = store.get('release', id)
        data = store.read_blob(release['package_artifact_digest'])
        return download(data, f'program-{release["version"]}-{id}.json', 'application/json')

    @app.post('/api/programs/{id}/candidates', status_code=201)
    def create_candidate(id: str, body: CandidateMutation):
        return service.create_candidate(id, body.expected_digest, body.reason)

    @app.post('/api/programs/{id}/discard')
    def discard_candidate(id: str, body: CandidateMutation):
        return service.discard_candidate(id, body.expected_digest, body.reason)

    @app.post('/api/programs/{id}/evaluate')
    def evaluate(id: str, body: Evaluate):
        return service.evaluate(id, body.expected_digest)

    @app.post('/api/programs/{id}/decisions')
    def resolve(id: str, body: Decision):
        return service.resolve(id, body.decision_id, body.resolution, body.expected_digest)

    @app.post('/api/programs/{id}/publish')
    def publish(id: str, body: Evaluate):
        return service.publish(id, body.expected_digest)

    @app.post('/api/report-runs', status_code=202)
    def run(body: Run):
        job = service.request_run(body.report_type_id, body.asset_id, body.period.model_dump(mode='json'), body.idempotency_key,
                                  image=body.image.model_dump(mode='json') if body.image else None)
        worker.wake.set()
        return job

    @app.get('/api/jobs/{id}')
    def job(id: str):
        return store.job(id)

    @app.post('/api/jobs/{id}/cancel')
    def cancel(id: str):
        return store.cancel(id)

    @app.get('/api/report-snapshots/{id}')
    def snapshot(id: str):
        from .service import validate_stored_snapshot
        r = store.get('snapshot', id)
        validate_stored_snapshot(r)
        return r

    @app.get('/api/report-snapshots/{id}/images/{node_id}')
    def snapshot_image(id: str, node_id: str):
        return Response(service.snapshot_image(id, node_id), media_type='image/png')

    @app.post('/api/report-snapshots/{id}/revisions', status_code=201)
    def revise(id: str, body: Revision):
        return service.revise(id, body.expected_revision, body.node_id, body.text, body.reason)

    @app.post('/api/report-snapshots/{id}/accept')
    def accept(id: str, body: Accept):
        return service.accept(id, body.expected_revision)

    @app.get('/api/report-snapshots/{id}/audit')
    def audit(id: str):
        record = store.get('snapshot', id)
        program = store.get('release', record['program']['id'])
        bundle = {'snapshot': record, 'program': program, 'snapshot_events': store.audit_for(id),
                  'program_events': store.audit_for(program['id']),
                  'exports': [e for e in store.list('export') if e['snapshot_id'] == id],
                  'disclosure': 'Raw source bytes are excluded; references resolve through the local authorized catalog.'}
        return download(canonical(bundle), f'{id}-audit.json', 'application/json')

    @app.post('/api/exports', status_code=202)
    def export(body: Export):
        job = service.request_export(body.snapshot_id, body.format, body.policy, body.idempotency_key)
        worker.wake.set()
        return job

    @app.get('/api/exports')
    def exports(snapshot_id: str | None = None):
        return [e for e in store.list('export') if not snapshot_id or e['snapshot_id'] == snapshot_id]

    @app.get('/api/exports/{id}/download')
    def download_export(id: str):
        export = store.get('export', id)
        return download(store.read_blob(export['digest']), export['filename'], export['media_type'])

    @app.get('/api/exports/{id}/preview')
    def preview_export(id: str):
        export = store.get('export', id)
        if not export.get('preview_digest'):
            raise DomainError('PREVIEW_UNAVAILABLE', 'A precision preview is not available for this export.', 404)
        data = store.read_blob(export['preview_digest'])
        return Response(data, media_type='application/pdf', headers={'Content-Disposition': 'inline'})

    @app.get('/api/exports/{id}/manifest')
    def manifest(id: str):
        return store.get('export', id)['manifest']

    # No user path is joined to storage. StaticFiles handles only the built UI.
    dist = ROOT / 'web' / 'dist'
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='ui-assets')

    @app.get('/{path:path}', include_in_schema=False)
    def ui(path: str):
        if path.startswith('api/'):
            raise DomainError('NOT_FOUND', 'API route not found.', 404)
        index = dist / 'index.html'
        if index.exists():
            return FileResponse(index)
        return JSONResponse({'message': 'Build the workbench with npm --prefix web run build, then reload.', 'api': '/docs'})

    return app


def download(data, filename, media_type):
    from urllib.parse import quote
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    return Response(data, media_type=media_type,
                    headers={'Content-Disposition': f'attachment; filename="{safe}"; filename*=UTF-8\'\'{quote(filename)}'})
