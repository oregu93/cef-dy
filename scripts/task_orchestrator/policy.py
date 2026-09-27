from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

from .model import Task, ValidationError


PROTECTED_PREFIXES = (
    "00_Project/", "01_Logbook/", "02_Work_Checkpoints/", "04_Results/",
    "05_Literature/", "06_Scientific_Understanding/", "03_Protocols/",
)


def normalize_relative(path_text: str) -> str:
    if not isinstance(path_text, str) or not path_text or "\x00" in path_text:
        raise ValidationError("path must be a non-empty string without NUL")
    path_text = path_text.replace("\\", "/")
    path = PurePosixPath(path_text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValidationError(f"unsafe repository path: {path_text}")
    return path.as_posix()


def resolve_read_path(repo: Path, path_text: str, forbidden: list[str]) -> Path:
    relative = normalize_relative(path_text)
    if any(fnmatch(relative, pattern) or fnmatch(relative + "/", pattern) for pattern in forbidden):
        raise ValidationError(f"path forbidden by policy: {relative}")
    candidate = (repo / relative).resolve(strict=False)
    root = repo.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValidationError(f"path escapes repository: {relative}")
    resolved_relative = candidate.relative_to(root).as_posix()
    if any(fnmatch(resolved_relative, pattern) or fnmatch(resolved_relative + "/", pattern)
           for pattern in forbidden):
        raise ValidationError(f"resolved path forbidden by policy: {relative}")
    return candidate


def validate_task_policy(task: Task, cfg: dict[str, Any]) -> None:
    forbidden = list(cfg["paths"]["forbidden_patterns"])
    for value in (*task.allowed_paths, *task.expected_artifacts):
        resolve_read_path(Path(cfg["repository_root"]), value, forbidden)
    if task.action == "test_command":
        command_id = task.inputs.get("command_id")
        if command_id not in cfg["commands"]["allow"]:
            raise ValidationError("test_command is not allowlisted")
    if task.is_llm:
        if cfg["llm"].get("paid_fallback_allowed") is not False:
            raise ValidationError("paid LLM fallback is forbidden")
        if int(cfg["max_concurrent_llm_runs"]) != 1:
            raise ValidationError("max_concurrent_llm_runs must be 1")


def task_has_issue_approval(task: Task, cfg: dict[str, Any]) -> bool:
    return cfg["llm"]["require_issue_label"] in task.labels
