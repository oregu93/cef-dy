"""Observable-aware distance construction for user-executed family clustering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from .wavefunctions import projector_overlap


@dataclass(frozen=True)
class SolutionObservables:
    solution_id: str
    h_coordinates_meV: NDArray[np.float64]
    doublet_energies_meV: NDArray[np.float64]
    projectors: NDArray[np.complex128]
    transition_strengths: NDArray[np.float64]
    g_principal_values: NDArray[np.float64]
    g_principal_axes: NDArray[np.float64]
    mh_predictions: NDArray[np.float64]


DEFAULT_WEIGHTS = {
    "parameter": 0.10,
    "energy": 0.25,
    "projector": 0.25,
    "neutron": 0.20,
    "g_tensor": 0.10,
    "magnetization": 0.10,
}


def _scaled_rms(first: NDArray[np.float64], second: NDArray[np.float64], scale: float) -> float:
    return float(
        np.sqrt(np.mean(np.square((first - second) / max(scale, np.finfo(float).eps))))
    )


def solution_distance_components(
    first: SolutionObservables,
    second: SolutionObservables,
    scales: Mapping[str, float],
) -> dict[str, float]:
    if first.projectors.shape != second.projectors.shape:
        raise ValueError("Solutions must contain matching doublet projector arrays")
    projector_distances = [
        np.sqrt(max(0.0, 1.0 - projector_overlap(a, b)))
        for a, b in zip(first.projectors, second.projectors)
    ]
    axes_first = np.abs(np.asarray(first.g_principal_axes, dtype=float))
    axes_second = np.abs(np.asarray(second.g_principal_axes, dtype=float))
    return {
        "parameter": _scaled_rms(
            first.h_coordinates_meV, second.h_coordinates_meV, float(scales["parameter_meV"])
        ),
        "energy": _scaled_rms(
            first.doublet_energies_meV,
            second.doublet_energies_meV,
            float(scales["energy_meV"]),
        ),
        "projector": float(np.sqrt(np.mean(np.square(projector_distances)))),
        "neutron": _scaled_rms(
            first.transition_strengths,
            second.transition_strengths,
            float(scales["transition_strength"]),
        ),
        "g_tensor": 0.5
        * (
            _scaled_rms(
                first.g_principal_values, second.g_principal_values, float(scales["g_value"])
            )
            + _scaled_rms(axes_first, axes_second, 1.0)
        ),
        "magnetization": _scaled_rms(
            first.mh_predictions,
            second.mh_predictions,
            float(scales["magnetization_muB"]),
        ),
    }


def observable_distance_matrix(
    solutions: Sequence[SolutionObservables],
    weights: Mapping[str, float],
    scales: Mapping[str, float],
) -> tuple[NDArray[np.float64], dict[str, NDArray[np.float64]]]:
    if len(solutions) < 2:
        raise ValueError("At least two solutions are required for clustering")
    missing = set(DEFAULT_WEIGHTS) - set(weights)
    if missing or any(float(weights[name]) < 0 for name in DEFAULT_WEIGHTS):
        raise ValueError(f"Missing or invalid clustering weights: {sorted(missing)}")
    component_matrices = {
        name: np.zeros((len(solutions), len(solutions)), dtype=float)
        for name in DEFAULT_WEIGHTS
    }
    total = np.zeros((len(solutions), len(solutions)), dtype=float)
    for first_index in range(len(solutions)):
        for second_index in range(first_index + 1, len(solutions)):
            components = solution_distance_components(
                solutions[first_index], solutions[second_index], scales
            )
            combined = 0.0
            for name, value in components.items():
                component_matrices[name][first_index, second_index] = value
                component_matrices[name][second_index, first_index] = value
                combined += float(weights[name]) * value**2
            total[first_index, second_index] = total[second_index, first_index] = np.sqrt(
                combined
            )
    return total, component_matrices


def cluster_observable_distances(
    distance_matrix: NDArray[np.float64],
    distance_threshold: float,
    method: str = "average",
) -> NDArray[np.int64]:
    matrix = np.asarray(distance_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] < 2:
        raise ValueError("distance_matrix must be square with at least two solutions")
    if not np.allclose(matrix, matrix.T) or np.any(matrix < 0):
        raise ValueError("distance_matrix must be symmetric and non-negative")
    hierarchy = linkage(squareform(matrix, checks=True), method=method)
    return np.asarray(
        fcluster(hierarchy, distance_threshold, criterion="distance"), dtype=np.int64
    )
