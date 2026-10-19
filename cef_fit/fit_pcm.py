"""Smoke-only A0/A1 PCM branch enumeration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

import numpy as np

from .cef_model import CEFModel
from .conventions import DIRECT_LM, hamiltonian_from_coefficients
from .objectives import energy_branch_objective
from .pcm_model import UniformPCM
from .g_tensor import g_tensor


@dataclass(frozen=True)
class PCMBranchResult:
    solution_id: str
    model_id: str
    assignment: str
    assignment_final_doublet: int
    scale: float
    calculated_energy_meV: float
    observed_energy_meV: float
    energy_sigma_meV: float
    objective: dict[str, float]
    scale_boundary_occupied: bool
    profile: str = "SMOKE_ONLY"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def run_pcm_smoke(
    formal_parameters: Mapping[str, float],
    energy_meV: float,
    energy_sigma_meV: float,
    assignments: Sequence[int],
    scale_bounds: tuple[float, float],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> dict[str, object]:
    formal_hamiltonian = hamiltonian_from_coefficients(j, formal_parameters, DIRECT_LM)
    formal_system = CEFModel(formal_hamiltonian, j=j, g_j=g_j).eigensystem()
    formal_g = g_tensor(formal_system.pair(0), j=j, g_j=g_j)
    family = UniformPCM(formal_hamiltonian, j=j, g_j=g_j)
    lower, upper = map(float, scale_bounds)
    if not 0 < lower < upper:
        raise ValueError("Invalid positive PCM scale bounds")
    rows = []
    for branch in assignments:
        unscaled = float(formal_system.doublet_energies_meV[branch])
        scale = float(np.clip(energy_meV / unscaled, lower, upper))
        system = family.model(scale).eigensystem()
        components = energy_branch_objective(system.doublet_energies_meV, branch, energy_meV, energy_sigma_meV)
        boundary = np.isclose(scale, lower, rtol=0, atol=1e-10) or np.isclose(scale, upper, rtol=0, atol=1e-10)
        rows.append(
            PCMBranchResult(
                solution_id=f"PCM-A1-D{branch}-SMOKE",
                model_id="MOD-PCM-M0",
                assignment=f"D0->D{branch}",
                assignment_final_doublet=int(branch),
                scale=scale,
                calculated_energy_meV=float(system.doublet_energies_meV[branch]),
                observed_energy_meV=float(energy_meV),
                energy_sigma_meV=float(energy_sigma_meV),
                objective=components.as_dict(),
                scale_boundary_occupied=bool(boundary),
            ).as_dict()
        )
    return {
        "profile": "SMOKE_ONLY",
        "model_hierarchy": ["MOD-PCM-FORMAL", "MOD-PCM-M0"],
        "M1_status": "IMPLEMENTED_INTERFACE_DISABLED_BY_DEFAULT",
        "formal_doublet_energies_meV": formal_system.doublet_energies_meV.tolist(),
        "formal_ground_g_principal_values": formal_g.principal_values.tolist(),
        "formal_ground_g_principal_axes_direct": formal_g.principal_axes.tolist(),
        "branches": rows,
    }
