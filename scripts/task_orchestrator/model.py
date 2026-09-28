from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class State(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    READY = "READY"
    RUNNING = "RUNNING"
    QUOTA_WAIT = "QUOTA_WAIT"
    WAITING_USER = "WAITING_USER"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    PAUSED_QUOTA = "PAUSED_QUOTA"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


TERMINAL_STATES = {State.SUCCEEDED, State.FAILED, State.REJECTED, State.BLOCKED}

TRANSITIONS = {
    State.RECEIVED: {State.VALIDATED, State.REJECTED},
    State.VALIDATED: {State.WAITING_DEPENDENCY, State.WAITING_APPROVAL, State.WAITING_RESOURCE, State.READY, State.REJECTED, State.BLOCKED},
    State.WAITING_DEPENDENCY: {State.READY, State.BLOCKED},
    State.WAITING_APPROVAL: {State.READY, State.WAITING_USER, State.BLOCKED},
    State.WAITING_USER: {State.READY, State.BLOCKED},
    State.WAITING_RESOURCE: {State.READY, State.WAITING_USER, State.BLOCKED},
    State.READY: {State.RUNNING, State.WAITING_APPROVAL, State.WAITING_USER, State.WAITING_RESOURCE, State.BLOCKED},
    State.RUNNING: {State.SUCCEEDED, State.FAILED, State.FAILED_RETRYABLE, State.QUOTA_WAIT, State.PAUSED_QUOTA, State.READY, State.WAITING_APPROVAL},
    State.FAILED_RETRYABLE: {State.READY, State.BLOCKED},
    State.QUOTA_WAIT: {State.READY, State.BLOCKED},
    State.PAUSED_QUOTA: {State.READY, State.WAITING_APPROVAL},
}


class ValidationError(ValueError):
    pass


class TransitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Task:
    schema_version: int
    task_id: str
    role: str
    canonical_head: str
    task_type: str
    action: str
    stop_condition: str
    dependencies: tuple[str, ...] = ()
    inputs: dict[str, Any] = field(default_factory=dict)
    allowed_paths: tuple[str, ...] = ()
    expected_artifacts: tuple[str, ...] = ()
    timeout_seconds: int = 60
    source_issue: int | None = None
    labels: tuple[str, ...] = ()

    def canonical_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["dependencies"] = list(self.dependencies)
        value["allowed_paths"] = list(self.allowed_paths)
        value["expected_artifacts"] = list(self.expected_artifacts)
        value["labels"] = sorted(self.labels)
        return value

    def envelope_dict(self) -> dict[str, Any]:
        value = self.canonical_dict()
        value.pop("source_issue", None)
        value.pop("labels", None)
        return value

    @property
    def envelope_hash(self) -> str:
        encoded = json.dumps(self.envelope_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def payload_hash(self) -> str:
        encoded = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def is_llm(self) -> bool:
        return self.task_type in {"llm_semantic", "llm_worker"}


@dataclass(frozen=True)
class WorkerResult:
    task_id: str
    attempt: int
    status: str
    canonical_head: str
    worker: str
    started_at: str
    finished_at: str
    checks: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, **asdict(self)}
