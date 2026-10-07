"""Deterministic Project-Control task authoring preflight.

This module validates proposed control-plane operations before an Issue is
created or changed.  It deliberately reuses the executable TASK validator,
policy validator, role registry, and resource suitability table: the
authoring contract is therefore test-bound to the worker-facing contract
rather than being a second hand-maintained schema.

The module is pure policy.  It performs no GitHub, SQLite, filesystem, network,
or scheduler mutation.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .model import Task, ValidationError
from .policy import normalize_relative, validate_task_policy
from .routing import SUITABILITY, canonical_role, resolve_resource_request
from .schema import (
    ACTIONS, RESOURCE_LANES, RESOURCE_REQUIREMENTS, ROLES, TASK_KEYS,
    TASK_TYPES, validate_task,
)


OPERATION_TYPES = (
    "NEW_ISSUE", "UPDATE_EXISTING", "RERUN", "SUPERSEDE", "CLOSE", "REOPEN",
)
MATERIALIZATION_STATES = (
    "MATERIALIZED", "PENDING_MATERIALIZATION",
    "EXPLICITLY_DEFERRED_WITH_REASON", "NOT_STATE_CHANGING",
)
LIFECYCLE_DISPOSITIONS = (
    "CURRENT", "SUPERSEDED", "RETIRED", "CLOSED_HISTORICAL",
)
PROJECT_PROGRESS_STATES = (
    "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "BLOCKED", "DEFERRED",
)
EXECUTION_CONTEXTS = (
    "SEPARATE_BOUNDED_WORK", "LOCAL_DETERMINISTIC", "PERSISTENT_NON_WORK",
)
STATE_FRESHNESS = ("FRESH", "CONTEXT_DELTA_BOUND", "STATE_SYNC_REQUIRED")
STATUS_FACETS = (
    "semantic_state", "design_state", "implementation_state",
    "deployment_state", "canonicalization_state",
)
HISTORICAL_LIFECYCLE_DISPOSITIONS = frozenset({
    "SUPERSEDED", "RETIRED", "CLOSED_HISTORICAL",
})
ACTIONABLE_FSM_STATES = frozenset({
    "WAITING_USER", "WAITING_APPROVAL", "BLOCKED", "FAILED", "REJECTED",
})

# Project-Control-approved R1 reconciliation targets.  These exact identities
# are reconciliation input, not attention-filtering shortcuts: every consumer
# still requires a validated receipt bound to the matching TASK envelope.
R1_HISTORICAL_DISPOSITIONS: dict[str, dict[str, Any]] = {
    "INFRA-SHADOW-001": {
        "source_issue": 1,
        "envelope_hash": "e30e68e772a43fb1a2f5f39bce7d787866f81905962be41694591361476647d6",
        "disposition": "CLOSED_HISTORICAL",
        "project_progress": "COMPLETED",
        "reason": (
            "Project Control renewal plan classifies the completed SHADOW HEAD "
            "verification as historical; its original WAITING_APPROVAL FSM and "
            "event history remain unchanged."
        ),
        "semantic_state": "SHADOW_VERIFICATION_COMPLETE",
        "design_state": "NOT_APPLICABLE",
        "implementation_state": "COMPLETED",
        "deployment_state": "NOT_APPLICABLE",
        "canonicalization_state": "NOT_STATE_CHANGING",
    },
    "INFRA-CONVERGENCE-DASHBOARD-V2-PRODUCTION-DEPLOYMENT-001": {
        "source_issue": 27,
        "envelope_hash": "d099ee9c8aeb551f22371e4c474675102661bd36a64ebbe06b1e9178de707c02",
        "disposition": "RETIRED",
        "project_progress": "DEFERRED",
        "reason": (
            "Project Control Issue #27 comment 5943372471 formally deferred "
            "Dashboard v2 production deployment from Infrastructure Baseline v1; "
            "the retired task's original WAITING_USER FSM and event history remain "
            "unchanged."
        ),
        "semantic_state": "DEPLOYMENT_DEFERRED",
        "design_state": "REVIEWED",
        "implementation_state": "DEFERRED",
        "deployment_state": "DEFERRED",
        "canonicalization_state": "EXPLICITLY_DEFERRED",
    },
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

REQUEST_KEYS = {
    "schema_version", "operation_type", "author_role", "canonical_head",
    "issue", "task", "existing_binding", "required_repository_paths",
    "dependency_bindings", "review_binding", "accepted_state_changes",
    "context_delta_bundle", "lifecycle", "project_status",
    "execution_context", "persistent_chat_role",
    "chatgpt_scheduler_requested",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mapping(value: Any, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a mapping")
    unknown = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    if unknown:
        raise ValidationError(f"unknown {label} fields: {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"missing {label} fields: {', '.join(missing)}")
    return value


def _text(value: Any, label: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    result = value.strip()
    if len(result) > limit or "\x00" in result:
        raise ValidationError(f"{label} is invalid or oversized")
    return result


def _optional_text(value: Any, label: str, limit: int = 1000) -> str | None:
    if value is None:
        return None
    return _text(value, label, limit)


def _hex(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    result = _text(value, label, 64).lower()
    if not pattern.fullmatch(result):
        raise ValidationError(f"{label} has invalid identity format")
    return result


def interface_manifest() -> dict[str, Any]:
    """Return the executable-interface inventory used by the preflight."""
    value: dict[str, Any] = {
        "schema_version": 1,
        "task_schema_fields": sorted(TASK_KEYS),
        "task_types": sorted(TASK_TYPES),
        "actions": sorted(ACTIONS),
        "roles": sorted(ROLES),
        "canonical_roles": sorted({value for value in (
            canonical_role(role) for role in ROLES
        ) if value is not None}),
        "resource_requirements": sorted(RESOURCE_REQUIREMENTS),
        "resource_lanes": sorted(RESOURCE_LANES),
        "resource_suitability": {
            key: list(value) for key, value in sorted(SUITABILITY.items())
        },
        "operation_types": list(OPERATION_TYPES),
        "materialization_states": list(MATERIALIZATION_STATES),
        "lifecycle_dispositions": list(LIFECYCLE_DISPOSITIONS),
        "project_progress_states": list(PROJECT_PROGRESS_STATES),
        "state_freshness": list(STATE_FRESHNESS),
        "persistent_project_control_mode": "NON_WORK",
        "chatgpt_scheduler_authorized": False,
    }
    value["manifest_sha256"] = _digest(value)
    return value


def _validate_issue(value: Any, operation: str, task_label: str) -> tuple[int | None, tuple[str, ...]]:
    issue = _mapping(value, "issue", {"number", "state", "labels"})
    number = issue["number"]
    if number is not None and (isinstance(number, bool) or not isinstance(number, int) or number < 1):
        raise ValidationError("issue.number must be null or a positive integer")
    if issue["state"] not in {"open", "closed"}:
        raise ValidationError("issue.state must be open or closed")
    labels = issue["labels"]
    if not isinstance(labels, list) or any(not isinstance(item, str) or not item for item in labels):
        raise ValidationError("issue.labels must be a list of non-empty strings")
    if len(labels) != len(set(labels)):
        raise ValidationError("issue.labels contains duplicates")
    if task_label not in labels:
        raise ValidationError("issue is missing the configured orchestrator task label")
    creates_issue = operation in {"NEW_ISSUE", "RERUN", "SUPERSEDE"}
    if creates_issue and number is not None:
        raise ValidationError(f"{operation} must not reuse an existing Issue identity")
    if not creates_issue and number is None:
        raise ValidationError(f"{operation} requires an existing Issue identity")
    if operation == "CLOSE" and issue["state"] != "closed":
        raise ValidationError("CLOSE requires issue.state=closed")
    if operation == "REOPEN" and issue["state"] != "open":
        raise ValidationError("REOPEN requires issue.state=open")
    return number, tuple(sorted(labels))


def _validate_existing_binding(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    binding = _mapping(value, "existing_binding", {"source_issue", "task_id", "envelope_hash"})
    if isinstance(binding["source_issue"], bool) or not isinstance(binding["source_issue"], int) or binding["source_issue"] < 1:
        raise ValidationError("existing_binding.source_issue must be a positive integer")
    return {
        "source_issue": binding["source_issue"],
        "task_id": _text(binding["task_id"], "existing_binding.task_id", 128),
        "envelope_hash": _hex(binding["envelope_hash"], "existing_binding.envelope_hash", SHA256),
    }


def _validate_identity_operation(
    operation: str, task: Task, issue_number: int | None, existing: dict[str, Any] | None,
) -> None:
    if operation == "NEW_ISSUE":
        if existing is not None:
            raise ValidationError("NEW_ISSUE cannot carry an existing Issue/TASK binding")
        return
    if existing is None:
        raise ValidationError(f"{operation} requires an immutable existing Issue/TASK binding")
    if operation in {"UPDATE_EXISTING", "CLOSE", "REOPEN"}:
        if issue_number != existing["source_issue"]:
            raise ValidationError("Issue identity differs from the immutable existing binding")
        if task.task_id != existing["task_id"] or task.envelope_hash != existing["envelope_hash"]:
            raise ValidationError("existing Issue cannot be rebound to a different TASK envelope")
        return
    if task.task_id == existing["task_id"]:
        raise ValidationError(f"{operation} must use a new TASK identity")
    field = "rerun_of" if operation == "RERUN" else "supersedes_task_id"
    if task.inputs.get(field) != existing["task_id"]:
        raise ValidationError(f"{operation} requires inputs.{field} to bind the original TASK")


def _validate_required_paths(task: Task, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 200:
        raise ValidationError("required_repository_paths must be a bounded list")
    required = tuple(normalize_relative(item) for item in value)
    if len(required) != len(set(required)):
        raise ValidationError("required_repository_paths contains duplicates")
    allowed = tuple(normalize_relative(item) for item in task.allowed_paths)
    for path in required:
        if not any(path == root or path.startswith(root.rstrip("/") + "/") for root in allowed):
            raise ValidationError(f"required path is outside the TASK allowed_paths: {path}")
    return required


def _validate_dependencies(task: Task, value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ValidationError("dependency_bindings must be a list")
    bindings: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        row = _mapping(item, f"dependency_bindings[{index}]", {
            "task_id", "result_sha256", "canonical_head", "status",
        })
        if row["status"] != "SUCCEEDED":
            raise ValidationError("dependency binding must reference a SUCCEEDED result")
        bindings.append({
            "task_id": _text(row["task_id"], "dependency task_id", 128),
            "result_sha256": _hex(row["result_sha256"], "dependency result_sha256", SHA256),
            "canonical_head": _hex(row["canonical_head"], "dependency canonical_head", SHA40),
            "status": "SUCCEEDED",
        })
    ids = [row["task_id"] for row in bindings]
    if len(ids) != len(set(ids)):
        raise ValidationError("dependency_bindings contains duplicate TASK identities")
    if task.inputs.get("bind_dependency_results") is True:
        if tuple(sorted(ids)) != tuple(sorted(task.dependencies)):
            raise ValidationError("dependency-result bindings do not exactly cover TASK dependencies")
    elif bindings:
        raise ValidationError("dependency bindings require inputs.bind_dependency_results=true")
    return tuple(sorted(bindings, key=lambda row: row["task_id"]))


def _validate_review(task: Task, value: Any) -> dict[str, Any] | None:
    if value is None:
        if task.inputs.get("independent_review") is True:
            raise ValidationError("independent review TASK requires exact review binding")
        return None
    row = _mapping(value, "review_binding", {
        "parent_task_id", "review_task_id", "review_role",
        "accepted_result_sha256", "review_material_sha256",
    })
    result = {
        "parent_task_id": _text(row["parent_task_id"], "review parent_task_id", 128),
        "review_task_id": _text(row["review_task_id"], "review task_id", 128),
        "review_role": _text(row["review_role"], "review role", 64),
        "accepted_result_sha256": _hex(row["accepted_result_sha256"], "accepted result SHA", SHA256),
        "review_material_sha256": _hex(row["review_material_sha256"], "review material SHA", SHA256),
    }
    if task.inputs.get("independent_review") is not True:
        raise ValidationError("review_binding is only valid for an independent-review TASK")
    if result["review_task_id"] != task.task_id:
        raise ValidationError("review binding does not name this exact review TASK")
    if task.inputs.get("review_of") != result["parent_task_id"]:
        raise ValidationError("review binding parent differs from inputs.review_of")
    if canonical_role(task.role) != canonical_role(result["review_role"]):
        raise ValidationError("review TASK role differs from the registered review role")
    if task.inputs.get("accepted_result_sha256") != result["accepted_result_sha256"]:
        raise ValidationError("review accepted-result SHA is not exactly bound")
    if task.inputs.get("review_material_sha256") != result["review_material_sha256"]:
        raise ValidationError("review material SHA is not exactly bound")
    return result


def _validate_materialization(value: Any) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    if not isinstance(value, list) or not value or len(value) > 100:
        raise ValidationError("accepted_state_changes must be a non-empty bounded list")
    records: list[dict[str, Any]] = []
    pending: list[str] = []
    for index, item in enumerate(value):
        row = _mapping(item, f"accepted_state_changes[{index}]", {
            "identity", "result_sha256", "materialization_state",
            "materialization_commit", "reason",
        })
        identity = _text(row["identity"], "accepted state-change identity", 200)
        state = row["materialization_state"]
        if state not in MATERIALIZATION_STATES:
            raise ValidationError(f"unsupported materialization state: {state}")
        commit = row["materialization_commit"]
        reason = row["reason"]
        if state == "MATERIALIZED":
            commit = _hex(commit, "materialization_commit", SHA40)
            if reason is not None:
                raise ValidationError("MATERIALIZED record must not carry a deferral reason")
        elif state == "EXPLICITLY_DEFERRED_WITH_REASON":
            if commit is not None:
                raise ValidationError("deferred materialization must not claim a commit")
            reason = _text(reason, "materialization deferral reason", 2000)
        else:
            if commit is not None or reason is not None:
                raise ValidationError(f"{state} must not claim a commit or deferral reason")
            if state == "PENDING_MATERIALIZATION":
                pending.append(identity)
        records.append({
            "identity": identity,
            "result_sha256": _hex(row["result_sha256"], "accepted result SHA", SHA256),
            "materialization_state": state,
            "materialization_commit": commit,
            "reason": reason,
        })
    identities = [row["identity"] for row in records]
    if len(identities) != len(set(identities)):
        raise ValidationError("accepted_state_changes contains duplicate identities")
    return tuple(sorted(records, key=lambda row: row["identity"])), tuple(sorted(pending))


def _validate_context_delta(value: Any, pending: tuple[str, ...]) -> dict[str, str] | None:
    if value is None:
        return None
    row = _mapping(value, "context_delta_bundle", {
        "bundle_id", "sha256", "pending_materialization_ids", "review_id",
        "review_result_sha256", "mandatory_later_materialization",
    })
    if row["mandatory_later_materialization"] is not True:
        raise ValidationError("context delta must preserve mandatory later materialization")
    ids = row["pending_materialization_ids"]
    if not isinstance(ids, list) or tuple(sorted(ids)) != pending or len(ids) != len(set(ids)):
        raise ValidationError("context delta does not exactly bind pending materialization identities")
    return {
        "bundle_id": _text(row["bundle_id"], "context delta bundle_id", 200),
        "sha256": _hex(row["sha256"], "context delta SHA", SHA256),
        "review_id": _text(row["review_id"], "context delta review_id", 200),
        "review_result_sha256": _hex(
            row["review_result_sha256"], "context delta review result SHA", SHA256,
        ),
    }


def _validate_lifecycle(
    value: Any, operation: str, task: Task, existing: dict[str, Any] | None,
) -> dict[str, Any]:
    row = _mapping(value, "lifecycle", {
        "disposition", "target_task_id", "target_envelope_hash",
        "successor_task_id", "reason",
    })
    disposition = row["disposition"]
    if disposition not in LIFECYCLE_DISPOSITIONS:
        raise ValidationError("unsupported lifecycle disposition")
    target_task_id = _text(row["target_task_id"], "lifecycle.target_task_id", 128)
    target_hash = _hex(row["target_envelope_hash"], "lifecycle.target_envelope_hash", SHA256)
    successor = _optional_text(row["successor_task_id"], "lifecycle.successor_task_id", 128)
    reason = _optional_text(row["reason"], "lifecycle.reason", 2000)
    expected_target = existing["task_id"] if operation in {"SUPERSEDE", "CLOSE"} and existing else task.task_id
    expected_hash = existing["envelope_hash"] if operation in {"SUPERSEDE", "CLOSE"} and existing else task.envelope_hash
    if target_task_id != expected_target or target_hash != expected_hash:
        raise ValidationError("lifecycle target is not the exact bound TASK envelope")
    if operation == "SUPERSEDE":
        if disposition != "SUPERSEDED" or successor != task.task_id:
            raise ValidationError("SUPERSEDE requires exact SUPERSEDED target and successor TASK")
    elif operation == "CLOSE":
        if disposition not in {"RETIRED", "CLOSED_HISTORICAL"} or successor is not None:
            raise ValidationError("CLOSE requires a historical terminal disposition without successor")
    elif disposition != "CURRENT" or successor is not None:
        raise ValidationError(f"{operation} cannot assign historical lifecycle disposition")
    if disposition == "CURRENT" and reason is not None:
        raise ValidationError("CURRENT lifecycle disposition does not accept historical reason")
    if disposition != "CURRENT" and reason is None:
        raise ValidationError("historical lifecycle disposition requires an explicit reason")
    return {
        "disposition": disposition, "target_task_id": target_task_id,
        "target_envelope_hash": target_hash, "successor_task_id": successor,
        "reason": reason,
    }


def _validate_project_status(value: Any) -> dict[str, Any]:
    keys = {"project_progress", "human_action_required", *STATUS_FACETS}
    row = _mapping(value, "project_status", keys)
    if row["project_progress"] not in PROJECT_PROGRESS_STATES:
        raise ValidationError("unsupported PROJECT_PROGRESS state")
    if type(row["human_action_required"]) is not bool:
        raise ValidationError("HUMAN_ACTION_REQUIRED must be boolean")
    result = {
        "project_progress": row["project_progress"],
        "human_action_required": row["human_action_required"],
    }
    for key in STATUS_FACETS:
        result[key] = _text(row[key], f"project_status.{key}", 128)
    return result


def preflight_authoring(
    request: Any, cfg: dict[str, Any], *, observed_canonical_head: str,
) -> dict[str, Any]:
    """Validate one proposed Project-Control operation and return a receipt.

    A receipt with ``STATE_SYNC_REQUIRED`` is deliberately not an authorizing
    receipt.  It records materialization debt while preventing dependent
    authoring from presenting stale canonical state as current.
    """
    data = _mapping(request, "authoring request", REQUEST_KEYS)
    if data["schema_version"] != 1:
        raise ValidationError("authoring schema_version must be integer 1")
    operation = data["operation_type"]
    if operation not in OPERATION_TYPES:
        raise ValidationError("unsupported operation_type")
    if data["author_role"] != "00_PROJECT_CONTROL":
        raise ValidationError("only Project Control may issue an authoring receipt")
    canonical_head = _hex(data["canonical_head"], "canonical_head", SHA40)
    observed = _hex(observed_canonical_head, "observed canonical head", SHA40)
    if canonical_head != observed:
        raise ValidationError("canonical HEAD drift")
    if data["persistent_chat_role"] != "00_PROJECT_CONTROL":
        raise ValidationError("persistent authoring authority must remain Project Control")
    if data["execution_context"] not in EXECUTION_CONTEXTS:
        raise ValidationError("unsupported execution_context")
    if data["execution_context"] == "PERSISTENT_NON_WORK":
        raise ValidationError("persistent 00 is NON-WORK and cannot execute repository authoring")
    if data["chatgpt_scheduler_requested"] is not False:
        raise ValidationError("ChatGPT scheduler automation from persistent 00 is forbidden")

    issue_number, labels = _validate_issue(
        data["issue"], operation, cfg["github"]["task_label"],
    )
    task = validate_task(data["task"], source_issue=issue_number, labels=labels)
    validate_task_policy(task, cfg)
    # CLOSE overlays an immutable historical TASK, whose original canonical
    # head is intentionally retained.  The operation itself is still bound to
    # the freshly observed current canonical head, exact Issue/TASK identity,
    # and exact envelope hash below.  Every operation that authors a new or
    # executable TASK continues to require the current canonical head.
    if operation != "CLOSE" and task.canonical_head != canonical_head:
        raise ValidationError("TASK canonical_head differs from preflight canonical HEAD")
    if task.is_llm and cfg["llm"]["require_issue_label"] not in labels:
        raise ValidationError("LLM-class TASK lacks the configured explicit approval label")
    project_status = _validate_project_status(data["project_status"])
    requirement, declared_lanes, compatible_lanes = resolve_resource_request(task)
    if not compatible_lanes or tuple(declared_lanes) != tuple(compatible_lanes):
        raise ValidationError("TASK resource/lane declaration is incompatible with executable routing")
    if canonical_role(task.role) is None:
        raise ValidationError("TASK role has no executable canonical specialist role")
    if task.inputs.get("review_required") is True:
        review_role = task.inputs.get("review_role")
        if review_role is None or canonical_role(str(review_role)) is None:
            raise ValidationError("review_required TASK must bind a canonical review role")
        if task.inputs.get("auto_review_authorized") is not True and not project_status["human_action_required"]:
            raise ValidationError("non-automatic review must remain visible as human action required")

    existing = _validate_existing_binding(data["existing_binding"])
    _validate_identity_operation(operation, task, issue_number, existing)
    required_paths = _validate_required_paths(task, data["required_repository_paths"])
    dependencies = _validate_dependencies(task, data["dependency_bindings"])
    review = _validate_review(task, data["review_binding"])
    changes, pending = _validate_materialization(data["accepted_state_changes"])
    delta = _validate_context_delta(data["context_delta_bundle"], pending)
    lifecycle = _validate_lifecycle(data["lifecycle"], operation, task, existing)

    if pending and delta is None:
        freshness = "STATE_SYNC_REQUIRED"
        status = "STATE_SYNC_REQUIRED"
    elif pending:
        freshness = "CONTEXT_DELTA_BOUND"
        status = "PREFLIGHT_PASS"
    else:
        if delta is not None:
            raise ValidationError("context delta supplied without pending materialization debt")
        freshness = "FRESH"
        status = "PREFLIGHT_PASS"

    manifest = interface_manifest()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "operation_type": operation,
        "author_role": "00_PROJECT_CONTROL",
        "canonical_head": canonical_head,
        "issue_number": issue_number,
        "task_id": task.task_id,
        "envelope_hash": task.envelope_hash,
        "interface_manifest_sha256": manifest["manifest_sha256"],
        "resource_requirement": requirement,
        "allowed_lanes": list(declared_lanes),
        "required_repository_paths": list(required_paths),
        "dependency_bindings": list(dependencies),
        "review_binding": review,
        "accepted_state_changes": list(changes),
        "state_freshness": freshness,
        "pending_materialization_ids": list(pending),
        "context_delta_bundle_id": delta["bundle_id"] if delta else None,
        "context_delta_bundle_sha256": delta["sha256"] if delta else None,
        "context_delta_review_id": delta["review_id"] if delta else None,
        "context_delta_review_result_sha256": (
            delta["review_result_sha256"] if delta else None
        ),
        "lifecycle_disposition": lifecycle["disposition"],
        "lifecycle_target_task_id": lifecycle["target_task_id"],
        "lifecycle_target_envelope_hash": lifecycle["target_envelope_hash"],
        "successor_task_id": lifecycle["successor_task_id"],
        "lifecycle_reason": lifecycle["reason"],
        **project_status,
        "execution_context": data["execution_context"],
        "persistent_project_control_mode": "NON_WORK",
        "chatgpt_scheduler_authorized": False,
    }
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt


def historical_disposition_receipt(
    task: Task, cfg: dict[str, Any], *, observed_canonical_head: str,
    authority_id: str, authority_result_sha256: str,
    specification: dict[str, Any],
) -> dict[str, Any]:
    """Build one exact, non-mutating historical lifecycle receipt.

    This helper is pure policy.  It neither writes SQLite nor treats Issue
    closure as authority.  A trusted local Project-Control operation must pass
    an already-reviewed authority identity/hash and later apply the returned
    receipt through ``Store.put_authoring_receipt``.  The original TASK/FSM and
    event rows are never rewritten.
    """
    required = {
        "source_issue", "envelope_hash", "disposition", "project_progress", "reason",
        "semantic_state", "design_state", "implementation_state",
        "deployment_state", "canonicalization_state",
    }
    if not isinstance(specification, dict) or set(specification) != required:
        raise ValidationError("historical disposition specification is incomplete")
    if task.source_issue != specification["source_issue"]:
        raise ValidationError("historical disposition source Issue mismatch")
    if task.envelope_hash != specification["envelope_hash"]:
        raise ValidationError("historical disposition TASK envelope mismatch")
    if specification["disposition"] not in {"RETIRED", "CLOSED_HISTORICAL"}:
        raise ValidationError("historical disposition must be RETIRED or CLOSED_HISTORICAL")
    authority = _text(authority_id, "historical authority identity", 200)
    authority_sha = _hex(
        authority_result_sha256, "historical authority result SHA", SHA256,
    )
    current_head = _hex(observed_canonical_head, "observed canonical head", SHA40)
    request = {
        "schema_version": 1,
        "operation_type": "CLOSE",
        "author_role": "00_PROJECT_CONTROL",
        "canonical_head": current_head,
        "issue": {
            "number": task.source_issue,
            "state": "closed",
            "labels": sorted(set(task.labels)),
        },
        "task": task.envelope_dict(),
        "existing_binding": {
            "source_issue": task.source_issue,
            "task_id": task.task_id,
            "envelope_hash": task.envelope_hash,
        },
        "required_repository_paths": [],
        "dependency_bindings": [],
        "review_binding": None,
        "accepted_state_changes": [{
            "identity": authority,
            "result_sha256": authority_sha,
            "materialization_state": "NOT_STATE_CHANGING",
            "materialization_commit": None,
            "reason": None,
        }],
        "context_delta_bundle": None,
        "lifecycle": {
            "disposition": specification["disposition"],
            "target_task_id": task.task_id,
            "target_envelope_hash": task.envelope_hash,
            "successor_task_id": None,
            "reason": _text(specification["reason"], "historical reason", 2000),
        },
        "project_status": {
            "project_progress": specification["project_progress"],
            "human_action_required": False,
            "semantic_state": specification["semantic_state"],
            "design_state": specification["design_state"],
            "implementation_state": specification["implementation_state"],
            "deployment_state": specification["deployment_state"],
            "canonicalization_state": specification["canonicalization_state"],
        },
        "execution_context": "SEPARATE_BOUNDED_WORK",
        "persistent_chat_role": "00_PROJECT_CONTROL",
        "chatgpt_scheduler_requested": False,
    }
    return preflight_authoring(
        request, cfg, observed_canonical_head=current_head,
    )


def repository_renewal_r1_receipts(
    tasks: dict[str, Task], cfg: dict[str, Any], *,
    observed_canonical_head: str,
    authority_id: str, authority_result_sha256: str,
) -> tuple[dict[str, Any], ...]:
    """Materialize the reviewed R1 receipts from exact durable TASK records."""
    if set(tasks) != set(R1_HISTORICAL_DISPOSITIONS):
        raise ValidationError("R1 reconciliation requires exactly the reviewed TASK identities")
    return tuple(
        historical_disposition_receipt(
            tasks[task_id], cfg,
            observed_canonical_head=observed_canonical_head,
            authority_id=authority_id,
            authority_result_sha256=authority_result_sha256,
            specification=R1_HISTORICAL_DISPOSITIONS[task_id],
        )
        for task_id in sorted(R1_HISTORICAL_DISPOSITIONS)
    )


def reconcile_repository_renewal_r1(
    store: Any, cfg: dict[str, Any], *, observed_canonical_head: str,
    authority_id: str, authority_result_sha256: str, dry_run: bool = False,
) -> dict[str, Any]:
    """Apply the exact reviewed R1 lifecycle receipts through the Store API.

    The surface deliberately reads only the two reviewed durable TASK records,
    validates their complete immutable identities before generating either
    receipt, and writes only through ``Store.put_authoring_receipt``.  It never
    changes execution history, TASK payloads, attempts, or accepted results.
    """
    authority = _text(authority_id, "R1 authority identity", 200)
    authority_sha = _hex(
        authority_result_sha256, "R1 authority result SHA", SHA256,
    )
    current_head = _hex(
        observed_canonical_head, "observed canonical head", SHA40,
    )
    tasks: dict[str, Task] = {}
    for task_id in sorted(R1_HISTORICAL_DISPOSITIONS):
        specification = R1_HISTORICAL_DISPOSITIONS[task_id]
        row = store.get(task_id)
        if row is None:
            raise ValidationError(f"R1 reconciliation target is missing: {task_id}")
        task = store.task(row)
        if (
            row["task_id"] != task_id
            or task.task_id != task_id
            or row["source_issue"] != specification["source_issue"]
            or task.source_issue != specification["source_issue"]
            or row["envelope_hash"] != specification["envelope_hash"]
            or task.envelope_hash != specification["envelope_hash"]
        ):
            raise ValidationError(
                f"R1 reconciliation target identity mismatch: {task_id}"
            )
        tasks[task_id] = task

    receipts = repository_renewal_r1_receipts(
        tasks, cfg, observed_canonical_head=current_head,
        authority_id=authority, authority_result_sha256=authority_sha,
    )
    results = []
    for receipt in receipts:
        outcome = "verified" if dry_run else store.put_authoring_receipt(receipt)
        if outcome not in {"verified", "created", "duplicate"}:
            raise ValidationError("R1 Store returned an invalid reconciliation result")
        results.append({
            "task_id": receipt["lifecycle_target_task_id"],
            "receipt_sha256": receipt["receipt_sha256"],
            "status": outcome,
        })
    statuses = {item["status"] for item in results}
    overall = (
        "verified" if dry_run else
        "duplicate" if statuses == {"duplicate"} else
        "created"
    )
    return {
        "status": overall,
        "dry_run": bool(dry_run),
        "canonical_head": current_head,
        "authority_id": authority,
        "results": results,
    }


RECEIPT_KEYS = {
    "schema_version", "status", "operation_type", "author_role",
    "canonical_head", "issue_number", "task_id", "envelope_hash",
    "interface_manifest_sha256", "resource_requirement", "allowed_lanes",
    "required_repository_paths", "dependency_bindings", "review_binding",
    "accepted_state_changes", "state_freshness",
    "pending_materialization_ids", "context_delta_bundle_id",
    "context_delta_bundle_sha256", "context_delta_review_id",
    "context_delta_review_result_sha256", "lifecycle_disposition",
    "lifecycle_target_task_id", "lifecycle_target_envelope_hash",
    "successor_task_id", "lifecycle_reason", "project_progress",
    "human_action_required", *STATUS_FACETS, "execution_context",
    "persistent_project_control_mode", "chatgpt_scheduler_authorized",
    "receipt_sha256",
}


def validate_preflight_receipt(
    receipt: Any, *, authorizing: bool = True, require_current_manifest: bool = True,
) -> dict[str, Any]:
    """Validate a receipt before it is consumed as durable control metadata."""
    data = _mapping(receipt, "authoring receipt", RECEIPT_KEYS)
    claimed = _hex(data["receipt_sha256"], "receipt_sha256", SHA256)
    unhashed = dict(data)
    unhashed.pop("receipt_sha256")
    if _digest(unhashed) != claimed:
        raise ValidationError("authoring receipt identity mismatch")
    if data["schema_version"] != 1 or data["author_role"] != "00_PROJECT_CONTROL":
        raise ValidationError("receipt lacks Project Control v1 authority")
    if data["operation_type"] not in OPERATION_TYPES:
        raise ValidationError("invalid receipt operation_type")
    _hex(data["canonical_head"], "receipt canonical_head", SHA40)
    _text(data["task_id"], "receipt task_id", 128)
    _hex(data["envelope_hash"], "receipt envelope_hash", SHA256)
    _hex(data["interface_manifest_sha256"], "receipt interface manifest SHA", SHA256)
    _text(data["lifecycle_target_task_id"], "receipt lifecycle target", 128)
    _hex(data["lifecycle_target_envelope_hash"], "receipt lifecycle envelope SHA", SHA256)
    successor = _optional_text(
        data["successor_task_id"], "receipt lifecycle successor", 128,
    )
    lifecycle_reason = _optional_text(
        data["lifecycle_reason"], "receipt lifecycle reason", 2000,
    )
    if authorizing and data["status"] != "PREFLIGHT_PASS":
        raise ValidationError("STATE_SYNC_REQUIRED receipt is not authorizing")
    if data["status"] not in {"PREFLIGHT_PASS", "STATE_SYNC_REQUIRED"}:
        raise ValidationError("invalid authoring receipt status")
    if data["state_freshness"] not in STATE_FRESHNESS:
        raise ValidationError("invalid CANONICAL_STATE_FRESHNESS")
    if data["status"] == "STATE_SYNC_REQUIRED" and data["state_freshness"] != "STATE_SYNC_REQUIRED":
        raise ValidationError("non-authorizing receipt has inconsistent freshness")
    if data["status"] == "PREFLIGHT_PASS" and data["state_freshness"] == "STATE_SYNC_REQUIRED":
        raise ValidationError("authorizing receipt cannot carry STATE_SYNC_REQUIRED")
    if data["lifecycle_disposition"] not in LIFECYCLE_DISPOSITIONS:
        raise ValidationError("invalid lifecycle disposition")
    historical = data["lifecycle_disposition"] != "CURRENT"
    if data["operation_type"] == "SUPERSEDE":
        if (
            data["lifecycle_disposition"] != "SUPERSEDED"
            or successor != data["task_id"]
            or not lifecycle_reason
        ):
            raise ValidationError("invalid SUPERSEDE lifecycle authority")
    elif data["operation_type"] == "CLOSE":
        if (
            data["lifecycle_disposition"] not in {"RETIRED", "CLOSED_HISTORICAL"}
            or data["task_id"] != data["lifecycle_target_task_id"]
            or successor is not None
            or not lifecycle_reason
        ):
            raise ValidationError("invalid CLOSE lifecycle authority")
    elif (
        historical or data["task_id"] != data["lifecycle_target_task_id"]
        or successor is not None or lifecycle_reason is not None
    ):
        raise ValidationError("operation cannot authorize historical lifecycle disposition")
    if data["project_progress"] not in PROJECT_PROGRESS_STATES:
        raise ValidationError("invalid PROJECT_PROGRESS")
    if type(data["human_action_required"]) is not bool:
        raise ValidationError("invalid HUMAN_ACTION_REQUIRED")
    for key in STATUS_FACETS:
        _text(data[key], f"receipt {key}", 128)
    if data["resource_requirement"] not in RESOURCE_REQUIREMENTS:
        raise ValidationError("invalid receipt resource requirement")
    lanes = data["allowed_lanes"]
    if not isinstance(lanes, list) or not lanes or any(lane not in RESOURCE_LANES for lane in lanes):
        raise ValidationError("invalid receipt allowed_lanes")
    changes, pending = _validate_materialization(data["accepted_state_changes"])
    if list(changes) != data["accepted_state_changes"]:
        raise ValidationError("receipt materialization records are not canonical")
    if list(pending) != data["pending_materialization_ids"]:
        raise ValidationError("receipt pending materialization identities are inconsistent")
    if data["state_freshness"] == "CONTEXT_DELTA_BOUND":
        _text(data["context_delta_bundle_id"], "receipt context delta ID", 200)
        _hex(data["context_delta_bundle_sha256"], "receipt context delta SHA", SHA256)
        _text(data["context_delta_review_id"], "receipt context delta review ID", 200)
        _hex(
            data["context_delta_review_result_sha256"],
            "receipt context delta review result SHA", SHA256,
        )
    elif any(data[key] is not None for key in (
        "context_delta_bundle_id", "context_delta_bundle_sha256",
        "context_delta_review_id", "context_delta_review_result_sha256",
    )):
        raise ValidationError("receipt context delta is inconsistent with freshness")
    if data["persistent_project_control_mode"] != "NON_WORK":
        raise ValidationError("persistent Project Control must remain NON-WORK")
    if data["chatgpt_scheduler_authorized"] is not False:
        raise ValidationError("receipt cannot authorize ChatGPT scheduler automation")
    if (
        require_current_manifest
        and data["interface_manifest_sha256"] != interface_manifest()["manifest_sha256"]
    ):
        raise ValidationError("receipt executable-interface manifest is stale")
    return dict(data)


def lifecycle_receipt_for_task(
    receipt: Any, *, task_id: str, envelope_hash: str,
) -> dict[str, Any] | None:
    """Return a validated receipt only when it targets this exact TASK envelope.

    The receipt digest provides integrity, not authentication.  Callers must
    obtain receipts from the trusted local Project-Control application path;
    untrusted task payloads, Issue closure, and free text are not authority.
    """
    try:
        value = validate_preflight_receipt(
            receipt, authorizing=True, require_current_manifest=False,
        )
    except (ValidationError, TypeError, ValueError):
        return None
    if (
        value["lifecycle_target_task_id"] != task_id
        or value["lifecycle_target_envelope_hash"] != envelope_hash
    ):
        return None
    return value


def is_historical_lifecycle_receipt(
    receipt: Any, *, task_id: str, envelope_hash: str,
) -> bool:
    """Apply the shared exact structured non-actionable overlay predicate."""
    value = lifecycle_receipt_for_task(
        receipt, task_id=task_id, envelope_hash=envelope_hash,
    )
    return bool(
        value and value["lifecycle_disposition"] in HISTORICAL_LIFECYCLE_DISPOSITIONS
    )


def task_status_projection(
    *, task_id: str, envelope_hash: str, fsm_state: str,
    receipt: Any = None, accepted_semantic_verdict: str | None = None,
) -> dict[str, Any]:
    """Return shared lifecycle/actionability facets for human projections.

    The FSM is immutable execution history.  A validated Project-Control
    receipt may add semantic, implementation, deployment, canonicalization,
    and current-attention facets, but never rewrites that FSM value.
    """
    value = lifecycle_receipt_for_task(
        receipt, task_id=task_id, envelope_hash=envelope_hash,
    ) if receipt is not None else None
    disposition = value["lifecycle_disposition"] if value else "UNRECORDED"
    historical = disposition in HISTORICAL_LIFECYCLE_DISPOSITIONS
    receipt_human_action = bool(value["human_action_required"]) if value else False
    semantic_state = value["semantic_state"] if value else "UNKNOWN"
    semantic_verdict = accepted_semantic_verdict or semantic_state
    return {
        "execution_fsm_state": fsm_state,
        "lifecycle_disposition": disposition,
        "historical_non_actionable": historical,
        "project_progress": value["project_progress"] if value else "UNKNOWN",
        "human_action_required": bool(
            not historical
            and (fsm_state in ACTIONABLE_FSM_STATES or receipt_human_action)
        ),
        "semantic_state": semantic_state,
        "semantic_verdict": semantic_verdict,
        "design_state": value["design_state"] if value else "UNKNOWN",
        "implementation_state": value["implementation_state"] if value else "UNKNOWN",
        "deployment_state": value["deployment_state"] if value else "UNKNOWN",
        "canonicalization_state": value["canonicalization_state"] if value else "UNKNOWN",
        "authoring_receipt_sha256": value["receipt_sha256"] if value else None,
    }
