"""Effective g tensors for Kramers doublets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .operators import angular_momentum_operators

PAULI = (
    np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex),
    np.array([[0.0, -1j], [1j, 0.0]], dtype=complex),
    np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex),
)


@dataclass(frozen=True)
class GTensor:
    matrix: NDArray[np.float64]
    principal_values: NDArray[np.float64]
    principal_axes: NDArray[np.float64]


def g_tensor(doublet_vectors: NDArray[np.complex128], j: float = 7.5, g_j: float = 4.0 / 3.0) -> GTensor:
    """Return a gauge-covariant 3x3 g matrix and gauge-invariant principal data."""
    vectors = np.asarray(doublet_vectors, dtype=complex)
    if vectors.shape != (int(2 * j + 1), 2):
        raise ValueError("doublet_vectors must contain two orthonormal state columns")
    if not np.allclose(vectors.conj().T @ vectors, np.eye(2), atol=1e-10):
        raise ValueError("doublet_vectors are not orthonormal")
    coefficients = np.zeros((3, 3), dtype=float)
    for alpha, j_op in enumerate(angular_momentum_operators(j)):
        projected = vectors.conj().T @ j_op @ vectors
        projected = 0.5 * (projected + projected.conj().T)
        for beta, sigma in enumerate(PAULI):
            coefficients[alpha, beta] = float(np.trace(projected @ sigma).real)
    matrix = g_j * coefficients
    metric = matrix @ matrix.T
    eigenvalues, axes = np.linalg.eigh(metric)
    order = np.argsort(eigenvalues)[::-1]
    principal = np.sqrt(np.clip(eigenvalues[order], 0.0, None))
    axes = axes[:, order]
    # Deterministic handedness; individual axis signs remain conventional.
    if np.linalg.det(axes) < 0:
        axes[:, -1] *= -1.0
    return GTensor(matrix=matrix, principal_values=principal, principal_axes=axes)
