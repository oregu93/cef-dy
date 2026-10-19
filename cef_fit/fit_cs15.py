"""Bounded smoke infrastructure for the underidentified Cs15 landscape."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

from .cef_model import CEFModel
from .conventions import DIRECT_LABELS, DIRECT_LM, direct_parameters_to_canonical
from .objectives import energy_branch_objective
from .operators import operator_norm_scale
from .g_tensor import g_tensor


@dataclass(frozen=True)
class Cs15BranchResult:
    solution_id: str
    assignment: str
    assignment_final_doublet: int
    objective: dict[str, float]
    converged: bool
    termination: str
    evaluations: int
    direct_parameters_meV: dict[str, float]
    canonical_parameters_meV: dict[str, float]
    canonical_projection_relative_residual: float
    h_coordinates_meV: list[float]
    search_boundary_occupied: bool
    doublet_energies_meV: list[float]
    transition_strengths: list[float]
    ground_g_principal_values: list[float]
    ground_g_principal_axes_direct: list[list[float]]
    profile: str = "SMOKE_ONLY"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def operator_scales(j: float = 7.5) -> np.ndarray:
    return np.array([operator_norm_scale(j, rank, m) for rank, m in DIRECT_LM], dtype=float)


def parameters_to_h(parameters: Mapping[str, float] | Sequence[float], j: float = 7.5) -> np.ndarray:
    if isinstance(parameters, Mapping):
        values = np.array([parameters[label] for label in DIRECT_LABELS], dtype=float)
    else:
        values = np.asarray(parameters, dtype=float)
    return operator_scales(j) * values


def h_to_parameters(h_coordinates: Sequence[float], j: float = 7.5) -> dict[str, float]:
    values = np.asarray(h_coordinates, dtype=float) / operator_scales(j)
    return dict(zip(DIRECT_LABELS, map(float, values)))


def run_cs15_smoke(
    seed_parameters: Mapping[str, float],
    energy_meV: float,
    energy_sigma_meV: float,
    assignments: Sequence[int],
    h_bounds: tuple[float, float],
    max_evaluations: int,
    random_seed: int,
    boundary_fraction: float = 0.02,
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> dict[str, object]:
    lower, upper = map(float, h_bounds)
    base = np.clip(parameters_to_h(seed_parameters, j=j), lower, upper)
    rng = np.random.default_rng(random_seed)
    rows = []
    for branch in assignments:
        start = np.clip(base + rng.normal(0.0, 0.01 * (upper - lower), size=base.shape), lower, upper)

        def scalar_objective(h_values: np.ndarray) -> float:
            model = CEFModel.from_coefficients(h_to_parameters(h_values, j=j), DIRECT_LM, j=j, g_j=g_j)
            levels = model.eigensystem().doublet_energies_meV
            return energy_branch_objective(levels, branch, energy_meV, energy_sigma_meV).total

        result = minimize(
            scalar_objective,
            start,
            method="L-BFGS-B",
            bounds=[(lower, upper)] * len(start),
            options={"maxfun": int(max_evaluations), "maxiter": int(max_evaluations), "ftol": 1e-12},
        )
        h_best = np.asarray(result.x, dtype=float)
        parameters = h_to_parameters(h_best, j=j)
        model = CEFModel.from_coefficients(parameters, DIRECT_LM, j=j, g_j=g_j)
        system = model.eigensystem()
        components = energy_branch_objective(system.doublet_energies_meV, branch, energy_meV, energy_sigma_meV)
        canonical = direct_parameters_to_canonical(parameters, j=j)
        ground_g = g_tensor(system.pair(0), j=j, g_j=g_j)
        width = upper - lower
        distance = np.minimum(h_best - lower, upper - h_best)
        boundary = bool(np.any(distance <= boundary_fraction * width))
        rows.append(
            Cs15BranchResult(
                solution_id=f"CS15-D{branch}-R1-SMOKE",
                assignment=f"D0->D{branch}",
                assignment_final_doublet=int(branch),
                objective=components.as_dict(),
                converged=bool(result.success),
                termination=str(result.message),
                evaluations=int(result.nfev),
                direct_parameters_meV=parameters,
                canonical_parameters_meV=canonical.coefficients,
                canonical_projection_relative_residual=float(canonical.relative_residual),
                h_coordinates_meV=h_best.tolist(),
                search_boundary_occupied=boundary,
                doublet_energies_meV=system.doublet_energies_meV.tolist(),
                transition_strengths=[transition.powder_strength for transition in model.ground_transitions(system)],
                ground_g_principal_values=ground_g.principal_values.tolist(),
                ground_g_principal_axes_direct=ground_g.principal_axes.tolist(),
            ).as_dict()
        )
    return {
        "profile": "SMOKE_ONLY",
        "model_id": "MOD-CEF-CS15",
        "scientific_interpretation": "LANDSCAPE_DIAGNOSTIC_ONLY__NO_UNIQUE_HAMILTONIAN_CLAIM",
        "objective_scope": "ENERGY_ONLY__INTENSITY_PROVENANCE_GATE_BLOCKED",
        "random_seed": int(random_seed),
        "branches": rows,
    }
