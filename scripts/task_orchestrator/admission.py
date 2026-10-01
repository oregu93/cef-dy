"""Pure defect-aware admission and lifecycle-visibility policy.

This module deliberately performs no I/O and mutates no state.  Callers supply
durable observations and apply the returned decision through the existing FSM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping


class VisibilityHealth(str, Enum):
    AUTONOMY_VISIBILITY_OK = "AUTONOMY_VISIBILITY_OK"
    AUTONOMY_VISIBILITY_DEGRADED = "AUTONOMY_VISIBILITY_DEGRADED"
    ADMISSION_PAUSED_OPAQUE_STATE = "ADMISSION_PAUSED_OPAQUE_STATE"


class AdmissionClass(str, Enum):
    ORDINARY = "ORDINARY"
    MANDATORY_REVIEW = "MANDATORY_REVIEW"
    DIAGNOSTIC = "DIAGNOSTIC"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class VisibilityFacts:
    ordinary_autonomy_enabled: bool
    publishing_enabled: bool
    preview_only: bool
    unresolved_terminal_ages_seconds: tuple[float | None, ...] = ()
    required_publication_statuses: tuple[str, ...] = ()
    required_outbox_identities: int = 0
    max_batch_tasks: int = 1
    poll_interval_seconds: int = 300


@dataclass(frozen=True)
class VisibilityAssessment:
    state: VisibilityHealth
    reasons: tuple[str, ...]
    unresolved_terminal_count: int
    unprojected_terminal_high_water: int
    unprojected_terminal_max_age_seconds: int
    outbox_required_high_water: int


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    admission_class: AdmissionClass
    visibility_state: VisibilityHealth
    reason: str


_OPAQUE_PUBLICATION_STATES = frozenset({"UNKNOWN", "CONFLICT", "FAILED", "SENDING"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def compute_visibility_health(facts: VisibilityFacts) -> VisibilityAssessment:
    terminal_high_water = max(2, 2 * max(1, int(facts.max_batch_tasks)))
    terminal_max_age = max(600, 2 * max(1, int(facts.poll_interval_seconds)))
    outbox_high_water = 4 * terminal_high_water
    ages = tuple(facts.unresolved_terminal_ages_seconds)
    statuses = tuple(str(value).upper() for value in facts.required_publication_statuses)
    reasons: list[str] = []

    if facts.ordinary_autonomy_enabled:
        if not facts.publishing_enabled:
            reasons.append("publishing disabled while ordinary autonomy is enabled")
        if facts.preview_only:
            reasons.append("preview-only projection while ordinary autonomy is enabled")
        if any(status in _OPAQUE_PUBLICATION_STATES for status in statuses):
            reasons.append("required publication identity has opaque terminal state")
        if len(ages) >= terminal_high_water:
            reasons.append("unprojected terminal high-water reached")
        if any(age is None or age < 0 or age > terminal_max_age for age in ages):
            reasons.append("unprojected terminal age is unknown or exceeds the guard")
        if int(facts.required_outbox_identities) >= outbox_high_water:
            reasons.append("required outbox identity high-water reached")
        state = (
            VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE
            if reasons else (
                VisibilityHealth.AUTONOMY_VISIBILITY_DEGRADED
                if ages or statuses else VisibilityHealth.AUTONOMY_VISIBILITY_OK
            )
        )
    else:
        # Disabled ordinary autonomy is an explicit maintenance/shadow state.
        # Preserve projection degradation as evidence without opening a breaker
        # for work that cannot be autonomously admitted in the first place.
        state = (
            VisibilityHealth.AUTONOMY_VISIBILITY_DEGRADED
            if ages or statuses else VisibilityHealth.AUTONOMY_VISIBILITY_OK
        )
        reasons = ["ordinary autonomous enrollment is disabled"] if state is not VisibilityHealth.AUTONOMY_VISIBILITY_OK else []

    return VisibilityAssessment(
        state=state,
        reasons=tuple(reasons),
        unresolved_terminal_count=len(ages),
        unprojected_terminal_high_water=terminal_high_water,
        unprojected_terminal_max_age_seconds=terminal_max_age,
        outbox_required_high_water=outbox_high_water,
    )


def classify_admission(inputs: Mapping[str, Any]) -> AdmissionClass:
    """Classify only exact structured declarations; free text is ignored."""
    review_of = inputs.get("review_of")
    material = inputs.get("review_material")
    if (
        inputs.get("independent_review") is True
        and isinstance(review_of, str) and bool(review_of)
        and isinstance(material, Mapping)
        and material.get("parent_task_id") == review_of
        and isinstance(material.get("accepted_result_sha256"), str)
        and _SHA256.fullmatch(str(material["accepted_result_sha256"])) is not None
    ):
        return AdmissionClass.MANDATORY_REVIEW

    control = inputs.get("admission_control")
    if (
        isinstance(control, Mapping)
        and control.get("class") in {
            AdmissionClass.DIAGNOSTIC.value, AdmissionClass.RECOVERY.value,
        }
    ):
        return AdmissionClass(str(control["class"]))
    return AdmissionClass.ORDINARY


def decide_admission(
    assessment: VisibilityAssessment,
    admission_class: AdmissionClass,
    *,
    identity_bound_review: bool = False,
    unresolved_replacement_identity: bool = False,
) -> AdmissionDecision:
    if admission_class in {AdmissionClass.DIAGNOSTIC, AdmissionClass.RECOVERY}:
        return AdmissionDecision(
            False, admission_class, assessment.state,
            "task-level diagnostic or recovery bypass has no trusted durable authority",
        )
    if unresolved_replacement_identity:
        return AdmissionDecision(
            False, admission_class, assessment.state,
            "replacement or superseding task references an unresolved original identity",
        )
    if admission_class is AdmissionClass.MANDATORY_REVIEW and not identity_bound_review:
        return AdmissionDecision(
            False, admission_class, assessment.state,
            "mandatory review is not bound to an existing accepted parent result",
        )
    if assessment.state is not VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE:
        return AdmissionDecision(True, admission_class, assessment.state, "visibility gate permits admission")
    if admission_class is AdmissionClass.MANDATORY_REVIEW:
        return AdmissionDecision(True, admission_class, assessment.state, "bounded paused-state exception")
    return AdmissionDecision(
        False, admission_class, assessment.state,
        "ordinary autonomous admission blocked by opaque lifecycle visibility",
    )
