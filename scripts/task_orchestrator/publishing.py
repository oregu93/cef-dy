"""Preview-first, idempotent terminal-result publication foundation.

The production configuration is disabled.  Network behavior is represented by
an injected transport protocol so tests use local mocks only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import html
from pathlib import Path
import re
import time
from typing import Any, Mapping, Protocol, Sequence

import yaml

from .locking import ProcessLock
from .model import TERMINAL_STATES, ValidationError


MARKER_RE = re.compile(
    r"<!-- cef-dy-orch-result:v1 repo=([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+) "
    r"task=([A-Z0-9][A-Z0-9._-]{2,199}) envelope=([0-9a-f]{64}) result=([0-9a-f]{64}) -->"
)
MAX_RESULT_BYTES = 2_000_000
MAX_PREVIEW_BYTES = 64_000


class OutboxStatus(str, Enum):
    PREVIEW = "PREVIEW"
    PENDING = "PENDING"
    SENDING = "SENDING"
    UNKNOWN = "UNKNOWN"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    remote_id: str | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class RemoteComment:
    body: str
    author: str | None
    comment_id: str


@dataclass(frozen=True)
class CommentPage:
    comments: tuple[RemoteComment, ...]
    pagination_complete: bool


class PublicationTransport(Protocol):
    def send_comment(self, target: str, body: str) -> TransportResponse: ...
    def list_comments(self, target: str) -> CommentPage: ...


class AmbiguousDelivery(RuntimeError):
    """Timeout/disconnect where remote acceptance cannot be established."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_result(path: Path) -> tuple[dict[str, Any], bytes, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"RESULT unavailable: {exc}") from exc
    if not raw or len(raw) > MAX_RESULT_BYTES:
        raise ValidationError("RESULT is empty or oversized")
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValidationError(f"RESULT is corrupt: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("RESULT must be a mapping")
    required = {"schema_version", "task_id", "attempt", "status", "canonical_head",
                "worker", "started_at", "finished_at", "checks", "artifacts", "error"}
    if set(value) != required or value["schema_version"] != 1:
        raise ValidationError("RESULT schema mismatch")
    if not isinstance(value["task_id"], str) or not isinstance(value["canonical_head"], str):
        raise ValidationError("RESULT identity fields must be text")
    if isinstance(value["attempt"], bool) or not isinstance(value["attempt"], int) or value["attempt"] < 0:
        raise ValidationError("RESULT attempt must be a nonnegative integer")
    for key in ("status", "worker", "started_at", "finished_at"):
        if not isinstance(value[key], str) or not value[key]:
            raise ValidationError(f"RESULT {key} must be nonempty text")
    if not isinstance(value["checks"], list) or not isinstance(value["artifacts"], list):
        raise ValidationError("RESULT checks and artifacts must be lists")
    if value["error"] is not None and not isinstance(value["error"], str):
        raise ValidationError("RESULT error must be null or text")
    return value, raw, sha256_bytes(raw)


def _safe_text(value: Any, limit: int = 4000) -> str:
    text = str(value).replace("\x00", "�")
    text = "".join(character for character in text if character in "\n\t" or ord(character) >= 32)
    text = html.escape(text, quote=False).replace("`", "ˋ")
    text = text.replace("@", "@\u200b")
    return text[:limit]


def publication_marker(repository: str, task_id: str, envelope_hash: str,
                       result_sha256: str) -> str:
    marker = (f"<!-- cef-dy-orch-result:v1 repo={repository} task={task_id} "
              f"envelope={envelope_hash} result={result_sha256} -->")
    if MARKER_RE.fullmatch(marker) is None:
        raise ValidationError("publication identity is malformed")
    return marker


def render_preview(repository: str, task: Mapping[str, Any], envelope_hash: str,
                   result: Mapping[str, Any], result_sha256: str) -> str:
    if result.get("task_id") != task.get("task_id"):
        raise ValidationError("RESULT task_id does not match TASK")
    if result.get("canonical_head") != task.get("canonical_head"):
        raise ValidationError("RESULT canonical_head does not match TASK")
    if result.get("status") not in {"SUCCEEDED", "FAILED", "PAUSED_QUOTA"}:
        raise ValidationError("RESULT status is not terminal/publishable")
    marker = publication_marker(repository, str(task["task_id"]), envelope_hash, result_sha256)
    lines = [
        marker,
        f"### Orchestrator RESULT preview — `{_safe_text(task['task_id'], 300)}`",
        "",
        f"- Status: `{_safe_text(result['status'], 100)}`",
        f"- Attempt: `{int(result['attempt'])}`",
        f"- Worker: `{_safe_text(result['worker'], 300)}`",
        f"- Canonical HEAD: `{_safe_text(result['canonical_head'], 100)}`",
        f"- RESULT SHA-256: `{result_sha256}`",
        "- Authority: operational evidence only; no scientific or Project Control promotion",
    ]
    error = result.get("error")
    if error:
        lines.extend(("", "Error:", "```text", _safe_text(error), "```"))
    preview = "\n".join(lines) + "\n"
    if len(preview.encode("utf-8")) > MAX_PREVIEW_BYTES:
        raise ValidationError("publication preview is oversized")
    return preview


def validate_result_against_store(store: Any, result: Mapping[str, Any],
                                  envelope_hash: str) -> dict[str, Any]:
    row = store.get(str(result.get("task_id", "")))
    if row is None:
        raise ValidationError("RESULT references an unknown TASK")
    if row["envelope_hash"] != envelope_hash:
        raise ValidationError("RESULT/TASK envelope mismatch")
    task = store.task(row)
    if result.get("canonical_head") != task.canonical_head:
        raise ValidationError("RESULT/TASK canonical HEAD mismatch")
    expected_state = {
        "SUCCEEDED": "SUCCEEDED", "FAILED": "FAILED", "PAUSED_QUOTA": "PAUSED_QUOTA",
    }.get(result.get("status"))
    if expected_state is None or row["state"] != expected_state:
        raise ValidationError("RESULT status does not match durable TASK state")
    if expected_state in {state.value for state in TERMINAL_STATES}:
        count = store.conn.execute(
            "SELECT count(*) FROM events WHERE task_id=? AND new_state=?",
            (task.task_id, expected_state),
        ).fetchone()[0]
        if int(count) == 0:
            raise ValidationError("RESULT has no matching durable transition event")
    return task.canonical_dict()


def enqueue_result_preview(
    store: Any, *, repository: str, target: str, result_path: Path,
    preview_only: bool = True,
) -> dict[str, Any]:
    if not isinstance(target, str) or re.fullmatch(r"issue:[1-9][0-9]*", target) is None:
        raise ValidationError("publication target must be an explicit issue:<number>")
    result, _raw, result_sha = load_result(result_path)
    row = store.get(result["task_id"])
    if row is None:
        raise ValidationError("RESULT references an unknown TASK")
    task = validate_result_against_store(store, result, row["envelope_hash"])
    preview = render_preview(repository, task, row["envelope_hash"], result, result_sha)
    status = OutboxStatus.PREVIEW if preview_only else OutboxStatus.PENDING
    publication_id = hashlib.sha256(
        f"{repository}\0{result['task_id']}\0{row['envelope_hash']}\0{target}".encode()
    ).hexdigest()
    outcome = store.enqueue_publication(
        publication_id=publication_id, repository=repository,
        task_id=result["task_id"], envelope_hash=row["envelope_hash"],
        result_sha256=result_sha, target=target, marker=publication_marker(
            repository, result["task_id"], row["envelope_hash"], result_sha),
        preview=preview, status=status.value,
    )
    return {"outcome": outcome, "publication_id": publication_id,
            "status": status.value, "preview": preview, "result_sha256": result_sha}


class Publisher:
    def __init__(self, store: Any, transport: PublicationTransport, *, lock_path: Path,
                 lock_stale_after_seconds: int, enabled: bool = False,
                 preview_only: bool = True, trusted_authors: Sequence[str] = ()):
        self.store = store
        self.transport = transport
        self.lock_path = lock_path
        self.lock_stale_after_seconds = lock_stale_after_seconds
        self.enabled = enabled
        self.preview_only = preview_only
        self.trusted_authors = frozenset(trusted_authors)

    def publish(self, publication_id: str, *, now_epoch: float | None = None) -> dict[str, Any]:
        if not self.enabled or self.preview_only:
            row = self.store.publication(publication_id)
            return {"status": OutboxStatus.PREVIEW.value,
                    "publication_id": publication_id,
                    "preview": row["preview"] if row else None,
                    "network_writes": 0}
        now_epoch = time.time() if now_epoch is None else now_epoch
        with ProcessLock(self.lock_path, self.lock_stale_after_seconds):
            row = self.store.claim_publication(publication_id, now_epoch=now_epoch)
            if row is None:
                current = self.store.publication(publication_id)
                return {"status": current["status"] if current else "MISSING",
                        "publication_id": publication_id, "network_writes": 0}
            try:
                response = self.transport.send_comment(row["target"], row["preview"])
            except (AmbiguousDelivery, TimeoutError, ConnectionError, OSError) as exc:
                self.store.update_publication(publication_id, OutboxStatus.UNKNOWN.value,
                                              reason=f"ambiguous delivery: {exc}")
                return {"status": OutboxStatus.UNKNOWN.value,
                        "publication_id": publication_id, "network_writes": 1}
            code = int(response.status_code)
            if 200 <= code < 300:
                self.store.update_publication(publication_id, OutboxStatus.PUBLISHED.value,
                                              remote_id=response.remote_id)
                status = OutboxStatus.PUBLISHED.value
            elif code in {401, 403}:
                self.store.update_publication(publication_id, OutboxStatus.FAILED.value,
                                              reason=f"HTTP {code}; authorization required")
                status = OutboxStatus.FAILED.value
            elif code == 429:
                retry = max(1, int(response.retry_after_seconds or 60))
                self.store.update_publication(publication_id, OutboxStatus.PENDING.value,
                                              reason="HTTP 429", backoff_until=now_epoch + retry)
                status = OutboxStatus.PENDING.value
            elif 500 <= code < 600:
                self.store.update_publication(publication_id, OutboxStatus.UNKNOWN.value,
                                              reason=f"HTTP {code}; acceptance uncertain")
                status = OutboxStatus.UNKNOWN.value
            else:
                self.store.update_publication(publication_id, OutboxStatus.FAILED.value,
                                              reason=f"HTTP {code}")
                status = OutboxStatus.FAILED.value
            return {"status": status, "publication_id": publication_id, "network_writes": 1}

    def reconcile(self, publication_id: str) -> dict[str, Any]:
        row = self.store.publication(publication_id)
        if row is None:
            raise ValidationError("unknown publication")
        page = self.transport.list_comments(row["target"])
        if not page.pagination_complete:
            self.store.update_publication(publication_id, OutboxStatus.UNKNOWN.value,
                                          reason="reconciliation pagination incomplete")
            return {"status": OutboxStatus.UNKNOWN.value, "matched": 0}
        marker_comments = [comment for comment in page.comments if row["marker"] in comment.body]
        matches = [comment for comment in marker_comments
                   if comment.author in self.trusted_authors
                   and comment.body == row["preview"]
                   and comment.body.count(row["marker"]) == 1]
        forged_or_edited = [comment for comment in marker_comments if comment not in matches]
        if forged_or_edited or len(matches) > 1:
            self.store.update_publication(publication_id, OutboxStatus.CONFLICT.value,
                                          reason="forged/duplicate/edited publication marker")
            return {"status": OutboxStatus.CONFLICT.value, "matched": len(matches),
                    "forged_or_edited": len(forged_or_edited)}
        if len(matches) == 1:
            self.store.update_publication(publication_id, OutboxStatus.PUBLISHED.value,
                                          remote_id=matches[0].comment_id,
                                          reason="reconciled exact trusted marker")
            return {"status": OutboxStatus.PUBLISHED.value, "matched": 1}
        self.store.update_publication(publication_id, OutboxStatus.UNKNOWN.value,
                                      reason="marker absent; manual retry authorization required")
        return {"status": OutboxStatus.UNKNOWN.value, "matched": 0}

    def audit_published(self, publication_id: str) -> dict[str, Any]:
        """Detect human edit/deletion without recreating or overwriting it."""
        return self.reconcile(publication_id)
