"""Profile positive instrument-block normalization scales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import minimize_scalar

from .objectives import censored_gaussian_deviance, detected_intensity_deviance


@dataclass(frozen=True)
class ProfiledScale:
    scale: float
    log_scale: float
    deviance: float
    converged: bool
    boundary_occupied: bool
    evaluations: int


def profile_block_scale(
    detected_calculated: Sequence[float] = (),
    detected_observed: Sequence[float] = (),
    detected_sigma: Sequence[float] = (),
    censored_calculated: Sequence[float] = (),
    censor_limits: Sequence[float] = (),
    censor_sigma: Sequence[float] = (),
    log_bounds: tuple[float, float] = (-10.0, 10.0),
) -> ProfiledScale:
    has_detected = len(detected_calculated) > 0
    has_censored = len(censored_calculated) > 0
    if not has_detected and not has_censored:
        raise ValueError("At least one detected or censored observation is required")

    def objective(log_scale: float) -> float:
        scale = float(np.exp(log_scale))
        detected = (
            detected_intensity_deviance(detected_calculated, detected_observed, detected_sigma, scale)
            if has_detected else 0.0
        )
        censored = (
            censored_gaussian_deviance(censored_calculated, censor_limits, censor_sigma, scale)
            if has_censored else 0.0
        )
        return detected + censored

    result = minimize_scalar(objective, bounds=log_bounds, method="bounded", options={"xatol": 1e-10})
    margin = 1e-5 * max(1.0, log_bounds[1] - log_bounds[0])
    boundary = result.x - log_bounds[0] <= margin or log_bounds[1] - result.x <= margin
    return ProfiledScale(
        scale=float(np.exp(result.x)),
        log_scale=float(result.x),
        deviance=float(result.fun),
        converged=bool(result.success),
        boundary_occupied=bool(boundary),
        evaluations=int(result.nfev),
    )
