"""Project-owned CEF transition layer used by all INS frontends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .cef_model import CEFModel
from .conventions import DIRECT_LM
from .polarization_factor import polarized_transition_strength, powder_transition_strength


@dataclass(frozen=True)
class CEFTransitions:
    doublet_energies_meV: NDArray[np.float64]
    transition_energies_meV: NDArray[np.float64]
    transition_tensors: NDArray[np.complex128]
    powder_strengths: NDArray[np.float64]


def calculate_cef_transitions(
    direct_parameters_meV: Mapping[str, float],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> CEFTransitions:
    model = CEFModel.from_coefficients(direct_parameters_meV, DIRECT_LM, j=j, g_j=g_j)
    system = model.eigensystem()
    transitions = model.ground_transitions(system)
    return CEFTransitions(
        doublet_energies_meV=np.asarray(system.doublet_energies_meV, dtype=float),
        transition_energies_meV=np.asarray([row.energy_meV for row in transitions], dtype=float),
        transition_tensors=np.asarray([row.tensor for row in transitions], dtype=complex),
        powder_strengths=np.asarray(
            [powder_transition_strength(row.tensor) for row in transitions], dtype=float
        ),
    )


def transition_strengths_at_q(
    transitions: CEFTransitions,
    qhat_direct: NDArray[np.float64] | None,
    n_points: int,
) -> NDArray[np.float64]:
    """Return point-by-transition polarization strengths."""

    if qhat_direct is None:
        return np.broadcast_to(transitions.powder_strengths, (n_points, 7)).copy()
    qhat = np.asarray(qhat_direct, dtype=float)
    if qhat.shape != (n_points, 3):
        raise ValueError("qhat_direct must have shape (n_points, 3)")
    strengths = np.empty((n_points, 7), dtype=float)
    for point in range(n_points):
        for transition in range(7):
            strengths[point, transition] = polarized_transition_strength(
                transitions.transition_tensors[transition], qhat[point]
            )
    return strengths
