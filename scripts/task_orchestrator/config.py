from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .model import ValidationError


DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "mode": "shadow",
    "repository_root": ".",
    "state_dir": "CEF_Dy_Backup/task_orchestrator",
    "poll_interval_seconds": 300,
    "lock_stale_after_seconds": 900,
    "orphaned_run_after_seconds": 1800,
    "max_concurrent_workers": 2,
    "max_concurrent_llm_runs": 1,
    "github": {"enabled": False, "repository": "oregu93/cef-dy", "task_label": "orchestrator:task", "track_manual_edits": True, "api_base": "https://api.github.com", "token_env": "GITHUB_TOKEN", "timeout_seconds": 20, "max_pages": 10, "backoff_initial_seconds": 5, "backoff_max_seconds": 300},
    "llm": {"dispatch_enabled": False, "paid_fallback_allowed": False, "require_issue_label": "orchestrator:llm-approved", "require_local_approval": True, "require_explicit_resume": True, "ollama": {"enabled": False, "base_url": "http://127.0.0.1:11434", "model": "", "timeout_seconds": 30}},
    "paths": {"allowed_read_roots": ["."], "forbidden_patterns": [".git/**", "CEF_Dy_Data/**", "private/**", "secrets/**", "credentials/**", "04_Results/raw/**", "04_Results/intermediate/**"], "allowed_output_root": "CEF_Dy_Backup/task_orchestrator"},
    "commands": {"allow": {}},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"cannot load config: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError("config must be a mapping")
    cfg = _merge(DEFAULTS, raw)
    if cfg["schema_version"] != 1 or cfg["mode"] not in {"shadow", "dry-run", "pilot"}:
        raise ValidationError("unsupported config schema or mode")
    if cfg["max_concurrent_llm_runs"] != 1:
        raise ValidationError("max_concurrent_llm_runs must equal 1")
    if cfg["llm"].get("paid_fallback_allowed") is not False:
        raise ValidationError("paid_fallback_allowed must be false")
    if cfg["mode"] in {"shadow", "dry-run"} and cfg["llm"].get("dispatch_enabled"):
        raise ValidationError("LLM dispatch cannot be enabled in shadow/dry-run")
    repo = Path(cfg["repository_root"])
    if not repo.is_absolute():
        repo = (path.parent.parent / repo).resolve()
    cfg["repository_root"] = str(repo)
    state = Path(cfg["state_dir"])
    if not state.is_absolute():
        state = (repo / state).resolve()
    cfg["state_dir"] = str(state)
    return cfg
