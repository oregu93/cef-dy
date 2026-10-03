"""M1b deterministic controller, durable leases, quota lane and result recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Protocol
import uuid

import yaml

from .admission import VisibilityHealth
from .engine import Engine
from .github import GitHubCommentTransport
from .model import State, Task, WorkerResult, utc_now
from .publishing import (
    OutboxStatus, Publisher, enqueue_attention_preview,
    enqueue_attention_resolution_preview, enqueue_result_preview,
)
from .policy import task_has_issue_approval
from . import workers
from .routing import (
    ProductionRouter, bootstrap_for_task, resolve_dependency_prompt_material,
    resolve_review_prompt_material,
)
from .ollama import OllamaHelper


RECOVERY_NOT_PROVEN = "NOT_PROVEN"
RECOVERY_ONE_HEALTHY = "ONE_HEALTHY_OBSERVATION"
RECOVERY_PROVEN = "PROVEN"
RECOVERY_PROOF_STATES = {
    RECOVERY_NOT_PROVEN, RECOVERY_ONE_HEALTHY, RECOVERY_PROVEN,
}


M1B_SCHEMA = """
CREATE TABLE IF NOT EXISTS controller_state (
  task_id TEXT PRIMARY KEY,
  state_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS worker_leases (
  task_id TEXT PRIMARY KEY,
  worker_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL UNIQUE,
  claimed_at REAL NOT NULL,
  lease_expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS accepted_results (
  task_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL,
  result_sha256 TEXT NOT NULL,
  result_json TEXT NOT NULL,
  accepted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempt_results (
  attempt_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  result_sha256 TEXT NOT NULL,
  result_json TEXT NOT NULL,
  accepted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dispatch_attempts (
  attempt_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  lane TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  admitted INTEGER NOT NULL DEFAULT 0,
  outcome TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS ai_lane (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  state TEXT NOT NULL,
  next_probe_at REAL,
  reset_at REAL,
  backoff_index INTEGER NOT NULL DEFAULT 0,
  refusal_count INTEGER NOT NULL DEFAULT 0,
  last_refusal TEXT,
  last_success_at TEXT,
  updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO ai_lane(singleton,state,updated_at)
VALUES(1,'AVAILABLE',strftime('%Y-%m-%dT%H:%M:%SZ','now'));
"""

QUOTA_PATTERNS = (
    "usage limit", "quota", "rate limit", "limit reached", "capacity exhausted",
    "too many requests", "credits exhausted",
)

SEMANTIC_RESULT_KEYS = {"status", "summary", "checks", "artifacts", "error"}


def _semantic_result_error(value: Any) -> str | None:
    """Return a deterministic producer-contract error, or None when valid."""
    if not isinstance(value, dict) or set(value) != SEMANTIC_RESULT_KEYS:
        return "semantic result keys invalid"
    if not isinstance(value["status"], str) or not value["status"].strip():
        return "semantic result status must be a non-empty string"
    if not isinstance(value["summary"], str):
        return "semantic result summary must be a string"
    if not isinstance(value["checks"], list):
        return "semantic result checks must be a list"
    if not isinstance(value["artifacts"], list):
        return "semantic result artifacts must be a list"
    if value["error"] is not None and not isinstance(value["error"], str):
        return "semantic result error must be a string or null"
    return None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _epoch_to_utc(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_reset(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _atomic_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


@dataclass(frozen=True)
class Admission:
    status: str
    result: dict[str, Any] | None = None
    reason: str | None = None
    reset_at: float | None = None


class AITransport(Protocol):
    def probe(self) -> Admission: ...
    def execute(self, task: Task, attempt: int) -> Admission: ...


class SubprocessAITransport:
    """Disposable Codex-compatible worker; never owns orchestration state."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.repo = Path(cfg["repository_root"])

    def _run(self, prompt: str) -> Admission:
        command = self.cfg["llm"]["command"]
        state_dir = Path(self.cfg["state_dir"])
        state_dir.mkdir(parents=True, exist_ok=True)
        fd, output_name = tempfile.mkstemp(prefix="ai-result.", suffix=".txt", dir=state_dir)
        os.close(fd)
        output = Path(output_name)
        argv = [part.replace("{output}", str(output)) for part in command["argv"]]
        try:
            proc = subprocess.run(
                argv, cwd=self.repo, input=prompt, text=True, capture_output=True,
                timeout=int(command["timeout_seconds"]), shell=False,
            )
            last_message = output.read_text(encoding="utf-8", errors="replace")
            combined = "\n".join((proc.stdout, proc.stderr, last_message))
        except subprocess.TimeoutExpired as exc:
            return Admission("FAILED_RETRYABLE", reason=f"AI worker timeout after {exc.timeout}s")
        except OSError as exc:
            return Admission("FAILED_RETRYABLE", reason=f"AI worker launch failed: {exc}")
        finally:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        lowered = combined.casefold()
        if proc.returncode != 0 and any(pattern in lowered for pattern in QUOTA_PATTERNS):
            reset = None
            match = re.search(r'"reset(?:s_at|_at)?"\s*:\s*("[^"]+"|[0-9.]+)', combined, re.I)
            if match:
                reset = _parse_reset(match.group(1).strip('"'))
            return Admission("QUOTA_REFUSED", reason=combined[-2000:], reset_at=reset)
        if proc.returncode != 0:
            return Admission("FAILED_RETRYABLE", reason=combined[-2000:] or f"exit {proc.returncode}")
        return Admission("ACCEPTED", result={"text": last_message or combined})

    def probe(self) -> Admission:
        outcome = self._run(self.cfg["llm"]["command"]["probe_prompt"])
        if outcome.status == "ACCEPTED" and "ADMISSION_OK" not in str(outcome.result):
            return Admission("FAILED_RETRYABLE", reason="admission probe returned an unexpected response")
        return outcome

    def execute(self, task: Task, attempt: int) -> Admission:
        envelope = _canonical(task.envelope_dict())
        specialist = ""
        if self.cfg.get("routing", {}).get("enabled"):
            try:
                role = bootstrap_for_task(self.cfg, task.role)
            except (OSError, ValueError) as exc:
                return Admission("FAILED_RETRYABLE", reason=f"specialist bootstrap unavailable: {exc}")
            specialist = (
                "The following text is the exact canonical bootstrap for your specialist role. "
                "Treat it as binding within the task envelope:\n\n" + role.bootstrap_text + "\n"
            )
        try:
            review_material = resolve_review_prompt_material(self.cfg, task)
        except (OSError, UnicodeError, ValueError) as exc:
            return Admission("REVIEW_MATERIAL_INVALID", reason=str(exc))
        try:
            dependency_material = resolve_dependency_prompt_material(self.cfg, task)
        except (OSError, UnicodeError, ValueError, sqlite3.DatabaseError) as exc:
            return Admission("DEPENDENCY_MATERIAL_INVALID", reason=str(exc))
        prompt = (
            "You are a disposable bounded specialist. Do not modify files, run scientific "
            "programs, access holdout/raw data, or change project authority. Complete only the "
            "semantic task below and return a compact JSON object with exactly these typed "
            "fields: status (non-empty string), summary (string), checks (list), artifacts "
            "(list), error (string or null). Do not substitute mappings or strings for the "
            "checks or artifacts lists.\n" + specialist + "TASK envelope:\n" + envelope
            + review_material + dependency_material
        )
        outcome = self._run(prompt)
        if outcome.status != "ACCEPTED":
            return outcome
        text = str((outcome.result or {}).get("text", "")).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return Admission("FAILED_RETRYABLE", reason="AI worker returned non-JSON output")
        schema_error = _semantic_result_error(parsed)
        if schema_error is not None:
            return Admission("RESULT_SCHEMA_REJECTED", reason=f"AI worker result schema invalid: {schema_error}")
        return Admission("ACCEPTED", result=parsed)


class M1bStore:
    def __init__(self, conn: sqlite3.Connection, cfg: dict[str, Any]):
        self.conn = conn
        self.cfg = cfg
        self.conn.executescript(M1B_SCHEMA)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(dispatch_attempts)")}
        if "attempt" not in columns:
            self.conn.execute("ALTER TABLE dispatch_attempts ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1")

    def checkpoint(self, **changes: Any) -> dict[str, Any]:
        task_id = "ORCH-M1B-RELIABILITY-REBUILD-001"
        row = self.conn.execute("SELECT state_json FROM controller_state WHERE task_id=?", (task_id,)).fetchone()
        state = json.loads(row[0]) if row else {
            "TASK_ID": task_id, "CURRENT_PHASE": "READY",
            "CANONICAL_HEAD": None, "CANDIDATE_BRANCH": "orch/m1b-p1",
            "CANDIDATE_WORKTREE": str(self.cfg["repository_root"]), "CURRENT_COMMIT": None,
            "LAST_VERIFIED_CHECKPOINT": None, "NEXT_EXACT_ACTION": "cycle-once",
            "CURRENT_TEST_GATE": "PENDING", "CURRENT_REVIEW_GATE": "PENDING",
            "AI_LANE_STATE": "AVAILABLE", "NEXT_AI_PROBE_AT": None,
            "ACTIVE_WORKER_LEASE": None, "LAST_WORKER_RESULT": None,
            "BLOCKED_TASKS": [], "WAITING_USER_TASKS": [], "HARD_BLOCKERS": [],
            "RECOVERY_PROOF_STATE": RECOVERY_NOT_PROVEN,
            "RECOVERY_FIRST_HEALTHY_AT": None,
            "RECOVERY_LAST_HEALTHY_AT": None,
            "RECOVERY_PROOF_REASON": "recovery proof has not been established",
        }
        state.setdefault("RECOVERY_PROOF_STATE", RECOVERY_NOT_PROVEN)
        state.setdefault("RECOVERY_FIRST_HEALTHY_AT", None)
        state.setdefault("RECOVERY_LAST_HEALTHY_AT", None)
        state.setdefault("RECOVERY_PROOF_REASON", "recovery proof has not been established")
        state.update(changes)
        now = utc_now()
        self.conn.execute(
            "INSERT INTO controller_state(task_id,state_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at",
            (task_id, _canonical(state), now),
        )
        return state

    def recovery_proof(self) -> dict[str, Any]:
        task_id = "ORCH-M1B-RELIABILITY-REBUILD-001"
        row = self.conn.execute(
            "SELECT state_json FROM controller_state WHERE task_id=?", (task_id,),
        ).fetchone()
        try:
            state = json.loads(row[0]) if row else {}
        except (TypeError, json.JSONDecodeError):
            state = {}
        proof_state = str(state.get("RECOVERY_PROOF_STATE", RECOVERY_NOT_PROVEN))
        if proof_state not in RECOVERY_PROOF_STATES:
            proof_state = RECOVERY_NOT_PROVEN
        first = state.get("RECOVERY_FIRST_HEALTHY_AT")
        last = state.get("RECOVERY_LAST_HEALTHY_AT")
        if not isinstance(first, (int, float)):
            first = None
        if not isinstance(last, (int, float)):
            last = None
        return {
            "state": proof_state,
            "first_healthy_at": first,
            "last_healthy_at": last,
            "reason": str(state.get(
                "RECOVERY_PROOF_REASON", "recovery proof has not been established",
            )),
        }

    def update_recovery_proof(
        self, *, live_capable: bool, healthy: bool, now: float,
        poll_interval_seconds: int, reason: str,
    ) -> dict[str, Any]:
        current = self.recovery_proof()
        state = current["state"]
        first = current["first_healthy_at"]
        last = current["last_healthy_at"]

        if not live_capable:
            state, first, last = RECOVERY_NOT_PROVEN, None, None
            reason = "live-capable publication is disabled; recovery proof reset"
        elif not healthy:
            state, first, last = RECOVERY_NOT_PROVEN, None, None
        elif state == RECOVERY_PROVEN:
            last = now
            reason = "healthy post-reconciliation observation preserved durable proof"
        elif state == RECOVERY_ONE_HEALTHY and first is not None:
            if now - float(first) >= max(1, int(poll_interval_seconds)):
                state = RECOVERY_PROVEN
                last = now
                reason = "second healthy post-reconciliation observation completed proof"
            else:
                last = now
                reason = "healthy observation retained; poll interval has not elapsed"
        else:
            state = RECOVERY_ONE_HEALTHY
            first = now
            last = now
            reason = "first healthy post-reconciliation observation recorded"

        self.checkpoint(
            RECOVERY_PROOF_STATE=state,
            RECOVERY_FIRST_HEALTHY_AT=first,
            RECOVERY_LAST_HEALTHY_AT=last,
            RECOVERY_PROOF_REASON=reason,
        )
        return {
            "state": state,
            "first_healthy_at": first,
            "last_healthy_at": last,
            "reason": reason,
        }

    def lane(self) -> dict[str, Any]:
        return dict(self.conn.execute("SELECT * FROM ai_lane WHERE singleton=1").fetchone())

    def claim(self, row: sqlite3.Row, worker_id: str, now: float) -> dict[str, Any] | None:
        attempt_id = str(uuid.uuid4())
        lease_seconds = int(self.cfg["llm"]["lease_seconds"])
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            current = self.conn.execute("SELECT state,attempt FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
            if current is None or current["state"] != State.READY.value:
                self.conn.execute("ROLLBACK")
                return None
            lane = "AI_BOUNDED_SPECIALIST" if self._is_ai(row["task_id"]) else "LOCAL_DETERMINISTIC"
            if self.cfg.get("routing", {}).get("enabled"):
                route = self.conn.execute(
                    "SELECT selected_lane,route_status FROM task_routes WHERE task_id=?", (row["task_id"],)
                ).fetchone()
                if route is None or route["route_status"] != "ROUTED":
                    self.conn.execute("ROLLBACK")
                    return None
                lane = route["selected_lane"]
                is_ai = self._is_ai(row["task_id"])
                if lane == "HUMAN_DECISION" or (lane == "LOCAL_DETERMINISTIC") == is_ai:
                    self.conn.execute("ROLLBACK")
                    return None
                lane_row = self.conn.execute(
                    "SELECT concurrency_limit FROM resource_lanes WHERE lane_id=?", (lane,)
                ).fetchone()
                active_lane = self.conn.execute(
                    "SELECT count(*) FROM worker_leases w JOIN dispatch_attempts d "
                    "ON d.attempt_id=w.attempt_id WHERE d.lane=?", (lane,)
                ).fetchone()[0]
                if lane_row is None or int(active_lane) >= int(lane_row["concurrency_limit"]):
                    self.conn.execute("ROLLBACK")
                    return None
            if lane in {"AI_BOUNDED_SPECIALIST", "WORK_CODEX"}:
                active_ai = self.conn.execute(
                    "SELECT count(*) FROM worker_leases w JOIN dispatch_attempts d "
                    "ON d.attempt_id=w.attempt_id WHERE d.lane IN ('AI_BOUNDED_SPECIALIST','WORK_CODEX')"
                ).fetchone()[0]
                if int(active_ai) >= int(self.cfg["max_concurrent_llm_runs"]):
                    self.conn.execute("ROLLBACK")
                    return None
            try:
                self.conn.execute(
                    "INSERT INTO worker_leases VALUES(?,?,?,?,?)",
                    (row["task_id"], worker_id, attempt_id, now, now + lease_seconds),
                )
            except sqlite3.IntegrityError:
                self.conn.execute("ROLLBACK")
                return None
            self.conn.execute(
                "UPDATE tasks SET state=?,reason=?,updated_at=? WHERE task_id=? AND state=?",
                (State.RUNNING.value, "durable worker lease claimed", utc_now(), row["task_id"], State.READY.value),
            )
            if self.conn.execute("SELECT changes()").fetchone()[0] != 1:
                self.conn.execute("ROLLBACK")
                return None
            self.conn.execute(
                "INSERT INTO dispatch_attempts(attempt_id,task_id,worker_id,lane,attempt,admitted,outcome,started_at,finished_at) "
                "VALUES(?,?,?,?,?,0,NULL,?,NULL)",
                (attempt_id, row["task_id"], worker_id, lane, int(current["attempt"]) + 1, utc_now()),
            )
            self.conn.execute("COMMIT")
            return {"task_id": row["task_id"], "attempt_id": attempt_id,
                    "attempt": int(current["attempt"]) + 1, "worker_id": worker_id,
                    "lane": lane,
                    "lease_expires_at": now + lease_seconds}
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def _is_ai(self, task_id: str) -> bool:
        row = self.conn.execute("SELECT payload_json FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return False
        return json.loads(row[0])["task_type"] in {"llm_semantic", "llm_worker"}

    def mark_admitted(self, attempt_id: str) -> None:
        self.conn.execute("UPDATE dispatch_attempts SET admitted=1 WHERE attempt_id=?", (attempt_id,))

    def reject_result_schema(self, attempt_id: str, reason: str) -> str:
        """Fence a leased attempt whose durable RESULT failed schema validation."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            dispatch = self.conn.execute(
                "SELECT task_id,outcome,finished_at FROM dispatch_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if dispatch is None:
                self.conn.execute("ROLLBACK")
                return "stale"
            if dispatch["finished_at"] is not None:
                self.conn.execute("COMMIT")
                return "duplicate_schema_rejected" if dispatch["outcome"] == "RESULT_SCHEMA_REJECTED" else "stale"
            task_id = dispatch["task_id"]
            lease = self.conn.execute(
                "SELECT 1 FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id)
            ).fetchone()
            task = self.conn.execute("SELECT state FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if lease is None or task is None or task["state"] != State.RUNNING.value:
                self.conn.execute("ROLLBACK")
                return "stale"
            detail = f"RESULT_SCHEMA_REJECTED: {reason}"[:2000]
            self.conn.execute(
                "UPDATE tasks SET state=?,reason=?,attempt=attempt+1,updated_at=? WHERE task_id=?",
                (State.FAILED_RETRYABLE.value, detail, utc_now(), task_id),
            )
            self.conn.execute(
                "DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id)
            )
            self.conn.execute(
                "UPDATE dispatch_attempts SET outcome='RESULT_SCHEMA_REJECTED',finished_at=? "
                "WHERE attempt_id=?", (utc_now(), attempt_id),
            )
            self.conn.execute(
                "INSERT INTO events(task_id,event_type,old_state,new_state,detail_json,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (task_id, "RESULT_SCHEMA_REJECTED", State.RUNNING.value,
                 State.FAILED_RETRYABLE.value,
                 _canonical({"attempt_id": attempt_id, "reason": reason}), utc_now()),
            )
            self.conn.execute("COMMIT")
            return "result_schema_rejected"
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def accept(self, attempt_id: str, result: dict[str, Any]) -> str:
        required = {"schema_version", "task_id", "attempt", "status", "canonical_head",
                    "worker", "started_at", "finished_at", "checks", "artifacts",
                    "error", "retryable"}
        semantic_fields = {"summary", "semantic_verdict", "semantic_error"}
        schema_error = None
        if (not isinstance(result, dict) or not required.issubset(result)
                or set(result) - required - semantic_fields):
            schema_error = "result schema mismatch"
        elif result["schema_version"] != 1 or result["status"] not in {"SUCCEEDED", "FAILED"}:
            schema_error = "result status/schema invalid"
        elif isinstance(result["attempt"], bool) or not isinstance(result["attempt"], int) or result["attempt"] < 1:
            schema_error = "result attempt invalid"
        elif (type(result["retryable"]) is not bool or not isinstance(result["checks"], list)
              or not isinstance(result["artifacts"], list)):
            schema_error = "result field types invalid"
        if schema_error is not None:
            return self.reject_result_schema(attempt_id, schema_error)
        for key in ("task_id", "status", "canonical_head", "worker", "started_at", "finished_at"):
            if not isinstance(result[key], str) or not result[key]:
                return self.reject_result_schema(attempt_id, f"result {key} invalid")
        if result["error"] is not None and not isinstance(result["error"], str):
            return self.reject_result_schema(attempt_id, "result error invalid")
        present_semantic = semantic_fields.intersection(result)
        if present_semantic and present_semantic != semantic_fields:
            return self.reject_result_schema(attempt_id, "semantic result fields must be complete")
        if present_semantic:
            if not isinstance(result["summary"], str):
                return self.reject_result_schema(attempt_id, "result summary invalid")
            if not isinstance(result["semantic_verdict"], str) or not result["semantic_verdict"]:
                return self.reject_result_schema(attempt_id, "result semantic_verdict invalid")
            if result["semantic_error"] is not None and not isinstance(result["semantic_error"], str):
                return self.reject_result_schema(attempt_id, "result semantic_error invalid")
        task_id = str(result["task_id"])
        encoded = _canonical(result)
        result_hash = hashlib.sha256(encoded.encode()).hexdigest()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            task_row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if task_row is None:
                self.conn.execute("ROLLBACK")
                return "stale"
            task = json.loads(task_row["payload_json"])
            if result["canonical_head"] != task["canonical_head"]:
                raise ValueError("result canonical_head mismatch")
            attempt_existing = self.conn.execute(
                "SELECT result_sha256 FROM attempt_results WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if attempt_existing:
                outcome = "duplicate_retryable" if attempt_existing["result_sha256"] == result_hash else "conflict"
                self.conn.execute("COMMIT")
                return outcome
            existing = self.conn.execute("SELECT * FROM accepted_results WHERE task_id=?", (task_id,)).fetchone()
            if existing:
                outcome = "duplicate" if existing["result_sha256"] == result_hash else "conflict"
                self.conn.execute("COMMIT")
                return outcome
            lease = self.conn.execute("SELECT * FROM worker_leases WHERE task_id=?", (task_id,)).fetchone()
            if lease is None or lease["attempt_id"] != attempt_id:
                self.conn.execute("ROLLBACK")
                return "stale"
            authorized = task_row["state"] == State.RUNNING.value
            if task["task_type"] in {"llm_semantic", "llm_worker"}:
                authorized = authorized and self.cfg["llm"]["require_issue_label"] in task.get("labels", [])
                authorized = authorized and (
                    bool(task_row["approved_at"]) or not self.cfg["llm"].get("require_local_approval", True)
                )
            if not authorized:
                self.conn.execute("DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id))
                self.conn.execute(
                    "UPDATE dispatch_attempts SET outcome='AUTHORIZATION_REVOKED',finished_at=? WHERE attempt_id=?",
                    (utc_now(), attempt_id),
                )
                self.conn.execute("COMMIT")
                return "revoked"
            dispatch = self.conn.execute("SELECT attempt FROM dispatch_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if dispatch is None or int(dispatch["attempt"]) != result["attempt"]:
                raise ValueError("result attempt does not match durable dispatch")
            if result["retryable"]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO attempt_results VALUES(?,?,?,?,?)",
                    (attempt_id, task_id, result_hash, encoded, utc_now()),
                )
                self.conn.execute(
                    "UPDATE tasks SET state=?,reason=?,attempt=attempt+1,updated_at=? WHERE task_id=?",
                    (State.FAILED_RETRYABLE.value, result.get("error") or "retryable worker failure", utc_now(), task_id),
                )
                self.conn.execute("DELETE FROM worker_leases WHERE task_id=?", (task_id,))
                self.conn.execute(
                    "UPDATE dispatch_attempts SET outcome=?,finished_at=? WHERE attempt_id=?",
                    (State.FAILED_RETRYABLE.value, utc_now(), attempt_id),
                )
                self.conn.execute("COMMIT")
                return "accepted_retryable"
            status = str(result["status"])
            target = State.SUCCEEDED.value if status == "SUCCEEDED" else State.FAILED.value
            self.conn.execute(
                "INSERT INTO accepted_results VALUES(?,?,?,?,?)",
                (task_id, attempt_id, result_hash, encoded, utc_now()),
            )
            self.conn.execute(
                "UPDATE tasks SET state=?,reason=?,attempt=attempt+1,updated_at=? WHERE task_id=?",
                (target, result.get("error") or "worker result accepted", utc_now(), task_id),
            )
            self.conn.execute("DELETE FROM worker_leases WHERE task_id=?", (task_id,))
            self.conn.execute(
                "UPDATE dispatch_attempts SET outcome=?,finished_at=? WHERE attempt_id=?",
                (target, utc_now(), attempt_id),
            )
            self.conn.execute(
                "INSERT INTO events(task_id,event_type,old_state,new_state,detail_json,created_at) VALUES(?,?,?,?,?,?)",
                (task_id, "RESULT_ACCEPTED", State.RUNNING.value, target,
                 _canonical({"attempt_id": attempt_id, "sha256": result_hash}), utc_now()),
            )
            self.conn.execute("COMMIT")
            return "accepted"
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def quota_refused(self, task_id: str, attempt_id: str, reason: str,
                      reset_at: float | None, now: float) -> str:
        backoffs = self.cfg["llm"]["quota_probe_backoff_seconds"]
        guard = int(self.cfg["llm"]["quota_probe_guard_seconds"])
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            task_row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            lease = self.conn.execute(
                "SELECT * FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id)
            ).fetchone()
            authorized = task_row is not None and lease is not None and task_row["state"] == State.RUNNING.value
            if authorized:
                task = json.loads(task_row["payload_json"])
                authorized = self.cfg["llm"]["require_issue_label"] in task.get("labels", [])
                authorized = authorized and (
                    bool(task_row["approved_at"]) or not self.cfg["llm"].get("require_local_approval", True)
                )
            if not authorized:
                self.conn.execute("DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id))
                self.conn.execute(
                    "UPDATE dispatch_attempts SET outcome='AUTHORIZATION_REVOKED',finished_at=? WHERE attempt_id=?",
                    (utc_now(), attempt_id),
                )
                self.conn.execute("COMMIT")
                return "revoked"
            lane = self.lane()
            index = int(lane["backoff_index"])
            if reset_at is None:
                next_probe = now + int(backoffs[min(index, len(backoffs) - 1)])
                next_index = min(index + 1, len(backoffs) - 1)
            else:
                next_probe = max(now, reset_at) + guard
                next_index = index
            self.conn.execute(
                "UPDATE ai_lane SET state='QUOTA_WAIT',next_probe_at=?,reset_at=?,backoff_index=?,"
                "refusal_count=refusal_count+1,last_refusal=?,updated_at=? WHERE singleton=1",
                (next_probe, reset_at, next_index, reason[-2000:], utc_now()),
            )
            self.conn.execute(
                "UPDATE tasks SET state=?,reason=?,updated_at=? WHERE task_id=?",
                ((State.WAITING_RESOURCE.value if self.cfg.get("routing", {}).get("enabled") else State.QUOTA_WAIT.value), "Work/Codex admission refused; automatic lane retry scheduled", utc_now(), task_id),
            )
            self.conn.execute("DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id))
            self.conn.execute(
                "UPDATE dispatch_attempts SET outcome='QUOTA_REFUSED',finished_at=? WHERE attempt_id=?",
                (utc_now(), attempt_id),
            )
            self.conn.execute("COMMIT")
            return "QUOTA_WAIT"
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def probe_result(self, outcome: Admission, now: float, admission_check: Any = None) -> None:
        if outcome.status == "ACCEPTED":
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "UPDATE ai_lane SET state='AVAILABLE',next_probe_at=NULL,reset_at=NULL,backoff_index=0,last_success_at=?,updated_at=? WHERE singleton=1",
                    (utc_now(), utc_now()),
                )
                states = () if self.cfg.get("routing", {}).get("enabled") else (State.QUOTA_WAIT.value,)
                marks = ",".join("?" for _ in states)
                rows = list(self.conn.execute(f"SELECT * FROM tasks WHERE state IN ({marks})", states)) if states else []
                for row in rows:
                    payload = json.loads(row["payload_json"])
                    authorized = self.cfg["llm"]["require_issue_label"] in payload.get("labels", [])
                    authorized = authorized and (
                        bool(row["approved_at"]) or not self.cfg["llm"].get("require_local_approval", True)
                    )
                    task = Task(**{
                        **payload,
                        "dependencies": tuple(payload["dependencies"]),
                        "allowed_paths": tuple(payload["allowed_paths"]),
                        "expected_artifacts": tuple(payload["expected_artifacts"]),
                        "labels": tuple(payload["labels"]),
                    })
                    visibility_allowed = admission_check is None or admission_check(task)
                    if authorized and visibility_allowed:
                        target = State.READY.value
                        reason = "AI admission probe succeeded; automatic resume"
                    elif authorized:
                        target = State.QUOTA_WAIT.value
                        reason = "AI lane recovered; task resume held by visibility admission gate"
                    else:
                        target = State.WAITING_USER.value
                        reason = "AI authorization missing at quota recovery"
                    self.conn.execute("UPDATE tasks SET state=?,reason=?,updated_at=? WHERE task_id=?",
                                      (target, reason, utc_now(), row["task_id"]))
                self.conn.execute("COMMIT")
            except Exception:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise
        elif outcome.status == "QUOTA_REFUSED":
            self._reschedule_probe(outcome.reason or "quota refused", outcome.reset_at, now)
        else:
            self._reschedule_probe(outcome.reason or "probe unavailable", None, now)

    def _reschedule_probe(self, reason: str, reset_at: float | None, now: float) -> None:
        backoffs = self.cfg["llm"]["quota_probe_backoff_seconds"]
        guard = int(self.cfg["llm"]["quota_probe_guard_seconds"])
        lane = self.lane()
        index = int(lane["backoff_index"])
        next_probe = max(now, reset_at) + guard if reset_at is not None else now + int(backoffs[min(index, len(backoffs) - 1)])
        self.conn.execute(
            "UPDATE ai_lane SET state='QUOTA_WAIT',next_probe_at=?,reset_at=?,backoff_index=?,"
            "refusal_count=refusal_count+1,last_refusal=?,updated_at=? WHERE singleton=1",
            (next_probe, reset_at, min(index + 1, len(backoffs) - 1), reason[-2000:], utc_now()),
        )

    def recover_expired(self, now: float, admission_check: Any = None) -> int:
        rows = list(self.conn.execute("SELECT * FROM worker_leases WHERE lease_expires_at<=?", (now,)))
        for lease in rows:
            accepted = self.conn.execute("SELECT 1 FROM accepted_results WHERE task_id=?", (lease["task_id"],)).fetchone()
            if accepted:
                self.conn.execute("DELETE FROM worker_leases WHERE task_id=?", (lease["task_id"],))
                continue
            dispatch = self.conn.execute("SELECT lane FROM dispatch_attempts WHERE attempt_id=?", (lease["attempt_id"],)).fetchone()
            work_lease = dispatch is not None and dispatch["lane"] in {"WORK_CODEX", "AI_BOUNDED_SPECIALIST"}
            target = (
                State.WAITING_RESOURCE.value if self.cfg.get("routing", {}).get("enabled")
                else State.QUOTA_WAIT.value
            ) if work_lease and self.lane()["state"] == "QUOTA_WAIT" else State.READY.value
            reason = "expired worker lease recovered"
            task_payload = self.conn.execute(
                "SELECT payload_json FROM tasks WHERE task_id=?", (lease["task_id"],)
            ).fetchone()
            if (
                target == State.READY.value and admission_check is not None
                and task_payload is not None
            ):
                value = json.loads(task_payload["payload_json"])
                task = Task(**{
                    **value,
                    "dependencies": tuple(value["dependencies"]),
                    "allowed_paths": tuple(value["allowed_paths"]),
                    "expected_artifacts": tuple(value["expected_artifacts"]),
                    "labels": tuple(value["labels"]),
                })
                if not admission_check(task):
                    target = State.FAILED_RETRYABLE.value
                    reason = "expired worker lease recovered; retry held by visibility admission gate"
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute("DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?", (lease["task_id"], lease["attempt_id"]))
                self.conn.execute(
                    "UPDATE tasks SET state=?,reason=?,updated_at=? WHERE task_id=? AND state=?",
                    (target, reason, utc_now(), lease["task_id"], State.RUNNING.value),
                )
                self.conn.execute(
                    "UPDATE dispatch_attempts SET outcome='LEASE_EXPIRED',finished_at=? WHERE attempt_id=?",
                    (utc_now(), lease["attempt_id"]),
                )
                self.conn.execute("COMMIT")
            except Exception:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise
        return len(rows)

    def cancel_invalid_leases(self) -> int:
        rows = list(self.conn.execute(
            "SELECT l.task_id,l.attempt_id FROM worker_leases l JOIN tasks t USING(task_id) "
            "WHERE t.state<>?", (State.RUNNING.value,)
        ))
        if not rows:
            return 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                self.conn.execute("DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?",
                                  (row["task_id"], row["attempt_id"]))
                self.conn.execute(
                    "UPDATE dispatch_attempts SET outcome='AUTHORIZATION_REVOKED',finished_at=? WHERE attempt_id=?",
                    (utc_now(), row["attempt_id"]),
                )
            self.conn.execute("COMMIT")
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        return len(rows)

    def status(self) -> dict[str, Any]:
        lane = self.lane()
        counts = {row["state"]: row["n"] for row in self.conn.execute(
            "SELECT state,count(*) n FROM tasks GROUP BY state ORDER BY state"
        )}
        leases = [dict(row) for row in self.conn.execute("SELECT * FROM worker_leases ORDER BY task_id")]
        llm_attempts = self.conn.execute(
            "SELECT count(*) FROM dispatch_attempts WHERE admitted=1 AND lane IN "
            "('AI_BOUNDED_SPECIALIST','WORK_CODEX','LOCAL_OSS_MODEL','NON_WORK_AI')"
        ).fetchone()[0]
        rejected = [dict(row) for row in self.conn.execute(
            "SELECT attempt_id,task_id,lane,attempt,finished_at FROM dispatch_attempts "
            "WHERE outcome='RESULT_SCHEMA_REJECTED' ORDER BY finished_at,attempt_id"
        )]
        recovery_required = [dict(row) for row in self.conn.execute(
            "SELECT t.task_id,t.state,t.reason,t.updated_at FROM tasks t "
            "LEFT JOIN worker_leases l USING(task_id) "
            "WHERE t.state=? AND l.task_id IS NULL ORDER BY t.task_id", (State.RUNNING.value,)
        )]
        return {
            "schema_version": 2, "generated_at": utc_now(),
            "ORCHESTRATOR_M1B_STATE": "OPERATIONAL",
            "RUNTIME_MODE": "PRODUCTION",
            "CONTROL_PLANE_STATE": "ACTIVE" if self.cfg["github"]["enabled"] else "LOCAL_ONLY",
            "DETERMINISTIC_LANE": "ACTIVE",
            "AI_LANE": lane["state"],
            "NEXT_AI_PROBE_AT": _epoch_to_utc(lane["next_probe_at"]),
            "AI_REFUSAL_COUNT": lane["refusal_count"],
            "ACTIVE_WORKER_LEASES": leases,
            "RESULT_SCHEMA_REJECTED_ATTEMPTS": rejected,
            "RECOVERY_REQUIRED": recovery_required,
            "LLM_EXECUTION_ATTEMPTS": int(llm_attempts),
            "TASK_COUNTS": counts,
            "SCIENCE_STRATEGY_AUTHORITY": "HUMAN",
        }


class M1bController:
    def __init__(self, cfg: dict[str, Any], store: Any, transport: AITransport | None = None,
                 *, publication_transport: Any = None,
                 worker_id: str | None = None, clock: Any = time.time):
        self.cfg = cfg
        self.store = store
        self.engine = Engine(cfg, store)
        self.engine.enable_recovery_barrier()
        self.state = M1bStore(store.conn, cfg)
        self.transport = transport or SubprocessAITransport(cfg)
        self.publication_transport = publication_transport or GitHubCommentTransport(cfg["github"])
        self.worker_id = worker_id or f"controller-{os.getpid()}"
        self.clock = clock
        self.state_dir = Path(cfg["state_dir"])
        self.spool = self.state_dir / cfg["autonomy"]["result_inbox_subdir"]
        self.spool.mkdir(parents=True, exist_ok=True)
        self.router = ProductionRouter(cfg, store, self.engine)

    def _live_capable(self) -> bool:
        return self.engine._live_capable()

    def _publication_recovery_health(
        self, visibility: Any, outcomes: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        reasons: list[str] = []
        if visibility.state is not VisibilityHealth.AUTONOMY_VISIBILITY_OK:
            reasons.append(f"visibility={visibility.state.value}")
        blocking = tuple(row[0] for row in self.store.conn.execute(
            "SELECT DISTINCT status FROM publication_outbox WHERE status IN "
            "('PREVIEW','PENDING','SENDING','UNKNOWN','CONFLICT','FAILED') ORDER BY status"
        ))
        if blocking:
            reasons.append("publication states=" + ",".join(str(value) for value in blocking))
        ambiguous = sorted({
            str(outcome.get("status")) for outcome in outcomes
            if str(outcome.get("status", "")).endswith("ERROR")
        })
        if ambiguous:
            reasons.append("reconciliation outcomes=" + ",".join(ambiguous))
        missing = self.store.conn.execute(
            "SELECT r.task_id FROM accepted_results r JOIN tasks t USING(task_id) "
            "WHERE t.source_issue IS NOT NULL AND NOT EXISTS ("
            "SELECT 1 FROM publication_outbox p WHERE p.task_id=r.task_id "
            "AND p.status='PUBLISHED' "
            "AND p.marker LIKE '<!-- cef-dy-orch-result:v1 %') "
            "ORDER BY r.accepted_at,r.task_id LIMIT 1"
        ).fetchone()
        if missing is not None:
            reasons.append(f"missing live projection for {missing['task_id']}")
        return (not reasons, "; ".join(reasons) if reasons else "post-reconciliation state is healthy")

    def _git_identity(self) -> dict[str, Any]:
        def value(*args: str) -> str | None:
            try:
                proc = subprocess.run(["git", *args], cwd=self.cfg["repository_root"],
                                      capture_output=True, text=True, timeout=10, shell=False)
            except (OSError, subprocess.TimeoutExpired):
                return None
            return proc.stdout.strip() if proc.returncode == 0 else None
        return {
            "CANONICAL_HEAD": value("rev-parse", "refs/remotes/origin/main"),
            "CURRENT_COMMIT": value("rev-parse", "HEAD"),
            "CANDIDATE_BRANCH": value("branch", "--show-current"),
            "CANDIDATE_WORKTREE": str(self.cfg["repository_root"]),
        }

    def reconcile_publications(self, now: float) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        self.store.recover_uncertain_publications()
        preview_only = bool(self.cfg["publishing"]["preview_only"])
        attention_states = {State.WAITING_USER.value, State.WAITING_APPROVAL.value,
                            State.BLOCKED.value}

        def attention_required(row: sqlite3.Row) -> bool:
            if row["state"] not in attention_states:
                return False
            if (
                row["state"] in {State.BLOCKED.value, State.FAILED.value, State.REJECTED.value}
                and self.store.lifecycle_disposition(row["task_id"])
                in {"SUPERSEDED", "RETIRED", "CLOSED_HISTORICAL"}
            ):
                return False
            if row["state"] == State.BLOCKED.value:
                return True
            task = self.store.task(row)
            local_ok = bool(row["approved_at"]) or not self.cfg["llm"].get(
                "require_local_approval", True,
            )
            authorization_complete = (
                task.is_llm
                and local_ok
                and task_has_issue_approval(task, self.cfg)
                and self.cfg["llm"].get("dispatch_enabled")
                and self.cfg["mode"] == "pilot"
            )
            # Publication recovery runs before WAITING -> READY promotion.  Once
            # approval metadata is complete, human attention is already resolved
            # even though the recovery barrier still keeps execution closed.
            return not authorization_complete

        resolved_attention_targets: list[tuple[str, str, str]] = []
        for row in self.store.conn.execute(
            "SELECT p.publication_id,p.status,p.task_id,p.target,t.* FROM publication_outbox p "
            "JOIN tasks t ON t.task_id=p.task_id "
            "WHERE p.marker LIKE '<!-- cef-dy-orch-attention:v1 %'"
        ):
            if attention_required(row):
                continue
            if row["status"] in {OutboxStatus.PREVIEW.value, OutboxStatus.PENDING.value}:
                self.store.update_publication(
                    row["publication_id"], OutboxStatus.SUPERSEDED.value,
                    reason="task no longer requires human attention",
                )
                outcomes.append({"publication_id": row["publication_id"],
                                 "status": OutboxStatus.SUPERSEDED.value})
            elif (
                row["status"] == OutboxStatus.PUBLISHED.value
                and row["state"] not in attention_states
            ):
                resolved_attention_targets.append(
                    (row["task_id"], row["target"], row["publication_id"])
                )
        for task_id, target, attention_publication_id in sorted(resolved_attention_targets):
            row = self.store.get(task_id)
            if row is None:
                continue
            resolution_sha = hashlib.sha256(
                f"{task_id}\0{attention_publication_id}\0resolved".encode()
            ).hexdigest()
            if self.store.conn.execute(
                "SELECT 1 FROM publication_outbox WHERE task_id=? AND result_sha256=? "
                "AND marker LIKE '<!-- cef-dy-orch-attention-resolution:v1 %' LIMIT 1",
                (task_id, resolution_sha),
            ).fetchone() is not None:
                continue
            try:
                outcomes.append(enqueue_attention_resolution_preview(
                    self.store, repository=self.cfg["github"]["repository"],
                    target=target, task_row=row,
                    attention_publication_id=attention_publication_id,
                    preview_only=preview_only,
                ))
            except Exception as exc:
                outcomes.append({"task_id": task_id, "status": "ATTENTION_RESOLUTION_ENQUEUE_ERROR",
                                 "error": str(exc)})
        for row in self.store.conn.execute(
            "SELECT r.task_id,t.source_issue FROM accepted_results r JOIN tasks t USING(task_id) "
            "WHERE t.source_issue IS NOT NULL ORDER BY r.accepted_at,r.task_id"
        ):
            result_path = self.state_dir / "results" / f"{row['task_id']}.yaml"
            if not result_path.is_file():
                continue
            try:
                outcomes.append(enqueue_result_preview(
                    self.store, repository=self.cfg["github"]["repository"],
                    target=f"issue:{row['source_issue']}", result_path=result_path,
                    preview_only=preview_only,
                ))
            except Exception as exc:
                outcomes.append({"task_id": row["task_id"], "status": "ENQUEUE_ERROR", "error": str(exc)})
        for row in self.store.conn.execute(
            "SELECT * FROM tasks WHERE state IN ('WAITING_USER','WAITING_APPROVAL','BLOCKED') "
            "ORDER BY created_at,task_id"
        ):
            if not attention_required(row):
                continue
            target_issue = row["source_issue"] or self.cfg["github"].get("attention_issue")
            if target_issue is None:
                outcomes.append({"task_id": row["task_id"], "status": "ATTENTION_LOCAL_ONLY",
                                 "error": "no source_issue or github.attention_issue"})
                continue
            try:
                outcomes.append(enqueue_attention_preview(
                    self.store, repository=self.cfg["github"]["repository"],
                    target=f"issue:{target_issue}", task_row=row,
                    preview_only=preview_only,
                ))
            except Exception as exc:
                outcomes.append({"task_id": row["task_id"], "status": "ATTENTION_ENQUEUE_ERROR",
                                 "error": str(exc)})
        live_enabled = (
            bool(self.cfg["publishing"]["enabled"])
            and self.cfg["mode"] == "pilot"
            and self.cfg["autonomy"]["enabled"]
            and not self.cfg["autonomy"]["plan_only"]
        )
        publisher = Publisher(
            self.store, self.publication_transport,
            lock_path=self.state_dir / "publication.lock",
            lock_stale_after_seconds=int(self.cfg["lock_stale_after_seconds"]),
            enabled=live_enabled, preview_only=preview_only,
            trusted_authors=self.cfg["publishing"]["trusted_authors"],
        )
        rows = list(self.store.conn.execute(
            "SELECT publication_id,status FROM publication_outbox ORDER BY created_at,publication_id"
        ))
        for row in rows:
            try:
                if row["status"] == OutboxStatus.PENDING.value:
                    outcomes.append(publisher.publish(row["publication_id"], now_epoch=now))
                elif row["status"] == OutboxStatus.UNKNOWN.value:
                    current = self.store.publication(row["publication_id"])
                    if current is not None and float(current["backoff_until"]) <= now:
                        outcomes.append(publisher.reconcile(row["publication_id"], now_epoch=now))
            except Exception as exc:
                current = self.store.publication(row["publication_id"])
                attempts = int(current["attempts"]) if current else 0
                delay = min(300, 5 * (2 ** min(attempts, 6)))
                if current is not None:
                    self.store.update_publication(row["publication_id"], OutboxStatus.UNKNOWN.value,
                                                  reason=f"reconciliation outage: {exc}",
                                                  backoff_until=now + delay)
                outcomes.append({"publication_id": row["publication_id"], "status": "RECONCILE_ERROR", "error": str(exc)})
        return outcomes

    def _spool_path(self, task_id: str, attempt_id: str) -> Path:
        return self.spool / f"{task_id}.{attempt_id}.yaml"

    def _write_spool(self, attempt_id: str, result: dict[str, Any]) -> Path:
        path = self._spool_path(result["task_id"], attempt_id)
        _atomic_yaml(path, {"attempt_id": attempt_id, "result": result})
        return path

    def _write_public_result(self, result: dict[str, Any]) -> None:
        required = {"schema_version", "task_id", "attempt", "status", "canonical_head",
                    "worker", "started_at", "finished_at", "checks", "artifacts", "error"}
        public = {key: result[key] for key in required if key in result}
        if set(public) == required:
            for key in ("summary", "semantic_verdict", "semantic_error"):
                if key in result:
                    public[key] = result[key]
            _atomic_yaml(self.state_dir / "results" / f"{result['task_id']}.yaml", public)

    def ingest_spool(self) -> dict[str, int]:
        counts = {"accepted": 0, "accepted_retryable": 0, "duplicate": 0,
                  "duplicate_retryable": 0, "duplicate_schema_rejected": 0,
                  "stale": 0, "revoked": 0,
                  "conflict": 0, "result_schema_rejected": 0, "malformed": 0}
        for path in sorted(self.spool.glob("*.yaml")):
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8"))
                if (not isinstance(payload, dict) or set(payload) != {"attempt_id", "result"}
                        or not isinstance(payload["attempt_id"], str)):
                    raise ValueError("spool schema mismatch")
                outcome = (
                    self.state.accept(payload["attempt_id"], payload["result"])
                    if isinstance(payload["result"], dict)
                    else self.state.reject_result_schema(
                        payload["attempt_id"], "spool result must be a mapping"
                    )
                )
                counts[outcome] += 1
                if outcome in {"accepted", "accepted_retryable", "duplicate", "duplicate_retryable"}:
                    if outcome not in {"accepted_retryable", "duplicate_retryable"}:
                        self._write_public_result(payload["result"])
                    path.rename(path.with_suffix(".accepted"))
                elif outcome in {"stale", "revoked", "conflict"}:
                    path.rename(path.with_suffix("." + outcome))
                elif outcome in {"result_schema_rejected", "duplicate_schema_rejected"}:
                    if outcome == "result_schema_rejected":
                        counts["malformed"] += 1
                    path.rename(path.with_suffix(".malformed"))
            except Exception:
                counts["malformed"] += 1
                path.rename(path.with_suffix(".malformed"))
        return counts

    @staticmethod
    def _result(task: Task, attempt: int, outcome: Admission) -> dict[str, Any]:
        result = outcome.result or {}
        schema_error = _semantic_result_error(result)
        if schema_error is not None:
            raise ValueError(schema_error)
        semantic_verdict = str(result.get("status", "UNKNOWN")).strip().upper() or "UNKNOWN"
        semantic_error = result.get("error")
        return {
            "schema_version": 1, "task_id": task.task_id, "attempt": attempt,
            # ACCEPTED means that the bounded semantic worker executed and
            # returned a structurally valid result.  Its substantive verdict
            # is evidence, not the transport/execution state of this task.
            "status": "SUCCEEDED", "canonical_head": task.canonical_head,
            "worker": "ai_bounded_specialist", "started_at": utc_now(),
            "finished_at": utc_now(), "checks": result.get("checks", []),
            "artifacts": result.get("artifacts", []), "error": None,
            "summary": str(result.get("summary", "")),
            "semantic_verdict": semantic_verdict,
            "semantic_error": None if semantic_error is None else str(semantic_error),
            "retryable": False,
        }

    def _run_claim(self, row: sqlite3.Row, now: float) -> dict[str, Any]:
        task = self.store.task(row)
        lease = self.state.claim(row, self.worker_id, now)
        if lease is None:
            return {"task_id": task.task_id, "outcome": "claim_lost"}
        if task.is_llm:
            if self.cfg["llm"].get("detached_workers"):
                return self._launch_detached(task, lease)
            if lease.get("lane") in {"LOCAL_OSS_MODEL", "NON_WORK_AI"}:
                return self._complete_alternate(task, lease)
            return self._complete_ai(task, lease, now)
        worker_result: WorkerResult = workers.run(task, lease["attempt"], self.cfg)
        result = {**worker_result.as_dict(), "retryable": False}
        spool_path = self._write_spool(lease["attempt_id"], result)
        accepted = self.state.accept(lease["attempt_id"], result)
        if accepted in {"accepted", "duplicate"}:
            self._write_public_result(result)
        if accepted in {"accepted", "accepted_retryable", "duplicate", "duplicate_retryable"}:
            spool_path.rename(spool_path.with_suffix(".accepted"))
        return {"task_id": task.task_id, "outcome": accepted}

    def _complete_alternate(self, task: Task, lease: dict[str, Any]) -> dict[str, Any]:
        lane = lease["lane"]
        role = bootstrap_for_task(self.cfg, task.role)
        try:
            review_material = resolve_review_prompt_material(self.cfg, task)
        except (OSError, UnicodeError, ValueError) as exc:
            return self._fail_closed_review_material(task, lease, str(exc))
        try:
            dependency_material = resolve_dependency_prompt_material(self.cfg, task)
        except (OSError, UnicodeError, ValueError, sqlite3.DatabaseError) as exc:
            return self._fail_closed_dependency_material(task, lease, str(exc))
        try:
            prompt = (role.bootstrap_text + "\nTASK envelope:\n" + _canonical(task.envelope_dict())
                      + review_material + dependency_material)
            if lane == "LOCAL_OSS_MODEL":
                text = OllamaHelper(self.cfg["llm"]["ollama"]).generate(prompt)
            else:
                command = self.cfg["non_work_ai"]["command"]
                proc = subprocess.run(command["argv"], input=prompt, text=True, capture_output=True,
                                      timeout=int(command["timeout_seconds"]), shell=False,
                                      cwd=self.cfg["repository_root"])
                if proc.returncode != 0:
                    raise RuntimeError((proc.stderr or proc.stdout or f"exit {proc.returncode}")[-2000:])
                text = proc.stdout
            parsed = json.loads(text)
            schema_error = _semantic_result_error(parsed)
            outcome = (
                Admission("RESULT_SCHEMA_REJECTED",
                          reason=f"alternate semantic worker result schema invalid: {schema_error}")
                if schema_error is not None else Admission("ACCEPTED", parsed)
            )
        except Exception as exc:
            outcome = Admission("FAILED_RETRYABLE", reason=f"{lane} worker failed: {exc}")
        if outcome.status == "RESULT_SCHEMA_REJECTED":
            rejected = self.state.reject_result_schema(
                lease["attempt_id"], outcome.reason or "alternate semantic result schema invalid"
            )
            return {"task_id": task.task_id, "outcome": rejected, "lane": lane}
        if outcome.status != "ACCEPTED" and any(
            pattern in (outcome.reason or "").casefold() for pattern in QUOTA_PATTERNS
        ):
            now = float(self.clock())
            delay = int(self.cfg["llm"]["quota_probe_backoff_seconds"][0])
            self.store.conn.execute("BEGIN IMMEDIATE")
            try:
                self.store.conn.execute(
                    "UPDATE resource_lanes SET availability_state='QUOTA_WAIT',quota_state='QUOTA_WAIT',"
                    "next_probe_at=?,refusal_count=refusal_count+1,updated_at=? WHERE lane_id=?",
                    (now + delay, utc_now(), lane),
                )
                self.store.conn.execute(
                    "UPDATE tasks SET state=?,reason=?,updated_at=? WHERE task_id=? AND state=?",
                    (State.WAITING_RESOURCE.value, f"{lane} quota refusal; lane-specific probe scheduled", utc_now(),
                     task.task_id, State.RUNNING.value),
                )
                self.store.conn.execute("DELETE FROM worker_leases WHERE task_id=? AND attempt_id=?", (task.task_id, lease["attempt_id"]))
                self.store.conn.execute("UPDATE dispatch_attempts SET outcome='LANE_QUOTA_REFUSED',finished_at=? WHERE attempt_id=?",
                                        (utc_now(), lease["attempt_id"]))
                self.store.conn.execute("COMMIT")
            except Exception:
                if self.store.conn.in_transaction:
                    self.store.conn.execute("ROLLBACK")
                raise
            return {"task_id": task.task_id, "outcome": "WAITING_RESOURCE", "lane": lane}
        if outcome.status == "ACCEPTED":
            self.state.mark_admitted(lease["attempt_id"])
            result = self._result(task, lease["attempt"], outcome)
            result["worker"] = lane.lower()
        else:
            result = {
                "schema_version": 1, "task_id": task.task_id, "attempt": lease["attempt"],
                "status": "FAILED", "canonical_head": task.canonical_head,
                "worker": lane.lower(), "started_at": utc_now(), "finished_at": utc_now(),
                "checks": [], "artifacts": [], "error": outcome.reason, "retryable": True,
            }
        path = self._write_spool(lease["attempt_id"], result)
        accepted = self.state.accept(lease["attempt_id"], result)
        if accepted in {"accepted", "duplicate"}:
            self._write_public_result(result)
        if accepted in {"accepted", "accepted_retryable", "duplicate", "duplicate_retryable"}:
            path.rename(path.with_suffix(".accepted"))
        return {"task_id": task.task_id, "outcome": accepted, "lane": lane}

    def _probe_alternate_lanes(self, now: float) -> list[dict[str, Any]]:
        if not self.router.enabled:
            return []
        results = []
        rows = list(self.store.conn.execute(
            "SELECT * FROM resource_lanes WHERE lane_id IN ('LOCAL_OSS_MODEL','NON_WORK_AI') "
            "AND quota_state='QUOTA_WAIT' AND next_probe_at IS NOT NULL AND next_probe_at<=?", (now,)
        ))
        for row in rows:
            lane = row["lane_id"]
            try:
                if lane == "LOCAL_OSS_MODEL":
                    response = OllamaHelper(self.cfg["llm"]["ollama"]).generate("Reply with exactly ADMISSION_OK")
                else:
                    command = self.cfg["non_work_ai"]["command"]
                    proc = subprocess.run(command["argv"], input="Reply with exactly ADMISSION_OK", text=True,
                                          capture_output=True, timeout=int(command["timeout_seconds"]),
                                          shell=False, cwd=self.cfg["repository_root"])
                    response = proc.stdout if proc.returncode == 0 else ""
                if "ADMISSION_OK" not in response:
                    raise RuntimeError("unexpected lane probe response")
                self.store.conn.execute(
                    "UPDATE resource_lanes SET availability_state='AVAILABLE',quota_state='AVAILABLE',"
                    "next_probe_at=NULL,updated_at=? WHERE lane_id=?", (utc_now(), lane),
                )
                results.append({"lane": lane, "status": "AVAILABLE"})
            except Exception as exc:
                delay = int(self.cfg["llm"]["quota_probe_backoff_seconds"][-1])
                self.store.conn.execute(
                    "UPDATE resource_lanes SET next_probe_at=?,updated_at=? WHERE lane_id=?",
                    (now + delay, utc_now(), lane),
                )
                results.append({"lane": lane, "status": "QUOTA_WAIT", "error": str(exc)})
        return results

    def _complete_ai(self, task: Task, lease: dict[str, Any], now: float) -> dict[str, Any]:
        outcome = self.transport.execute(task, lease["attempt"])
        if outcome.status == "REVIEW_MATERIAL_INVALID":
            return self._fail_closed_review_material(task, lease, outcome.reason or "review material invalid")
        if outcome.status == "DEPENDENCY_MATERIAL_INVALID":
            return self._fail_closed_dependency_material(
                task, lease, outcome.reason or "dependency material invalid"
            )
        if outcome.status == "QUOTA_REFUSED":
            quota_outcome = self.state.quota_refused(
                task.task_id, lease["attempt_id"], outcome.reason or "quota refused", outcome.reset_at, now,
            )
            return {"task_id": task.task_id, "outcome": quota_outcome}
        if outcome.status == "ACCEPTED":
            schema_error = _semantic_result_error(outcome.result)
            if schema_error is not None:
                outcome = Admission(
                    "RESULT_SCHEMA_REJECTED",
                    reason=f"AI worker result schema invalid: {schema_error}",
                )
        if outcome.status == "RESULT_SCHEMA_REJECTED":
            rejected = self.state.reject_result_schema(
                lease["attempt_id"], outcome.reason or "semantic result schema invalid"
            )
            return {"task_id": task.task_id, "outcome": rejected}
        if outcome.status != "ACCEPTED":
            result = {
                "schema_version": 1, "task_id": task.task_id, "attempt": lease["attempt"],
                "status": "FAILED", "canonical_head": task.canonical_head,
                "worker": "ai_bounded_specialist", "started_at": utc_now(), "finished_at": utc_now(),
                "checks": [], "artifacts": [], "error": outcome.reason, "retryable": True,
            }
        else:
            self.state.mark_admitted(lease["attempt_id"])
            result = self._result(task, lease["attempt"], outcome)
        spool_path = self._write_spool(lease["attempt_id"], result)
        accepted = self.state.accept(lease["attempt_id"], result)
        if accepted in {"accepted", "duplicate"}:
            self._write_public_result(result)
        if accepted in {"accepted", "accepted_retryable", "duplicate", "duplicate_retryable"}:
            spool_path.rename(spool_path.with_suffix(".accepted"))
        return {"task_id": task.task_id, "outcome": accepted}

    def _fail_closed_review_material(self, task: Task, lease: dict[str, Any], reason: str) -> dict[str, Any]:
        self.store.transition(
            task.task_id, State.WAITING_USER,
            "independent review material verification failed: " + reason,
            force_recovery=True,
        )
        self.state.cancel_invalid_leases()
        return {"task_id": task.task_id, "outcome": "WAITING_USER", "reason": reason}

    def _fail_closed_dependency_material(self, task: Task, lease: dict[str, Any], reason: str) -> dict[str, Any]:
        self.store.transition(
            task.task_id, State.WAITING_USER,
            "dependency result material verification failed: " + reason,
            force_recovery=True,
        )
        self.state.cancel_invalid_leases()
        return {"task_id": task.task_id, "outcome": "WAITING_USER", "reason": reason}

    def _launch_detached(self, task: Task, lease: dict[str, Any]) -> dict[str, Any]:
        config_path = self.cfg.get("_config_path")
        if not config_path:
            raise RuntimeError("detached worker requires a resolved config path")
        unit = "cef-dy-ai-" + lease["attempt_id"]
        argv = [
            "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}",
            "--property=Type=exec", "--property=NoNewPrivileges=yes",
            f"--property=WorkingDirectory={self.cfg['repository_root']}",
            "/usr/bin/python3", str(Path(self.cfg["repository_root"]) / "scripts/orchestrate_tasks.py"),
            "--config", str(config_path), "worker-once", task.task_id, lease["attempt_id"],
        ]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, shell=False)
        if proc.returncode == 0:
            return {"task_id": task.task_id, "outcome": "launched", "attempt_id": lease["attempt_id"]}
        failure = Admission("FAILED_RETRYABLE", reason=(proc.stderr or proc.stdout or "systemd-run failed")[-2000:])
        return self._complete_ai_failure_without_launch(task, lease, failure)

    def _complete_ai_failure_without_launch(self, task: Task, lease: dict[str, Any], outcome: Admission) -> dict[str, Any]:
        result = {
            "schema_version": 1, "task_id": task.task_id, "attempt": lease["attempt"],
            "status": "FAILED", "canonical_head": task.canonical_head,
            "worker": "ai_worker_launcher", "started_at": utc_now(), "finished_at": utc_now(),
            "checks": [], "artifacts": [], "error": outcome.reason, "retryable": True,
        }
        path = self._write_spool(lease["attempt_id"], result)
        accepted = self.state.accept(lease["attempt_id"], result)
        if accepted in {"accepted_retryable", "duplicate_retryable"}:
            path.rename(path.with_suffix(".accepted"))
        return {"task_id": task.task_id, "outcome": accepted}

    def run_leased_ai(self, task_id: str, attempt_id: str) -> dict[str, Any]:
        lease_row = self.store.conn.execute(
            "SELECT * FROM worker_leases WHERE task_id=? AND attempt_id=?", (task_id, attempt_id)
        ).fetchone()
        task_row = self.store.get(task_id)
        if lease_row is None or task_row is None or task_row["state"] != State.RUNNING.value:
            return {"task_id": task_id, "outcome": "stale"}
        lease = dict(lease_row)
        lease["attempt"] = int(task_row["attempt"]) + 1
        attempt = self.store.conn.execute("SELECT lane FROM dispatch_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        lease["lane"] = attempt["lane"] if attempt else "WORK_CODEX"
        if lease["lane"] in {"LOCAL_OSS_MODEL", "NON_WORK_AI"}:
            return self._complete_alternate(self.store.task(task_row), lease)
        return self._complete_ai(self.store.task(task_row), lease, float(self.clock()))

    def cycle(self, source: Any = None) -> dict[str, Any]:
        now = float(self.clock())
        # A previous cycle's in-memory decision never authorizes this cycle.
        # Every cycle must re-establish the gate after publication recovery.
        self.engine.set_recovery_barrier_proven(False)
        self.state.checkpoint(CURRENT_PHASE="RUNNING", NEXT_EXACT_ACTION="recover, reconcile, prove, poll, dispatch",
                              **self._git_identity())
        cancelled = self.state.cancel_invalid_leases()
        recovered_results = self.ingest_spool()
        visibility = self.engine.visibility_health(now)
        expired = self.state.recover_expired(
            now,
            admission_check=lambda task: self.engine.admission_decision(task, visibility).allowed,
        )
        try:
            pre_admission_publications = self.reconcile_publications(now)
        except Exception as exc:
            pre_admission_publications = [{
                "status": "PRE_ADMISSION_RECONCILE_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }]
        visibility = self.engine.visibility_health(now)
        recovery_healthy, recovery_reason = self._publication_recovery_health(
            visibility, pre_admission_publications,
        )
        recovery_proof = self.state.update_recovery_proof(
            live_capable=self._live_capable(),
            healthy=recovery_healthy,
            now=now,
            poll_interval_seconds=int(self.cfg.get("poll_interval_seconds", 300)),
            reason=recovery_reason,
        )
        recovery_open = recovery_proof["state"] == RECOVERY_PROVEN
        self.engine.set_recovery_barrier_proven(recovery_open)
        try:
            poll = self.engine.poll(source)
        except Exception as exc:
            poll = {"status": "outage", "error": f"{type(exc).__name__}: {exc}"}
        routing_ok = True
        try:
            routing = self.router.reconcile()
        except (OSError, ValueError, sqlite3.DatabaseError) as exc:
            routing_ok = False
            routing = {"status": "DEGRADED", "error": f"{type(exc).__name__}: {exc}"}
            self.store.append_event(None, "M2_ROUTING_DEGRADED", None, None, routing)
        lane = self.state.lane()
        probe = "not_due"
        if (self.cfg["llm"]["dispatch_enabled"] and lane["state"] == "QUOTA_WAIT"
                and lane["next_probe_at"] is not None and now >= float(lane["next_probe_at"])):
            outcome = self.transport.probe()
            visibility = self.engine.visibility_health(now)
            self.state.probe_result(
                outcome, now,
                admission_check=lambda task: self.engine.admission_decision(
                    task, visibility,
                ).allowed,
            )
            if self.router.enabled:
                routing = self.router.reconcile()
            probe = outcome.status
        alternate_probes = self._probe_alternate_lanes(now)
        if alternate_probes:
            routing = self.router.reconcile()
        self.engine.reevaluate_waiting()
        visibility = self.engine.visibility_health(now)
        for row in self.store.list_state(State.FAILED_RETRYABLE):
            if int(row["attempt"]) >= 3:
                self.store.transition(
                    row["task_id"], State.BLOCKED, "ordinary retry limit reached",
                )
                continue
            task = self.store.task(row)
            decision = self.engine.admission_decision(task, visibility)
            if decision.allowed:
                self.store.transition(task.task_id, State.READY, "retryable failure scheduled")
        dispatched: list[dict[str, Any]] = []
        limit = int(self.cfg["autonomy"]["max_batch_tasks"])
        execution_enabled = (
            self.cfg["mode"] == "pilot"
            and self.cfg["autonomy"]["enabled"]
            and not self.cfg["autonomy"]["plan_only"]
        )
        ready = self.store.list_state(State.READY)
        if self.router.enabled:
            ready = sorted(ready, key=lambda row: (
                self.store.task(row).is_llm, row["created_at"], row["task_id"]
            ))
        for row in ready if execution_enabled else ():
            if len(dispatched) >= limit:
                break
            task = self.store.task(row)
            if task.is_llm and self.router.enabled and not routing_ok:
                continue
            route = None
            if self.router.enabled:
                route = self.store.conn.execute("SELECT selected_lane,route_status FROM task_routes WHERE task_id=?", (task.task_id,)).fetchone()
                if route is None or route["route_status"] != "ROUTED" or route["selected_lane"] == "HUMAN_DECISION":
                    self.store.transition(task.task_id, State.WAITING_USER, "no executable valid resource route", force_recovery=True)
                    continue
            if task.is_llm:
                if task.inputs.get("independent_review") is True:
                    valid, reason = self.router.verify_review_material(task)
                    if not valid:
                        self.store.transition(task.task_id, State.WAITING_USER, reason, force_recovery=True)
                        continue
                if task.inputs.get("bind_dependency_results") is True:
                    valid, reason = self.router.verify_dependency_bundle(task)
                    if not valid:
                        self.store.transition(task.task_id, State.WAITING_USER, reason, force_recovery=True)
                        continue
                local_ok = bool(row["approved_at"]) or not self.cfg["llm"].get("require_local_approval", True)
                if not local_ok or self.cfg["llm"]["require_issue_label"] not in task.labels:
                    self.store.transition(task.task_id, State.WAITING_USER,
                                          "AI authorization missing at dispatch", force_recovery=True)
                    continue
                selected = route["selected_lane"] if self.router.enabled else "WORK_CODEX"
                if selected == "WORK_CODEX" and (not self.cfg["llm"]["dispatch_enabled"] or self.state.lane()["state"] != "AVAILABLE"):
                    self.store.transition(task.task_id, State.WAITING_RESOURCE, "Work/Codex lane unavailable", force_recovery=True)
                    continue
            visibility = self.engine.visibility_health(now)
            decision = self.engine.admission_decision(task, visibility)
            if not decision.allowed:
                continue
            dispatched.append(self._run_claim(row, now))
        publications = pre_admission_publications + self.reconcile_publications(now)
        visibility = self.engine.visibility_health(now)
        final_healthy, final_reason = self._publication_recovery_health(
            visibility, publications,
        )
        if self._live_capable() and not final_healthy:
            recovery_proof = self.state.update_recovery_proof(
                live_capable=True,
                healthy=False,
                now=now,
                poll_interval_seconds=int(self.cfg.get("poll_interval_seconds", 300)),
                reason=final_reason,
            )
            recovery_open = False
            self.engine.set_recovery_barrier_proven(False)
        status = self.state.status()
        status.update(self.router.status())
        if not routing_ok:
            status["M2_PRODUCTION_ROUTING"] = "DEGRADED"
        if not execution_enabled:
            status["ORCHESTRATOR_M1B_STATE"] = "SHADOW"
        if not self.cfg["llm"]["dispatch_enabled"]:
            status["AI_LANE"] = "DISABLED"
        status["AUTONOMY_VISIBILITY_STATE"] = visibility.state.value
        status["AUTONOMY_VISIBILITY_REASONS"] = list(visibility.reasons)
        status["UNPROJECTED_TERMINAL_COUNT"] = visibility.unresolved_terminal_count
        status["UNPROJECTED_TERMINAL_HIGH_WATER"] = visibility.unprojected_terminal_high_water
        status["UNPROJECTED_TERMINAL_MAX_AGE_SECONDS"] = visibility.unprojected_terminal_max_age_seconds
        status["OUTBOX_REQUIRED_HIGH_WATER"] = visibility.outbox_required_high_water
        status["RECOVERY_PROOF_STATE"] = recovery_proof["state"]
        status["RECOVERY_FIRST_HEALTHY_AT"] = recovery_proof["first_healthy_at"]
        status["RECOVERY_LAST_HEALTHY_AT"] = recovery_proof["last_healthy_at"]
        status["RECOVERY_PROOF_REASON"] = recovery_proof["reason"]
        status["ORDINARY_ADMISSION_OPEN"] = recovery_open
        live = self.state_dir / self.cfg["autonomy"]["evidence_subdir"] / "ORCH_LIVE_STATUS.yaml"
        _atomic_yaml(live, status)
        blockers = [dict(row) for row in self.store.conn.execute("SELECT task_id,reason FROM tasks WHERE state='BLOCKED'")]
        waiting = [dict(row) for row in self.store.conn.execute("SELECT task_id,reason FROM tasks WHERE state IN ('WAITING_USER','WAITING_APPROVAL')")]
        self.state.checkpoint(
            CURRENT_PHASE="READY", LAST_VERIFIED_CHECKPOINT=utc_now(),
            NEXT_EXACT_ACTION="next timer cycle", AI_LANE_STATE=status["AI_LANE"],
            NEXT_AI_PROBE_AT=status["NEXT_AI_PROBE_AT"], ACTIVE_WORKER_LEASE=status["ACTIVE_WORKER_LEASES"],
            LAST_WORKER_RESULT=dispatched[-1] if dispatched else None,
            BLOCKED_TASKS=blockers, WAITING_USER_TASKS=waiting,
            AUTONOMY_VISIBILITY_STATE=visibility.state.value,
            AUTONOMY_VISIBILITY_REASONS=list(visibility.reasons),
        )
        # The dashboard reads SQLite in query-only mode and can observe WAL
        # state.  Checkpoint opportunistically without making it a writer or a
        # controller dependency.
        self.store.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        return {"poll": poll, "cancelled_leases": cancelled,
                "recovered_results": recovered_results,
                "expired_leases": expired, "routing": routing, "probe": probe,
                "alternate_probes": alternate_probes,
                "dispatched": dispatched, "publications": publications,
                "admission_visibility": visibility.state.value,
                "recovery_proof": recovery_proof,
                "ordinary_admission_open": recovery_open, "status": status}
