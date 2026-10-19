"""Optional PyCrystalField positive-q Hamiltonian cross-check."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from ..conventions import DIRECT_LABELS, DIRECT_LM


def available() -> bool:
    try:
        from pcf_lib.StevensOperators import StevensOp  # noqa: F401
    except ImportError:
        return False
    return True


def direct_hamiltonian(parameters: Mapping[str, float], j: float = 7.5) -> np.ndarray:
    try:
        from pcf_lib.StevensOperators import StevensOp
    except ImportError as error:
        raise RuntimeError("PyCrystalField/pcf_lib is not installed") from error
    hamiltonian = np.zeros((int(2 * j + 1), int(2 * j + 1)), dtype=complex)
    for label, (rank, m) in zip(DIRECT_LABELS, DIRECT_LM):
        hamiltonian += float(parameters[label]) * np.asarray(StevensOp(j, rank, m), dtype=complex)
    return hamiltonian
