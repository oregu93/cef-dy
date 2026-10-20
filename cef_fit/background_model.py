"""Visible, configurable backgrounds for the exploratory E-Q objective."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray


BACKGROUND_SEMANTICS = frozenset(
    {
        "DATASET_ALREADY_BACKGROUND_SUBTRACTED",
        "LOCAL_LINEAR_BACKGROUND",
        "LOCAL_SMOOTH_BACKGROUND",
    }
)


@dataclass(frozen=True)
class ProfiledBackgroundResult:
    fitted: NDArray[np.float64]
    background: NDArray[np.float64]
    signal_scales: dict[str, float]
    background_parameters: dict[str, tuple[float, ...]]
    nuisance_boundary_blocks: tuple[str, ...]


def evaluate_background(
    energy_meV: ArrayLike,
    q_ainv: ArrayLike,
    config: Mapping[str, object],
) -> NDArray[np.float64]:
    energy = np.asarray(energy_meV, dtype=float)
    q = np.asarray(q_ainv, dtype=float)
    if energy.shape != q.shape:
        raise ValueError("energy and Q arrays must have the same shape")
    model = str(config.get("model", "CONSTANT"))
    if model in {"LOCAL_LINEAR_BACKGROUND", "LOCAL_SMOOTH_BACKGROUND"} and bool(
        config.get("profile_in_objective", False)
    ):
        # The forward-only stage displays the physical CEF signal. The additive
        # nuisance is determined from data only inside the objective stage.
        return np.zeros(energy.shape, dtype=float)
    if model == "DATASET_ALREADY_BACKGROUND_SUBTRACTED":
        if not bool(config.get("verified_background_subtracted", False)):
            raise ValueError("Background-subtracted semantics require explicit verification")
        return np.zeros(energy.shape, dtype=float)
    coefficients = config.get("coefficients", {})
    if not isinstance(coefficients, Mapping):
        raise ValueError("background.coefficients must be a mapping")
    constant = float(coefficients.get("constant", 0.0))
    if model == "CONSTANT":
        result = np.full(energy.shape, constant)
    elif model == "LINEAR_ENERGY":
        energy_reference = float(coefficients.get("energy_reference_meV", 0.0))
        result = constant + float(coefficients.get("energy_slope", 0.0)) * (
            energy - energy_reference
        )
    elif model == "SMOOTH_Q_ENERGY":
        energy_reference = float(coefficients.get("energy_reference_meV", 0.0))
        q_reference = float(coefficients.get("q_reference_Ainv", 0.0))
        result = (
            constant
            + float(coefficients.get("energy_slope", 0.0)) * (energy - energy_reference)
            + float(coefficients.get("q_slope", 0.0)) * (q - q_reference)
            + float(coefficients.get("q_quadratic", 0.0)) * (q - q_reference) ** 2
        )
    else:
        raise ValueError(f"Unsupported background model: {model}")
    if bool(config.get("clip_nonnegative", True)):
        result = np.maximum(result, 0.0)
    if np.any(~np.isfinite(result)):
        raise ValueError("Background model produced non-finite values")
    return np.asarray(result, dtype=float)


def profile_signal_and_background(
    observed: ArrayLike,
    signal_unscaled: ArrayLike,
    energy_meV: ArrayLike,
    q_ainv: ArrayLike,
    blocks: Sequence[str],
    include_mask: ArrayLike,
    config: Mapping[str, object],
    *,
    sigma: ArrayLike | None = None,
    scale_bounds: tuple[float, float] = (1.0e-6, 1.0e6),
) -> ProfiledBackgroundResult:
    """Profile one signal scale and an explicit smooth background per block."""

    observed_values = np.asarray(observed, dtype=float)
    signal = np.asarray(signal_unscaled, dtype=float)
    energy = np.asarray(energy_meV, dtype=float)
    q = np.asarray(q_ainv, dtype=float)
    include = np.asarray(include_mask, dtype=bool)
    block_values = np.asarray(tuple(blocks), dtype=str)
    if not (
        observed_values.shape
        == signal.shape
        == energy.shape
        == q.shape
        == include.shape
        == block_values.shape
    ):
        raise ValueError("Background profiling inputs must have matching shapes")
    model = str(config.get("model"))
    if model not in BACKGROUND_SEMANTICS:
        raise ValueError(f"Unsupported background semantics for profiling: {model}")
    weights = np.ones(signal.shape, dtype=float)
    if sigma is not None:
        sigma_values = np.asarray(sigma, dtype=float)
        if sigma_values.shape != signal.shape or np.any(sigma_values[include] <= 0):
            raise ValueError("sigma must match and be positive for included points")
        weights[include] = 1.0 / np.square(sigma_values[include])
    lower, upper = map(float, scale_bounds)
    if not 0 < lower < upper:
        raise ValueError("scale_bounds must satisfy 0 < lower < upper")
    fitted = np.zeros_like(signal)
    background = np.zeros_like(signal)
    scales: dict[str, float] = {}
    parameters: dict[str, tuple[float, ...]] = {}
    boundary: list[str] = []
    for block in sorted(set(block_values[include])):
        selected = include & (block_values == block)
        e_scale = max(float(np.ptp(energy[selected])), 1.0)
        q_scale = max(float(np.ptp(q[selected])), 1.0)
        e0 = float(np.mean(energy[selected]))
        q0 = float(np.mean(q[selected]))
        columns = [signal[selected]]
        if model == "LOCAL_LINEAR_BACKGROUND":
            columns.extend([np.ones(np.count_nonzero(selected)), (energy[selected] - e0) / e_scale])
        elif model == "LOCAL_SMOOTH_BACKGROUND":
            e_normal = (energy[selected] - e0) / e_scale
            q_normal = (q[selected] - q0) / q_scale
            columns.extend([np.ones(np.count_nonzero(selected)), e_normal, e_normal**2, q_normal, q_normal**2])
        design = np.column_stack(columns)
        root_weight = np.sqrt(weights[selected])
        coefficients, *_ = np.linalg.lstsq(
            design * root_weight[:, None], observed_values[selected] * root_weight, rcond=None
        )
        signal_scale = float(np.clip(coefficients[0], lower, upper))
        if signal_scale != float(coefficients[0]):
            background_design = design[:, 1:]
            if background_design.shape[1]:
                background_coefficients, *_ = np.linalg.lstsq(
                    background_design * root_weight[:, None],
                    (observed_values[selected] - signal_scale * signal[selected]) * root_weight,
                    rcond=None,
                )
            else:
                background_coefficients = np.empty(0)
        else:
            background_coefficients = coefficients[1:]
        block_background = (
            design[:, 1:] @ background_coefficients
            if background_coefficients.size
            else np.zeros(np.count_nonzero(selected))
        )
        if bool(config.get("clip_nonnegative", False)):
            block_background = np.maximum(block_background, 0.0)
        fitted[selected] = signal_scale * signal[selected] + block_background
        background[selected] = block_background
        scales[str(block)] = signal_scale
        parameters[str(block)] = tuple(map(float, background_coefficients))
        margin = 1.0e-10 * max(1.0, upper - lower)
        if signal_scale - lower <= margin or upper - signal_scale <= margin:
            boundary.append(str(block))
    for values in (fitted, background):
        values.setflags(write=False)
    return ProfiledBackgroundResult(
        fitted=fitted,
        background=background,
        signal_scales=scales,
        background_parameters=parameters,
        nuisance_boundary_blocks=tuple(boundary),
    )
