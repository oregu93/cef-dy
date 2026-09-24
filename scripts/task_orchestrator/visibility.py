"""Read-only task-board and resource-planning projections.

This module never dispatches work.  Operational sidecars are independent of
the TASK-v1 worker queue and cannot alter the finite-state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

from .model import State, ValidationError


HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,199}$")
MAX_SIDECAR_BYTES = 32_768


class ExecutionLane(str, Enum):
    LOCAL_DETERMINISTIC = "LOCAL_DETERMINISTIC"
    QUOTA_CONSUMING_INTERACTIVE = "QUOTA_CONSUMING_INTERACTIVE"
    QUOTA_CONSUMING_UNATTENDED = "QUOTA_CONSUMING_UNATTENDED"
    HUMAN_CHAT_HANDOFF = "HUMAN_CHAT_HANDOFF"


class HumanAttention(str, Enum):
    NONE = "NONE"
    REVIEW = "REVIEW"
    APPROVAL = "APPROVAL"
    HANDOFF = "HANDOFF"


class QuotaState(str, Enum):
    AVAILABLE = "AVAILABLE"
    EXHAUSTED = "EXHAUSTED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


class VisibilityState(str, Enum):
    PROJECTED = "PROJECTED"
    REVIEW_RUNNING = "REVIEW_RUNNING"
    COMPLETED_RESULT_LEVEL_REVIEW = "COMPLETED_RESULT_LEVEL_REVIEW"
    TASK_AVAILABLE_BUT_NOT_DISPATCHED = "TASK_AVAILABLE_BUT_NOT_DISPATCHED"
    CHAT_HANDOFF_REQUIRED = "CHAT_HANDOFF_REQUIRED"


CURRENT_SCIENCE_LANE_FIXTURE = {
    "repository": "oregu93/cef-dy",
    "task_id": "STAGE03R-CS15-SYNTHETIC-HYPERSPACE-MVP-SCIENTIFIC-REVIEW-001",
    "envelope_hash": "0" * 64,
    "target_chat": "03 - CEF Modelling & Fit Design",
    "scientific_parent": "MOD-CEF-CS15 / Stage03R landscape-identifiability programme",
    "current_observed_status": "COMPLETED_RESULT_LEVEL_REVIEW",
    "execution_lane": ExecutionLane.HUMAN_CHAT_HANDOFF.value,
    "human_attention_class": HumanAttention.REVIEW.value,
    "unattended_safe": False,
    "away_eligible": False,
    "interactive_explicit": True,
    "chat_only": True,
    "handoff_delivered": True,
    "observation_source": "USER_SUPPLIED_ACTIVE_TASK_OBSERVATION",
    "observed_at": "2026-09-24T00:00:00Z",
    "dispatch_claim": "NONE",
    "external_project_fields": {
        "envelope_hash_status": "NOT_SUPPLIED_DISPLAY_FIXTURE",
        "terminal_verdict": "IMPLEMENTATION_ARTIFACT_VERIFICATION_REQUIRED",
        "scientific_result": (
            "synthetic intensity information supports increased local CS15 "
            "identifiability at result level; global identifiability remains unresolved"
        ),
        "canonicalization": "DEFERRED_PENDING_ARTIFACT_LEVEL_VERIFICATION",
    },
}


NEXT_SCIENCE_SUPPORT_FIXTURE = {
    "repository": "oregu93/cef-dy",
    "task_id": "STAGE03R-CS15-SYNTHETIC-MVP-ARTIFACT-REVIEW-PACKAGE-001",
    "envelope_hash": "1" * 64,
    "target_chat": "WKB-R3",
    "scientific_parent": "MOD-CEF-CS15 / Stage03R landscape-identifiability programme",
    "current_observed_status": "WAITING_EXECUTION_LANE",
    "execution_lane": ExecutionLane.QUOTA_CONSUMING_INTERACTIVE.value,
    "human_attention_class": HumanAttention.REVIEW.value,
    "unattended_safe": False,
    "away_eligible": False,
    "interactive_explicit": False,
    "chat_only": False,
    "handoff_delivered": False,
    "observation_source": "USER_SUPPLIED_ACTIVE_TASK_OBSERVATION",
    "observed_at": "2026-09-24T00:00:00Z",
    "dispatch_claim": "NONE",
    "external_project_fields": {
        "envelope_hash_status": "NOT_SUPPLIED_DISPLAY_FIXTURE",
        "target_role": "WKB-R3",
        "declared_why_not_running": (
            "WKB-R3 currently occupied by active Orch M1 implementation"
        ),
        "dependency": "complete current bounded WKB M1 task first",
    },
}


SCIENCE_LANE_CONTINUATION_FIXTURE = {
    "target_chat": "03 - CEF Modelling & Fit Design",
    "purpose": "artifact-level continuation of the existing CS15 scientific review",
    "state": "WAITING_DEPENDENCY",
    "dependency": "CS15 exact artifact review package",
    "dispatch_claim": "NONE",
}


def _iso_epoch(value: str, field: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an ISO-8601 timestamp") from exc


def _bounded_json(value: Mapping[str, Any], maximum: int, label: str) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be finite JSON data") from exc
    if len(encoded.encode("utf-8")) > maximum:
        raise ValidationError(f"{label} exceeds {maximum} bytes")
    return encoded


def validate_sidecar(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("sidecar must be a mapping")
    required = {
        "repository", "task_id", "envelope_hash", "target_chat", "scientific_parent",
        "current_observed_status", "execution_lane", "human_attention_class",
        "unattended_safe", "away_eligible", "interactive_explicit", "chat_only",
        "handoff_delivered", "observation_source", "observed_at", "dispatch_claim",
        "external_project_fields",
    }
    if set(value) != required:
        raise ValidationError(
            "sidecar fields mismatch; missing=" + str(sorted(required - set(value)))
            + " unknown=" + str(sorted(set(value) - required))
        )
    result = dict(value)
    if not isinstance(result["repository"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", result["repository"]):
        raise ValidationError("sidecar repository must be owner/name")
    if not isinstance(result["task_id"], str) or not TASK_RE.fullmatch(result["task_id"]):
        raise ValidationError("invalid sidecar task_id")
    if not isinstance(result["envelope_hash"], str) or not HASH_RE.fullmatch(result["envelope_hash"]):
        raise ValidationError("invalid sidecar envelope_hash")
    for key in ("target_chat", "scientific_parent", "current_observed_status",
                "observation_source"):
        if not isinstance(result[key], str) or not result[key].strip() or len(result[key]) > 1000:
            raise ValidationError(f"invalid sidecar {key}")
    result["execution_lane"] = ExecutionLane(result["execution_lane"]).value
    result["human_attention_class"] = HumanAttention(result["human_attention_class"]).value
    for key in ("unattended_safe", "away_eligible", "interactive_explicit",
                "chat_only", "handoff_delivered"):
        if not isinstance(result[key], bool):
            raise ValidationError(f"sidecar {key} must be boolean")
    if result["away_eligible"] and not result["unattended_safe"]:
        raise ValidationError("away_eligible requires unattended_safe")
    if result["execution_lane"] == ExecutionLane.HUMAN_CHAT_HANDOFF.value and not result["chat_only"]:
        raise ValidationError("HUMAN_CHAT_HANDOFF must remain chat_only")
    if result["dispatch_claim"] != "NONE":
        raise ValidationError("programmatic chat dispatch claims are forbidden")
    _iso_epoch(result["observed_at"], "observed_at")
    if not isinstance(result["external_project_fields"], Mapping):
        raise ValidationError("external_project_fields must be a mapping")
    forbidden = {"state", "task_state", "approved", "execute", "dispatch", "canonical_authority"}
    if forbidden & set(result["external_project_fields"]):
        raise ValidationError("external Project fields cannot override human/FSM authority")
    _bounded_json(result, MAX_SIDECAR_BYTES, "sidecar")
    return result


@dataclass(frozen=True)
class QuotaWindow:
    name: str
    state: str
    observed_at: str | None
    reset_at: str | None

    def effective_state(self, *, now_epoch: float, stale_after_seconds: int) -> str:
        state = QuotaState(self.state)
        if state in {QuotaState.UNKNOWN, QuotaState.STALE} or self.observed_at is None:
            if self.reset_at is not None:
                _iso_epoch(self.reset_at, f"{self.name}.reset_at")
            return QuotaState.UNKNOWN.value if state == QuotaState.UNKNOWN else QuotaState.STALE.value
        observed = _iso_epoch(self.observed_at, f"{self.name}.observed_at")
        if self.reset_at is not None:
            _iso_epoch(self.reset_at, f"{self.name}.reset_at")
        if now_epoch - observed > stale_after_seconds:
            return QuotaState.STALE.value
        # reset_at is descriptive only: passing it never changes PAUSED_QUOTA or quota state.
        return state.value


@dataclass(frozen=True)
class QuotaSnapshot:
    five_hour: QuotaWindow
    weekly: QuotaWindow
    stale_after_seconds: int

    @classmethod
    def unknown(cls, stale_after_seconds: int = 900) -> "QuotaSnapshot":
        return cls(
            QuotaWindow("five_hour", QuotaState.UNKNOWN.value, None, None),
            QuotaWindow("weekly", QuotaState.UNKNOWN.value, None, None),
            stale_after_seconds,
        )

    def states(self, now_epoch: float) -> dict[str, str]:
        if isinstance(self.stale_after_seconds, bool) or self.stale_after_seconds <= 0:
            raise ValidationError("quota stale_after_seconds must be positive")
        return {
            "five_hour": self.five_hour.effective_state(
                now_epoch=now_epoch, stale_after_seconds=self.stale_after_seconds),
            "weekly": self.weekly.effective_state(
                now_epoch=now_epoch, stale_after_seconds=self.stale_after_seconds),
        }


def quota_eligibility(
    *, lane: str, unattended_safe: bool, interactive_explicit: bool,
    task_state: str | None, quota: QuotaSnapshot, now_epoch: float,
) -> tuple[bool, list[str]]:
    lane_value = ExecutionLane(lane)
    if task_state == State.PAUSED_QUOTA.value:
        return False, ["EXPLICIT_RESUME_REQUIRED"]
    if lane_value == ExecutionLane.LOCAL_DETERMINISTIC:
        return True, []
    if lane_value == ExecutionLane.HUMAN_CHAT_HANDOFF:
        return False, ["HUMAN_CHAT_HANDOFF_REQUIRED"]
    states = quota.states(now_epoch)
    if QuotaState.EXHAUSTED.value in states.values():
        return False, [f"{name.upper()}_QUOTA_EXHAUSTED" for name, state in states.items()
                       if state == QuotaState.EXHAUSTED.value]
    uncertain = [name for name, state in states.items()
                 if state in {QuotaState.UNKNOWN.value, QuotaState.STALE.value}]
    if interactive_explicit and lane_value == ExecutionLane.QUOTA_CONSUMING_INTERACTIVE:
        return True, [f"{name.upper()}_QUOTA_{states[name]}_INTERACTIVE_OVERRIDE" for name in uncertain]
    reasons = [f"{name.upper()}_QUOTA_{states[name]}" for name in uncertain]
    if not unattended_safe:
        reasons.append("NOT_UNATTENDED_SAFE")
    return not reasons, reasons


def sidecar_identity(value: Mapping[str, Any]) -> tuple[str, str, str, str]:
    record = validate_sidecar(value)
    encoded = _bounded_json(record, MAX_SIDECAR_BYTES, "sidecar").encode("utf-8")
    return (record["repository"], record["task_id"], record["envelope_hash"],
            hashlib.sha256(encoded).hexdigest())


def project_board(store: Any, quota: QuotaSnapshot, *, now_epoch: float) -> dict[str, Any]:
    tasks = {row["task_id"]: dict(row) for row in store.list_state()}
    items: list[dict[str, Any]] = []
    for raw in store.list_sidecars():
        metadata = validate_sidecar(json.loads(raw["metadata_json"]))
        task = tasks.get(metadata["task_id"])
        task_state = task["state"] if task else None
        eligible, reasons = quota_eligibility(
            lane=metadata["execution_lane"],
            unattended_safe=metadata["unattended_safe"],
            interactive_explicit=metadata["interactive_explicit"],
            task_state=task_state,
            quota=quota,
            now_epoch=now_epoch,
        )
        declared_reason = metadata["external_project_fields"].get(
            "declared_why_not_running"
        )
        if isinstance(declared_reason, str) and declared_reason.strip():
            reasons = list(dict.fromkeys(reasons + [declared_reason]))
        if metadata["current_observed_status"] == VisibilityState.REVIEW_RUNNING.value:
            visibility = VisibilityState.REVIEW_RUNNING.value
            eligible = False
            reasons = ["REVIEW_ALREADY_RUNNING"]
        elif metadata["current_observed_status"] == VisibilityState.COMPLETED_RESULT_LEVEL_REVIEW.value:
            visibility = VisibilityState.COMPLETED_RESULT_LEVEL_REVIEW.value
            eligible = False
            reasons = ["IMPLEMENTATION_ARTIFACT_VERIFICATION_REQUIRED"]
        elif metadata["chat_only"] and not metadata["handoff_delivered"]:
            visibility = VisibilityState.CHAT_HANDOFF_REQUIRED.value
        elif task is None:
            visibility = VisibilityState.TASK_AVAILABLE_BUT_NOT_DISPATCHED.value
            reasons = list(dict.fromkeys(reasons + ["TASK_NOT_IN_WORKER_QUEUE"]))
            eligible = False
        else:
            visibility = VisibilityState.PROJECTED.value
            if task_state != State.READY.value:
                reasons = list(dict.fromkeys(reasons + [f"FSM_STATE_{task_state}"]))
                eligible = False
        items.append({
            **metadata,
            "worker_task_present": task is not None,
            "worker_task_state": task_state,
            "visibility_state": visibility,
            "resource_eligible": eligible,
            "WHY_NOT_RUNNING": reasons,
            "external_project_fields_observed_only": metadata["external_project_fields"],
        })
    return {
        "schema_version": 1,
        "projection_only": True,
        "dispatch_performed": False,
        "worker_starts": 0,
        "llm_calls": 0,
        "github_mutations": 0,
        "quota_windows": quota.states(now_epoch),
        "queue": sorted(items, key=lambda item: (item["task_id"], item["envelope_hash"])),
    }


def science_lane_fixture() -> dict[str, Any]:
    return validate_sidecar(dict(CURRENT_SCIENCE_LANE_FIXTURE))


def science_lane_fixtures() -> dict[str, Any]:
    """Return corrected display-only science-lane observations and continuation."""
    return {
        "current_review": science_lane_fixture(),
        "next_science_support_task": validate_sidecar(dict(NEXT_SCIENCE_SUPPORT_FIXTURE)),
        "continuation": dict(SCIENCE_LANE_CONTINUATION_FIXTURE),
    }
