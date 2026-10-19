"""Version-controlled manuscript observation table and admission audit."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


REQUIRED_COLUMNS = (
    "observation_id", "dataset_id", "source_scan_id", "instrument_block_id",
    "observable_type", "energy_meV", "energy_sigma_meV", "temperature_K",
    "h_pbnm", "k_pbnm", "l_pbnm", "Q_Ainv", "intensity_value",
    "intensity_sigma", "intensity_units", "detection_status", "censor_threshold",
    "censor_sigma", "censor_confidence", "assignment_status",
    "allowed_final_doublets", "likelihood_role", "source_artifact",
    "provenance_status", "normalization_status", "grouping_rationale",
    "missing_configuration_fields", "notes", "aggregation_status",
    "source_scan_set", "provenance_manifest",
)


class ObjectiveReadiness(str, Enum):
    ENERGY_ONLY = "ENERGY_ONLY"
    ENERGY_PLUS_DETECTED_INTENSITY = "ENERGY_PLUS_DETECTED_INTENSITY"
    ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING = (
        "ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING"
    )


_READINESS_RANK = {
    ObjectiveReadiness.ENERGY_ONLY: 1,
    ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY: 2,
    ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING: 3,
}


@dataclass(frozen=True)
class AdmissionPolicy:
    energy_provenance_statuses: frozenset[str] = frozenset({"REVIEWED_ENERGY_ONLY", "REVIEWED"})
    intensity_provenance_statuses: frozenset[str] = frozenset({"REVIEWED"})
    censor_provenance_statuses: frozenset[str] = frozenset({"REVIEWED"})
    normalization_statuses: frozenset[str] = frozenset({"REVIEWED"})
    minimum_detected_rows_per_block: int = 2
    require_q_ainv_for_intensity: bool = True

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None) -> "AdmissionPolicy":
        values = values or {}

        def statuses(name: str, default: frozenset[str]) -> frozenset[str]:
            configured = values.get(name)
            if configured is None:
                return default
            if not isinstance(configured, list) or not configured or not all(
                isinstance(value, str) and value for value in configured
            ):
                raise ValueError(f"inputs.admission.{name} must be a non-empty list of strings")
            return frozenset(configured)

        minimum = int(values.get("minimum_detected_rows_per_block", 2))
        if minimum < 2:
            raise ValueError("minimum_detected_rows_per_block must be at least 2")
        require_q = values.get("require_Q_Ainv_for_intensity", True)
        if not isinstance(require_q, bool):
            raise ValueError("require_Q_Ainv_for_intensity must be boolean")
        return cls(
            energy_provenance_statuses=statuses(
                "accepted_energy_provenance_statuses", cls.energy_provenance_statuses
            ),
            intensity_provenance_statuses=statuses(
                "accepted_intensity_provenance_statuses", cls.intensity_provenance_statuses
            ),
            censor_provenance_statuses=statuses(
                "accepted_censor_provenance_statuses", cls.censor_provenance_statuses
            ),
            normalization_statuses=statuses(
                "accepted_normalization_statuses", cls.normalization_statuses
            ),
            minimum_detected_rows_per_block=minimum,
            require_q_ainv_for_intensity=require_q,
        )


def _float_or_none(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def _finite(value: float | None) -> bool:
    return value is not None and bool(np.isfinite(value))


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


@dataclass(frozen=True)
class Observation:
    raw: dict[str, str]

    @property
    def observation_id(self) -> str:
        return self.raw["observation_id"]

    @property
    def likelihood_role(self) -> str:
        return self.raw["likelihood_role"]

    @property
    def energy_meV(self) -> float | None:
        return _float_or_none(self.raw.get("energy_meV"))

    @property
    def energy_sigma_meV(self) -> float | None:
        return _float_or_none(self.raw.get("energy_sigma_meV"))

    @property
    def temperature_K(self) -> float | None:
        return _float_or_none(self.raw.get("temperature_K"))

    @property
    def q_ainv(self) -> float | None:
        return _float_or_none(self.raw.get("Q_Ainv"))

    @property
    def intensity_value(self) -> float | None:
        return _float_or_none(self.raw.get("intensity_value"))

    @property
    def intensity_sigma(self) -> float | None:
        return _float_or_none(self.raw.get("intensity_sigma"))

    @property
    def censor_threshold(self) -> float | None:
        return _float_or_none(self.raw.get("censor_threshold"))

    @property
    def censor_sigma(self) -> float | None:
        return _float_or_none(self.raw.get("censor_sigma"))

    @property
    def instrument_block_id(self) -> str:
        return self.raw.get("instrument_block_id", "").strip()


@dataclass(frozen=True)
class InputAudit:
    objective_readiness: ObjectiveReadiness | None
    row_count: int
    admitted_energy_count: int
    admitted_detected_intensity_count: int
    admitted_censored_count: int
    admissible_instrument_blocks: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def status(self) -> str:
        return "INPUT_INVALID" if self.blockers else str(self.objective_readiness.value)

    @property
    def manuscript_intensity_ready(self) -> bool:
        return self.satisfies(ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY)

    @property
    def production_ready(self) -> bool:
        return self.manuscript_intensity_ready

    @property
    def full_joint_ready(self) -> bool:
        return self.satisfies(ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING)

    def satisfies(self, required: ObjectiveReadiness | str) -> bool:
        if self.blockers or self.objective_readiness is None:
            return False
        required_class = ObjectiveReadiness(required)
        return _READINESS_RANK[self.objective_readiness] >= _READINESS_RANK[required_class]


def load_observations(path: str | Path) -> tuple[Observation, ...]:
    table = Path(path)
    with table.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"Observation table is missing columns: {missing}")
        rows = tuple(Observation(dict(row)) for row in reader)
    identifiers = [row.observation_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("observation_id values must be unique")
    return rows


def admitted_energy_rows(rows: Iterable[Observation]) -> tuple[Observation, ...]:
    return tuple(row for row in rows if row.likelihood_role == "ENERGY_CANDIDATE")


def _energy_issues(row: Observation, policy: AdmissionPolicy) -> list[str]:
    issues: list[str] = []
    if not _finite(row.energy_meV) or not _finite(row.energy_sigma_meV) or row.energy_sigma_meV <= 0:
        issues.append("INVALID_ENERGY_OBSERVATION")
    if not _present(row.raw.get("source_artifact")):
        issues.append("MISSING_EXACT_SOURCE_ARTIFACT")
    if row.raw.get("provenance_status") not in policy.energy_provenance_statuses:
        issues.append("ENERGY_PROVENANCE_NOT_ADMITTED")
    aggregation = row.raw.get("aggregation_status", "").strip()
    if aggregation == "AGGREGATE":
        if not (_present(row.raw.get("source_scan_set")) or _present(row.raw.get("provenance_manifest"))):
            issues.append("MISSING_AGGREGATE_SOURCE_SCAN_SET")
    elif aggregation == "SINGLE_SCAN":
        if not _present(row.raw.get("source_scan_id")):
            issues.append("MISSING_SOURCE_SCAN_ID")
        if not _finite(row.temperature_K) or row.temperature_K <= 0:
            issues.append("INVALID_TEMPERATURE")
        if not _finite(row.q_ainv) or row.q_ainv <= 0:
            issues.append("INVALID_Q_AINV")
    else:
        issues.append("AGGREGATION_STATUS_NOT_EXPLICIT")
    return issues


def _intensity_issues(
    row: Observation,
    policy: AdmissionPolicy,
    provenance_statuses: frozenset[str],
    censored: bool,
) -> list[str]:
    issues: list[str] = []
    if not row.instrument_block_id:
        issues.append("MISSING_INSTRUMENT_BLOCK")
    if not _present(row.raw.get("source_scan_id")):
        issues.append("MISSING_SOURCE_SCAN_ID")
    if not _present(row.raw.get("source_artifact")):
        issues.append("MISSING_EXACT_SOURCE_ARTIFACT")
    if row.raw.get("provenance_status") not in provenance_statuses:
        issues.append("PROVENANCE_STATUS_NOT_ADMITTED")
    if row.raw.get("normalization_status") not in policy.normalization_statuses:
        issues.append("NORMALIZATION_STATUS_NOT_ADMITTED")
    if not _present(row.raw.get("grouping_rationale")):
        issues.append("MISSING_MULTIPLICATIVE_SCALE_RATIONALE")
    if policy.require_q_ainv_for_intensity and (not _finite(row.q_ainv) or row.q_ainv <= 0):
        issues.append("INVALID_Q_AINV_FOR_INTENSITY_MODEL")
    if censored:
        if (
            not _finite(row.censor_threshold)
            or row.censor_threshold < 0
            or not _finite(row.censor_sigma)
            or row.censor_sigma <= 0
        ):
            issues.append("INVALID_CENSOR_MODEL")
    else:
        if row.raw.get("observable_type") not in {"integrated_intensity", "peak_area"}:
            issues.append("DETECTED_OBSERVATION_IS_NOT_AREA")
        if (
            not _finite(row.intensity_value)
            or row.intensity_value <= 0
            or not _finite(row.intensity_sigma)
            or row.intensity_sigma <= 0
        ):
            issues.append("INVALID_DETECTED_INTENSITY")
    return issues


def audit_observations(
    rows: Iterable[Observation], policy: AdmissionPolicy | None = None
) -> InputAudit:
    rows = tuple(rows)
    policy = policy or AdmissionPolicy()
    blockers: list[str] = []
    warnings: list[str] = []

    energy_rows = admitted_energy_rows(rows)
    valid_energy: list[Observation] = []
    if not energy_rows:
        blockers.append("NO_ADMITTED_ENERGY_CANDIDATE")
    for row in energy_rows:
        issues = _energy_issues(row, policy)
        blockers.extend(f"{row.observation_id}:{issue}" for issue in issues)
        if not issues:
            valid_energy.append(row)

    detected_rows = tuple(row for row in rows if row.likelihood_role == "DETECTED_INTENSITY")
    valid_detected: list[Observation] = []
    for row in detected_rows:
        issues = _intensity_issues(
            row, policy, policy.intensity_provenance_statuses, censored=False
        )
        blockers.extend(f"{row.observation_id}:{issue}" for issue in issues)
        if not issues:
            valid_detected.append(row)

    detected_by_block: dict[str, list[Observation]] = defaultdict(list)
    for row in valid_detected:
        detected_by_block[row.instrument_block_id].append(row)
    admissible_blocks = tuple(sorted(
        block for block, block_rows in detected_by_block.items()
        if len(block_rows) >= policy.minimum_detected_rows_per_block
    ))
    admitted_detected = tuple(
        row for row in valid_detected if row.instrument_block_id in admissible_blocks
    )
    if not detected_rows:
        warnings.append("NO_DETECTED_INTENSITY_ROWS")
    elif not admissible_blocks and not blockers:
        warnings.append("NO_ADMISSIBLE_DETECTED_INTENSITY_BLOCK")

    censored_rows = tuple(row for row in rows if row.likelihood_role == "CENSORED_NONDETECTION")
    valid_censored: list[Observation] = []
    for row in censored_rows:
        issues = _intensity_issues(
            row, policy, policy.censor_provenance_statuses, censored=True
        )
        blockers.extend(f"{row.observation_id}:{issue}" for issue in issues)
        if not issues:
            valid_censored.append(row)
    admitted_censored = tuple(
        row for row in valid_censored if row.instrument_block_id in admissible_blocks
    )
    if valid_censored and not admitted_censored and not blockers:
        warnings.append("NO_CENSORED_ROW_IN_ADMISSIBLE_INTENSITY_BLOCK")

    if any(
        row.observation_id == "STAGE03R-38MEV-NULL"
        and row.likelihood_role != "EXCLUDED_FROM_CEF_LIKELIHOOD"
        for row in rows
    ):
        blockers.append("STAGE03R_LEVEL2_SENSITIVITY_MISUSED")
    if any(
        row.observation_id in {"HIST-6P447", "HIST-27P896"}
        and row.likelihood_role != "EXCLUDED_FROM_BASELINE_LIKELIHOOD"
        for row in rows
    ):
        blockers.append("HISTORICAL_ENERGY_MISUSED")
    if any(
        row.observation_id == "LEGACY-44P4" and row.likelihood_role != "DIAGNOSTIC_ONLY"
        for row in rows
    ):
        blockers.append("AMBIGUOUS_44P4_MISUSED")
    if not rows:
        blockers.append("EMPTY_OBSERVATION_TABLE")

    if blockers or not valid_energy:
        readiness = None
    elif admitted_detected and admitted_censored:
        readiness = ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING
    elif admitted_detected:
        readiness = ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY
    else:
        readiness = ObjectiveReadiness.ENERGY_ONLY

    return InputAudit(
        objective_readiness=readiness,
        row_count=len(rows),
        admitted_energy_count=len(valid_energy),
        admitted_detected_intensity_count=len(admitted_detected),
        admitted_censored_count=len(admitted_censored),
        admissible_instrument_blocks=admissible_blocks,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
