"""Reviewed feature-table parsing and deterministic explicit assignments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Mapping

import yaml

from .provenance import sha256_file


ALLOWED_FIT_ROLES = frozenset(
    {
        "ACTIVE_CEF_FEATURE",
        "SHAPE_ONLY",
        "RELATIVE_INTENSITY_ONLY",
        "DIAGNOSTIC_ONLY",
        "EXCLUDED",
    }
)


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    fit_role: str
    energy_min_meV: float
    energy_max_meV: float
    penalty_scale_meV: float
    point_count: int
    ten_k_scan_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class AssignmentHypothesis:
    assignment_id: str
    mappings: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_feature_table(path: str | Path) -> tuple[FeatureDefinition, ...]:
    """Load a complete BF-001..BF-008 table and fail closed on ambiguity."""

    source = Path(path).expanduser().resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("feature_table_id") != (
        "MANUSCRIPT_CEF_FIT_FEATURE_TABLE_V1"
    ):
        raise ValueError("Unexpected feature-table identity")
    rows = payload.get("features")
    if not isinstance(rows, list):
        raise ValueError("feature table must contain a features list")
    features: list[FeatureDefinition] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Each feature-table row must be a mapping")
        role = str(row["fit_role"])
        if role not in ALLOWED_FIT_ROLES:
            raise ValueError(f"Unsupported feature fit role: {role}")
        window = tuple(map(float, row["discovery_window_meV"]))
        if len(window) != 2 or not window[0] < window[1]:
            raise ValueError("Feature discovery_window_meV must satisfy min < max")
        scale = float(row["window_penalty_scale_meV"])
        count = int(row["point_count"])
        if scale <= 0 or count < 0:
            raise ValueError("Feature energy scale must be positive and point count non-negative")
        features.append(
            FeatureDefinition(
                feature_id=str(row["feature_id"]),
                fit_role=role,
                energy_min_meV=window[0],
                energy_max_meV=window[1],
                penalty_scale_meV=scale,
                point_count=count,
                ten_k_scan_record_ids=tuple(map(str, row.get("ten_k_scan_record_ids", ()))),
            )
        )
    expected = tuple(f"BF-{index:03d}" for index in range(1, 9))
    observed = tuple(feature.feature_id for feature in features)
    if observed != expected:
        raise ValueError(f"Feature table must list {expected}, observed {observed}")
    if any(feature.fit_role == "ACTIVE_CEF_FEATURE" and feature.point_count == 0 for feature in features):
        raise ValueError("An ACTIVE_CEF_FEATURE must have 10-K point support")
    return tuple(features)


def enumerate_assignment_hypotheses(
    features: tuple[FeatureDefinition, ...],
    *,
    final_doublets: tuple[int, ...] = tuple(range(1, 8)),
) -> tuple[AssignmentHypothesis, ...]:
    """Enumerate ordered, one-to-one D0-to-Dj branches without nearest matching."""

    active = sorted(
        (feature for feature in features if feature.fit_role == "ACTIVE_CEF_FEATURE"),
        key=lambda feature: (
            0.5 * (feature.energy_min_meV + feature.energy_max_meV),
            feature.feature_id,
        ),
    )
    if not active:
        raise ValueError("Feature table contains no ACTIVE_CEF_FEATURE")
    finals = tuple(sorted(map(int, final_doublets)))
    if any(value < 1 or value > 7 for value in finals) or len(finals) != len(set(finals)):
        raise ValueError("final_doublets must be unique members of D1..D7")
    if len(active) > len(finals):
        raise ValueError("More active features than available final doublets")
    hypotheses: list[AssignmentHypothesis] = []
    for selected in combinations(finals, len(active)):
        mappings = tuple(
            {
                "feature_id": feature.feature_id,
                "initial_doublet": 0,
                "final_doublet": final,
                "energy_window_min_meV": feature.energy_min_meV,
                "energy_window_max_meV": feature.energy_max_meV,
                "penalty_scale_meV": feature.penalty_scale_meV,
                "penalty_semantics": "DISCOVERY_WINDOW_CONTAINMENT_PENALTY",
            }
            for feature, final in zip(active, selected, strict=True)
        )
        identifier = "ASSIGN__" + "__".join(
            f"{feature.feature_id.replace('-', '')}_D0-D{final}"
            for feature, final in zip(active, selected, strict=True)
        )
        hypotheses.append(AssignmentHypothesis(identifier, mappings))
    return tuple(hypotheses)


def feature_table_identity(path: str | Path) -> dict[str, str]:
    source = Path(path).expanduser().resolve()
    return {"path": str(source), "sha256": sha256_file(source)}


def discovery_window_containment_penalty(
    calculated_energy_meV: float,
    energy_min_meV: float,
    energy_max_meV: float,
    penalty_scale_meV: float,
) -> tuple[float, float]:
    """Return a continuous outside-window loss and distance to the window."""

    calculated = float(calculated_energy_meV)
    lower = float(energy_min_meV)
    upper = float(energy_max_meV)
    scale = float(penalty_scale_meV)
    if not lower < upper or scale <= 0:
        raise ValueError("Window must satisfy min < max and penalty scale must be positive")
    if calculated < lower:
        distance = lower - calculated
    elif calculated > upper:
        distance = calculated - upper
    else:
        distance = 0.0
    return (distance / scale) ** 2, distance
