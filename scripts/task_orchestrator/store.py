from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterator

from .model import State, Task, TransitionError, TRANSITIONS, TERMINAL_STATES, utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  envelope_hash TEXT,
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
CREATE TABLE IF NOT EXISTS issue_snapshots (
  issue_number INTEGER PRIMARY KEY,
  task_id TEXT,
  snapshot_hash TEXT NOT NULL,
  title TEXT NOT NULL,
  body_hash TEXT NOT NULL,
  labels_json TEXT NOT NULL,
  issue_state TEXT NOT NULL,
  comments_count INTEGER NOT NULL,
  github_updated_at TEXT NOT NULL,
  seen_at TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS task_sidecars (
  repository TEXT NOT NULL,
  task_id TEXT NOT NULL,
  envelope_hash TEXT NOT NULL,
  metadata_hash TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(repository,task_id,envelope_hash),
  UNIQUE(repository,task_id)
);
CREATE TABLE IF NOT EXISTS publication_outbox (
  publication_id TEXT PRIMARY KEY,
  repository TEXT NOT NULL,
  task_id TEXT NOT NULL,
  envelope_hash TEXT NOT NULL,
  result_sha256 TEXT NOT NULL,
  target TEXT NOT NULL,
  marker TEXT NOT NULL,
  preview TEXT NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  backoff_until REAL NOT NULL DEFAULT 0,
  reason TEXT,
  remote_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(repository,task_id,envelope_hash,target)
);
CREATE TABLE IF NOT EXISTS chat_health_registry (
  chat_id TEXT PRIMARY KEY,
  record_hash TEXT NOT NULL,
  record_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS authoring_receipts (
  receipt_sha256 TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  envelope_hash TEXT NOT NULL,
  operation_type TEXT NOT NULL,
  lifecycle_disposition TEXT NOT NULL,
  project_progress TEXT NOT NULL,
  human_action_required INTEGER NOT NULL,
  receipt_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS authoring_receipts_task_id
  ON authoring_receipts(task_id);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(tasks)")}
        if "envelope_hash" not in columns:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN envelope_hash TEXT")
        rows = list(self.conn.execute("SELECT task_id,payload_json FROM tasks WHERE envelope_hash IS NULL"))
        for row in rows:
            value = json.loads(row["payload_json"])
            task = Task(**{**value, "dependencies": tuple(value["dependencies"]), "allowed_paths": tuple(value["allowed_paths"]), "expected_artifacts": tuple(value["expected_artifacts"]), "labels": tuple(value["labels"])})
            self.conn.execute("UPDATE tasks SET envelope_hash=? WHERE task_id=?", (task.envelope_hash, row["task_id"]))

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
            row = self.conn.execute("SELECT payload_hash,envelope_hash,payload_json,state,source_issue FROM tasks WHERE task_id=?", (task.task_id,)).fetchone()
            if row:
                if row["envelope_hash"] != task.envelope_hash:
                    self.append_event(task.task_id, "MANUAL_TASK_ENVELOPE_CONFLICT", row["state"], row["state"], {"incoming_envelope_hash": task.envelope_hash, "source_issue": task.source_issue})
                    return "conflict"
                if row["payload_hash"] != task.payload_hash or row["source_issue"] != task.source_issue:
                    previous = json.loads(row["payload_json"])
                    self.conn.execute(
                        "UPDATE tasks SET payload_hash=?,payload_json=?,source_issue=? WHERE task_id=?",
                        (task.payload_hash, payload, task.source_issue, task.task_id),
                    )
                    self.append_event(task.task_id, "ISSUE_METADATA_UPDATED", row["state"], row["state"], {"old_labels": previous.get("labels", []), "new_labels": list(task.labels), "source_issue": task.source_issue})
                    return "metadata_updated"
                self.append_event(task.task_id, "DUPLICATE_DELIVERY", row["state"], row["state"], {"payload_hash": task.payload_hash})
                return "duplicate"
            now = utc_now()
            self.conn.execute(
                "INSERT INTO tasks(task_id,payload_hash,envelope_hash,payload_json,state,source_issue,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (task.task_id, task.payload_hash, task.envelope_hash, payload, State.RECEIVED.value, task.source_issue, now, now),
            )
            self.append_event(task.task_id, "INGESTED", None, State.RECEIVED.value, {"payload_hash": task.payload_hash})
        return "created"

    def task_id_for_issue(self, issue_number: int) -> str | None:
        row = self.conn.execute("SELECT task_id FROM tasks WHERE source_issue=?", (issue_number,)).fetchone()
        return str(row[0]) if row else None

    def record_issue_snapshot(self, issue: Any, task_id: str | None = None) -> tuple[str, list[str]]:
        body_hash = hashlib.sha256(issue.body.encode()).hexdigest()
        labels_json = json.dumps(sorted(issue.labels), ensure_ascii=False)
        with self.transaction():
            row = self.conn.execute("SELECT * FROM issue_snapshots WHERE issue_number=?", (issue.number,)).fetchone()
            if row and row["snapshot_hash"] == issue.snapshot_hash:
                self.conn.execute(
                    "UPDATE issue_snapshots SET task_id=COALESCE(?,task_id),seen_at=? WHERE issue_number=?",
                    (task_id, utc_now(), issue.number),
                )
                return "unchanged", []
            changed: list[str] = []
            if row:
                comparisons = {
                    "title": (row["title"], issue.title),
                    "body": (row["body_hash"], body_hash),
                    "labels": (row["labels_json"], labels_json),
                    "state": (row["issue_state"], issue.state),
                    "comments": (row["comments_count"], issue.comments),
                    "updated_at": (row["github_updated_at"], issue.updated_at),
                }
                changed = [name for name, values in comparisons.items() if values[0] != values[1]]
            now = utc_now()
            self.conn.execute(
                "INSERT INTO issue_snapshots(issue_number,task_id,snapshot_hash,title,body_hash,labels_json,issue_state,comments_count,github_updated_at,seen_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(issue_number) DO UPDATE SET task_id=COALESCE(excluded.task_id,issue_snapshots.task_id),snapshot_hash=excluded.snapshot_hash,title=excluded.title,body_hash=excluded.body_hash,labels_json=excluded.labels_json,issue_state=excluded.issue_state,comments_count=excluded.comments_count,github_updated_at=excluded.github_updated_at,seen_at=excluded.seen_at",
                (issue.number, task_id, issue.snapshot_hash, issue.title, body_hash, labels_json, issue.state, issue.comments, issue.updated_at, now),
            )
            event_task = task_id or (row["task_id"] if row else None)
            self.append_event(event_task, "ISSUE_DISCOVERED" if row is None else "ISSUE_WEB_CHANGE", None, None, {"issue": issue.number, "changed": changed, "state": issue.state, "comments": issue.comments})
            return ("new" if row is None else "changed"), changed

    def pause_for_manual_issue_change(self, task_id: str, reason: str) -> None:
        row = self.get(task_id)
        if not row or row["state"] in {s.value for s in TERMINAL_STATES}:
            return
        target = State.WAITING_APPROVAL
        self.transition(task_id, target, reason, force_recovery=True)

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

    def put_sidecar(self, metadata: dict[str, Any]) -> str:
        from .visibility import sidecar_identity, validate_sidecar
        value = validate_sidecar(metadata)
        repository, task_id, envelope_hash, metadata_hash = sidecar_identity(value)
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self.transaction():
            task_row = self.conn.execute(
                "SELECT envelope_hash FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if task_row and task_row["envelope_hash"] != envelope_hash:
                raise TransitionError(
                    "sidecar envelope hash conflicts with worker task identity"
                )
            row = self.conn.execute(
                "SELECT envelope_hash,metadata_hash FROM task_sidecars WHERE repository=? AND task_id=?",
                (repository, task_id),
            ).fetchone()
            if row and row["envelope_hash"] != envelope_hash:
                raise TransitionError("sidecar task identity conflicts with existing envelope hash")
            if row and row["metadata_hash"] == metadata_hash:
                return "duplicate"
            now = utc_now()
            self.conn.execute(
                "INSERT INTO task_sidecars(repository,task_id,envelope_hash,metadata_hash,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(repository,task_id) DO UPDATE SET metadata_hash=excluded.metadata_hash,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at",
                (repository, task_id, envelope_hash, metadata_hash, payload, now, now),
            )
            self.append_event(task_id, "SIDECAR_CREATED" if row is None else "SIDECAR_UPDATED",
                              None, None, {"repository": repository,
                                           "envelope_hash": envelope_hash,
                                           "metadata_hash": metadata_hash})
            return "created" if row is None else "updated"

    def list_sidecars(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM task_sidecars ORDER BY repository,task_id"
        ))

    def enqueue_publication(self, *, publication_id: str, repository: str, task_id: str,
                            envelope_hash: str, result_sha256: str, target: str,
                            marker: str, preview: str, status: str) -> str:
        with self.transaction():
            identity = self.conn.execute(
                "SELECT publication_id,result_sha256,status FROM publication_outbox "
                "WHERE repository=? AND task_id=? AND envelope_hash=? AND target=?",
                (repository, task_id, envelope_hash, target),
            ).fetchone()
            if identity:
                if identity["result_sha256"] != result_sha256:
                    raise TransitionError("same publication identity has a different RESULT SHA-256")
                if identity["status"] == "PREVIEW" and status == "PENDING":
                    now = utc_now()
                    self.conn.execute(
                        "UPDATE publication_outbox SET status='PENDING',updated_at=? "
                        "WHERE publication_id=? AND status='PREVIEW'",
                        (now, identity["publication_id"]),
                    )
                    self.append_event(task_id, "PUBLICATION_STATUS", "PREVIEW", "PENDING",
                                      {"publication_id": identity["publication_id"],
                                       "reason": "live publishing activated"})
                    return "promoted"
                return "duplicate"
            now = utc_now()
            self.conn.execute(
                "INSERT INTO publication_outbox(publication_id,repository,task_id,envelope_hash,result_sha256,target,marker,preview,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (publication_id, repository, task_id, envelope_hash, result_sha256,
                 target, marker, preview, status, now, now),
            )
            self.append_event(task_id, "PUBLICATION_PREVIEW_CREATED", None, status,
                              {"publication_id": publication_id,
                               "result_sha256": result_sha256, "target": target})
            return "created"

    def publication(self, publication_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM publication_outbox WHERE publication_id=?", (publication_id,)
        ).fetchone()

    def claim_publication(self, publication_id: str, *, now_epoch: float) -> sqlite3.Row | None:
        with self.transaction():
            row = self.publication(publication_id)
            if row is None or row["status"] != "PENDING" or float(row["backoff_until"]) > now_epoch:
                return None
            self.conn.execute(
                "UPDATE publication_outbox SET status='SENDING',attempts=attempts+1,updated_at=? WHERE publication_id=? AND status='PENDING'",
                (utc_now(), publication_id),
            )
            if self.conn.execute("SELECT changes()").fetchone()[0] != 1:
                return None
            return self.publication(publication_id)

    def update_publication(self, publication_id: str, status: str, *,
                           reason: str | None = None, remote_id: str | None = None,
                           backoff_until: float = 0) -> None:
        with self.transaction():
            row = self.publication(publication_id)
            if row is None:
                raise TransitionError("unknown publication")
            self.conn.execute(
                "UPDATE publication_outbox SET status=?,reason=?,remote_id=COALESCE(?,remote_id),backoff_until=?,updated_at=? WHERE publication_id=?",
                (status, reason, remote_id, backoff_until, utc_now(), publication_id),
            )
            self.append_event(row["task_id"], "PUBLICATION_STATUS", row["status"], status,
                              {"publication_id": publication_id, "reason": reason,
                               "remote_id": remote_id})

    def recover_uncertain_publications(self) -> int:
        with self.transaction():
            rows = list(self.conn.execute(
                "SELECT publication_id,task_id FROM publication_outbox WHERE status='SENDING'"
            ))
            for row in rows:
                self.conn.execute(
                    "UPDATE publication_outbox SET status='UNKNOWN',reason=?,updated_at=? WHERE publication_id=?",
                    ("restart during send; reconciliation required", utc_now(), row["publication_id"]),
                )
                self.append_event(row["task_id"], "PUBLICATION_STATUS", "SENDING", "UNKNOWN",
                                  {"publication_id": row["publication_id"],
                                   "reason": "restart during send"})
            return len(rows)

    def put_chat_health(self, record: dict[str, Any]) -> str:
        from .chat_health import health_record_hash, validate_health_record
        value = validate_health_record(record)
        record_hash = health_record_hash(value)
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self.transaction():
            row = self.conn.execute(
                "SELECT record_hash FROM chat_health_registry WHERE chat_id=?", (value["chat_id"],)
            ).fetchone()
            if row and row["record_hash"] == record_hash:
                return "duplicate"
            now = utc_now()
            self.conn.execute(
                "INSERT INTO chat_health_registry(chat_id,record_hash,record_json,observed_at,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(chat_id) DO UPDATE SET record_hash=excluded.record_hash,record_json=excluded.record_json,observed_at=excluded.observed_at,updated_at=excluded.updated_at",
                (value["chat_id"], record_hash, payload, value["observed_at"], now),
            )
            return "created" if row is None else "updated"

    def chat_health(self, chat_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM chat_health_registry WHERE chat_id=?", (chat_id,)
        ).fetchone()

    def put_authoring_receipt(self, receipt: dict[str, Any]) -> str:
        """Append one validated Project-Control authoring receipt.

        Receipts are immutable.  A later operation (for example, an explicit
        REOPEN) is represented by another receipt; history is never rewritten.
        This is a trusted local authority boundary: receipt SHA-256 proves
        integrity, not the identity of an untrusted caller.  TASK payloads and
        remote Issue content must never call this method as self-authorization.
        """
        from .authoring import validate_preflight_receipt

        value = validate_preflight_receipt(receipt, authorizing=True)
        task_id = value["lifecycle_target_task_id"]
        with self.transaction():
            task_row = self.conn.execute(
                "SELECT envelope_hash FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if task_row is None:
                raise TransitionError("authoring receipt target TASK is not locally known")
            if task_row["envelope_hash"] != value["lifecycle_target_envelope_hash"]:
                raise TransitionError("authoring receipt conflicts with TASK envelope identity")
            existing = self.conn.execute(
                "SELECT 1 FROM authoring_receipts WHERE receipt_sha256=?",
                (value["receipt_sha256"],),
            ).fetchone()
            if existing:
                return "duplicate"
            payload = json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            )
            self.conn.execute(
                "INSERT INTO authoring_receipts(receipt_sha256,task_id,envelope_hash,"
                "operation_type,lifecycle_disposition,project_progress,"
                "human_action_required,receipt_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    value["receipt_sha256"], task_id,
                    value["lifecycle_target_envelope_hash"], value["operation_type"],
                    value["lifecycle_disposition"], value["project_progress"],
                    int(value["human_action_required"]), payload, utc_now(),
                ),
            )
            return "created"

    def latest_authoring_receipt(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT receipt_json FROM authoring_receipts WHERE task_id=? "
            "ORDER BY rowid DESC LIMIT 1", (task_id,),
        ).fetchone()
        return json.loads(row["receipt_json"]) if row else None

    def lifecycle_disposition(self, task_id: str) -> str | None:
        receipt = self.latest_authoring_receipt(task_id)
        return str(receipt["lifecycle_disposition"]) if receipt else None

    def is_historical_lifecycle(self, task_id: str, envelope_hash: str) -> bool:
        from .authoring import is_historical_lifecycle_receipt

        receipt = self.latest_authoring_receipt(task_id)
        return bool(receipt and is_historical_lifecycle_receipt(
            receipt, task_id=task_id, envelope_hash=envelope_hash,
        ))
