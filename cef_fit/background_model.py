"""Visible, configurable backgrounds for the exploratory E-Q objective."""

from __future__ import annotations

from typing import Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray


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
