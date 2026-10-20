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
    "exposure_s",
    "h_pbnm",
    "k_pbnm",
    "l_pbnm",
    "qhat_direct_x",
    "qhat_direct_y",
    "qhat_direct_z",
    "background_metadata",
    "constraint_class",
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
    qhat_direct: NDArray[np.float64] | None
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
        qhat_direct=qhat,
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


def audit_eq_dataset(config: Mapping[str, Any], repository: str | Path) -> dict[str, object]:
    repository_path = Path(repository).resolve()
    inputs = config["inputs"]
    dataset_path = _resolve(repository_path, str(inputs["taipan_eq_dataset"]))
    mask_path = _resolve(repository_path, str(inputs["taipan_mask_definition"]))
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
    }
    if not dataset_path.exists():
        return {
            **base,
            "status": "NOT_READY",
            "blockers": ["PREPARED_NUMERICAL_TAIPAN_EQ_DATASET_MISSING"],
            "number_of_points": 0,
        }
    try:
        dataset = load_eq_dataset(dataset_path, str(inputs["intensity_domain"]))
        masks = load_mask_definition(mask_path)
        applied = apply_masks(dataset, masks)
    except (OSError, ValueError, KeyError) as error:
        return {**base, "status": "NOT_READY", "blockers": [str(error)]}
    total = dataset.size
    included = int(np.count_nonzero(applied.include))
    uncertainty_status = "AVAILABLE_FOR_ALL_POINTS" if dataset.sigma is not None else "UNAVAILABLE"
    blocks = sorted(set(dataset.blocks))
    normalization_values = sorted(set(dataset.normalization_metadata))
    blockers: list[str] = []
    if included == 0:
        blockers.append("MASK_EXCLUDES_ALL_POINTS")
    included_constraint_counts = {
        name: int(
            np.count_nonzero(
                applied.include & (np.asarray(dataset.constraint_classes, dtype=str) == name)
            )
        )
        for name in sorted(CONSTRAINT_CLASSES)
    }
    if included_constraint_counts["ENERGY_CONSTRAINT"] == 0:
        blockers.append("NO_INCLUDED_ENERGY_CONSTRAINT_ROWS_FOR_ASSIGNMENT_BRANCHES")
    if len(normalization_values) != 1:
        blockers.append("NORMALIZATION_METADATA_NOT_UNIFORM_OR_EXPLICIT")
    return {
        **base,
        "status": "READY_FOR_EXPLORATORY_SEARCH" if not blockers else "NOT_READY",
        "blockers": blockers,
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
        "qhat_availability": "PER_POINT" if dataset.qhat_direct is not None else "POWDER_AVERAGE",
        "normalization_metadata_values": normalization_values,
    }
