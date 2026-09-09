"""Single-user durable catalog and immutable content store.

SQLite transactions fence worker publication. Files can be orphaned by a crash,
but no orphan is visible without a committed catalog reference.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from .errors import DomainError


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid4().hex[:20]}"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = self.root / 'objects'
        self.objects.mkdir(exist_ok=True)
        self.db = self.root / 'catalog.sqlite3'
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS entities (
                kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                PRIMARY KEY(kind,id)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, scope TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]', result TEXT, error TEXT,
                token TEXT, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(scope,idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS audit (
                id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, action TEXT NOT NULL,
                data TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS job_queue ON jobs(status,lease_until,created_at);
            CREATE INDEX IF NOT EXISTS audit_subject ON audit(subject_id,created_at);
            ''')

    def connect(self):
        db = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put_blob(self, data: bytes):
        sha = digest(data)
        path = self.objects / sha[:2] / sha
        path.parent.mkdir(exist_ok=True)
        if path.is_symlink():
            raise DomainError('ARTIFACT_INVALID', 'Object storage path is a symlink.', 409)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError:
            self.read_blob(sha)
        else:
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            path.chmod(0o400)
        return sha

    def blob_path(self, sha):
        if not re.fullmatch('[a-f0-9]{64}', sha):
            raise DomainError('ARTIFACT_INVALID', 'Invalid artifact digest.', 422)
        path = self.objects / sha[:2] / sha
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise DomainError('ARTIFACT_MISSING', 'The immutable artifact is unavailable.', 404)
        return path

    def read_blob(self, sha):
        data = self.blob_path(sha).read_bytes()
        if digest(data) != sha:
            raise DomainError('ARTIFACT_INTEGRITY', 'Artifact bytes do not match their recorded digest.', 409)
        return data

    def insert(self, kind, record, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.insert(kind, record, conn)
        try:
            db.execute('INSERT INTO entities(kind,id,data,created_at) VALUES(?,?,?,?)',
                       (kind, record['id'], canonical(record).decode(), record.get('created_at', now())))
        except sqlite3.IntegrityError as exc:
            raise DomainError('VERSION_CONFLICT', 'This record already exists.', 409) from exc
        return record

    def get(self, kind, id, db=None):
        if db is None:
            with self.connect() as conn:
                return self.get(kind, id, conn)
        row = db.execute('SELECT data FROM entities WHERE kind=? AND id=?', (kind, id)).fetchone()
        if not row:
            raise DomainError('NOT_FOUND', f'{kind.replace("_", " ").capitalize()} not found.', 404)
        return json.loads(row['data'])

    def list(self, kind):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                'SELECT data FROM entities WHERE kind=? ORDER BY created_at DESC,id', (kind,))]

    def update(self, kind, id, record, db=None):
        if kind in {'snapshot', 'asset', 'export', 'release', 'example'}:
            raise DomainError('IMMUTABLE_RECORD', f'{kind} records cannot be overwritten.', 409)
        if db is None:
            with self.transaction() as conn:
                return self.update(kind, id, record, conn)
        cursor = db.execute('UPDATE entities SET data=?,version=version+1 WHERE kind=? AND id=?',
                            (canonical(record).decode(), kind, id))
        if cursor.rowcount != 1:
            raise DomainError('NOT_FOUND', 'Record not found.', 404)
        return record

    def audit(self, subject, action, data, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.audit(subject, action, data, conn)
        entry = {'id': uid('audit'), 'subject_id': subject, 'action': action, 'data': data, 'created_at': now()}
        db.execute('INSERT INTO audit VALUES(?,?,?,?,?)',
                   (entry['id'], subject, action, canonical(data).decode(), entry['created_at']))
        return entry

    def audit_for(self, subject):
        with self.connect() as db:
            return [{**dict(r), 'data': json.loads(r['data'])} for r in db.execute(
                'SELECT * FROM audit WHERE subject_id=? ORDER BY created_at', (subject,))]

    @staticmethod
    def job_record(row):
        if not row:
            raise DomainError('NOT_FOUND', 'Job not found.', 404)
        result = dict(row)
        for key in ('payload', 'steps', 'result', 'error'):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def job(self, id):
        with self.connect() as db:
            return self.job_record(db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone())

    def jobs(self):
        with self.connect() as db:
            return [self.job_record(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100')]

    def enqueue(self, kind, scope, key, payload, request_identity=None):
        if not key or len(key) > 200:
            raise DomainError('IDEMPOTENCY_INVALID', 'Provide an idempotency key up to 200 characters.')
        sha, timestamp = digest(payload if request_identity is None else request_identity), now()
        with self.transaction() as db:
            existing = db.execute('SELECT * FROM jobs WHERE scope=? AND idempotency_key=?', (scope, key)).fetchone()
            if existing:
                if existing['request_digest'] != sha:
                    raise DomainError('IDEMPOTENCY_CONFLICT', 'This key was already used with different inputs.', 409)
                return self.job_record(existing)
            id = uid('job')
            db.execute('''INSERT INTO jobs(id,kind,scope,idempotency_key,request_digest,payload,status,stage,created_at,updated_at)
                          VALUES(?,?,?,?,?,?,'queued','queued',?,?)''',
                       (id, kind, scope, key, sha, canonical(payload).decode(), timestamp, timestamp))
        return self.job(id)

    def claim(self, lease_seconds=120):
        with self.transaction() as db:
            row = db.execute('''SELECT * FROM jobs WHERE status='queued' OR
                (status='running' AND lease_until<?) ORDER BY created_at LIMIT 1''', (time.time(),)).fetchone()
            if not row:
                return None
            token = uid('lease')
            db.execute("UPDATE jobs SET status='running',token=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=?",
                       (token, time.time() + lease_seconds, now(), row['id']))
            return self.job_record(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())

    def check_lease(self, db, id, token):
        row = db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone()
        if not row or row['status'] != 'running' or row['token'] != token or row['lease_until'] < time.time():
            raise DomainError('LEASE_LOST', 'Job cancelled or its worker lease expired.', 409)
        return row

    def heartbeat(self, id, token):
        with self.transaction() as db:
            self.check_lease(db, id, token)
            db.execute('UPDATE jobs SET lease_until=? WHERE id=?', (time.time() + 120, id))

    def stage(self, id, token, name):
        with self.transaction() as db:
            row = self.check_lease(db, id, token)
            steps = json.loads(row['steps'])
            if not any(s['stage'] == name for s in steps):
                steps.append({'stage': name, 'at': now()})
            db.execute('UPDATE jobs SET stage=?,steps=?,lease_until=?,updated_at=? WHERE id=?',
                       (name, canonical(steps).decode(), time.time() + 120, now(), id))

    def finish(self, id, token, result=None, error=None, records=(), status='completed'):
        with self.transaction() as db:
            self.check_lease(db, id, token)
            for kind, record in records:
                self.insert(kind, record, db)
            db.execute('UPDATE jobs SET status=?,stage=?,result=?,error=?,token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                       (status, status, canonical(result).decode() if result is not None else None,
                        canonical(error).decode() if error else None, now(), id))
            self.audit(id, status, result or error or {}, db)

    def cancel(self, id):
        with self.transaction() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone()
            if not row:
                raise DomainError('NOT_FOUND', 'Job not found.', 404)
            if row['status'] in ('queued', 'running'):
                db.execute("UPDATE jobs SET status='cancelled',stage='cancelled',token=NULL,lease_until=NULL,updated_at=? WHERE id=?", (now(), id))
                self.audit(id, 'cancelled', {}, db)
        return self.job(id)
