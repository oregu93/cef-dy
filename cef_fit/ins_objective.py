"""Explicit feature, exploratory E-Q, and disabled manuscript objectives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike

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
    nuisance_boundary_blocks: tuple[str, ...]
    residuals: tuple[float, ...]

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
        nuisance_boundary_blocks=(),
        residuals=tuple(map(float, residuals)),
    )


def eq_map_exploratory_objective(
    dataset: EQDataset,
    include_mask: ArrayLike,
    calculated_unscaled: ArrayLike,
    config: Mapping[str, object],
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
    scales = profile_block_scales(
        calculated,
        dataset.intensity,
        dataset.blocks,
        include,
        sigma=sigma,
        bounds=(bounds[0], bounds[1]),
    )
    denominator = dataset.sigma if use_sigma and dataset.sigma is not None else np.ones(dataset.size)
    residual = (dataset.intensity - scales.fitted) / denominator
    residual = np.where(include, residual, 0.0)
    components: dict[str, float] = {name: 0.0 for name in CONSTRAINT_CLASSES}
    classes = np.asarray(dataset.constraint_classes, dtype=str)
    for name in CONSTRAINT_CLASSES:
        selected = include & (classes == name)
        components[name] = float(np.sum(np.square(residual[selected])))
    total = float(sum(components.values()))
    interpretation = (
        "CALIBRATED_GAUSSIAN_CHI_SQUARE"
        if use_sigma and dataset.sigma is not None
        else "EXPLORATORY_WEIGHTED_LOSS_NOT_STATISTICAL_CHI_SQUARE"
    )
    return INSObjectiveResult(
        mode=INSObjectiveMode.EQ_MAP_EXPLORATORY_OBJECTIVE.value,
        energy_constraint=components["ENERGY_CONSTRAINT"],
        spectral_shape_constraint=components["SPECTRAL_SHAPE_CONSTRAINT"],
        exploratory_relative_intensity_constraint=components[
            "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT"
        ],
        total=total,
        loss_interpretation=interpretation,
        block_scales=scales.scales,
        nuisance_boundary_blocks=scales.boundary_blocks,
        residuals=tuple(map(float, residual)),
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
