"""Frozen-CEF, zero-exchange single-ion magnetization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from .operators import angular_momentum_operators

MU_B_MEV_PER_T = 0.0578838
K_B_MEV_PER_K = 0.08617333


@dataclass(frozen=True)
class MagnetizationCurve:
    fields_T: NDArray[np.float64]
    magnetization_muB_per_ion: NDArray[np.float64]
    temperature_K: float
    direction: NDArray[np.float64]


def magnetization_curve(
    h_cef_meV: NDArray[np.complex128],
    fields_T: Sequence[float],
    temperature_K: float,
    direction: Sequence[float],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> MagnetizationCurve:
    if temperature_K <= 0:
        raise ValueError("temperature_K must be positive")
    axis = np.asarray(direction, dtype=float)
    if axis.shape != (3,) or not np.isfinite(axis).all() or np.linalg.norm(axis) == 0:
        raise ValueError("direction must be a finite non-zero 3-vector")
    axis /= np.linalg.norm(axis)
    j_axis = sum(component * operator for component, operator in zip(axis, angular_momentum_operators(j)))
    fields = np.asarray(fields_T, dtype=float)
    moments = np.empty_like(fields)
    for index, field in enumerate(fields):
        h_total = h_cef_meV - g_j * MU_B_MEV_PER_T * field * j_axis
        energies, states = np.linalg.eigh(h_total)
        energies -= energies.min()
        weights = np.exp(-energies / (K_B_MEV_PER_K * temperature_K))
        weights /= weights.sum()
        expectations = np.real(np.diag(states.conj().T @ j_axis @ states))
        moments[index] = g_j * float(np.dot(weights, expectations))
    return MagnetizationCurve(fields, moments, float(temperature_K), axis)


def abc_direction_in_direct_frame(axis: str) -> NDArray[np.float64]:
    """Map crystallographic a,b,c to direct PCF axes (X,Y,Z)=(b,c,a)."""
    mapping = {
        "a": np.array([0.0, 0.0, 1.0]),
        "b": np.array([1.0, 0.0, 0.0]),
        "c": np.array([0.0, 1.0, 0.0]),
    }
    try:
        return mapping[axis.lower()].copy()
    except KeyError as error:
        raise ValueError("axis must be one of a, b, c") from error


def configured_directions_in_direct_frame(
    magnetization_config: Mapping[str, object],
) -> dict[str, NDArray[np.float64]]:
    """Resolve configured crystallographic labels in the internal direct frame."""
    labels = magnetization_config.get("directions")
    if not isinstance(labels, list) or not labels:
        raise ValueError("magnetization.directions must be a non-empty list of a/b/c labels")
    if not all(isinstance(label, str) for label in labels):
        raise ValueError("magnetization.directions must contain only a/b/c labels")
    normalized = [label.lower() for label in labels]
    if len(normalized) != len(set(normalized)):
        raise ValueError("magnetization.directions must not contain duplicate labels")
    return {label: abc_direction_in_direct_frame(label) for label in normalized}
