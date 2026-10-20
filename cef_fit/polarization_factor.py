"""Magnetic neutron polarization contractions in the direct (b,c,a) frame."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from numpy.typing import NDArray


def orthorhombic_hkl_to_q_direct(
    hkl: Sequence[float],
    lattice_constants_abc_A: Sequence[float],
) -> tuple[float, NDArray[np.float64]]:
    """Convert orthorhombic HKL to ``Q`` and ``qhat`` in direct ``(b,c,a)``.

    Reciprocal vectors are evaluated as ``2 pi (h/a, k/b, l/c)`` in the
    crystallographic ``(a,b,c)`` frame and then reordered to ``(b,c,a)``.
    """

    indices = np.asarray(hkl, dtype=float)
    lattice = np.asarray(lattice_constants_abc_A, dtype=float)
    if indices.shape != (3,) or lattice.shape != (3,):
        raise ValueError("hkl and lattice_constants_abc_A must be three-vectors")
    if np.any(~np.isfinite(indices)) or np.any(~np.isfinite(lattice)) or np.any(lattice <= 0):
        raise ValueError("HKL must be finite and lattice constants finite and positive")
    q_abc = 2.0 * np.pi * indices / lattice
    magnitude = float(np.linalg.norm(q_abc))
    if magnitude == 0:
        raise ValueError("The (0,0,0) reflection has no defined Q direction")
    q_direct = np.asarray([q_abc[1], q_abc[2], q_abc[0]], dtype=float)
    return magnitude, q_direct / magnitude


def polarization_matrix(qhat: Sequence[float]) -> NDArray[np.float64]:
    direction = np.asarray(qhat, dtype=float)
    if direction.shape != (3,) or np.any(~np.isfinite(direction)):
        raise ValueError("qhat must be a finite three-vector")
    norm = float(np.linalg.norm(direction))
    if norm == 0.0:
        raise ValueError("qhat must be non-zero")
    unit = direction / norm
    return np.eye(3) - np.outer(unit, unit)


def polarized_transition_strength(
    transition_tensor: NDArray[np.complex128],
    qhat: Sequence[float],
) -> float:
    """Contract ``(delta_ab-Qhat_a Qhat_b) T_ab`` explicitly."""

    tensor = np.asarray(transition_tensor, dtype=complex)
    if tensor.shape != (3, 3) or not np.allclose(tensor, tensor.conj().T, atol=1e-10):
        raise ValueError("transition_tensor must be a 3x3 Hermitian matrix")
    value = float(np.einsum("ab,ab->", polarization_matrix(qhat), tensor).real)
    return max(0.0, value)


def powder_transition_strength(transition_tensor: NDArray[np.complex128]) -> float:
    """Orientational average of the polarization contraction: ``2/3 Tr(T)``."""

    tensor = np.asarray(transition_tensor, dtype=complex)
    if tensor.shape != (3, 3):
        raise ValueError("transition_tensor must have shape (3, 3)")
    return max(0.0, float((2.0 / 3.0) * np.trace(tensor).real))
