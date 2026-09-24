"""Explicit-observation Chat Health registry and deterministic re-entry packages."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from .model import ValidationError


MAX_RECORD_BYTES = 64_000
UNKNOWN = "UNKNOWN"


class ContextHealth(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    YELLOW_HIGH = "YELLOW_HIGH"
    RED = "RED"


class FinalizationHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    SEVERELY_DEGRADED = "SEVERELY_DEGRADED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DeliveryHealth(str, Enum):
    NO_KNOWN_ISSUE = "NO_KNOWN_ISSUE"
    USER_REPORTED_DEGRADED = "USER_REPORTED_DEGRADED"
    SEVERELY_DEGRADED = "SEVERELY_DEGRADED"
    UNKNOWN = "UNKNOWN"


class MigrationState(str, Enum):
    CONTEXT_HEALTHY = "CONTEXT_HEALTHY"
    REENTRY_PREPARE = "REENTRY_PREPARE"
    MIGRATE_SAME_ROLE = "MIGRATE_SAME_ROLE"
    HANDOFF_VERIFIED = "HANDOFF_VERIFIED"
    OLD_CHAT_ARCHIVE_READY = "OLD_CHAT_ARCHIVE_READY"
    UNKNOWN = "UNKNOWN"


HEALTH_FIELDS = {
    "chat_id", "logical_role", "role", "bootstrap_version", "bootstrap_last_refresh",
    "canonical_baseline", "current_task", "last_substantive_activity",
    "open_task_count", "CONTEXT_HEALTH", "FINALIZATION_HEALTH", "DELIVERY_HEALTH",
    "MIGRATION_STATE", "observation_source", "observed_at", "warning_reason",
}

REENTRY_FIELDS = {
    "CHAT_REENTRY_ID", "ROLE", "BOOTSTRAP_VERSION", "BOOTSTRAP_LAST_REFRESH",
    "CURRENT_CANONICAL_BASELINE", "CURRENT_TASK", "TASK_STATUS",
    "AUTHORITATIVE_INPUTS", "FROZEN_CONSTRAINTS", "CURRENT_DECISIONS",
    "IMPORTANT_NEGATIVE_CONSTRAINTS", "WORK_COMPLETED", "OPEN_QUESTIONS",
    "PENDING_DECISIONS", "NEXT_EXACT_ACTION", "FILES_PATHS_HASHES", "REVIEW_IDS",
    "AUTHORIZATIONS", "EXPLICITLY_NOT_AUTHORIZED", "KNOWN_RISKS",
    "RESEARCH_PORTFOLIO_REFERENCES",
}

EXPLICIT_OBSERVATION_SOURCES = {
    "EXPLICIT_USER_OBSERVATION",
    "EXPLICIT_CHAT_SELF_REPORT",
    "EXPLICIT_PROJECT_CONTROL_OBSERVATION",
}


def _json(value: Mapping[str, Any], maximum: int = MAX_RECORD_BYTES) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("record must be finite JSON") from exc
    if len(encoded.encode("utf-8")) > maximum:
        raise ValidationError(f"record exceeds {maximum} bytes")
    return encoded


def _timestamp(value: Any, name: str) -> float:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be ISO-8601 text")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        raise ValidationError(f"{name} must be ISO-8601 text") from exc


def _reject_inference_fields(value: Mapping[str, Any]) -> None:
    for key in value:
        lowered = str(key).lower()
        if "token" in lowered or "percent" in lowered or "context_remaining" in lowered:
            raise ValidationError("token/context percentages and inferred capacity fields are forbidden")


def expected_migration_state(context: str, finalization: str, delivery: str) -> str:
    if UNKNOWN in {context, finalization}:
        return MigrationState.UNKNOWN.value
    if context == ContextHealth.RED.value or finalization == FinalizationHealth.SEVERELY_DEGRADED.value:
        return MigrationState.MIGRATE_SAME_ROLE.value
    if context in {ContextHealth.YELLOW.value, ContextHealth.YELLOW_HIGH.value} or finalization == FinalizationHealth.DEGRADED.value or delivery == DeliveryHealth.SEVERELY_DEGRADED.value:
        return MigrationState.REENTRY_PREPARE.value
    return MigrationState.CONTEXT_HEALTHY.value


def validate_health_record(value: Mapping[str, Any], *, allow_unknown: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != HEALTH_FIELDS:
        raise ValidationError("Chat Health record fields mismatch")
    _reject_inference_fields(value)
    result = dict(value)
    for key in ("chat_id", "logical_role", "role", "bootstrap_version",
                "canonical_baseline", "observation_source"):
        if not isinstance(result[key], str) or not result[key].strip() or len(result[key]) > 1000:
            raise ValidationError(f"invalid Chat Health {key}")
    if allow_unknown and result["observation_source"] == "NONE":
        pass
    elif result["observation_source"] not in EXPLICIT_OBSERVATION_SOURCES:
        raise ValidationError("Chat Health accepts only explicitly supplied observations")
    for key in ("bootstrap_last_refresh", "last_substantive_activity", "observed_at"):
        _timestamp(result[key], key)
    if result["current_task"] is not None and (not isinstance(result["current_task"], str)
                                                or len(result["current_task"]) > 500):
        raise ValidationError("current_task must be null or bounded text")
    if isinstance(result["open_task_count"], bool) or not isinstance(result["open_task_count"], int) or result["open_task_count"] < 0:
        raise ValidationError("open_task_count must be a nonnegative integer")
    if allow_unknown and result["CONTEXT_HEALTH"] == UNKNOWN:
        pass
    else:
        result["CONTEXT_HEALTH"] = ContextHealth(result["CONTEXT_HEALTH"]).value
    if allow_unknown and result["FINALIZATION_HEALTH"] == UNKNOWN:
        pass
    else:
        result["FINALIZATION_HEALTH"] = FinalizationHealth(result["FINALIZATION_HEALTH"]).value
    result["DELIVERY_HEALTH"] = DeliveryHealth(result["DELIVERY_HEALTH"]).value
    migration = MigrationState(result["MIGRATION_STATE"]).value
    if migration in {MigrationState.HANDOFF_VERIFIED.value,
                     MigrationState.OLD_CHAT_ARCHIVE_READY.value}:
        raise ValidationError("handoff/archive state requires package verification, not observation")
    expected = expected_migration_state(result["CONTEXT_HEALTH"],
                                        result["FINALIZATION_HEALTH"],
                                        result["DELIVERY_HEALTH"])
    if migration != expected:
        raise ValidationError(f"MIGRATION_STATE must be {expected} for supplied health signals")
    result["MIGRATION_STATE"] = migration
    warning = result["warning_reason"]
    if migration == MigrationState.CONTEXT_HEALTHY.value:
        if warning not in {None, ""}:
            raise ValidationError("GREEN/healthy observation must not emit warning noise")
        result["warning_reason"] = None
    elif not isinstance(warning, str) or not warning.strip() or len(warning) > 2000:
        raise ValidationError("non-healthy/unknown record requires a warning_reason")
    _json(result)
    return result


def explicit_health_observation(value: Mapping[str, Any], *, now_epoch: float,
                                stale_after_seconds: int) -> dict[str, Any]:
    record = validate_health_record(value)
    if stale_after_seconds <= 0:
        raise ValidationError("stale_after_seconds must be positive")
    if now_epoch - _timestamp(record["observed_at"], "observed_at") <= stale_after_seconds:
        return record
    return unknown_health_projection(
        record["chat_id"], record["logical_role"], record["role"],
        record["bootstrap_version"], record["bootstrap_last_refresh"],
        record["canonical_baseline"], warning_reason="explicit observation is stale",
        observed_at=record["observed_at"],
    )


def unknown_health_projection(
    chat_id: str, logical_role: str, role: str, bootstrap_version: str,
    bootstrap_last_refresh: str, canonical_baseline: str, *,
    warning_reason: str = "persistent-chat telemetry not explicitly supplied",
    observed_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    value = {
        "chat_id": chat_id, "logical_role": logical_role, "role": role,
        "bootstrap_version": bootstrap_version,
        "bootstrap_last_refresh": bootstrap_last_refresh,
        "canonical_baseline": canonical_baseline, "current_task": None,
        "last_substantive_activity": observed_at, "open_task_count": 0,
        "CONTEXT_HEALTH": UNKNOWN, "FINALIZATION_HEALTH": UNKNOWN,
        "DELIVERY_HEALTH": DeliveryHealth.UNKNOWN.value,
        "MIGRATION_STATE": MigrationState.UNKNOWN.value,
        "observation_source": "NONE", "observed_at": observed_at,
        "warning_reason": warning_reason,
    }
    return validate_health_record(value, allow_unknown=True)


def health_record_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(validate_health_record(value, allow_unknown=True)).encode()).hexdigest()


def validate_reentry_package(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != REENTRY_FIELDS:
        raise ValidationError("re-entry package fields mismatch")
    _reject_inference_fields(value)
    result = dict(value)
    for key in ("CHAT_REENTRY_ID", "ROLE", "BOOTSTRAP_VERSION",
                "BOOTSTRAP_LAST_REFRESH", "CURRENT_CANONICAL_BASELINE",
                "CURRENT_TASK", "TASK_STATUS", "NEXT_EXACT_ACTION"):
        if not isinstance(result[key], str) or not result[key].strip():
            raise ValidationError(f"re-entry {key} must be nonempty text")
    for key in REENTRY_FIELDS - {
        "CHAT_REENTRY_ID", "ROLE", "BOOTSTRAP_VERSION", "BOOTSTRAP_LAST_REFRESH",
        "CURRENT_CANONICAL_BASELINE", "CURRENT_TASK", "TASK_STATUS", "NEXT_EXACT_ACTION",
    }:
        if not isinstance(result[key], list):
            raise ValidationError(f"re-entry {key} must be a list")
    if not result["EXPLICITLY_NOT_AUTHORIZED"]:
        raise ValidationError("re-entry package must preserve explicit prohibitions")
    if not result["RESEARCH_PORTFOLIO_REFERENCES"]:
        raise ValidationError("re-entry package must preserve related/deferred research references")
    _json(result)
    return result


def generate_reentry_package(**fields: Any) -> dict[str, Any]:
    return validate_reentry_package(fields)


def reentry_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(validate_reentry_package(value)).encode()).hexdigest()


def compare_handoff(expected: Mapping[str, Any], successor_observed: Mapping[str, Any]) -> dict[str, Any]:
    expected_hash = reentry_hash(expected)
    observed_hash = reentry_hash(successor_observed)
    verified = expected_hash == observed_hash
    return {
        "status": MigrationState.HANDOFF_VERIFIED.value if verified else "CHAT_HANDOFF_REQUIRED",
        "expected_hash": expected_hash,
        "observed_hash": observed_hash,
        "exact_match": verified,
        "programmatic_dispatch_claim": False,
    }


def archive_readiness(handoff: Mapping[str, Any]) -> str:
    if handoff.get("status") != MigrationState.HANDOFF_VERIFIED.value or handoff.get("exact_match") is not True:
        raise ValidationError("OLD_CHAT_ARCHIVE_READY requires HANDOFF_VERIFIED")
    return MigrationState.OLD_CHAT_ARCHIVE_READY.value
