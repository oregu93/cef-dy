from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from .model import Task, WorkerResult, utc_now
from .policy import resolve_read_path


class WorkerFailure(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise WorkerFailure((proc.stderr or proc.stdout).strip() or "git command failed")
    return proc.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_structured(path: Path) -> Any:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run(task: Task, attempt: int, cfg: dict[str, Any]) -> WorkerResult:
    started = utc_now()
    checks: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    error = None
    status = "SUCCEEDED"
    repo = Path(cfg["repository_root"])
    forbidden = list(cfg["paths"]["forbidden_patterns"])
    try:
        actual_head = _git(repo, "rev-parse", "HEAD")
        if actual_head != task.canonical_head:
            raise WorkerFailure(f"HEAD_DRIFT expected={task.canonical_head} actual={actual_head}")
        checks.append({"check": "canonical_head", "status": "PASS", "actual": actual_head})

        if task.action == "head_check":
            origin = _git(repo, "rev-parse", "origin/main")
            expected_origin = task.inputs.get("expected_origin", task.canonical_head)
            if origin != expected_origin:
                raise WorkerFailure(f"ORIGIN_HEAD_DRIFT expected={expected_origin} actual={origin}")
            checks.append({"check": "origin_main", "status": "PASS", "actual": origin})

        elif task.action == "sha256_check":
            expected = task.inputs.get("files")
            if not isinstance(expected, dict) or not expected:
                raise WorkerFailure("inputs.files must be a non-empty path-to-SHA mapping")
            for name, digest in sorted(expected.items()):
                path = resolve_read_path(repo, name, forbidden)
                if not path.is_file():
                    raise WorkerFailure(f"missing file: {name}")
                actual = _sha256(path)
                if actual != digest:
                    raise WorkerFailure(f"SHA_MISMATCH path={name} expected={digest} actual={actual}")
                checks.append({"check": "sha256", "path": name, "status": "PASS", "actual": actual})

        elif task.action == "schema_check":
            paths = task.inputs.get("paths", [])
            required = task.inputs.get("required_keys", [])
            if not isinstance(paths, list) or not isinstance(required, list):
                raise WorkerFailure("schema_check paths and required_keys must be lists")
            for name in paths:
                path = resolve_read_path(repo, name, forbidden)
                value = _read_structured(path)
                if not isinstance(value, dict):
                    raise WorkerFailure(f"structured file is not a mapping: {name}")
                missing = sorted(set(required) - set(value))
                if missing:
                    raise WorkerFailure(f"missing keys in {name}: {', '.join(missing)}")
                checks.append({"check": "schema", "path": name, "status": "PASS"})

        elif task.action == "dependency_check":
            checks.append({"check": "dependencies", "status": "PASS", "count": len(task.dependencies)})

        elif task.action == "status_check":
            porcelain = _git(repo, "status", "--porcelain=v1", "--untracked-files=no")
            expected_clean = bool(task.inputs.get("tracked_clean", True))
            if expected_clean and porcelain:
                raise WorkerFailure("tracked worktree is dirty")
            checks.append({"check": "tracked_status", "status": "PASS", "clean": not bool(porcelain)})

        elif task.action == "artifact_check":
            for name in task.expected_artifacts:
                path = resolve_read_path(repo, name, forbidden)
                if not path.is_file():
                    raise WorkerFailure(f"missing artifact: {name}")
                artifacts.append({"path": name, "size": path.stat().st_size, "sha256": _sha256(path)})
            checks.append({"check": "artifacts", "status": "PASS", "count": len(artifacts)})

        elif task.action == "test_command":
            command_id = task.inputs["command_id"]
            command = cfg["commands"]["allow"][command_id]
            argv = command["argv"]
            if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
                raise WorkerFailure("allowlisted argv is invalid")
            timeout = min(task.timeout_seconds, int(command.get("timeout_seconds", task.timeout_seconds)))
            proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout, shell=False)
            checks.append({"check": "test_command", "command_id": command_id, "status": "PASS" if proc.returncode == 0 else "FAIL", "returncode": proc.returncode, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]})
            if proc.returncode:
                raise WorkerFailure(f"allowlisted command failed with exit code {proc.returncode}")
        else:
            raise WorkerFailure(f"worker action is unavailable: {task.action}")
    except subprocess.TimeoutExpired as exc:
        status, error = "FAILED", f"WORKER_TIMEOUT after {exc.timeout}s"
    except Exception as exc:
        status, error = "FAILED", f"{type(exc).__name__}: {exc}"
    return WorkerResult(task.task_id, attempt, status, task.canonical_head, task.action, started, utc_now(), checks, artifacts, error)
