"""Explicit feature, exploratory E-Q, and disabled manuscript objectives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike

from .background_model import BACKGROUND_SEMANTICS, profile_signal_and_background
from .eq_data import CONSTRAINT_CLASSES, EQDataset
from .normalization_nuisance import profile_block_scales
from .objectives import energy_deviance


class INSObjectiveMode(str, Enum):
    FEATURE_OBJECTIVE = "FEATURE_OBJECTIVE"
    EQ_MAP_EXPLORATORY_OBJECTIVE = "EQ_MAP_EXPLORATORY_OBJECTIVE"
    MANUSCRIPT_OBJECTIVE = "MANUSCRIPT_OBJECTIVE"


@dataclass(frozen=True)
class INSObjectiveResult:
    mode: str
    energy_constraint: float
    spectral_shape_constraint: float
    exploratory_relative_intensity_constraint: float
    total: float
    loss_interpretation: str
    block_scales: dict[str, float]
    background_parameters: dict[str, tuple[float, ...]]
    nuisance_boundary_blocks: tuple[str, ...]
    raw_components: dict[str, float]
    normalized_components: dict[str, float]
    component_weights: dict[str, float]
    included_points_by_class: dict[str, int]
    included_points_by_feature: dict[str, int]
    residuals: tuple[float, ...]
    normalized_residuals: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def feature_objective(
    calculated_energies_meV: Sequence[float],
    observed_energies_meV: Sequence[float],
    sigma_meV: Sequence[float],
) -> INSObjectiveResult:
    value = energy_deviance(calculated_energies_meV, observed_energies_meV, sigma_meV)
    residuals = tuple(
        (np.asarray(calculated_energies_meV) - np.asarray(observed_energies_meV))
        / np.asarray(sigma_meV)
    )
    return INSObjectiveResult(
        mode=INSObjectiveMode.FEATURE_OBJECTIVE.value,
        energy_constraint=value,
        spectral_shape_constraint=0.0,
        exploratory_relative_intensity_constraint=0.0,
        total=value,
        loss_interpretation="FEATURE_LEVEL_DEVIANCE",
        block_scales={},
        background_parameters={},
        nuisance_boundary_blocks=(),
        raw_components={"L_energy": value, "L_shape": 0.0, "L_relative_intensity": 0.0},
        normalized_components={"L_energy": value, "L_shape": 0.0, "L_relative_intensity": 0.0},
        component_weights={"energy": 1.0, "shape": 0.0, "relative_intensity": 0.0},
        included_points_by_class={"ENERGY_CONSTRAINT": len(residuals)},
        included_points_by_feature={},
        residuals=tuple(map(float, residuals)),
        normalized_residuals=tuple(map(float, residuals)),
    )


def eq_map_exploratory_objective(
    dataset: EQDataset,
    include_mask: ArrayLike,
    calculated_unscaled: ArrayLike,
    config: Mapping[str, object],
    *,
    background_config: Mapping[str, object] | None = None,
) -> INSObjectiveResult:
    """Evaluate linear prepared intensities without claiming calibrated chi-square."""

    include = np.asarray(include_mask, dtype=bool)
    calculated = np.asarray(calculated_unscaled, dtype=float)
    if include.shape != (dataset.size,) or calculated.shape != (dataset.size,):
        raise ValueError("Mask and calculation must match the E-Q dataset")
    if not np.any(include):
        raise ValueError("At least one E-Q point must remain included")
    use_sigma = bool(config.get("uncertainties_statistically_calibrated", False))
    sigma = dataset.sigma if use_sigma else None
    bounds = tuple(map(float, config.get("nuisance_scale_bounds", [1.0e-6, 1.0e6])))
    background_parameters: dict[str, tuple[float, ...]] = {}
    if background_config is not None and str(background_config.get("model")) in BACKGROUND_SEMANTICS:
        profiled = profile_signal_and_background(
            dataset.intensity,
            calculated,
            dataset.energy_meV,
            dataset.q_ainv,
            dataset.blocks,
            include,
            background_config,
            sigma=sigma,
            scale_bounds=(bounds[0], bounds[1]),
        )
        fitted = profiled.fitted
        block_scales = profiled.signal_scales
        boundary_blocks = profiled.nuisance_boundary_blocks
        background_parameters = profiled.background_parameters
    else:
        scales = profile_block_scales(
            calculated,
            dataset.intensity,
            dataset.blocks,
            include,
            sigma=sigma,
            bounds=(bounds[0], bounds[1]),
        )
        fitted = scales.fitted
        block_scales = scales.scales
        boundary_blocks = scales.boundary_blocks
    denominator = dataset.sigma if use_sigma and dataset.sigma is not None else np.ones(dataset.size)
    residual = (dataset.intensity - fitted) / denominator
    residual = np.where(include, residual, 0.0)
    raw_by_class: dict[str, float] = {name: 0.0 for name in CONSTRAINT_CLASSES}
    normalized_by_class: dict[str, float] = {name: 0.0 for name in CONSTRAINT_CLASSES}
    counts: dict[str, int] = {name: 0 for name in CONSTRAINT_CLASSES}
    normalized_residual = np.zeros(dataset.size, dtype=float)
    classes = np.asarray(dataset.constraint_classes, dtype=str)
    for name in CONSTRAINT_CLASSES:
        selected = include & (classes == name)
        count = int(np.count_nonzero(selected))
        counts[name] = count
        if count == 0:
            continue
        raw_by_class[name] = float(np.sum(np.square(residual[selected])))
        if use_sigma and dataset.sigma is not None:
            scale = 1.0
        else:
            scale = max(float(np.sqrt(np.mean(np.square(dataset.intensity[selected])))), 1.0e-15)
        normalized_residual[selected] = residual[selected] / scale
        normalized_by_class[name] = float(np.mean(np.square(normalized_residual[selected])))
    # Shape is normalized inside each represented feature, then averaged across
    # features. This prevents broad windows or dense scans from dominating only
    # because they contain more points. Overlapping reviewed windows remain
    # visible as separate shape diagnostics but are not treated as energy levels.
    shape_feature_losses: list[float] = []
    shape_raw = 0.0
    shape_selected = include & (classes == "SPECTRAL_SHAPE_CONSTRAINT")
    represented = sorted(
        {
            feature
            for index, identifiers in enumerate(dataset.feature_ids)
            if shape_selected[index]
            for feature in identifiers
        }
    )
    for feature in represented:
        selected = shape_selected & np.asarray(
            [feature in identifiers for identifiers in dataset.feature_ids], dtype=bool
        )
        if not np.any(selected):
            continue
        scale = max(float(np.sqrt(np.mean(np.square(dataset.intensity[selected])))), 1.0e-15)
        values = residual[selected] / scale
        shape_raw += float(np.sum(np.square(residual[selected])))
        shape_feature_losses.append(float(np.mean(np.square(values))))
    if shape_feature_losses:
        raw_by_class["SPECTRAL_SHAPE_CONSTRAINT"] = shape_raw
        normalized_by_class["SPECTRAL_SHAPE_CONSTRAINT"] = float(
            np.mean(shape_feature_losses)
        )
    # Relative spectral weight is normalized within accepted normalization
    # blocks and averaged over blocks, never with a free scale per scan.
    relative_selected = include & (
        classes == "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT"
    )
    relative_block_losses: list[float] = []
    for block in sorted(set(np.asarray(dataset.blocks, dtype=str)[relative_selected])):
        selected = relative_selected & (np.asarray(dataset.blocks, dtype=str) == block)
        scale = max(float(np.sqrt(np.mean(np.square(dataset.intensity[selected])))), 1.0e-15)
        relative_block_losses.append(float(np.mean(np.square(residual[selected] / scale))))
    if relative_block_losses:
        normalized_by_class["EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT"] = float(
            np.mean(relative_block_losses)
        )
    labels = {
        "ENERGY_CONSTRAINT": "L_energy",
        "SPECTRAL_SHAPE_CONSTRAINT": "L_shape",
        "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT": "L_relative_intensity",
    }
    raw_components = {labels[name]: raw_by_class[name] for name in labels}
    normalized_components = {labels[name]: normalized_by_class[name] for name in labels}
    configured_weights = config.get("component_weights", {})
    if not isinstance(configured_weights, Mapping):
        raise ValueError("objective.component_weights must be a mapping")
    weight_to_component = {
        "energy": "L_energy",
        "shape": "L_shape",
        "relative_intensity": "L_relative_intensity",
    }
    unknown_weights = sorted(set(configured_weights) - set(weight_to_component))
    if unknown_weights:
        raise ValueError(f"Unknown objective component weights: {unknown_weights}")
    component_weights = {
        name: float(configured_weights.get(name, 1.0)) for name in weight_to_component
    }
    if any(not np.isfinite(value) or value < 0 for value in component_weights.values()):
        raise ValueError("Objective component weights must be finite and non-negative")
    total = float(
        sum(
            component_weights[weight]
            * normalized_components[component]
            for weight, component in weight_to_component.items()
        )
    )
    feature_counts: dict[str, int] = {}
    for index, identifiers in enumerate(dataset.feature_ids):
        if not include[index]:
            continue
        for identifier in identifiers:
            feature_counts[identifier] = feature_counts.get(identifier, 0) + 1
    interpretation = (
        "CALIBRATED_GAUSSIAN_CHI_SQUARE"
        if use_sigma and dataset.sigma is not None
        else "EXPLORATORY_WEIGHTED_LOSS_NOT_STATISTICAL_CHI_SQUARE"
    )
    return INSObjectiveResult(
        mode=INSObjectiveMode.EQ_MAP_EXPLORATORY_OBJECTIVE.value,
        energy_constraint=normalized_components["L_energy"],
        spectral_shape_constraint=normalized_components["L_shape"],
        exploratory_relative_intensity_constraint=normalized_components["L_relative_intensity"],
        total=total,
        loss_interpretation=interpretation,
        block_scales=block_scales,
        background_parameters=background_parameters,
        nuisance_boundary_blocks=boundary_blocks,
        raw_components=raw_components,
        normalized_components=normalized_components,
        component_weights=component_weights,
        included_points_by_class=counts,
        included_points_by_feature=dict(sorted(feature_counts.items())),
        residuals=tuple(map(float, residual)),
        normalized_residuals=tuple(map(float, normalized_residual)),
    )


def require_objective_mode(mode: str, manuscript_enabled: bool = False) -> INSObjectiveMode:
    parsed = INSObjectiveMode(mode)
    if parsed is INSObjectiveMode.MANUSCRIPT_OBJECTIVE and not manuscript_enabled:
        raise PermissionError(
            "MANUSCRIPT_OBJECTIVE is disabled: exploratory intensities are not manuscript-admitted"
        )
    return parsed


def joint_mh_interface(
    ins_deviance: float,
    mh_deviance: float,
    lambda_m: float,
    *,
    enabled: bool,
    accepted_bulk_contribution_model: str | None,
) -> float:
    """Future joint interface; fails closed without the independent policy gate."""

    if not enabled:
        raise PermissionError("ENABLE_JOINT_MH_FIT is false")
    if not accepted_bulk_contribution_model:
        raise PermissionError("An accepted Fe/Dy-Fe bulk contribution model is required")
    values = np.asarray([ins_deviance, mh_deviance, lambda_m], dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("Joint-objective terms and weight must be finite and non-negative")
    return float(ins_deviance + lambda_m * mh_deviance)
