"""Optional CrysFieldExplorer positive-q Hamiltonian cross-check."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from ..conventions import DIRECT_LABELS, DIRECT_LM


def available() -> bool:
    try:
        from CrysFieldExplorer.CrysFieldExplorer import CrysFieldExplorer  # noqa: F401
    except ImportError:
        return False
    return True


def direct_hamiltonian(parameters: Mapping[str, float], temperature_K: float = 5.0) -> np.ndarray:
    try:
        from CrysFieldExplorer.CrysFieldExplorer import CrysFieldExplorer
    except ImportError as error:
        raise RuntimeError("CrysFieldExplorer is not installed") from error
    indices = [list(item) for item in DIRECT_LM]
    values = [float(parameters[label]) for label in DIRECT_LABELS]
    model = CrysFieldExplorer("Dy3+", indices, 1.0, 1.0, 1.0, values, temperature_K, [0.0, 0.0, 0.0])
    _, _, hamiltonian = model.Hamiltonian()
    return np.asarray(hamiltonian, dtype=complex)
