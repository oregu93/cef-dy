"""Angular-momentum and real Stevens operators.

The formulas follow the explicit real-tesseral Stevens convention used by the
project's historical positive-q PCF/CFE calculations.  Negative m denotes the
sine tesseral partner; it is never treated as an alias for a positive-q label.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

ComplexMatrix = NDArray[np.complex128]


def _mpow(matrix: ComplexMatrix, power: int) -> ComplexMatrix:
    return np.linalg.matrix_power(matrix, power)


@lru_cache(maxsize=None)
def angular_momentum_operators(j: float) -> tuple[ComplexMatrix, ComplexMatrix, ComplexMatrix]:
    """Return Jx, Jy, Jz in PCF-compatible ascending |J,m> basis."""
    dimension = int(round(2.0 * j + 1.0))
    if dimension <= 0 or not np.isclose(2.0 * j, round(2.0 * j)):
        raise ValueError(f"J must be a non-negative integer or half-integer; got {j}")
    m = np.arange(-j, j + 1.0, 1.0, dtype=float)
    jz = np.diag(m).astype(complex)
    jp = np.zeros((dimension, dimension), dtype=complex)
    for column, m_value in enumerate(m):
        raised = m_value + 1.0
        if raised <= j and column < dimension - 1:
            jp[column + 1, column] = np.sqrt(j * (j + 1.0) - m_value * raised)
    jm = jp.conj().T
    jx = 0.5 * (jp + jm)
    jy = (jp - jm) / (2.0j)
    return jx, jy, jz


@lru_cache(maxsize=None)
def ladder_operators(j: float) -> tuple[ComplexMatrix, ComplexMatrix, ComplexMatrix]:
    jx, jy, jz = angular_momentum_operators(j)
    return jx + 1j * jy, jx - 1j * jy, jz


@lru_cache(maxsize=None)
def stevens_operator(j: float, rank: int, m: int) -> ComplexMatrix:
    """Return the explicit real Stevens operator O_rank^m for ranks 2, 4, 6."""
    if rank not in (2, 4, 6) or abs(m) > rank:
        raise ValueError(f"Unsupported Stevens operator ({rank}, {m})")
    jp, jm, jz = ladder_operators(j)
    identity = np.eye(jz.shape[0], dtype=complex)
    x = j * (j + 1.0)

    def cosine(power: int) -> ComplexMatrix:
        return _mpow(jp, power) + _mpow(jm, power)

    def sine(power: int) -> ComplexMatrix:
        return _mpow(jp, power) - _mpow(jm, power)

    if rank == 2:
        if m == 0:
            result = 3.0 * _mpow(jz, 2) - x * identity
        elif m == 1:
            result = 0.25 * (jz @ cosine(1) + cosine(1) @ jz)
        elif m == -1:
            result = -0.25j * (jz @ sine(1) + sine(1) @ jz)
        elif m == 2:
            result = 0.5 * cosine(2)
        else:
            result = -0.5j * sine(2)
    elif rank == 4:
        if m == 0:
            result = (
                35.0 * _mpow(jz, 4)
                - (30.0 * x - 25.0) * _mpow(jz, 2)
                + (3.0 * x * x - 6.0 * x) * identity
            )
        elif abs(m) == 1:
            poly = 7.0 * _mpow(jz, 3) - (3.0 * x + 1.0) * jz
            base = cosine(1) if m > 0 else sine(1)
            result = 0.25 * (base @ poly + poly @ base)
            if m < 0:
                result *= -1j
        elif abs(m) == 2:
            poly = 7.0 * _mpow(jz, 2) - (x + 5.0) * identity
            base = cosine(2) if m > 0 else sine(2)
            result = 0.25 * (base @ poly + poly @ base)
            if m < 0:
                result *= -1j
        elif abs(m) == 3:
            base = cosine(3) if m > 0 else sine(3)
            result = 0.25 * (base @ jz + jz @ base)
            if m < 0:
                result *= -1j
        elif m == 4:
            result = 0.5 * cosine(4)
        else:
            result = -0.5j * sine(4)
    else:
        if m == 0:
            result = (
                231.0 * _mpow(jz, 6)
                - (315.0 * x - 735.0) * _mpow(jz, 4)
                + (105.0 * x * x - 525.0 * x + 294.0) * _mpow(jz, 2)
                + (-5.0 * x**3 + 40.0 * x * x - 60.0 * x) * identity
            )
        elif abs(m) == 1:
            poly = (
                33.0 * _mpow(jz, 5)
                - (30.0 * x - 15.0) * _mpow(jz, 3)
                + (5.0 * x * x - 10.0 * x + 12.0) * jz
            )
            base = cosine(1) if m > 0 else sine(1)
            result = 0.25 * (base @ poly + poly @ base)
            if m < 0:
                result *= -1j
        elif abs(m) == 2:
            poly = (
                33.0 * _mpow(jz, 4)
                - (18.0 * x + 123.0) * _mpow(jz, 2)
                + (x * x + 10.0 * x + 102.0) * identity
            )
            base = cosine(2) if m > 0 else sine(2)
            result = 0.25 * (base @ poly + poly @ base)
            if m < 0:
                result *= -1j
        elif abs(m) == 3:
            poly = 11.0 * _mpow(jz, 3) - (3.0 * x + 59.0) * jz
            base = cosine(3) if m > 0 else sine(3)
            result = 0.25 * (base @ poly + poly @ base)
            if m < 0:
                result *= -1j
        elif abs(m) == 4:
            poly = 11.0 * _mpow(jz, 2) - (x + 38.0) * identity
            base = cosine(4) if m > 0 else sine(4)
            result = 0.25 * (base @ poly + poly @ base)
            if m < 0:
                result *= -1j
        elif abs(m) == 5:
            base = cosine(5) if m > 0 else sine(5)
            result = 0.25 * (base @ jz + jz @ base)
            if m < 0:
                result *= -1j
        elif m == 6:
            result = 0.5 * cosine(6)
        else:
            result = -0.5j * sine(6)

    result = np.asarray(result, dtype=complex)
    if not np.allclose(result, result.conj().T, atol=1e-11):
        raise RuntimeError(f"Stevens operator ({rank}, {m}) is not Hermitian")
    return result


def operator_norm_scale(j: float, rank: int, m: int) -> float:
    """Frobenius operator scale kappa = ||O||_F / sqrt(2J+1)."""
    op = stevens_operator(j, rank, m)
    return float(np.linalg.norm(op) / np.sqrt(op.shape[0]))
