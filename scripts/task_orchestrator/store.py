from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterator

from .model import State, Task, TransitionError, TRANSITIONS, utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL,
  reason TEXT,
  attempt INTEGER NOT NULL DEFAULT 0,
  source_issue INTEGER,
  approved_at TEXT,
  resume_nonce INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT,
  event_type TEXT NOT NULL,
  old_state TEXT,
  new_state TEXT,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
  delivery_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_state (
  source TEXT PRIMARY KEY,
  etag TEXT,
  cursor TEXT,
  backoff_until REAL NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def integrity_check(self) -> None:
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise RuntimeError(f"corrupted local state: {row[0] if row else 'no result'}")

    @staticmethod
    def quarantine_corrupt(path: Path) -> Path:
        target = path.with_name(path.name + ".corrupt." + utc_now().replace(":", ""))
        shutil.copy2(path, target)
        return target

    def append_event(self, task_id: str | None, event_type: str, old: str | None, new: str | None, detail: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "INSERT INTO events(task_id,event_type,old_state,new_state,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (task_id, event_type, old, new, json.dumps(detail or {}, sort_keys=True), utc_now()),
        )

    def ingest(self, task: Task) -> str:
        payload = json.dumps(task.canonical_dict(), sort_keys=True, ensure_ascii=False)
        with self.transaction():
            row = self.conn.execute("SELECT payload_hash,state FROM tasks WHERE task_id=?", (task.task_id,)).fetchone()
            if row:
                if row["payload_hash"] != task.payload_hash:
                    self.append_event(task.task_id, "IDENTITY_CONFLICT", row["state"], row["state"], {"incoming_hash": task.payload_hash})
                    raise TransitionError(f"task_id {task.task_id} already exists with a different payload")
                self.append_event(task.task_id, "DUPLICATE_DELIVERY", row["state"], row["state"], {"payload_hash": task.payload_hash})
                return "duplicate"
            now = utc_now()
            self.conn.execute(
                "INSERT INTO tasks(task_id,payload_hash,payload_json,state,source_issue,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (task.task_id, task.payload_hash, payload, State.RECEIVED.value, task.source_issue, now, now),
            )
            self.append_event(task.task_id, "INGESTED", None, State.RECEIVED.value, {"payload_hash": task.payload_hash})
        return "created"

    def transition(self, task_id: str, new_state: State, reason: str, *, force_recovery: bool = False) -> None:
        with self.transaction():
            row = self.conn.execute("SELECT state FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                raise TransitionError(f"unknown task: {task_id}")
            old = State(row["state"])
            if new_state == old:
                return
            if not force_recovery and new_state not in TRANSITIONS.get(old, set()):
                raise TransitionError(f"invalid transition {old.value} -> {new_state.value}")
            self.conn.execute("UPDATE tasks SET state=?,reason=?,updated_at=? WHERE task_id=?", (new_state.value, reason, utc_now(), task_id))
            self.append_event(task_id, "TRANSITION", old.value, new_state.value, {"reason": reason, "recovery": force_recovery})

    def approve(self, task_id: str) -> None:
        with self.transaction():
            row = self.conn.execute("SELECT state FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                raise TransitionError(f"unknown task: {task_id}")
            self.conn.execute("UPDATE tasks SET approved_at=?,updated_at=? WHERE task_id=?", (utc_now(), utc_now(), task_id))
            self.append_event(task_id, "LOCAL_APPROVAL", row["state"], row["state"], {})

    def resume(self, task_id: str) -> None:
        row = self.get(task_id)
        if not row or row["state"] != State.PAUSED_QUOTA.value:
            raise TransitionError("resume is permitted only from PAUSED_QUOTA")
        with self.transaction():
            self.conn.execute("UPDATE tasks SET resume_nonce=resume_nonce+1,updated_at=? WHERE task_id=?", (utc_now(), task_id))
            self.conn.execute("UPDATE tasks SET state=?,reason=? WHERE task_id=?", (State.WAITING_APPROVAL.value, "explicit resume requested", task_id))
            self.append_event(task_id, "EXPLICIT_RESUME", State.PAUSED_QUOTA.value, State.WAITING_APPROVAL.value, {})

    def increment_attempt(self, task_id: str) -> int:
        with self.transaction():
            self.conn.execute("UPDATE tasks SET attempt=attempt+1,updated_at=? WHERE task_id=?", (utc_now(), task_id))
            return int(self.conn.execute("SELECT attempt FROM tasks WHERE task_id=?", (task_id,)).fetchone()[0])

    def get(self, task_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()

    def task(self, row: sqlite3.Row) -> Task:
        value = json.loads(row["payload_json"])
        return Task(**{**value, "dependencies": tuple(value["dependencies"]), "allowed_paths": tuple(value["allowed_paths"]), "expected_artifacts": tuple(value["expected_artifacts"]), "labels": tuple(value["labels"])})

    def list_state(self, *states: State) -> list[sqlite3.Row]:
        if not states:
            return list(self.conn.execute("SELECT * FROM tasks ORDER BY created_at,task_id"))
        marks = ",".join("?" for _ in states)
        return list(self.conn.execute(f"SELECT * FROM tasks WHERE state IN ({marks}) ORDER BY created_at,task_id", tuple(s.value for s in states)))

    def dependency_states(self, task: Task) -> dict[str, str | None]:
        result = {}
        for dep in task.dependencies:
            row = self.get(dep)
            result[dep] = row["state"] if row else None
        return result

    def event_count(self, task_id: str, event_type: str) -> int:
        return int(self.conn.execute("SELECT count(*) FROM events WHERE task_id=? AND event_type=?", (task_id, event_type)).fetchone()[0])

    def events(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM events ORDER BY event_id")]

    def source(self, name: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM source_state WHERE source=?", (name,)).fetchone()
        return dict(row) if row else {"source": name, "etag": None, "cursor": None, "backoff_until": 0, "failures": 0}

    def update_source(self, name: str, *, etag: str | None, backoff_until: float, failures: int) -> None:
        self.conn.execute(
            "INSERT INTO source_state(source,etag,backoff_until,failures,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET etag=excluded.etag,backoff_until=excluded.backoff_until,failures=excluded.failures,updated_at=excluded.updated_at",
            (name, etag, backoff_until, failures, utc_now()),
        )
