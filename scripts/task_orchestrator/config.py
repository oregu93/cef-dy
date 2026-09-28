from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
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
    "github": {"enabled": False, "repository": "oregu93/cef-dy", "task_label": "orchestrator:task", "attention_issue": None, "track_manual_edits": True, "api_base": "https://api.github.com", "token_env": "GITHUB_TOKEN", "timeout_seconds": 20, "max_pages": 10, "backoff_initial_seconds": 5, "backoff_max_seconds": 300},
    "llm": {
        "dispatch_enabled": False, "paid_fallback_allowed": False,
        "require_issue_label": "orchestrator:llm-approved",
        "require_local_approval": True, "require_explicit_resume": True,
        "detached_workers": True,
        "lease_seconds": 1200, "quota_probe_guard_seconds": 60,
        "quota_probe_backoff_seconds": [300, 900, 1800, 3600],
        "command": {
            "argv": ["/usr/lib/chatgpt/resources/codex", "exec", "--ephemeral",
                     "--sandbox", "read-only", "--skip-git-repo-check",
                     "--output-last-message", "{output}", "-"],
            "probe_prompt": "Reply with exactly ADMISSION_OK and do not use tools.",
            "timeout_seconds": 900,
        },
        "ollama": {"enabled": False, "verified_interface": False, "base_url": "http://127.0.0.1:11434", "model": "", "timeout_seconds": 30, "max_concurrent_runs": 1},
    },
    "non_work_ai": {
        "enabled": False, "verified_interface": False, "max_concurrent_runs": 1,
        "command": {"argv": [], "timeout_seconds": 900},
    },
    "visibility": {
        "enabled": False,
        "quota_stale_after_seconds": 900,
        "quota": {
            "five_hour": {"state": "UNKNOWN", "observed_at": None, "reset_at": None},
            "weekly": {"state": "UNKNOWN", "observed_at": None, "reset_at": None},
        },
    },
    "publishing": {
        "enabled": False,
        "preview_only": True,
        "trusted_authors": [],
    },
    "chat_health": {
        "enabled": False,
        "observation_stale_after_seconds": 86400,
    },
    "autonomy": {
        "enabled": False,
        "plan_only": False,
        "away_mode": False,
        "max_batch_tasks": 1,
        "max_parallel_local": 1,
        "checkpoint_subdir": "autonomy",
        "result_inbox_subdir": "result-inbox",
        "evidence_subdir": "m1b-evidence",
    },
    "routing": {
        "enabled": False,
        "bootstrap_path": "03_Protocols/CHAT_BOOTSTRAPS.md",
        "auto_create_reviews": True,
    },
    "dashboard": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 8765,
        "stale_after_seconds": 300,
        "recent_events": 100,
    },
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
    workers = cfg["max_concurrent_workers"]
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
        raise ValidationError("max_concurrent_workers must be an integer from 1 to 16")
    if cfg["llm"].get("paid_fallback_allowed") is not False:
        raise ValidationError("paid_fallback_allowed must be false")
    if cfg["mode"] in {"shadow", "dry-run"} and cfg["llm"].get("dispatch_enabled"):
        raise ValidationError("LLM dispatch cannot be enabled in shadow/dry-run")
    if type(cfg["publishing"].get("enabled")) is not bool or type(cfg["publishing"].get("preview_only")) is not bool:
        raise ValidationError("publishing enabled/preview_only must be boolean")
    if cfg["publishing"].get("enabled") and cfg["publishing"].get("preview_only"):
        raise ValidationError("live publishing requires preview_only=false")
    if not isinstance(cfg["publishing"].get("trusted_authors"), list):
        raise ValidationError("publishing.trusted_authors must be a list")
    if cfg["publishing"].get("enabled") and not cfg["publishing"].get("trusted_authors"):
        raise ValidationError("live publishing requires trusted_authors")
    if cfg["publishing"].get("enabled") and not cfg["github"].get("enabled"):
        raise ValidationError("live publishing requires github.enabled")
    attention_issue = cfg["github"].get("attention_issue")
    if attention_issue is not None and (
        isinstance(attention_issue, bool) or not isinstance(attention_issue, int) or attention_issue < 1
    ):
        raise ValidationError("github.attention_issue must be null or a positive integer")
    if isinstance(cfg["visibility"].get("quota_stale_after_seconds"), bool) or int(cfg["visibility"].get("quota_stale_after_seconds", 0)) <= 0:
        raise ValidationError("visibility quota_stale_after_seconds must be positive")
    for window in ("five_hour", "weekly"):
        value = cfg["visibility"].get("quota", {}).get(window, {})
        if value.get("state") not in {"AVAILABLE", "EXHAUSTED", "UNKNOWN", "STALE"}:
            raise ValidationError(f"invalid {window} quota state")
    if isinstance(cfg["chat_health"].get("observation_stale_after_seconds"), bool) or int(cfg["chat_health"].get("observation_stale_after_seconds", 0)) <= 0:
        raise ValidationError("chat_health observation_stale_after_seconds must be positive")
    autonomy = cfg.get("autonomy")
    autonomy_keys = {
        "enabled", "plan_only", "away_mode", "max_batch_tasks",
        "max_parallel_local", "checkpoint_subdir", "result_inbox_subdir",
        "evidence_subdir",
    }
    if not isinstance(autonomy, dict) or set(autonomy) != autonomy_keys:
        raise ValidationError("autonomy fields mismatch")
    for key in ("enabled", "plan_only", "away_mode"):
        if type(autonomy[key]) is not bool:
            raise ValidationError(f"autonomy.{key} must be boolean")
    for key in ("max_batch_tasks", "max_parallel_local"):
        value = autonomy[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
            raise ValidationError(f"autonomy.{key} must be an integer from 1 to 16")
        if value > workers:
            raise ValidationError(f"autonomy.{key} cannot exceed max_concurrent_workers")
    for name in ("checkpoint_subdir", "result_inbox_subdir", "evidence_subdir"):
        subdir = autonomy[name]
        if not isinstance(subdir, str) or subdir in {".", ".."} or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", subdir
        ) is None:
            raise ValidationError(f"autonomy.{name} must be one safe relative component")
    llm = cfg["llm"]
    if isinstance(llm.get("lease_seconds"), bool) or int(llm.get("lease_seconds", 0)) < 30:
        raise ValidationError("llm.lease_seconds must be at least 30")
    if type(llm.get("detached_workers")) is not bool:
        raise ValidationError("llm.detached_workers must be boolean")
    if isinstance(llm.get("quota_probe_guard_seconds"), bool) or int(llm.get("quota_probe_guard_seconds", 0)) < 0:
        raise ValidationError("llm.quota_probe_guard_seconds must be nonnegative")
    backoff = llm.get("quota_probe_backoff_seconds")
    if not isinstance(backoff, list) or not backoff or any(
        isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in backoff
    ):
        raise ValidationError("llm.quota_probe_backoff_seconds must be positive integers")
    command = llm.get("command")
    if not isinstance(command, dict) or set(command) != {"argv", "probe_prompt", "timeout_seconds"}:
        raise ValidationError("llm.command fields mismatch")
    if not isinstance(command["argv"], list) or not command["argv"] or any(
        not isinstance(v, str) or not v for v in command["argv"]
    ):
        raise ValidationError("llm.command.argv must be nonempty strings")
    if isinstance(command["timeout_seconds"], bool) or not isinstance(command["timeout_seconds"], int) or command["timeout_seconds"] < 1:
        raise ValidationError("llm.command.timeout_seconds must be a positive integer")
    if llm["detached_workers"] and int(llm["lease_seconds"]) < int(command["timeout_seconds"]) + 120:
        raise ValidationError("detached worker lease must exceed worker timeout by at least 120 seconds")
    for name, lane in (("llm.ollama", llm["ollama"]), ("non_work_ai", cfg["non_work_ai"])):
        if type(lane.get("enabled")) is not bool or type(lane.get("verified_interface")) is not bool:
            raise ValidationError(f"{name} enabled/verified_interface must be boolean")
        concurrency = lane.get("max_concurrent_runs")
        if isinstance(concurrency, bool) or not isinstance(concurrency, int) or not 1 <= concurrency <= 16:
            raise ValidationError(f"{name}.max_concurrent_runs must be an integer from 1 to 16")
        if lane["enabled"] and not lane["verified_interface"]:
            raise ValidationError(f"{name} cannot be enabled without a verified interface")
    non_work_command = cfg["non_work_ai"]["command"]
    if set(non_work_command) != {"argv", "timeout_seconds"} or not isinstance(non_work_command["argv"], list):
        raise ValidationError("non_work_ai.command fields mismatch")
    if any(not isinstance(value, str) or not value for value in non_work_command["argv"]):
        raise ValidationError("non_work_ai.command.argv must contain nonempty strings")
    if isinstance(non_work_command["timeout_seconds"], bool) or not isinstance(non_work_command["timeout_seconds"], int) or non_work_command["timeout_seconds"] < 1:
        raise ValidationError("non_work_ai.command.timeout_seconds must be positive")
    if cfg["non_work_ai"]["enabled"] and not non_work_command["argv"]:
        raise ValidationError("enabled non_work_ai requires command.argv")
    if cfg["publishing"].get("enabled") and (
        cfg["mode"] != "pilot" or not autonomy["enabled"] or autonomy["plan_only"]
    ):
        raise ValidationError("live publishing requires active pilot autonomy")
    routing = cfg.get("routing")
    if not isinstance(routing, dict) or set(routing) != {
        "enabled", "bootstrap_path", "auto_create_reviews",
    }:
        raise ValidationError("routing fields mismatch")
    if type(routing["enabled"]) is not bool or type(routing["auto_create_reviews"]) is not bool:
        raise ValidationError("routing enabled/auto_create_reviews must be boolean")
    if not isinstance(routing["bootstrap_path"], str) or not routing["bootstrap_path"]:
        raise ValidationError("routing.bootstrap_path must be a nonempty path")
    dashboard = cfg.get("dashboard")
    if not isinstance(dashboard, dict) or set(dashboard) != {
        "enabled", "host", "port", "stale_after_seconds", "recent_events",
    }:
        raise ValidationError("dashboard fields mismatch")
    if type(dashboard["enabled"]) is not bool:
        raise ValidationError("dashboard.enabled must be boolean")
    if dashboard["host"] != "127.0.0.1":
        raise ValidationError("dashboard host must be loopback-only")
    for name, low, high in (("port", 1, 65535), ("stale_after_seconds", 1, 86400), ("recent_events", 1, 1000)):
        value = dashboard[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValidationError(f"dashboard.{name} must be an integer from {low} to {high}")
    repo = Path(cfg["repository_root"])
    if not repo.is_absolute():
        repo = (path.parent.parent / repo).resolve()
    cfg["repository_root"] = str(repo)
    bootstrap = Path(routing["bootstrap_path"])
    if not bootstrap.is_absolute():
        bootstrap = (repo / bootstrap).resolve()
    routing["bootstrap_path"] = str(bootstrap)
    state = Path(cfg["state_dir"])
    if not state.is_absolute():
        state = (repo / state).resolve()
    cfg["state_dir"] = str(state)
    cfg["_config_path"] = str(path)
    return cfg
