"""Persisted local job worker with heartbeat, fencing and cancellation."""
from __future__ import annotations
import logging
import threading
from .errors import DomainError

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, service):
        self.service = service
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def start(self):
        if not self.thread:
            self.thread = threading.Thread(target=self.loop, name='foundry-worker', daemon=True)
            self.thread.start()
        return self

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=3)

    def loop(self):
        while not self.stop_event.is_set():
            if not self.run_one():
                self.wake.wait(0.4)
                self.wake.clear()

    def run_one(self):
        job = self.service.store.claim()
        if not job:
            return False
        heartbeat_done = threading.Event()
        def heartbeat():
            while not heartbeat_done.wait(20):
                try:
                    self.service.store.heartbeat(job['id'], job['token'])
                except DomainError:
                    return
        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()
        def stage(name):
            self.service.store.stage(job['id'], job['token'], name)
        try:
            if job['kind'] == 'generation':
                self.service.execute_generation(job, stage)
            elif job['kind'] == 'export':
                self.service.execute_export(job, stage)
            else:
                raise DomainError('JOB_UNKNOWN', 'Unknown worker operation.', 500)
        except Exception as exc:
            code = getattr(exc, 'code', 'EXECUTION_FAILED')
            findings = getattr(exc, 'findings', None)
            if findings:
                first = findings[0]
                code = first.get('code', code) if isinstance(first, dict) else first.code
                message = first.get('message', str(exc)) if isinstance(first, dict) else first.message
                details = [f if isinstance(f, dict) else f.model_dump(mode='json') for f in findings]
            else:
                message = getattr(exc, 'message', str(exc))
                details = getattr(exc, 'details', None)
            if code != 'LEASE_LOST':
                known = isinstance(exc, DomainError) or findings or hasattr(exc, 'code')
                error = {'code': code, 'message': message if known else 'The operation failed. Details are recorded in the local server log.'}
                if details:
                    error['details'] = details
                if not known:
                    log.exception('Job %s failed', job['id'])
                try:
                    self.service.store.finish(job['id'], job['token'], error=error, status='blocked' if known else 'failed')
                except DomainError:
                    pass  # Cancelled or a newer worker now owns this job.
        finally:
            heartbeat_done.set()
        return True
