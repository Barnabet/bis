"""Reproducible command-line entry point, also used by the local workbench."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from .storage import Store, now
from .service import Service, ROOT
from .jobs import Worker


def emit(record):
    print(json.dumps(record, indent=2, ensure_ascii=False, default=str))


def seed_demo(service):
    existing = [t for t in service.store.list('report_type') if t.get('demo')]
    if existing:
        return {'report_type': existing[0], 'message': 'Demo already exists. Original records retained.'}
    asset = service.upload((ROOT / 'fixtures' / 'transactions.csv').read_bytes(), 'regional-transactions-demo.csv', demo=True)
    result = service.create_type('Quarterly revenue report', 'Synthetic regional revenue fixture from the supplied architecture. Manually authored policy.', demo=True)
    program = result['program']
    for decision in program['decisions']:
        program = service.resolve(program['id'], decision['id'], decision['alternatives'][0]['value'], program['digest'])
    program = service.evaluate(program['id'], program['digest'])
    if not program['evaluation']['passed']:
        return {'error': 'Demo evaluation failed; candidate remains unpublished.', 'program': program}
    program = service.publish(program['id'], program['digest'], actor='system_fixture_policy_from_specification')
    from .runtime import default_period
    job = service.request_run(result['report_type']['id'], asset['id'], default_period().model_dump(mode='json'), 'initial-synthetic-demo')
    worker = Worker(service)
    while service.store.job(job['id'])['status'] in ('queued', 'running'):
        if not worker.run_one():
            break
    return {'report_type': service.store.get('report_type', result['report_type']['id']),
            'asset': asset, 'program': program, 'job': service.store.job(job['id'])}


def main():
    parser = argparse.ArgumentParser(prog='foundry', description='Local native reporting workbench')
    parser.add_argument('--data-dir', default=os.environ.get('FOUNDRY_DATA_DIR', str(ROOT / '.foundry')))
    commands = parser.add_subparsers(dest='command', required=True)
    serve = commands.add_parser('serve', help='Serve the loopback API and built React workbench')
    serve.add_argument('--port', type=int, default=8741)
    serve.add_argument('--no-worker', action='store_true')
    commands.add_parser('seed-demo', help='Evaluate/publish the supplied synthetic reference and generate its native report')
    commands.add_parser('worker', help='Process persisted queued jobs until idle')
    commands.add_parser('status', help='List sources, programs, reports and jobs')
    ingest = commands.add_parser('ingest', help='Inspect and store an immutable input')
    ingest.add_argument('file', type=Path)
    create = commands.add_parser('create-type', help='Create a report type using the trusted revenue adapter')
    create.add_argument('name')
    resolve = commands.add_parser('resolve', help='Record a candidate policy decision')
    resolve.add_argument('program_id'); resolve.add_argument('decision_id'); resolve.add_argument('resolution')
    for operation in ('evaluate', 'publish'):
        sub = commands.add_parser(operation)
        sub.add_argument('program_id')
    run = commands.add_parser('run', help='Generate from explicit period JSON and immutable source')
    run.add_argument('report_type_id'); run.add_argument('asset_id'); run.add_argument('--period', type=Path, required=True)
    run.add_argument('--key', required=True)
    export = commands.add_parser('export', help='Export an existing frozen native snapshot')
    export.add_argument('snapshot_id'); export.add_argument('format', choices=['docx', 'xlsx', 'pdf', 'pptx'])
    export.add_argument('--strict', action='store_true'); export.add_argument('--key', required=True)
    export.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'serve':
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.data_dir, start_worker=not args.no_worker), host='127.0.0.1', port=args.port, log_level='info')
        return
    service = Service(Store(args.data_dir))
    try:
        if args.command == 'seed-demo':
            result = seed_demo(service)
        elif args.command == 'status':
            result = service.bootstrap()
        elif args.command == 'ingest':
            result = service.upload(args.file.read_bytes(), args.file.name)
        elif args.command == 'create-type':
            result = service.create_type(args.name)
        elif args.command == 'resolve':
            p = service.store.get('program', args.program_id)
            result = service.resolve(p['id'], args.decision_id, args.resolution, p['digest'])
        elif args.command in ('evaluate', 'publish'):
            p = service.store.get('program', args.program_id)
            result = getattr(service, args.command)(p['id'], p['digest'])
        elif args.command == 'worker':
            count = 0
            worker = Worker(service)
            while worker.run_one():
                count += 1
            result = {'jobs_processed': count}
        else:
            if args.command == 'run':
                from .contracts import Period
                period = Period.model_validate_json(args.period.read_text()).model_dump(mode='json')
                job = service.request_run(args.report_type_id, args.asset_id, period, args.key)
            else:
                job = service.request_export(args.snapshot_id, args.format, 'strict' if args.strict else 'compatible', args.key)
            worker = Worker(service)
            while service.store.job(job['id'])['status'] == 'queued':
                if not worker.run_one():
                    break
            result = service.store.job(job['id'])
            if args.command == 'export' and args.output and result['status'] == 'completed':
                artifact = service.store.get('export', result['result']['export_id'])
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(service.store.read_blob(artifact['digest']))
                result['output'] = str(args.output.resolve())
        emit(result)
        if result.get('error') or result.get('status') in ('failed', 'blocked'):
            sys.exit(1)
    except Exception as exc:
        emit({'error': getattr(exc, 'as_dict', lambda: {'message': str(exc)})()})
        sys.exit(1)


if __name__ == '__main__':
    main()
