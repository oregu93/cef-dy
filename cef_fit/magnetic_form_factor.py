"""Dy3+ dipole magnetic form factor used by the visible INS forward model."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


# International-Tables-style four-term approximation for the Dy3+ <j0> term.
# The argument of the exponentials is s^2 with s = Q / (4 pi), Q in A^-1.
DY3_J0_COEFFICIENTS = (
    (0.1157, 15.0732),
    (0.3270, 6.7991),
    (0.5821, 3.0202),
)
DY3_J0_CONSTANT = -0.0249


def dy3_j0_form_factor(q_ainv: ArrayLike) -> NDArray[np.float64]:
    """Return the explicitly documented Dy3+ ``<j0>`` approximation.

    This is an amplitude form factor, not an empirical intensity correction.
    The forward model squares it when calculating an intensity.
    """

    q = np.asarray(q_ainv, dtype=float)
    if np.any(~np.isfinite(q)) or np.any(q < 0):
        raise ValueError("Q must contain finite non-negative values in A^-1")
    s2 = (q / (4.0 * np.pi)) ** 2
    result = np.full(q.shape, DY3_J0_CONSTANT, dtype=float)
    for amplitude, exponent in DY3_J0_COEFFICIENTS:
        result += amplitude * np.exp(-exponent * s2)
    return result


def dy3_form_factor_intensity(q_ainv: ArrayLike) -> NDArray[np.float64]:
    """Return ``|f(Q)|^2`` for the configured Dy3+ dipole approximation."""

    form_factor = dy3_j0_form_factor(q_ainv)
    return np.square(form_factor)
