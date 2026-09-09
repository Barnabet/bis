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


def candidate_reason(value):
    value = value.strip()
    if not 1 <= len(value) <= 1000:
        raise argparse.ArgumentTypeError('Provide a reason between 1 and 1,000 characters.')
    return value


def seed_demo(service):
    existing = [t for t in service.store.list('report_type') if t.get('demo')]
    if existing:
        return {'report_type': existing[0], 'message': 'Demo already exists. Original records retained.'}
    asset = service.upload((ROOT / 'fixtures' / 'transactions.csv').read_bytes(), 'regional-transactions-demo.csv', demo=True)
    image_asset = service.upload((ROOT / 'fixtures' / 'report-image.png').read_bytes(), 'report-image-demo.png', demo=True)
    result = service.create_type('Quarterly revenue report', 'Synthetic regional revenue fixture from the supplied architecture. Manually authored policy.', demo=True)
    program = result['program']
    for decision in program['decisions']:
        program = service.resolve(program['id'], decision['id'], decision['alternatives'][0]['value'], program['digest'])
    program = service.evaluate(program['id'], program['digest'])
    if not program['evaluation']['passed']:
        return {'error': 'Demo evaluation failed; candidate remains unpublished.', 'program': program}
    program = service.publish(program['id'], program['digest'], actor='system_fixture_policy_from_specification')
    from .runtime import default_period
    job = service.request_run(result['report_type']['id'], asset['id'], default_period().model_dump(mode='json'), 'initial-synthetic-demo',
                              image={'asset_id': image_asset['id'], 'alt_text': 'Report Foundry wordmark with three green bars.', 'decorative': False})
    worker = Worker(service)
    while service.store.job(job['id'])['status'] in ('queued', 'running'):
        if not worker.run_one():
            break
    return {'report_type': service.store.get('report_type', result['report_type']['id']),
            'asset': asset, 'image_asset': image_asset, 'program': program, 'job': service.store.job(job['id'])}


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
    commands.add_parser('model-status', help='Show provider readiness and budgets without exposing credentials')
    example = commands.add_parser('add-example', help='Pair a historical DOCX/PDF report with a transaction source')
    example.add_argument('report_type_id'); example.add_argument('report_asset_id'); example.add_argument('source_asset_id')
    example.add_argument('--period', type=Path, required=True)
    example.add_argument('--role', choices=['authoring', 'development', 'reserved'], required=True)
    example.add_argument('--label', default=''); example.add_argument('--caveats', default='')
    examples = commands.add_parser('examples', help='Inspect permitted examples and reserved metadata')
    examples.add_argument('report_type_id')
    reveal = commands.add_parser('reveal-example', help='Permanently promote a reserved pair to development evidence')
    reveal.add_argument('example_id'); reveal.add_argument('--reason', required=True, type=candidate_reason)
    learn = commands.add_parser('learn', help='Investigate three executable selection policies against paired examples')
    learn.add_argument('program_id'); learn.add_argument('--key', required=True)
    learn.add_argument('--requirements', default=''); learn.add_argument('--engine', choices=['deterministic', 'openai'], default='deterministic')
    coverage = commands.add_parser('exclude-region', help='Record an explicit, reasoned exclusion from historical reconstruction')
    coverage.add_argument('program_id'); coverage.add_argument('coverage_id')
    coverage.add_argument('--reason', required=True, type=candidate_reason)
    compose = commands.add_parser('compose', help='Draft fact-bound commentary as a new reviewable revision')
    compose.add_argument('snapshot_id'); compose.add_argument('--source', action='append', default=[])
    compose.add_argument('--objective', required=True); compose.add_argument('--key', required=True)
    ingest = commands.add_parser('ingest', help='Inspect and store an immutable input')
    ingest.add_argument('file', type=Path)
    create = commands.add_parser('create-type', help='Create a report type using the trusted revenue adapter')
    create.add_argument('name')
    for operation, help_text in (
        ('create-candidate', 'Start the next program version within an existing report type'),
        ('discard-candidate', 'Discard an unpublished candidate while preserving the active release'),
    ):
        candidate = commands.add_parser(operation, help=help_text)
        candidate.add_argument('program_id')
        candidate.add_argument('--reason', required=True, type=candidate_reason)
    resolve = commands.add_parser('resolve', help='Record a candidate policy decision')
    resolve.add_argument('program_id'); resolve.add_argument('decision_id'); resolve.add_argument('resolution')
    for operation in ('evaluate', 'publish'):
        sub = commands.add_parser(operation)
        sub.add_argument('program_id')
    run = commands.add_parser('run', help='Generate from explicit period JSON and immutable source')
    run.add_argument('report_type_id'); run.add_argument('asset_id'); run.add_argument('--period', type=Path, required=True)
    run.add_argument('--key', required=True)
    run.add_argument('--image-asset', help='Optional inspected PNG/JPEG asset ID')
    run.add_argument('--image-alt', default='', help='Description required for a non-decorative image')
    run.add_argument('--image-decorative', action='store_true', help='Explicitly mark the optional image decorative')
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
        elif args.command == 'model-status':
            from .model_provider import status
            result = status()
        elif args.command == 'add-example':
            from .contracts import Period
            period = Period.model_validate_json(args.period.read_text()).model_dump(mode='json')
            result = service.add_example(args.report_type_id, args.report_asset_id, [args.source_asset_id], period,
                                         args.role, args.label, args.caveats)
        elif args.command == 'examples':
            result = {'examples': service.examples(args.report_type_id)}
        elif args.command == 'reveal-example':
            result = service.reveal_example(args.example_id, args.reason)
        elif args.command == 'exclude-region':
            p = service.store.get('program', args.program_id)
            result = service.review_coverage(p['id'], p['digest'], args.coverage_id, 'out_of_scope', args.reason)
        elif args.command == 'ingest':
            result = service.upload(args.file.read_bytes(), args.file.name)
        elif args.command == 'create-type':
            result = service.create_type(args.name)
        elif args.command in ('create-candidate', 'discard-candidate'):
            p = service.store.get('program', args.program_id)
            operation = service.create_candidate if args.command == 'create-candidate' else service.discard_candidate
            result = operation(p['id'], p['digest'], args.reason)
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
                image = None
                if args.image_asset:
                    image = {'asset_id': args.image_asset, 'alt_text': args.image_alt, 'decorative': args.image_decorative}
                elif args.image_alt or args.image_decorative:
                    from .errors import DomainError
                    raise DomainError('IMAGE_REQUIRED', 'Provide --image-asset when using image description options.')
                job = service.request_run(args.report_type_id, args.asset_id, period, args.key, image=image)
            elif args.command == 'learn':
                p = service.store.get('program', args.program_id)
                job = service.request_learning(p['id'], p['digest'], args.requirements, args.engine, args.key)
            elif args.command == 'compose':
                snapshot = service.store.get('snapshot', args.snapshot_id)
                job = service.request_composition(snapshot['id'], snapshot['revision'], args.source, args.objective, args.key)
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
