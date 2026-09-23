"""Durable single-process run/event journal, separate from business source tables."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

TERMINAL = {'completed', 'partial', 'failed', 'cancelled', 'timed_out', 'interrupted'}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        database = sqlite3.connect(self.path, timeout=5)
        database.row_factory = sqlite3.Row
        try:
            with database:
                yield database
        finally:
            database.close()

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as database:
            database.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS agent_run (
                    run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, task_id TEXT,
                    question TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS agent_event (
                    run_id TEXT NOT NULL, event_id INTEGER NOT NULL, event_type TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(run_id,event_id));
                CREATE INDEX IF NOT EXISTS agent_conversation ON agent_run(conversation_id,created_at);
            ''')
            interrupted = database.execute("SELECT run_id FROM agent_run WHERE status IN ('queued','running')").fetchall()
        for row in interrupted:
            self.finish(row['run_id'], 'interrupted', {'answer': '服务重启，分析已中断，请重新发起。'})

    def create(self, request):
        run_id = str(uuid4())
        conversation_id = request.conversation_id or str(uuid4())
        with self.connect() as database:
            database.execute('INSERT INTO agent_run VALUES(?,?,?,?,?,?,?)', (
                run_id, conversation_id, request.task_id, request.question, 'queued', timestamp(), '{}'))
        return self.get(run_id)

    def get(self, run_id):
        with self.connect() as database:
            row = database.execute('SELECT * FROM agent_run WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return {**dict(row), 'result': json.loads(row['result'])}

    def mark_running(self, run_id):
        with self.connect() as database:
            database.execute("UPDATE agent_run SET status='running' WHERE run_id=? AND status='queued'", (run_id,))

    def append(self, run_id, event_type, payload):
        with self.connect() as database:
            # IMMEDIATE serializes event IDs and terminal transitions.
            database.execute('BEGIN IMMEDIATE')
            status = database.execute('SELECT status FROM agent_run WHERE run_id=?', (run_id,)).fetchone()
            if status is None or status['status'] in TERMINAL:
                return
            self._append(database, run_id, event_type, payload)

    @staticmethod
    def _append(database, run_id, event_type, payload):
        sequence = database.execute('SELECT COALESCE(MAX(event_id),0)+1 FROM agent_event WHERE run_id=?', (run_id,)).fetchone()[0]
        database.execute('INSERT INTO agent_event VALUES(?,?,?,?)', (
            run_id, sequence, event_type, json.dumps({'run_id': run_id, 'time': timestamp(), **payload}, ensure_ascii=False, default=str)))

    def finish(self, run_id, status, result):
        if status not in TERMINAL:
            raise ValueError('Invalid terminal state')
        with self.connect() as database:
            database.execute('BEGIN IMMEDIATE')
            row = database.execute('SELECT status FROM agent_run WHERE run_id=?', (run_id,)).fetchone()
            if row is None or row['status'] in TERMINAL:
                return
            self._append(database, run_id, 'run_finished', {'status': status, 'result': result})
            database.execute('UPDATE agent_run SET status=?,result=? WHERE run_id=?', (
                status, json.dumps(result, ensure_ascii=False, default=str), run_id))

    def events(self, run_id, after=0):
        with self.connect() as database:
            rows = database.execute('SELECT * FROM agent_event WHERE run_id=? AND event_id>? ORDER BY event_id', (run_id, after)).fetchall()
        return [{**dict(row), 'payload': json.loads(row['payload'])} for row in rows]

    def history(self, conversation_id, task_id, exclude_run_id):
        with self.connect() as database:
            rows = database.execute('''SELECT question FROM agent_run
                WHERE conversation_id=? AND task_id IS ? AND run_id!=?
                AND status IN ('completed','partial') ORDER BY created_at DESC LIMIT 3''',
                (conversation_id, task_id, exclude_run_id)).fetchall()
        # Retain questions only: past generated answers are not authoritative evidence.
        return [row['question'][:500] for row in reversed(rows)]
