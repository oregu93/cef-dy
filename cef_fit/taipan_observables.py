"""Version-controlled manuscript observation table and admission audit."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = (
    "observation_id", "dataset_id", "source_scan_id", "instrument_block_id",
    "observable_type", "energy_meV", "energy_sigma_meV", "temperature_K",
    "h_pbnm", "k_pbnm", "l_pbnm", "Q_Ainv", "intensity_value",
    "intensity_sigma", "intensity_units", "detection_status", "censor_threshold",
    "censor_sigma", "censor_confidence", "assignment_status",
    "allowed_final_doublets", "likelihood_role", "source_artifact",
    "provenance_status", "normalization_status", "grouping_rationale",
    "missing_configuration_fields", "notes",
)


def _float_or_none(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


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
        return self.raw.get("instrument_block_id", "")


@dataclass(frozen=True)
class InputAudit:
    status: str
    row_count: int
    admitted_energy_count: int
    admitted_detected_intensity_count: int
    admitted_censored_count: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def production_ready(self) -> bool:
        return self.status == "MANUSCRIPT_PRODUCTION_READY"


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


def audit_observations(rows: Iterable[Observation]) -> InputAudit:
    rows = tuple(rows)
    blockers: list[str] = []
    warnings: list[str] = []
    energy = admitted_energy_rows(rows)
    detected = tuple(row for row in rows if row.likelihood_role == "DETECTED_INTENSITY")
    censored = tuple(row for row in rows if row.likelihood_role == "CENSORED_NONDETECTION")
    if not energy:
        blockers.append("NO_ADMITTED_ENERGY_CANDIDATE")
    for row in energy:
        if row.energy_meV is None or row.energy_sigma_meV is None or row.energy_sigma_meV <= 0:
            blockers.append(f"{row.observation_id}:INVALID_ENERGY_OBSERVATION")
    for row in detected:
        if not row.instrument_block_id:
            blockers.append(f"{row.observation_id}:MISSING_INSTRUMENT_BLOCK")
        if row.intensity_value is None or row.intensity_sigma is None or row.intensity_sigma <= 0:
            blockers.append(f"{row.observation_id}:INVALID_DETECTED_INTENSITY")
        if row.raw.get("provenance_status") != "REVIEWED":
            blockers.append(f"{row.observation_id}:INTENSITY_PROVENANCE_NOT_REVIEWED")
        if row.raw.get("normalization_status") != "REVIEWED":
            blockers.append(f"{row.observation_id}:NORMALIZATION_GROUPING_NOT_REVIEWED")
    for row in censored:
        if not row.instrument_block_id:
            blockers.append(f"{row.observation_id}:MISSING_INSTRUMENT_BLOCK")
        if row.censor_threshold is None or row.censor_sigma is None or row.censor_sigma <= 0:
            blockers.append(f"{row.observation_id}:INVALID_CENSOR_MODEL")
        if row.raw.get("provenance_status") != "REVIEWED":
            blockers.append(f"{row.observation_id}:CENSOR_PROVENANCE_NOT_REVIEWED")
    candidate = next((row for row in energy if row.observation_id == "TAIPAN-18P247-ENERGY"), None)
    if candidate is not None:
        required = ("source_scan_id", "temperature_K", "Q_Ainv")
        missing = [field for field in required if not candidate.raw.get(field, "").strip()]
        if missing:
            blockers.append("TAIPAN-18P247-ENERGY:MISSING_SCAN_LEVEL_PROVENANCE=" + ";".join(missing))
    if not detected:
        blockers.append("NO_PROVENANCE_QUALIFIED_DETECTED_INTENSITY_ROWS")
    if not censored:
        blockers.append("NO_PROVENANCE_QUALIFIED_CENSORED_ROWS")
    if any(row.observation_id == "STAGE03R-38MEV-NULL" and row.likelihood_role != "EXCLUDED_FROM_CEF_LIKELIHOOD" for row in rows):
        blockers.append("STAGE03R_LEVEL2_SENSITIVITY_MISUSED")
    if any(row.observation_id in {"HIST-6P447", "HIST-27P896"} and row.likelihood_role != "EXCLUDED_FROM_BASELINE_LIKELIHOOD" for row in rows):
        blockers.append("HISTORICAL_ENERGY_MISUSED")
    if any(row.observation_id == "LEGACY-44P4" and row.likelihood_role != "DIAGNOSTIC_ONLY" for row in rows):
        blockers.append("AMBIGUOUS_44P4_MISUSED")
    if not rows:
        blockers.append("EMPTY_OBSERVATION_TABLE")
    status = "MANUSCRIPT_PRODUCTION_READY" if not blockers else "DRAFT_PROVENANCE_INCOMPLETE"
    return InputAudit(status, len(rows), len(energy), len(detected), len(censored), tuple(blockers), tuple(warnings))
