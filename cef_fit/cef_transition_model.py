"""Project-owned CEF transition layer used by all INS frontends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .cef_model import CEFModel
from .conventions import DIRECT_LM
from .polarization_factor import polarized_transition_strength, powder_transition_strength

K_B_MEV_PER_K = 0.08617333262
POPULATION_MODES = frozenset({"GROUND_DOUBLET_ONLY", "BOLTZMANN_ALL_CEF_STATES"})
PBNM_DY_4C_TENSOR_CONTRACT_ID = "STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001"
PBNM_DY_4C_ROTATIONS_CEF = np.asarray(
    [
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]],
        [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]],
        [[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]],
    ],
    dtype=float,
)
PBNM_DY_4C_ROTATIONS_CEF.setflags(write=False)


@dataclass(frozen=True)
class CEFTransitions:
    doublet_energies_meV: NDArray[np.float64]
    transition_energies_meV: NDArray[np.float64]
    transition_tensors: NDArray[np.complex128]
    powder_strengths: NDArray[np.float64]
    initial_doublets: NDArray[np.int64]
    final_doublets: NDArray[np.int64]
    doublet_populations: NDArray[np.float64]
    transition_population_factors: NDArray[np.float64]
    population_mode: str
    temperature_K: float | None


def boltzmann_doublet_populations(
    doublet_energies_meV: NDArray[np.float64], temperature_K: float
) -> NDArray[np.float64]:
    """Return normalized populations of equally degenerate Kramers doublets."""

    energies = np.asarray(doublet_energies_meV, dtype=float)
    temperature = float(temperature_K)
    if not np.isfinite(temperature) or temperature < 0:
        raise ValueError("temperature_K must be finite and non-negative")
    if temperature == 0.0:
        populations = np.zeros_like(energies)
        populations[np.flatnonzero(np.isclose(energies, np.min(energies), atol=1e-12))] = 1.0
        populations /= np.sum(populations)
    else:
        shifted = energies - np.min(energies)
        weights = np.exp(-shifted / (K_B_MEV_PER_K * temperature))
        populations = weights / np.sum(weights)
    populations.setflags(write=False)
    return populations


def calculate_cef_transitions(
    direct_parameters_meV: Mapping[str, float],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
    population_mode: str = "GROUND_DOUBLET_ONLY",
    temperature_K: float | None = None,
) -> CEFTransitions:
    model = CEFModel.from_coefficients(direct_parameters_meV, DIRECT_LM, j=j, g_j=g_j)
    system = model.eigensystem()
    mode = str(population_mode)
    if mode not in POPULATION_MODES:
        raise ValueError(f"Unknown population mode: {mode}")
    if mode == "GROUND_DOUBLET_ONLY":
        populations = np.zeros(len(system.doublet_energies_meV), dtype=float)
        populations[0] = 1.0
        pairs = [(0, final) for final in range(1, len(populations))]
        resolved_temperature = None
    else:
        if temperature_K is None:
            raise ValueError("BOLTZMANN_ALL_CEF_STATES requires temperature_K")
        populations = boltzmann_doublet_populations(
            system.doublet_energies_meV, float(temperature_K)
        )
        pairs = [
            (initial, final)
            for initial in range(len(populations))
            for final in range(initial + 1, len(populations))
        ]
        resolved_temperature = float(temperature_K)
    tensors = np.asarray(
        [model.transition_tensor(initial, final, system) for initial, final in pairs],
        dtype=complex,
    )
    energies = np.asarray(
        [
            system.doublet_energies_meV[final] - system.doublet_energies_meV[initial]
            for initial, final in pairs
        ],
        dtype=float,
    )
    population_factors = np.asarray([populations[initial] for initial, _ in pairs], dtype=float)
    powder = np.asarray([powder_transition_strength(tensor) for tensor in tensors], dtype=float)
    for values in (tensors, energies, population_factors, powder, populations):
        values.setflags(write=False)
    return CEFTransitions(
        doublet_energies_meV=np.asarray(system.doublet_energies_meV, dtype=float),
        transition_energies_meV=energies,
        transition_tensors=tensors,
        powder_strengths=powder,
        initial_doublets=np.asarray([initial for initial, _ in pairs], dtype=int),
        final_doublets=np.asarray([final for _, final in pairs], dtype=int),
        doublet_populations=populations,
        transition_population_factors=population_factors,
        population_mode=mode,
        temperature_K=resolved_temperature,
    )


def pbnm_dy_four_site_tensor_sum(
    transition_tensors: NDArray[np.complex128],
) -> NDArray[np.complex128]:
    """Sum the accepted Pbnm Dy(4c) independent-site tensor transports.

    The rotations and site order are pinned by
    ``STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001`` in the direct CEF
    frame ``(b,c,a)``.  This is a localized independent-site sum and does not
    represent coherent inter-site dynamical cross correlations.
    """

    tensors = np.asarray(transition_tensors, dtype=complex)
    if tensors.ndim < 2 or tensors.shape[-2:] != (3, 3):
        raise ValueError("transition_tensors must end in shape (3, 3)")
    if not np.allclose(tensors, np.swapaxes(tensors.conj(), -1, -2), atol=1e-10):
        raise ValueError("transition_tensors must be Hermitian")
    transported = np.zeros_like(tensors)
    for rotation in PBNM_DY_4C_ROTATIONS_CEF:
        transported += np.einsum("ab,...bc,dc->...ad", rotation, tensors, rotation)
    expected = np.zeros_like(tensors)
    diagonal = np.diagonal(tensors, axis1=-2, axis2=-1)
    indices = np.arange(3)
    expected[..., indices, indices] = 4.0 * diagonal
    if not np.allclose(transported, expected, atol=1e-10):
        raise RuntimeError("Pbnm Dy(4c) orbit-sum regression invariant failed")
    transported.setflags(write=False)
    return transported


def transition_strengths_at_q(
    transitions: CEFTransitions,
    qhat_direct: NDArray[np.float64] | None,
    n_points: int,
    *,
    allow_powder_average: bool = False,
    four_site_pbnm_sum: bool = False,
) -> NDArray[np.float64]:
    """Return point-by-transition polarization strengths."""

    tensors = (
        pbnm_dy_four_site_tensor_sum(transitions.transition_tensors)
        if four_site_pbnm_sum
        else transitions.transition_tensors
    )

    if qhat_direct is None:
        if not allow_powder_average:
            raise ValueError("Per-point qhat_direct is required; silent powder averaging is forbidden")
        powder = np.asarray([powder_transition_strength(tensor) for tensor in tensors])
        return np.broadcast_to(
            powder, (n_points, len(powder))
        ).copy()
    qhat = np.asarray(qhat_direct, dtype=float)
    if qhat.shape != (n_points, 3):
        raise ValueError("qhat_direct must have shape (n_points, 3)")
    strengths = np.empty((n_points, len(transitions.transition_energies_meV)), dtype=float)
    for point in range(n_points):
        for transition in range(len(transitions.transition_energies_meV)):
            strengths[point, transition] = polarized_transition_strength(
                tensors[transition], qhat[point]
            )
    return strengths
