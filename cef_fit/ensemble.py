"""Compatibility classification for future fitted ensembles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class Compatibility:
    compatible: bool
    reasons: tuple[str, ...]


def classify_compatibility(
    energy_residuals: Sequence[float],
    intensity_residuals: Sequence[float] = (),
    nondetection_probabilities: Sequence[float] = (),
    search_boundary_occupied: bool = False,
    nuisance_boundary_occupied: bool = False,
) -> Compatibility:
    reasons = []
    if np.any(np.abs(energy_residuals) > 3.0):
        reasons.append("ENERGY_RESIDUAL_GT_3SIGMA")
    if len(intensity_residuals) and np.any(np.abs(intensity_residuals) > 3.0):
        reasons.append("INTENSITY_RESIDUAL_GT_3SIGMA")
    if len(nondetection_probabilities) and np.any(np.asarray(nondetection_probabilities) < 0.05):
        reasons.append("NONDETECTION_PROBABILITY_LT_0P05")
    if search_boundary_occupied:
        reasons.append("SEARCH_BOUNDARY_OCCUPIED")
    if nuisance_boundary_occupied:
        reasons.append("NUISANCE_SCALE_BOUNDARY_OCCUPIED")
    return Compatibility(not reasons, tuple(reasons))
