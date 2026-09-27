"""Deterministic M1b-P1 plan-only autonomy and durable checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
from typing import Any, Iterable
from urllib.parse import quote

from .model import State, Task, ValidationError
from .schema import validate_task
from .visibility import sidecar_identity, validate_sidecar


CANONICAL_REPOSITORY = "oregu93/cef-dy"
SAFE_ACTIONS = {"head_check", "status_check", "dependency_check"}
REASON_ORDER = (
    "TASK_MISSING", "ENVELOPE_MISMATCH", "REPOSITORY_NOT_CANONICAL",
    "ROLE_NOT_INFRASTRUCTURE", "TASK_TYPE_NOT_DETERMINISTIC",
    "ACTION_NOT_P1_SAFE", "TASK_HEAD_MISMATCH", "TASK_NOT_READY",
    "DEPENDENCY_NOT_SUCCEEDED", "NON_LOCAL_DETERMINISTIC_LANE",
    "NOT_UNATTENDED_SAFE", "HUMAN_ATTENTION_REQUIRED", "CHAT_ONLY",
    "DISPATCH_CLAIM_FORBIDDEN", "TASK_CLASS_NOT_INFRASTRUCTURE",
    "INPUT_CONTRACT_VIOLATION", "PATH_OR_ARTIFACT_SCOPE_FORBIDDEN",
    "AWAY_INELIGIBLE", "PROHIBITED_DOMAIN_TOKEN", "CAPACITY_EXHAUSTED",
)
TASK_DEPENDENT = {
    "ENVELOPE_MISMATCH", "ROLE_NOT_INFRASTRUCTURE",
    "TASK_TYPE_NOT_DETERMINISTIC", "ACTION_NOT_P1_SAFE",
    "TASK_HEAD_MISMATCH", "TASK_NOT_READY", "DEPENDENCY_NOT_SUCCEEDED",
    "INPUT_CONTRACT_VIOLATION", "PATH_OR_ARTIFACT_SCOPE_FORBIDDEN",
}
PROHIBITED_TOKENS = (
    "SCIENTIFIC", "CEF", "STAGE03", "HOLDOUT", "FULLPROF", "STRUCTURE-A",
    "EXCHANGE", "FIT", "RAW_DATA", "PRODUCTION_PUBLISH",
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SIDECAR_TASK_ID = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,199}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
UTC_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

ZERO_DISABLED = {
    "status": "DISABLED", "dispatch_performed": False, "worker_starts": 0,
    "worker_subprocess_starts": 0, "identity_git_reads": 0,
    "identity_network_reads": 0, "network_writes": 0, "llm_calls": 0,
    "scientific_execution": False,
}
ENABLED_INVARIANTS = {
    "dispatch_performed": False, "worker_starts": 0,
    "worker_subprocess_starts": 0, "identity_git_reads": 4,
    "identity_network_reads": 1, "network_writes": 0, "llm_calls": 0,
    "scientific_execution": False, "production_publishing": False,
}


class AutonomyError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AutonomyError(f"non-canonical JSON value: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def disabled_result() -> dict[str, Any]:
    return dict(ZERO_DISABLED)


def _git(repo: Path, argv: list[str], *, remote: bool = False) -> str:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if remote:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=5"
    try:
        proc = subprocess.run(
            ["git", *argv], cwd=repo, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, shell=False, timeout=15, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutonomyError(f"HEAD_IDENTITY_UNVERIFIED: {exc}") from exc
    if proc.returncode != 0:
        raise AutonomyError(
            "HEAD_IDENTITY_UNVERIFIED: " + (proc.stderr or proc.stdout).strip()
        )
    return proc.stdout.strip()


def verify_git_identity(repository_root: Path) -> str:
    branch = _git(repository_root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    local = _git(repository_root, ["rev-parse", "HEAD"])
    tracked = _git(repository_root, ["rev-parse", "refs/remotes/origin/main"])
    remote_text = _git(
        repository_root, ["ls-remote", "--heads", "origin", "main"], remote=True,
    )
    lines = [line for line in remote_text.splitlines() if line.strip()]
    if branch != "main" or len(lines) != 1:
        raise AutonomyError("HEAD_IDENTITY_UNVERIFIED: branch or remote line count")
    parts = lines[0].split()
    if len(parts) != 2 or parts[1] != "refs/heads/main":
        raise AutonomyError("HEAD_IDENTITY_UNVERIFIED: malformed remote result")
    remote = parts[0]
    if not all(SHA40.fullmatch(value) for value in (local, tracked, remote)):
        raise AutonomyError("HEAD_IDENTITY_UNVERIFIED: malformed SHA")
    if len({local, tracked, remote}) != 1:
        raise AutonomyError("HEAD_IDENTITY_UNVERIFIED: local/origin/remote drift")
    return local


def open_readonly_database(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise AutonomyError("STATE_DATABASE_UNAVAILABLE")
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _task_from_row(row: sqlite3.Row) -> Task:
    try:
        raw = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise AutonomyError("TASK_ROW_INVALID: malformed payload_json") from exc
    expected_keys = {
        "schema_version", "task_id", "role", "canonical_head", "task_type",
        "action", "stop_condition", "dependencies", "inputs", "allowed_paths",
        "expected_artifacts", "timeout_seconds", "source_issue", "labels",
    }
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise AutonomyError("TASK_ROW_INVALID: canonical keys")
    if type(raw["schema_version"]) is not int:
        raise AutonomyError("TASK_ROW_INVALID: schema_version type")
    source = raw["source_issue"]
    if source is not None and (type(source) is not int or source < 1):
        raise AutonomyError("TASK_ROW_INVALID: source_issue type")
    labels = raw["labels"]
    if (not isinstance(labels, list) or any(not isinstance(v, str) for v in labels)
            or labels != sorted(set(labels))):
        raise AutonomyError("TASK_ROW_INVALID: labels")
    envelope = {key: value for key, value in raw.items()
                if key not in {"source_issue", "labels"}}
    try:
        task = validate_task(envelope, source_issue=source, labels=tuple(labels))
    except Exception as exc:
        raise AutonomyError(f"TASK_ROW_INVALID: {exc}") from exc
    if canonical_json(task.canonical_dict()) != canonical_json(raw):
        raise AutonomyError("TASK_ROW_INVALID: canonical type/value mismatch")
    if row["task_id"] != task.task_id:
        raise AutonomyError("TASK_ROW_INVALID: SQL task_id mismatch")
    if type(row["source_issue"]) is not type(task.source_issue) or row["source_issue"] != task.source_issue:
        raise AutonomyError("TASK_ROW_INVALID: SQL source_issue mismatch")
    if row["payload_hash"] != task.payload_hash or row["envelope_hash"] != task.envelope_hash:
        raise AutonomyError("TASK_ROW_INVALID: stored hash mismatch")
    return task


def _string_leaves(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from _string_leaves(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from _string_leaves(item)


def _has_prohibited_token(task: Task | None, sidecar: dict[str, Any]) -> bool:
    values: list[str] = []
    if task is not None:
        values.extend((task.task_id, task.stop_condition))
    values.extend((
        sidecar["target_chat"], sidecar["scientific_parent"],
        sidecar["current_observed_status"],
    ))
    values.extend(_string_leaves(sidecar["external_project_fields"]))
    for value in values:
        upper = value.casefold().upper()
        for token in PROHIBITED_TOKENS:
            if re.search(r"(?<![A-Z0-9])" + re.escape(token) + r"(?![A-Z0-9])", upper):
                return True
    return False


def _input_contract(task: Task, head: str) -> bool:
    if task.action == "head_check":
        return task.inputs in ({}, {"expected_origin": head})
    if task.action == "status_check":
        return task.inputs == {} or (
            set(task.inputs) == {"tracked_clean"}
            and type(task.inputs["tracked_clean"]) is bool
            and task.inputs["tracked_clean"] is True
        )
    return task.action == "dependency_check" and task.inputs == {}


def _candidate(
    *, sidecar: dict[str, Any], metadata_hash: str, task: Task | None,
    task_row: sqlite3.Row | None, states: dict[str, str], head: str,
    config_hash: str,
) -> dict[str, Any]:
    dependencies = [] if task is None else [
        {"task_id": dep, "state": states.get(dep)} for dep in sorted(task.dependencies)
    ]
    reason = None if task_row is None else task_row["reason"]
    if reason is not None and (not isinstance(reason, str) or len(reason) > 2000):
        raise AutonomyError("TASK_ROW_INVALID: fsm_reason")
    return {
        "repository": sidecar["repository"], "task_id": sidecar["task_id"],
        "sidecar_envelope_hash": sidecar["envelope_hash"],
        "sidecar_metadata_hash": metadata_hash,
        "task_envelope_hash": None if task is None else task.envelope_hash,
        "task_payload_hash": None if task is None else task.payload_hash,
        "fsm_state": None if task_row is None else task_row["state"],
        "fsm_reason": reason, "dependencies": dependencies,
        "verified_head": head, "effective_config_hash": config_hash,
    }


def _reasons(
    *, sidecar: dict[str, Any], task: Task | None, task_row: sqlite3.Row | None,
    states: dict[str, str], head: str, away: bool,
) -> list[str]:
    found: set[str] = set()
    if task is None:
        found.add("TASK_MISSING")
    else:
        if task.envelope_hash != sidecar["envelope_hash"]: found.add("ENVELOPE_MISMATCH")
        if task.role != "07_INFRASTRUCTURE": found.add("ROLE_NOT_INFRASTRUCTURE")
        if task.task_type != "deterministic": found.add("TASK_TYPE_NOT_DETERMINISTIC")
        if task.action not in SAFE_ACTIONS: found.add("ACTION_NOT_P1_SAFE")
        if task.canonical_head != head: found.add("TASK_HEAD_MISMATCH")
        if task_row is None or task_row["state"] != State.READY.value: found.add("TASK_NOT_READY")
        if any(states.get(dep) != State.SUCCEEDED.value for dep in task.dependencies):
            found.add("DEPENDENCY_NOT_SUCCEEDED")
        if not _input_contract(task, head): found.add("INPUT_CONTRACT_VIOLATION")
        if task.allowed_paths or task.expected_artifacts:
            found.add("PATH_OR_ARTIFACT_SCOPE_FORBIDDEN")
    if sidecar["repository"] != CANONICAL_REPOSITORY: found.add("REPOSITORY_NOT_CANONICAL")
    if sidecar["execution_lane"] != "LOCAL_DETERMINISTIC": found.add("NON_LOCAL_DETERMINISTIC_LANE")
    if sidecar["unattended_safe"] is not True: found.add("NOT_UNATTENDED_SAFE")
    if sidecar["human_attention_class"] != "NONE": found.add("HUMAN_ATTENTION_REQUIRED")
    if sidecar["chat_only"] is not False: found.add("CHAT_ONLY")
    if sidecar["dispatch_claim"] != "NONE": found.add("DISPATCH_CLAIM_FORBIDDEN")
    if sidecar["external_project_fields"].get("task_class") != "INFRASTRUCTURE":
        found.add("TASK_CLASS_NOT_INFRASTRUCTURE")
    if away and sidecar["away_eligible"] is not True: found.add("AWAY_INELIGIBLE")
    if _has_prohibited_token(task, sidecar): found.add("PROHIBITED_DOMAIN_TOKEN")
    return [reason for reason in REASON_ORDER if reason in found]


def build_plan(cfg: dict[str, Any], conn: sqlite3.Connection, head: str) -> dict[str, Any]:
    effective_config = {
        "autonomy": cfg["autonomy"],
        "max_concurrent_workers": cfg["max_concurrent_workers"],
    }
    config_hash = digest(effective_config)
    conn.execute("BEGIN")
    try:
        task_rows = list(conn.execute("SELECT * FROM tasks ORDER BY task_id"))
        sidecar_rows = list(conn.execute(
            "SELECT * FROM task_sidecars ORDER BY repository,task_id,envelope_hash"
        ))
        states = {row["task_id"]: row["state"] for row in task_rows}
        tasks: dict[str, tuple[sqlite3.Row, Task]] = {}
        for row in task_rows:
            task = _task_from_row(row)
            if task.task_id in tasks:
                raise AutonomyError("TASK_ROW_INVALID: duplicate task identity")
            tasks[task.task_id] = (row, task)
        prepared: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in sidecar_rows:
            try:
                raw = json.loads(row["metadata_json"])
                sidecar = validate_sidecar(raw)
                repository, task_id, envelope_hash, metadata_hash = sidecar_identity(sidecar)
            except Exception as exc:
                raise AutonomyError(f"SIDECAR_ROW_INVALID: {exc}") from exc
            if (repository != row["repository"] or task_id != row["task_id"]
                    or envelope_hash != row["envelope_hash"]
                    or metadata_hash != row["metadata_hash"]):
                raise AutonomyError("SIDECAR_ROW_INVALID: stored identity mismatch")
            identity = (repository, task_id, envelope_hash)
            if identity in seen:
                raise AutonomyError("SIDECAR_ROW_INVALID: duplicate logical identity")
            seen.add(identity)
            pair = tasks.get(task_id)
            task_row, task = pair if pair is not None else (None, None)
            candidate = _candidate(
                sidecar=sidecar, metadata_hash=metadata_hash, task=task,
                task_row=task_row, states=states, head=head, config_hash=config_hash,
            )
            reasons = _reasons(
                sidecar=sidecar, task=task, task_row=task_row, states=states,
                head=head, away=cfg["autonomy"]["away_mode"],
            )
            prepared.append((candidate, sidecar, reasons))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    prepared.sort(key=lambda item: (
        item[0]["repository"], item[0]["task_id"], item[0]["sidecar_envelope_hash"],
    ))
    capacity = min(
        cfg["autonomy"]["max_batch_tasks"],
        cfg["autonomy"]["max_parallel_local"],
        cfg["max_concurrent_workers"],
    )
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate, _sidecar, reasons in prepared:
        identity = {
            "repository": candidate["repository"], "task_id": candidate["task_id"],
            "envelope_hash": candidate["sidecar_envelope_hash"],
        }
        if not reasons and len(selected) < capacity:
            selected.append({**identity, "slot": len(selected)})
        else:
            if not reasons:
                reasons = ["CAPACITY_EXHAUSTED"]
            excluded.append({**identity, "reasons": reasons})
    candidates = [item[0] for item in prepared]
    body = {
        "schema_version": 1, "repository": CANONICAL_REPOSITORY,
        "canonical_head": head, "origin_main": head,
        "effective_config": effective_config,
        "effective_config_hash": config_hash,
        "candidates": candidates, "input_fingerprint": digest(candidates),
        "away_mode": cfg["autonomy"]["away_mode"],
        "capacity": {
            "max_batch_tasks": cfg["autonomy"]["max_batch_tasks"],
            "max_parallel_local": cfg["autonomy"]["max_parallel_local"],
            "max_concurrent_workers": cfg["max_concurrent_workers"],
            "effective": capacity,
        },
        "selected": selected, "excluded": excluded,
        "invariants": dict(ENABLED_INVARIANTS),
    }
    return {"batch_id": digest(body), **body}


def _regular_at(dir_fd: int, name: str) -> bool:
    try:
        mode = os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise AutonomyError("CHECKPOINT_INVALID: target is not a regular file")
    return True


def _read_at(dir_fd: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AutonomyError("CHECKPOINT_INVALID: not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk: break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_temp(dir_fd: int, prefix: str, data: bytes) -> str:
    name = f".{prefix}.{secrets.token_hex(8)}.tmp"
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
        dir_fd=dir_fd,
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return name


def _open_checkpoint_dirs(state_dir: Path, subdir: str) -> tuple[int, int, int]:
    state = state_dir.resolve(strict=True)
    state_fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            entry = os.stat(subdir, dir_fd=state_fd, follow_symlinks=False)
            if not stat.S_ISDIR(entry.st_mode):
                raise AutonomyError("CHECKPOINT_INVALID: checkpoint component")
        except FileNotFoundError:
            os.mkdir(subdir, 0o700, dir_fd=state_fd)
            os.fsync(state_fd)
        checkpoint_fd = os.open(
            subdir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=state_fd,
        )
        try:
            try:
                entry = os.stat("batches", dir_fd=checkpoint_fd, follow_symlinks=False)
                if not stat.S_ISDIR(entry.st_mode):
                    raise AutonomyError("CHECKPOINT_INVALID: batches component")
            except FileNotFoundError:
                os.mkdir("batches", 0o700, dir_fd=checkpoint_fd)
                os.fsync(checkpoint_fd)
            batches_fd = os.open(
                "batches", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=checkpoint_fd,
            )
        except Exception:
            os.close(checkpoint_fd)
            raise
        return state_fd, checkpoint_fd, batches_fd
    except Exception:
        os.close(state_fd)
        raise


def publish_checkpoint(cfg: dict[str, Any], batch: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
    validate_batch(batch)
    observed_at = observed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    latest = {
        "schema_version": 1, "batch_id": batch["batch_id"],
        "canonical_head": batch["canonical_head"], "observed_at": observed_at,
    }
    validate_latest(latest)
    batch_bytes = canonical_json(batch) + b"\n"
    latest_bytes = canonical_json(latest) + b"\n"
    state_fd, checkpoint_fd, batches_fd = _open_checkpoint_dirs(
        Path(cfg["state_dir"]), cfg["autonomy"]["checkpoint_subdir"],
    )
    batch_temp = latest_temp = None
    try:
        checkpoint_stat = os.fstat(checkpoint_fd)
        batches_stat = os.fstat(batches_fd)
        final_name = batch["batch_id"] + ".json"
        batch_temp = _write_temp(batches_fd, "batch", batch_bytes)
        try:
            os.link(
                batch_temp, final_name, src_dir_fd=batches_fd, dst_dir_fd=batches_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if not _regular_at(batches_fd, final_name) or _read_at(batches_fd, final_name) != batch_bytes:
                raise AutonomyError("BATCH_ID_CONFLICT")
        os.unlink(batch_temp, dir_fd=batches_fd); batch_temp = None
        os.fsync(batches_fd)
        latest_temp = _write_temp(checkpoint_fd, "latest", latest_bytes)
        if (os.fstat(checkpoint_fd).st_ino != checkpoint_stat.st_ino
                or os.fstat(checkpoint_fd).st_dev != checkpoint_stat.st_dev
                or os.fstat(batches_fd).st_ino != batches_stat.st_ino
                or os.fstat(batches_fd).st_dev != batches_stat.st_dev):
            raise AutonomyError("CHECKPOINT_INVALID: directory identity changed")
        if _regular_at(checkpoint_fd, "latest.json"):
            pass
        os.replace(
            latest_temp, "latest.json", src_dir_fd=checkpoint_fd,
            dst_dir_fd=checkpoint_fd,
        ); latest_temp = None
        os.fsync(checkpoint_fd)
        return {"status": "PLANNED", **batch}
    finally:
        for fd, name in ((batches_fd, batch_temp), (checkpoint_fd, latest_temp)):
            if name:
                try: os.unlink(name, dir_fd=fd)
                except FileNotFoundError: pass
        os.close(batches_fd); os.close(checkpoint_fd); os.close(state_fd)


def validate_latest(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"schema_version", "batch_id", "canonical_head", "observed_at"}:
        raise AutonomyError("CHECKPOINT_INVALID: latest keys")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise AutonomyError("CHECKPOINT_INVALID: latest schema")
    if not SHA64.fullmatch(value["batch_id"]) or not SHA40.fullmatch(value["canonical_head"]):
        raise AutonomyError("CHECKPOINT_INVALID: latest identity")
    if not isinstance(value["observed_at"], str) or not UTC_SECONDS.fullmatch(value["observed_at"]):
        raise AutonomyError("CHECKPOINT_INVALID: latest timestamp")


def validate_batch(value: Any) -> None:
    required = {
        "schema_version", "batch_id", "repository", "canonical_head", "origin_main",
        "effective_config", "effective_config_hash", "candidates", "input_fingerprint",
        "away_mode", "capacity", "selected", "excluded", "invariants",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise AutonomyError("CHECKPOINT_INVALID: batch keys")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise AutonomyError("CHECKPOINT_INVALID: batch schema")
    if value["repository"] != CANONICAL_REPOSITORY:
        raise AutonomyError("CHECKPOINT_INVALID: repository")
    for key in ("batch_id", "effective_config_hash", "input_fingerprint"):
        if not isinstance(value[key], str) or not SHA64.fullmatch(value[key]):
            raise AutonomyError("CHECKPOINT_INVALID: hash")
    if value["canonical_head"] != value["origin_main"] or not SHA40.fullmatch(value["canonical_head"]):
        raise AutonomyError("CHECKPOINT_INVALID: HEAD")
    if type(value["away_mode"]) is not bool or value["invariants"] != ENABLED_INVARIANTS:
        raise AutonomyError("CHECKPOINT_INVALID: invariants")
    if digest(value["effective_config"]) != value["effective_config_hash"]:
        raise AutonomyError("CHECKPOINT_INVALID: config hash")
    if digest(value["candidates"]) != value["input_fingerprint"]:
        raise AutonomyError("CHECKPOINT_INVALID: input hash")
    body = {key: item for key, item in value.items() if key != "batch_id"}
    if digest(body) != value["batch_id"]:
        raise AutonomyError("CHECKPOINT_INVALID: batch hash")
    identities = []
    for candidate in value["candidates"]:
        candidate_keys = {
            "repository", "task_id", "sidecar_envelope_hash", "sidecar_metadata_hash",
            "task_envelope_hash", "task_payload_hash", "fsm_state", "fsm_reason",
            "dependencies", "verified_head", "effective_config_hash",
        }
        if not isinstance(candidate, dict) or set(candidate) != candidate_keys:
            raise AutonomyError("CHECKPOINT_INVALID: candidate keys")
        if not REPOSITORY_RE.fullmatch(candidate["repository"]) or not SIDECAR_TASK_ID.fullmatch(candidate["task_id"]):
            raise AutonomyError("CHECKPOINT_INVALID: candidate identity")
        if not SHA64.fullmatch(candidate["sidecar_envelope_hash"]) or not SHA64.fullmatch(candidate["sidecar_metadata_hash"]):
            raise AutonomyError("CHECKPOINT_INVALID: candidate hash")
        for key in ("task_envelope_hash", "task_payload_hash"):
            if candidate[key] is not None and not SHA64.fullmatch(candidate[key]):
                raise AutonomyError("CHECKPOINT_INVALID: nullable task hash")
        if candidate["fsm_state"] is not None and candidate["fsm_state"] not in {state.value for state in State}:
            raise AutonomyError("CHECKPOINT_INVALID: state")
        if candidate["fsm_reason"] is not None and (not isinstance(candidate["fsm_reason"], str) or len(candidate["fsm_reason"]) > 2000):
            raise AutonomyError("CHECKPOINT_INVALID: reason")
        if candidate["verified_head"] != value["canonical_head"] or candidate["effective_config_hash"] != value["effective_config_hash"]:
            raise AutonomyError("CHECKPOINT_INVALID: candidate context")
        dependencies = candidate["dependencies"]
        if not isinstance(dependencies, list): raise AutonomyError("CHECKPOINT_INVALID: dependencies")
        dep_ids = []
        for dep in dependencies:
            if not isinstance(dep, dict) or set(dep) != {"task_id", "state"}:
                raise AutonomyError("CHECKPOINT_INVALID: dependency keys")
            if not isinstance(dep["task_id"], str) or not SIDECAR_TASK_ID.fullmatch(dep["task_id"]):
                raise AutonomyError("CHECKPOINT_INVALID: dependency id")
            if dep["state"] is not None and dep["state"] not in {state.value for state in State}:
                raise AutonomyError("CHECKPOINT_INVALID: dependency state")
            dep_ids.append(dep["task_id"])
        if dep_ids != sorted(set(dep_ids)):
            raise AutonomyError("CHECKPOINT_INVALID: dependency order")
        identities.append((candidate["repository"], candidate["task_id"], candidate["sidecar_envelope_hash"]))
    if identities != sorted(set(identities)):
        raise AutonomyError("CHECKPOINT_INVALID: candidate order")
    decision_ids = []
    slots = []
    for selected in value["selected"]:
        if not isinstance(selected, dict) or set(selected) != {"repository", "task_id", "envelope_hash", "slot"}:
            raise AutonomyError("CHECKPOINT_INVALID: selected")
        decision_ids.append((selected["repository"], selected["task_id"], selected["envelope_hash"]))
        slots.append(selected["slot"])
    for excluded in value["excluded"]:
        if not isinstance(excluded, dict) or set(excluded) != {"repository", "task_id", "envelope_hash", "reasons"}:
            raise AutonomyError("CHECKPOINT_INVALID: excluded")
        reasons = excluded["reasons"]
        if not isinstance(reasons, list) or reasons != [r for r in REASON_ORDER if r in reasons] or len(reasons) != len(set(reasons)):
            raise AutonomyError("CHECKPOINT_INVALID: reason order")
        decision_ids.append((excluded["repository"], excluded["task_id"], excluded["envelope_hash"]))
    if sorted(decision_ids) != identities or len(decision_ids) != len(set(decision_ids)):
        raise AutonomyError("CHECKPOINT_INVALID: partition")
    if slots != list(range(len(slots))):
        raise AutonomyError("CHECKPOINT_INVALID: slots")


def checkpoint_status(cfg: dict[str, Any]) -> dict[str, Any]:
    if not cfg["autonomy"]["enabled"]:
        return {"status": "DISABLED"}
    root = Path(cfg["state_dir"]).resolve() / cfg["autonomy"]["checkpoint_subdir"]
    if not root.exists(): return {"status": "ABSENT"}
    if root.is_symlink() or not root.is_dir():
        raise AutonomyError("CHECKPOINT_INVALID: checkpoint directory")
    checkpoint_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if not _regular_at(checkpoint_fd, "latest.json"):
            return {"status": "ABSENT"}
        latest = json.loads(_read_at(checkpoint_fd, "latest.json"))
        validate_latest(latest)
        batches_fd = os.open("batches", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=checkpoint_fd)
        try:
            batch = json.loads(_read_at(batches_fd, latest["batch_id"] + ".json"))
        finally:
            os.close(batches_fd)
        validate_batch(batch)
        if latest["batch_id"] != batch["batch_id"] or latest["canonical_head"] != batch["canonical_head"]:
            raise AutonomyError("CHECKPOINT_INVALID: latest mismatch")
        return {"status": "VALID", "latest": latest, "batch": batch}
    except (OSError, json.JSONDecodeError) as exc:
        raise AutonomyError(f"CHECKPOINT_INVALID: {exc}") from exc
    finally:
        os.close(checkpoint_fd)
