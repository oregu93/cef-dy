from __future__ import annotations

import re
import json
from typing import Any

import yaml

from .model import Task, ValidationError


TASK_KEYS = {
    "schema_version", "task_id", "role", "canonical_head", "task_type", "action",
    "dependencies", "inputs", "allowed_paths", "expected_artifacts", "timeout_seconds",
    "stop_condition",
}
REQUIRED = {"schema_version", "task_id", "role", "canonical_head", "task_type", "action", "stop_condition"}
ROLES = {
    "00_PROJECT_CONTROL", "01_LITERATURE", "01_LITERATURE_PHYSICS",
    "02_TAIPAN_DATA_REDUCTION", "03_CEF", "03_CEF_MODELLING_FIT_DESIGN",
    "04_STRUCTURE", "04_STRUCTURE_CONVENTIONS", "07_INFRASTRUCTURE",
    "07_RESEARCH_SOFTWARE_INFRASTRUCTURE",
}
RESOURCE_REQUIREMENTS = {
    "DETERMINISTIC_REQUIRED", "LOCAL_SEMANTIC_OK", "NON_WORK_AI_OK",
    "WORK_PREFERRED", "WORK_REQUIRED", "HUMAN_REQUIRED",
}
RESOURCE_LANES = {
    "LOCAL_DETERMINISTIC", "LOCAL_OSS_MODEL", "NON_WORK_AI", "WORK_CODEX",
    "HUMAN_DECISION",
}
TASK_TYPES = {"deterministic", "llm_semantic", "llm_worker"}
ACTIONS = {"head_check", "sha256_check", "schema_check", "dependency_check", "status_check", "artifact_check", "test_command", "semantic_helper"}
DETERMINISTIC_ACTIONS = ACTIONS - {"semantic_helper"}
TASK_ID = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,127}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.IGNORECASE | re.DOTALL)


def _string(value: Any, label: str, max_length: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    if len(value) > max_length:
        raise ValidationError(f"{label} exceeds {max_length} characters")
    if "\x00" in value:
        raise ValidationError(f"{label} contains NUL")
    return value.strip()


def _string_list(value: Any, label: str, limit: int = 100) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > limit:
        raise ValidationError(f"{label} must be a list with at most {limit} items")
    result = tuple(_string(item, f"{label}[]", 500) for item in value)
    if len(set(result)) != len(result):
        raise ValidationError(f"{label} contains duplicates")
    return result


def validate_task(data: Any, *, source_issue: int | None = None, labels: tuple[str, ...] = ()) -> Task:
    if not isinstance(data, dict):
        raise ValidationError("task must be a mapping")
    unknown = sorted(set(data) - TASK_KEYS)
    missing = sorted(REQUIRED - set(data))
    if unknown:
        raise ValidationError(f"unknown task fields: {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"missing task fields: {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise ValidationError("schema_version must be integer 1")
    task_id = _string(data["task_id"], "task_id", 128)
    if not TASK_ID.fullmatch(task_id):
        raise ValidationError("task_id has invalid format")
    role = _string(data["role"], "role", 64)
    if role not in ROLES:
        raise ValidationError(f"unsupported role: {role}")
    head = _string(data["canonical_head"], "canonical_head", 40).lower()
    if not SHA.fullmatch(head):
        raise ValidationError("canonical_head must be a full lowercase Git SHA")
    task_type = _string(data["task_type"], "task_type", 32)
    action = _string(data["action"], "action", 64)
    if task_type not in TASK_TYPES:
        raise ValidationError(f"unsupported task_type: {task_type}")
    if action not in ACTIONS:
        raise ValidationError(f"unsupported action: {action}")
    if task_type == "deterministic" and action not in DETERMINISTIC_ACTIONS:
        raise ValidationError("deterministic task cannot use semantic_helper")
    if task_type != "deterministic" and action != "semantic_helper":
        raise ValidationError("LLM-class task may only use semantic_helper")
    inputs = data.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ValidationError("inputs must be a mapping")
    if not all(isinstance(key, str) for key in inputs):
        raise ValidationError("inputs keys must be strings")
    try:
        json.dumps(inputs, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"inputs must contain only finite JSON-compatible values: {exc}") from exc
    if len(yaml.safe_dump(inputs, allow_unicode=True)) > 100_000:
        raise ValidationError("inputs exceeds 100000 serialized characters")
    requirement = inputs.get("resource_requirement")
    if requirement is not None and requirement not in RESOURCE_REQUIREMENTS:
        raise ValidationError("inputs.resource_requirement is invalid")
    if requirement is not None:
        if task_type == "deterministic" and requirement not in {"DETERMINISTIC_REQUIRED", "HUMAN_REQUIRED"}:
            raise ValidationError("deterministic tasks require DETERMINISTIC_REQUIRED or HUMAN_REQUIRED")
        if task_type != "deterministic" and requirement == "DETERMINISTIC_REQUIRED":
            raise ValidationError("semantic tasks cannot declare DETERMINISTIC_REQUIRED")
    lanes = inputs.get("allowed_lanes")
    if lanes is not None:
        if not isinstance(lanes, list) or not lanes or len(lanes) != len(set(lanes)) or any(
            lane not in RESOURCE_LANES for lane in lanes
        ):
            raise ValidationError("inputs.allowed_lanes must be a nonempty unique list of supported lanes")
    for key in ("review_required", "auto_review_authorized", "bind_dependency_results"):
        if key in inputs and type(inputs[key]) is not bool:
            raise ValidationError(f"inputs.{key} must be boolean")
    if inputs.get("bind_dependency_results") is True:
        if task_type == "deterministic":
            raise ValidationError("dependency-result binding requires a semantic task")
        dependencies = data.get("dependencies")
        if not isinstance(dependencies, list) or not dependencies:
            raise ValidationError("dependency-result binding requires at least one dependency")
    if "review_role" in inputs and inputs["review_role"] not in ROLES:
        raise ValidationError("inputs.review_role is invalid")
    timeout = data.get("timeout_seconds", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        raise ValidationError("timeout_seconds must be an integer from 1 to 3600")
    return Task(
        schema_version=1, task_id=task_id, role=role, canonical_head=head,
        task_type=task_type, action=action, stop_condition=_string(data["stop_condition"], "stop_condition"),
        dependencies=_string_list(data.get("dependencies", []), "dependencies"), inputs=inputs,
        allowed_paths=_string_list(data.get("allowed_paths", []), "allowed_paths"),
        expected_artifacts=_string_list(data.get("expected_artifacts", []), "expected_artifacts"),
        timeout_seconds=timeout, source_issue=source_issue, labels=tuple(sorted(set(labels))),
    )


def parse_issue_body(body: str, *, source_issue: int, labels: tuple[str, ...]) -> Task:
    if not isinstance(body, str) or len(body) > 200_000:
        raise ValidationError("issue body missing or too large")
    matches = FENCE.findall(body)
    if len(matches) != 1:
        raise ValidationError("issue must contain exactly one fenced YAML task envelope")
    try:
        data = yaml.safe_load(matches[0])
    except yaml.YAMLError as exc:
        raise ValidationError(f"malformed task YAML: {exc}") from exc
    return validate_task(data, source_issue=source_issue, labels=labels)
