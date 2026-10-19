"""CEF coefficient orders, frames, rotations, and regression helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

from .operators import angular_momentum_operators, stevens_operator

DIRECT_LM: tuple[tuple[int, int], ...] = (
    (2, 0), (2, 1), (2, 2),
    (4, 0), (4, 1), (4, 2), (4, 3), (4, 4),
    (6, 0), (6, 1), (6, 2), (6, 3), (6, 4), (6, 5), (6, 6),
)
CANONICAL_CS_LM: tuple[tuple[int, int], ...] = (
    (2, 0), (2, -2), (2, 2),
    (4, 0), (4, -2), (4, 2), (4, -4), (4, 4),
    (6, 0), (6, -2), (6, 2), (6, -4), (6, 4), (6, -6), (6, 6),
)
DIRECT_LABELS = tuple(f"B{rank}{m}" for rank, m in DIRECT_LM)
CANONICAL_LABELS = tuple(
    f"B{rank}{'n' + str(abs(m)) if m < 0 else m}" for rank, m in CANONICAL_CS_LM
)

R_CAN_FROM_DIRECT = np.array(
    [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]], dtype=float
)
R_ABC_FROM_DIRECT = np.array(
    [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float
)


@dataclass(frozen=True)
class ProjectionResult:
    coefficients: dict[str, float]
    reconstruction: NDArray[np.complex128]
    relative_residual: float
    max_abs_residual_meV: float
    rank: int


def labels_for(lm_order: Sequence[tuple[int, int]]) -> tuple[str, ...]:
    if tuple(lm_order) == DIRECT_LM:
        return DIRECT_LABELS
    if tuple(lm_order) == CANONICAL_CS_LM:
        return CANONICAL_LABELS
    return tuple(f"B{rank}{'n' + str(abs(m)) if m < 0 else m}" for rank, m in lm_order)


def coefficient_vector(
    parameters: Mapping[str, float] | Sequence[float], lm_order: Sequence[tuple[int, int]]
) -> NDArray[np.float64]:
    if isinstance(parameters, Mapping):
        return np.array([float(parameters[label]) for label in labels_for(lm_order)], dtype=float)
    vector = np.asarray(parameters, dtype=float)
    if vector.shape != (len(lm_order),):
        raise ValueError(f"Expected {len(lm_order)} coefficients; got {vector.shape}")
    return vector


def hamiltonian_from_coefficients(
    j: float,
    parameters: Mapping[str, float] | Sequence[float],
    lm_order: Sequence[tuple[int, int]],
) -> NDArray[np.complex128]:
    values = coefficient_vector(parameters, lm_order)
    hamiltonian = np.zeros((int(2 * j + 1), int(2 * j + 1)), dtype=complex)
    for value, (rank, m) in zip(values, lm_order):
        hamiltonian += value * stevens_operator(j, rank, m)
    return 0.5 * (hamiltonian + hamiltonian.conj().T)


def direct_to_canonical_unitary(j: float) -> NDArray[np.complex128]:
    """Active +90 degree rotation about direct X || b."""
    jx, _, _ = angular_momentum_operators(j)
    return expm(-1j * (np.pi / 2.0) * jx)


def rotate_direct_hamiltonian_to_canonical(
    hamiltonian: NDArray[np.complex128], j: float
) -> NDArray[np.complex128]:
    unitary = direct_to_canonical_unitary(j)
    return unitary @ hamiltonian @ unitary.conj().T


def project_hamiltonian(
    hamiltonian: NDArray[np.complex128], j: float, lm_order: Sequence[tuple[int, int]]
) -> ProjectionResult:
    operators = [stevens_operator(j, rank, m) for rank, m in lm_order]
    design = np.column_stack(
        [np.concatenate((operator.real.ravel(), operator.imag.ravel())) for operator in operators]
    )
    target = np.concatenate((hamiltonian.real.ravel(), hamiltonian.imag.ravel()))
    norms = np.linalg.norm(design, axis=0)
    scaled, _, rank, _ = np.linalg.lstsq(design / norms, target, rcond=None)
    coefficients = scaled / norms
    reconstruction = sum(value * operator for value, operator in zip(coefficients, operators))
    difference = hamiltonian - reconstruction
    denominator = max(float(np.linalg.norm(hamiltonian)), np.finfo(float).eps)
    return ProjectionResult(
        coefficients=dict(zip(labels_for(lm_order), map(float, coefficients))),
        reconstruction=np.asarray(reconstruction, dtype=complex),
        relative_residual=float(np.linalg.norm(difference) / denominator),
        max_abs_residual_meV=float(np.max(np.abs(difference))),
        rank=int(rank),
    )


def direct_parameters_to_canonical(
    parameters: Mapping[str, float] | Sequence[float], j: float = 7.5
) -> ProjectionResult:
    direct_h = hamiltonian_from_coefficients(j, parameters, DIRECT_LM)
    canonical_h = rotate_direct_hamiltonian_to_canonical(direct_h, j)
    return project_hamiltonian(canonical_h, j, CANONICAL_CS_LM)


def rotate_tensor(tensor: NDArray[np.float64], rotation: NDArray[np.float64]) -> NDArray[np.float64]:
    return rotation @ tensor @ rotation.T
