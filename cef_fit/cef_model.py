"""Single-ion CEF Hamiltonian, Kramers doublets, and transition tensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from .conventions import DIRECT_LM, hamiltonian_from_coefficients
from .operators import angular_momentum_operators


@dataclass(frozen=True)
class Eigensystem:
    state_energies_meV: NDArray[np.float64]
    eigenvectors: NDArray[np.complex128]
    doublet_energies_meV: NDArray[np.float64]
    doublet_splittings_meV: NDArray[np.float64]
    projectors: tuple[NDArray[np.complex128], ...]

    def pair(self, doublet: int) -> NDArray[np.complex128]:
        return self.eigenvectors[:, 2 * doublet : 2 * doublet + 2]


@dataclass(frozen=True)
class Transition:
    initial_doublet: int
    final_doublet: int
    energy_meV: float
    tensor: NDArray[np.complex128]
    powder_strength: float


class CEFModel:
    def __init__(self, hamiltonian_meV: NDArray[np.complex128], j: float = 7.5, g_j: float = 4.0 / 3.0):
        hamiltonian = np.asarray(hamiltonian_meV, dtype=complex)
        dimension = int(round(2 * j + 1))
        if hamiltonian.shape != (dimension, dimension):
            raise ValueError(f"Expected a {dimension}x{dimension} Hamiltonian")
        if not np.allclose(hamiltonian, hamiltonian.conj().T, atol=1e-10):
            raise ValueError("CEF Hamiltonian must be Hermitian")
        self.hamiltonian_meV = 0.5 * (hamiltonian + hamiltonian.conj().T)
        self.j = float(j)
        self.g_j = float(g_j)

    @classmethod
    def from_coefficients(
        cls,
        parameters: Mapping[str, float] | Sequence[float],
        lm_order: Sequence[tuple[int, int]] = DIRECT_LM,
        j: float = 7.5,
        g_j: float = 4.0 / 3.0,
    ) -> "CEFModel":
        return cls(hamiltonian_from_coefficients(j, parameters, lm_order), j=j, g_j=g_j)

    def eigensystem(self, kramers_tolerance_meV: float = 1e-8) -> Eigensystem:
        values, vectors = np.linalg.eigh(self.hamiltonian_meV)
        values = np.asarray(values.real, dtype=float)
        values -= values[0]
        if len(values) % 2:
            raise ValueError("Kramers workflow requires an even Hilbert-space dimension")
        pair_energies = np.array(
            [np.mean(values[index : index + 2]) for index in range(0, len(values), 2)], dtype=float
        )
        pair_energies -= pair_energies[0]
        splittings = np.array(
            [abs(values[index + 1] - values[index]) for index in range(0, len(values), 2)], dtype=float
        )
        if np.max(splittings) > kramers_tolerance_meV:
            raise ValueError(
                f"Maximum Kramers splitting {np.max(splittings):.3e} meV exceeds "
                f"tolerance {kramers_tolerance_meV:.3e} meV"
            )
        projectors = tuple(
            vectors[:, index : index + 2] @ vectors[:, index : index + 2].conj().T
            for index in range(0, len(values), 2)
        )
        return Eigensystem(values, vectors, pair_energies, splittings, projectors)

    def transition_tensor(
        self, initial_doublet: int, final_doublet: int, eigensystem: Eigensystem | None = None
    ) -> NDArray[np.complex128]:
        system = eigensystem or self.eigensystem()
        p_initial = system.projectors[initial_doublet]
        p_final = system.projectors[final_doublet]
        j_ops = angular_momentum_operators(self.j)
        tensor = np.empty((3, 3), dtype=complex)
        for alpha, j_alpha in enumerate(j_ops):
            for beta, j_beta in enumerate(j_ops):
                tensor[alpha, beta] = 0.5 * np.trace(p_initial @ j_alpha @ p_final @ j_beta)
        return tensor

    def ground_transitions(self, eigensystem: Eigensystem | None = None) -> tuple[Transition, ...]:
        system = eigensystem or self.eigensystem()
        transitions = []
        for final in range(1, len(system.doublet_energies_meV)):
            tensor = self.transition_tensor(0, final, system)
            transitions.append(
                Transition(0, final, float(system.doublet_energies_meV[final]), tensor, float(np.trace(tensor).real))
            )
        return tuple(transitions)

    def polarized_strength(
        self, initial_doublet: int, final_doublet: int, qhat: Sequence[float]
    ) -> float:
        direction = np.asarray(qhat, dtype=float)
        direction /= np.linalg.norm(direction)
        polarization = np.eye(3) - np.outer(direction, direction)
        tensor = self.transition_tensor(initial_doublet, final_doublet)
        return float(np.einsum("ab,ab->", polarization, tensor).real)
