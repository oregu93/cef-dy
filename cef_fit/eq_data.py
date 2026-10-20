"""Prepared numerical TAIPAN E-Q data contract, immutable masks, and audit."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
import yaml

from .provenance import sha256_file


REQUIRED_COLUMNS = (
    "point_id",
    "energy_meV",
    "Q_Ainv",
    "normalized_intensity",
    "instrument_block_id",
    "scan_id",
    "mask_status",
    "normalization_metadata",
)
OPTIONAL_COLUMNS = (
    "normalized_intensity_sigma",
    "monitor_counts",
    "monitor",
    "exposure_s",
    "time",
    "Ei_meV",
    "Ef_meV",
    "h_pbnm",
    "k_pbnm",
    "l_pbnm",
    "qhat_direct_x",
    "qhat_direct_y",
    "qhat_direct_z",
    "background_metadata",
    "constraint_class",
    "feature_id",
    "temperature_status",
    "temperature_K_if_verified",
    "discovery_holdout_role",
    "count_control_mode",
    "normalization_compatibility_group_id",
    "acquisition_state_id",
    "lattice_state_id",
    "UB_state_id",
    "validity_status",
    "mask_flags",
    "source_artifact",
    "source_commit",
)
FORBIDDEN_DISPLAY_COLUMNS = frozenset(
    {
        "log_intensity",
        "log10_intensity",
        "display_intensity",
        "colour_value",
        "color_value",
        "pixel_value",
    }
)
CONSTRAINT_CLASSES = frozenset(
    {
        "ENERGY_CONSTRAINT",
        "SPECTRAL_SHAPE_CONSTRAINT",
        "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT",
    }
)


def _readonly(values: NDArray[Any]) -> NDArray[Any]:
    values.setflags(write=False)
    return values


@dataclass(frozen=True)
class EQDataset:
    path: Path
    sha256: str
    point_ids: tuple[str, ...]
    energy_meV: NDArray[np.float64]
    q_ainv: NDArray[np.float64]
    intensity: NDArray[np.float64]
    sigma: NDArray[np.float64] | None
    blocks: tuple[str, ...]
    scan_ids: tuple[str, ...]
    mask_status: tuple[str, ...]
    normalization_metadata: tuple[str, ...]
    constraint_classes: tuple[str, ...]
    feature_ids: tuple[tuple[str, ...], ...]
    qhat_direct: NDArray[np.float64] | None
    ei_meV: NDArray[np.float64] | None
    ef_meV: NDArray[np.float64] | None
    temperature_K: NDArray[np.float64] | None
    temperature_status: tuple[str, ...]
    discovery_holdout_role: tuple[str, ...]
    count_control_mode: tuple[str, ...]
    normalization_groups: tuple[str, ...]
    lattice_state_ids: tuple[str, ...]
    ub_state_ids: tuple[str, ...]
    columns: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.point_ids)


@dataclass(frozen=True)
class MaskRule:
    rule_id: str
    kind: str
    reason: str
    enabled: bool
    parameters: dict[str, object]


@dataclass(frozen=True)
class MaskDefinition:
    path: Path
    sha256: str
    mask_id: str
    rules: tuple[MaskRule, ...]


@dataclass(frozen=True)
class AppliedMask:
    include: NDArray[np.bool_]
    excluded_by_rule: dict[str, int]
    dataset_status_excluded: int


def _float_column(rows: Sequence[Mapping[str, str]], name: str) -> NDArray[np.float64]:
    try:
        values = np.asarray([float(row[name]) for row in rows], dtype=float)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Column {name} must contain finite numeric values") from error
    if np.any(~np.isfinite(values)):
        raise ValueError(f"Column {name} contains non-finite values")
    return _readonly(values)


def load_eq_dataset(path: str | Path, intensity_domain: str) -> EQDataset:
    """Load linear pre-display numerical data; rendered/log-map data fail closed."""

    source = Path(path).expanduser().resolve()
    if intensity_domain != "LINEAR_PRE_DISPLAY":
        raise ValueError("intensity_domain must be LINEAR_PRE_DISPLAY; log/display data are forbidden")
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        rows = tuple(dict(row) for row in reader)
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise ValueError(f"Prepared E-Q table is missing required columns: {missing}")
    forbidden = sorted(FORBIDDEN_DISPLAY_COLUMNS.intersection(columns))
    if forbidden:
        raise ValueError(f"Display/log intensity columns are forbidden fitting inputs: {forbidden}")
    if not rows:
        raise ValueError("Prepared E-Q table contains no numerical rows")
    point_ids = tuple(row["point_id"].strip() for row in rows)
    if any(not value for value in point_ids) or len(point_ids) != len(set(point_ids)):
        raise ValueError("point_id must be non-empty and unique")
    energy = _float_column(rows, "energy_meV")
    q = _float_column(rows, "Q_Ainv")
    intensity = _float_column(rows, "normalized_intensity")
    if np.any(q <= 0):
        raise ValueError("Q_Ainv must be positive")
    blocks = tuple(row["instrument_block_id"].strip() for row in rows)
    scans = tuple(row["scan_id"].strip() for row in rows)
    statuses = tuple(row["mask_status"].strip() for row in rows)
    normalization = tuple(row["normalization_metadata"].strip() for row in rows)
    if any(not value for value in blocks + scans + statuses + normalization):
        raise ValueError("block, scan, mask status, and normalization metadata must be explicit")
    sigma: NDArray[np.float64] | None = None
    if "normalized_intensity_sigma" in columns:
        raw_sigma = tuple(row["normalized_intensity_sigma"].strip() for row in rows)
        if any(raw_sigma) and not all(raw_sigma):
            raise ValueError("normalized_intensity_sigma must be present for every row or none")
        if all(raw_sigma):
            sigma = _float_column(rows, "normalized_intensity_sigma")
            if np.any(sigma <= 0):
                raise ValueError("normalized_intensity_sigma must be positive")
    constraint_classes = tuple(
        (row.get("constraint_class") or "SPECTRAL_SHAPE_CONSTRAINT").strip()
        for row in rows
    )
    invalid_classes = sorted(set(constraint_classes) - CONSTRAINT_CLASSES)
    if invalid_classes:
        raise ValueError(f"Unknown constraint_class values: {invalid_classes}")
    feature_ids = tuple(
        tuple(value for value in (row.get("feature_id") or "").split(";") if value)
        for row in rows
    )
    qhat_columns = ("qhat_direct_x", "qhat_direct_y", "qhat_direct_z")
    qhat_present = [name in columns for name in qhat_columns]
    if any(qhat_present) and not all(qhat_present):
        raise ValueError("All three qhat_direct columns must be present together")
    qhat: NDArray[np.float64] | None = None
    if all(qhat_present):
        qhat = np.column_stack([_float_column(rows, name) for name in qhat_columns])
        norms = np.linalg.norm(qhat, axis=1)
        if np.any(norms <= 0):
            raise ValueError("qhat_direct vectors must be non-zero")
        qhat = _readonly(qhat / norms[:, None])

    def optional_numeric(name: str) -> NDArray[np.float64] | None:
        if name not in columns:
            return None
        raw = tuple(row[name].strip() for row in rows)
        if not any(raw):
            return None
        if not all(raw):
            raise ValueError(f"{name} must be present for every row or none")
        return _float_column(rows, name)

    ei = optional_numeric("Ei_meV")
    ef = optional_numeric("Ef_meV")
    if (ei is None) != (ef is None):
        raise ValueError("Ei_meV and Ef_meV must be present together")
    if ei is not None and (np.any(ei <= 0) or np.any(ef <= 0)):
        raise ValueError("Ei_meV and Ef_meV must be positive")
    temperature = optional_numeric("temperature_K_if_verified")
    if temperature is not None and np.any(temperature <= 0):
        raise ValueError("temperature_K_if_verified must be positive")

    def optional_text(name: str, default: str) -> tuple[str, ...]:
        return tuple((row.get(name) or default).strip() for row in rows)

    return EQDataset(
        path=source,
        sha256=sha256_file(source),
        point_ids=point_ids,
        energy_meV=energy,
        q_ainv=q,
        intensity=intensity,
        sigma=sigma,
        blocks=blocks,
        scan_ids=scans,
        mask_status=statuses,
        normalization_metadata=normalization,
        constraint_classes=constraint_classes,
        feature_ids=feature_ids,
        qhat_direct=qhat,
        ei_meV=ei,
        ef_meV=ef,
        temperature_K=temperature,
        temperature_status=optional_text("temperature_status", "NOT_RECORDED"),
        discovery_holdout_role=optional_text("discovery_holdout_role", "UNSPECIFIED"),
        count_control_mode=optional_text("count_control_mode", "UNSPECIFIED"),
        normalization_groups=optional_text(
            "normalization_compatibility_group_id", "UNSPECIFIED"
        ),
        lattice_state_ids=optional_text("lattice_state_id", "UNSPECIFIED"),
        ub_state_ids=optional_text("UB_state_id", "UNSPECIFIED"),
        columns=columns,
    )


def load_mask_definition(path: str | Path) -> MaskDefinition:
    source = Path(path).expanduser().resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not payload.get("mask_id"):
        raise ValueError("Mask file must define mask_id")
    rules: list[MaskRule] = []
    for raw in payload.get("rules", []):
        if not isinstance(raw, Mapping):
            raise ValueError("Each mask rule must be a mapping")
        reserved = {"rule_id", "kind", "reason", "enabled"}
        rules.append(
            MaskRule(
                rule_id=str(raw["rule_id"]),
                kind=str(raw["kind"]),
                reason=str(raw["reason"]),
                enabled=bool(raw.get("enabled", True)),
                parameters={str(key): value for key, value in raw.items() if key not in reserved},
            )
        )
    identifiers = [rule.rule_id for rule in rules]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Mask rule_id values must be unique")
    return MaskDefinition(source, sha256_file(source), str(payload["mask_id"]), tuple(rules))


def _rule_selection(dataset: EQDataset, rule: MaskRule) -> NDArray[np.bool_]:
    parameters = rule.parameters
    if rule.kind == "ENERGY_RANGE":
        return (dataset.energy_meV >= float(parameters["min_meV"])) & (
            dataset.energy_meV <= float(parameters["max_meV"])
        )
    if rule.kind == "Q_RANGE":
        return (dataset.q_ainv >= float(parameters["min_Ainv"])) & (
            dataset.q_ainv <= float(parameters["max_Ainv"])
        )
    if rule.kind == "RECTANGLE":
        return (
            (dataset.energy_meV >= float(parameters["energy_min_meV"]))
            & (dataset.energy_meV <= float(parameters["energy_max_meV"]))
            & (dataset.q_ainv >= float(parameters["q_min_Ainv"]))
            & (dataset.q_ainv <= float(parameters["q_max_Ainv"]))
        )
    if rule.kind == "MASK_STATUS":
        values = {str(value) for value in parameters["values"]}
        return np.asarray([status in values for status in dataset.mask_status], dtype=bool)
    raise ValueError(f"Unsupported mask rule kind: {rule.kind}")


def apply_masks(dataset: EQDataset, definition: MaskDefinition) -> AppliedMask:
    """Apply only the immutable, version-controlled mask definition."""

    include = np.asarray([status == "INCLUDE" for status in dataset.mask_status], dtype=bool)
    dataset_excluded = int(np.count_nonzero(~include))
    excluded_by_rule: dict[str, int] = {}
    for rule in definition.rules:
        if not rule.enabled:
            excluded_by_rule[rule.rule_id] = 0
            continue
        selection = _rule_selection(dataset, rule)
        newly_excluded = include & selection
        excluded_by_rule[rule.rule_id] = int(np.count_nonzero(newly_excluded))
        include[newly_excluded] = False
    include = _readonly(include)
    return AppliedMask(include, excluded_by_rule, dataset_excluded)


def _resolve(repository: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else repository / candidate


def audit_eq_dataset(
    config: Mapping[str, Any],
    repository: str | Path,
    materialization_report: Mapping[str, object] | None = None,
) -> dict[str, object]:
    repository_path = Path(repository).resolve()
    inputs = config["inputs"]
    dataset_path = _resolve(repository_path, str(inputs["taipan_eq_dataset"]))
    mask_path = _resolve(repository_path, str(inputs["taipan_mask_definition"]))
    cx02_preflight_path = _resolve(
        repository_path, str(inputs.get("cx02_priority_scan_preflight", ""))
    )
    site_model = config["forward_model"].get("dy_site_intensity", {})
    site_contract_path = _resolve(repository_path, str(site_model.get("contract_path", "")))
    site_contract_hash = (
        sha256_file(site_contract_path) if site_contract_path.is_file() else None
    )
    expected_site_contract_hash = site_model.get("contract_sha256")
    site_status = str(site_model.get("status", "BLOCKED_BY_MISSING_SYMMETRY_DEFINITION"))
    base = {
        "dataset_path": str(dataset_path),
        "dataset_hash": None,
        "mask_path": str(mask_path),
        "mask_hash": sha256_file(mask_path) if mask_path.exists() else None,
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "manuscript_intensity_gate": "FAIL_CLEANLY",
        "exploratory_eq_map_use": "AUTHORIZED",
        "normalization_description": inputs["normalization_description"],
        "background_model": config["forward_model"]["background"]["model"],
        "resolution_model": config["forward_model"]["resolution"]["model"],
        "objective_mode": config["objective"]["mode"],
        "expected_schema": str(_resolve(repository_path, str(inputs["taipan_schema"]))),
        "cx02_priority_scan_preflight": {
            "path": str(cx02_preflight_path),
            "sha256": sha256_file(cx02_preflight_path) if cx02_preflight_path.is_file() else None,
        },
        "source_artifacts": (
            list(materialization_report.get("source_artifacts", []))
            if materialization_report is not None
            else []
        ),
        "temperature_population_model": config["forward_model"]["population"]["mode"],
        "objective_component_definitions": config["objective"].get("component_definitions", {}),
        "objective_component_weights": config["objective"].get("component_weights", {}),
        "resolution_semantics": config["forward_model"]["resolution"],
        "background_semantics": config["forward_model"]["background"],
        "four_dy_site_intensity": {
            **dict(site_model),
            "observed_contract_sha256": site_contract_hash,
        },
    }
    if not dataset_path.exists():
        return {
            **base,
            "status": "NOT_READY",
            "terminal_status": "NOT_READY",
            "blockers": ["PREPARED_NUMERICAL_TAIPAN_EQ_DATASET_MISSING"],
            "number_of_points": 0,
        }
    try:
        dataset = load_eq_dataset(dataset_path, str(inputs["intensity_domain"]))
        masks = load_mask_definition(mask_path)
        applied = apply_masks(dataset, masks)
    except (OSError, ValueError, KeyError) as error:
        return {
            **base,
            "status": "NOT_READY",
            "terminal_status": "NOT_READY",
            "blockers": [str(error)],
        }
    total = dataset.size
    included = int(np.count_nonzero(applied.include))
    uncertainty_status = "AVAILABLE_FOR_ALL_POINTS" if dataset.sigma is not None else "UNAVAILABLE"
    blocks = sorted(set(dataset.blocks))
    normalization_values = sorted(set(dataset.normalization_metadata))
    included_constraint_counts = {
        name: int(
            np.count_nonzero(
                applied.include & (np.asarray(dataset.constraint_classes, dtype=str) == name)
            )
        )
        for name in sorted(CONSTRAINT_CLASSES)
    }
    blockers: list[str] = []
    if site_status != "IMPLEMENTED_AND_TESTED":
        blockers.append("FOUR_DY_SITE_INTENSITY_NOT_IMPLEMENTED_AND_TESTED")
    elif site_contract_hash is None or site_contract_hash != expected_site_contract_hash:
        blockers.append("FOUR_DY_SITE_SYMMETRY_CONTRACT_IDENTITY_MISMATCH")
    temperature_statuses = sorted(set(dataset.temperature_status))
    established_statuses = {"VERIFIED", "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"}
    if len(temperature_statuses) != 1 or temperature_statuses[0] not in established_statuses:
        blockers.append("TEN_K_BLOCK_NOT_REPRODUCIBLY_ESTABLISHED")
    if dataset.temperature_K is None:
        blockers.append("VERIFIED_SAMPLE_TEMPERATURE_VALUES_UNAVAILABLE")
    elif not np.allclose(dataset.temperature_K, 10.0, atol=1.0):
        blockers.append("PREPARED_DATASET_IS_NOT_A_SINGLE_APPROXIMATELY_10_K_BLOCK")
    holdout_points = sum(role == "holdout" for role in dataset.discovery_holdout_role)
    if holdout_points:
        blockers.append("HOLDOUT_POINTS_PRESENT_IN_EXPLORATORY_DATASET")
    if dataset.qhat_direct is None:
        blockers.append("PER_POINT_Q_DIRECTION_UNAVAILABLE__POWDER_FALLBACK_FORBIDDEN")
    count_modes = sorted(set(dataset.count_control_mode))
    if count_modes not in (["monitor_controlled"], ["UNSPECIFIED"]):
        blockers.append("COUNT_CONTROL_MODES_MIXED_OR_NOT_MONITOR_CONTROLLED")
    if included == 0 and "TEN_K_BLOCK_NOT_REPRODUCIBLY_ESTABLISHED" not in blockers:
        blockers.append("MASK_EXCLUDES_ALL_POINTS")
    if len(normalization_values) != 1:
        blockers.append("NORMALIZATION_METADATA_NOT_UNIFORM_OR_EXPLICIT")
    search_blockers: list[str] = []
    if included_constraint_counts["ENERGY_CONSTRAINT"] == 0:
        search_blockers.append("NO_EXPLICIT_FEATURE_ENERGY_ASSIGNMENTS")
    feature_ids = sorted({feature for row in dataset.feature_ids for feature in row})
    selected_temperature_scans = sorted(
        {
            dataset.scan_ids[index]
            for index, status in enumerate(dataset.temperature_status)
            if status in established_statuses
        }
    )
    status = "READY_FOR_EXPLORATORY_SANITY_RUN" if not blockers else "NOT_READY"
    return {
        **base,
        "status": status,
        "terminal_status": status,
        "blockers": blockers,
        "search_blockers": search_blockers,
        "dataset_hash": dataset.sha256,
        "number_of_points": total,
        "included_points": included,
        "energy_range_meV": [float(np.min(dataset.energy_meV)), float(np.max(dataset.energy_meV))],
        "q_range_Ainv": [float(np.min(dataset.q_ainv)), float(np.max(dataset.q_ainv))],
        "number_of_instrument_blocks": len(blocks),
        "instrument_blocks": blocks,
        "mask_fraction": float(1.0 - included / total),
        "mask_counts": {
            "dataset_status": applied.dataset_status_excluded,
            **applied.excluded_by_rule,
        },
        "included_constraint_counts": included_constraint_counts,
        "uncertainty_availability": uncertainty_status,
        "uncertainties_statistically_calibrated": bool(
            inputs.get("uncertainties_statistically_calibrated", False)
        ),
        "qhat_availability": "PER_POINT_DIRECT_B_C_A" if dataset.qhat_direct is not None else "UNAVAILABLE",
        "q_direction_status": "PER_POINT_DIRECT_B_C_A" if dataset.qhat_direct is not None else "UNAVAILABLE",
        "normalization_metadata_values": normalization_values,
        "normalization_groups": sorted(set(dataset.normalization_groups)),
        "count_control_modes": count_modes,
        "discovery_points": sum(role == "discovery" for role in dataset.discovery_holdout_role),
        "holdout_points_used": holdout_points,
        "holdout_detector_access_count": int(
            materialization_report.get("holdout_detector_access_count", 0)
            if materialization_report is not None
            else 0
        ),
        "ten_k_block_status": temperature_statuses[0] if len(temperature_statuses) == 1 else "MIXED",
        "selected_ten_k_scan_ids": selected_temperature_scans,
        "ten_k_scan_ids_source": (
            materialization_report.get("ten_k_scan_ids_source")
            if materialization_report is not None
            else None
        ),
        "lattice_states": sorted(set(dataset.lattice_state_ids)),
        "ub_states": sorted(set(dataset.ub_state_ids)),
        "blind_feature_windows_represented": feature_ids,
        "blind_feature_windows": (
            list(materialization_report.get("blind_feature_windows", []))
            if materialization_report is not None
            else []
        ),
        "feature_overlaps": (
            list(materialization_report.get("feature_overlaps", []))
            if materialization_report is not None
            else []
        ),
    }
