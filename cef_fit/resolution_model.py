"""Explicit energy-resolution kernels for the exploratory E-Q model."""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray


FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))


def resolution_sigma_meV(
    transition_energy_meV: ArrayLike,
    config: Mapping[str, object],
) -> NDArray[np.float64]:
    """Evaluate a fixed or quadrature-linear Gaussian width model."""

    energy = np.asarray(transition_energy_meV, dtype=float)
    model = str(config.get("model", "GAUSSIAN_FIXED_FWHM"))
    if model == "GAUSSIAN_FIXED_FWHM":
        fwhm = float(config["fwhm_meV"])
        sigma = np.full(energy.shape, fwhm * FWHM_TO_SIGMA)
    elif model == "GAUSSIAN_QUADRATURE_FWHM":
        intercept = float(config["fwhm_intercept_meV"])
        slope = float(config["fwhm_slope_sqrt_meV"])
        fwhm = np.sqrt(intercept**2 + slope**2 * np.maximum(energy, 0.0))
        sigma = fwhm * FWHM_TO_SIGMA
    else:
        raise ValueError(f"Unsupported resolution model: {model}")
    if np.any(~np.isfinite(sigma)) or np.any(sigma <= 0):
        raise ValueError("Resolution widths must be finite and positive")
    return sigma


def gaussian_line_shape(
    sample_energy_meV: ArrayLike,
    center_meV: float,
    sigma_meV: float,
) -> NDArray[np.float64]:
    """Unit-area Gaussian line evaluated at arbitrary energy samples."""

    sample = np.asarray(sample_energy_meV, dtype=float)
    sigma = float(sigma_meV)
    if sigma <= 0 or not np.isfinite(sigma):
        raise ValueError("sigma_meV must be finite and positive")
    z = (sample - float(center_meV)) / sigma
    return np.exp(-0.5 * z**2) / (np.sqrt(2.0 * np.pi) * sigma)


def broaden_discrete_transitions(
    sample_energy_meV: ArrayLike,
    transition_energies_meV: Sequence[float],
    transition_amplitudes: NDArray[np.float64],
    config: Mapping[str, object],
) -> NDArray[np.float64]:
    """Convolve per-point transition amplitudes with the configured kernel."""

    sample = np.asarray(sample_energy_meV, dtype=float)
    energies = np.asarray(transition_energies_meV, dtype=float)
    amplitudes = np.asarray(transition_amplitudes, dtype=float)
    if amplitudes.shape != (sample.size, energies.size):
        raise ValueError("transition_amplitudes must have shape (n_points, n_transitions)")
    widths = resolution_sigma_meV(energies, config)
    result = np.zeros(sample.size, dtype=float)
    for index, (center, width) in enumerate(zip(energies, widths)):
        result += amplitudes[:, index] * gaussian_line_shape(sample, center, width)
    return result
