"""Low-dimensional structural PCM-family interfaces."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .cef_model import CEFModel


@dataclass(frozen=True)
class UniformPCM:
    """A1/M0: a positive common scale multiplying a reviewed formal PCM seed."""

    formal_hamiltonian_meV: NDArray[np.complex128]
    j: float = 7.5
    g_j: float = 4.0 / 3.0

    def model(self, scale: float) -> CEFModel:
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("PCM scale must be positive and finite")
        return CEFModel(scale * self.formal_hamiltonian_meV, j=self.j, g_j=self.g_j)


@dataclass(frozen=True)
class NeutralTwoOxygenPCM:
    """M1 interface with neutrality-derived cation scale.

    It is implemented as a reusable forward model but remains disabled in the
    manuscript-v1 configuration until separately approved component matrices
    are admitted.
    """

    oxygen1_hamiltonian_meV: NDArray[np.complex128]
    oxygen2_hamiltonian_meV: NDArray[np.complex128]
    cation_hamiltonian_meV: NDArray[np.complex128]
    j: float = 7.5
    g_j: float = 4.0 / 3.0

    @staticmethod
    def cation_scale(s_o1: float, s_o2: float) -> float:
        return (s_o1 + 2.0 * s_o2) / 3.0

    def model(self, s_o1: float, s_o2: float) -> CEFModel:
        if min(s_o1, s_o2) <= 0 or not np.isfinite([s_o1, s_o2]).all():
            raise ValueError("M1 oxygen scales must be positive and finite")
        hamiltonian = (
            s_o1 * self.oxygen1_hamiltonian_meV
            + s_o2 * self.oxygen2_hamiltonian_meV
            + self.cation_scale(s_o1, s_o2) * self.cation_hamiltonian_meV
        )
        return CEFModel(hamiltonian, j=self.j, g_j=self.g_j)
