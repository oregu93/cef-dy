"""Project-owned additive likelihood/deviance components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
from scipy.special import log_ndtr


@dataclass(frozen=True)
class ObjectiveComponents:
    chi_energy: float = 0.0
    chi_intensity: float = 0.0
    deviance_censored: float = 0.0
    deviance_prior: float = 0.0

    @property
    def total(self) -> float:
        return self.chi_energy + self.chi_intensity + self.deviance_censored + self.deviance_prior

    def as_dict(self) -> dict[str, float]:
        return {
            "chi_energy": self.chi_energy,
            "chi_intensity": self.chi_intensity,
            "deviance_censored": self.deviance_censored,
            "deviance_prior": self.deviance_prior,
            "total": self.total,
        }


def energy_deviance(calculated: Iterable[float], observed: Iterable[float], sigma: Iterable[float]) -> float:
    calculated = np.asarray(tuple(calculated), dtype=float)
    observed = np.asarray(tuple(observed), dtype=float)
    sigma = np.asarray(tuple(sigma), dtype=float)
    if calculated.shape != observed.shape or observed.shape != sigma.shape or np.any(sigma <= 0):
        raise ValueError("Energy arrays must have equal shapes and positive sigma")
    return float(np.sum(((calculated - observed) / sigma) ** 2))


def detected_intensity_deviance(
    calculated: Iterable[float], observed: Iterable[float], sigma: Iterable[float], scale: float = 1.0
) -> float:
    calculated = np.asarray(tuple(calculated), dtype=float)
    observed = np.asarray(tuple(observed), dtype=float)
    sigma = np.asarray(tuple(sigma), dtype=float)
    if calculated.shape != observed.shape or observed.shape != sigma.shape or np.any(sigma <= 0) or scale <= 0:
        raise ValueError("Intensity arrays must have equal shapes, positive sigma, and positive scale")
    return float(np.sum(((observed - scale * calculated) / sigma) ** 2))


def censored_gaussian_deviance(
    calculated: Iterable[float], limits: Iterable[float], sigma: Iterable[float], scale: float = 1.0
) -> float:
    calculated = np.asarray(tuple(calculated), dtype=float)
    limits = np.asarray(tuple(limits), dtype=float)
    sigma = np.asarray(tuple(sigma), dtype=float)
    if calculated.shape != limits.shape or limits.shape != sigma.shape or np.any(sigma <= 0) or scale <= 0:
        raise ValueError("Censor arrays must have equal shapes, positive sigma, and positive scale")
    arguments = (limits - scale * calculated) / sigma
    return float(-2.0 * np.sum(log_ndtr(arguments)))


def assemble_objective(
    *,
    energy: float = 0.0,
    detected_intensity: float = 0.0,
    censored: float = 0.0,
    prior: float = 0.0,
) -> ObjectiveComponents:
    values = (energy, detected_intensity, censored, prior)
    if not all(np.isfinite(values)) or any(value < 0 for value in values):
        raise ValueError("Objective components must be finite and non-negative")
    return ObjectiveComponents(*map(float, values))


def energy_branch_objective(calculated_doublets_meV: np.ndarray, branch: int, energy_meV: float, sigma_meV: float) -> ObjectiveComponents:
    if branch <= 0 or branch >= len(calculated_doublets_meV):
        raise ValueError("Assignment branch must be D0->D1 through D0->D7")
    term = energy_deviance([calculated_doublets_meV[branch]], [energy_meV], [sigma_meV])
    return ObjectiveComponents(chi_energy=term)
