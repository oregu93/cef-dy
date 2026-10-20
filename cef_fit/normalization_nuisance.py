"""One explicit positive multiplicative nuisance scale per justified block."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True)
class BlockScaleResult:
    scales: dict[str, float]
    boundary_blocks: tuple[str, ...]
    fitted: NDArray[np.float64]


def profile_block_scales(
    calculated: ArrayLike,
    observed: ArrayLike,
    blocks: Sequence[str],
    include_mask: ArrayLike,
    sigma: ArrayLike | None = None,
    bounds: tuple[float, float] = (1.0e-6, 1.0e6),
) -> BlockScaleResult:
    """Profile independent weighted least-squares scales for declared blocks.

    No per-scan scale is created here. The caller controls the block identifiers,
    which must come from the version-controlled prepared dataset.
    """

    calc = np.asarray(calculated, dtype=float)
    obs = np.asarray(observed, dtype=float)
    mask = np.asarray(include_mask, dtype=bool)
    block_values = np.asarray(tuple(blocks), dtype=str)
    if calc.shape != obs.shape or calc.shape != mask.shape or calc.shape != block_values.shape:
        raise ValueError("calculated, observed, blocks, and mask must have equal shapes")
    weights = np.ones(calc.shape, dtype=float)
    if sigma is not None:
        sigma_values = np.asarray(sigma, dtype=float)
        if sigma_values.shape != calc.shape or np.any(sigma_values[mask] <= 0):
            raise ValueError("sigma must match the data and be positive for included points")
        weights[mask] = 1.0 / np.square(sigma_values[mask])
    lower, upper = map(float, bounds)
    if not (0.0 < lower < upper):
        raise ValueError("scale bounds must satisfy 0 < lower < upper")
    fitted = np.zeros(calc.shape, dtype=float)
    scales: dict[str, float] = {}
    boundary: list[str] = []
    for block in sorted(set(block_values[mask])):
        selected = mask & (block_values == block)
        denominator = float(np.sum(weights[selected] * np.square(calc[selected])))
        if denominator <= np.finfo(float).eps:
            scale = lower
        else:
            scale = float(np.sum(weights[selected] * calc[selected] * obs[selected]) / denominator)
            scale = float(np.clip(scale, lower, upper))
        scales[str(block)] = scale
        fitted[block_values == block] = scale * calc[block_values == block]
        margin = 1.0e-10 * max(1.0, upper - lower)
        if scale - lower <= margin or upper - scale <= margin:
            boundary.append(str(block))
    fitted.setflags(write=False)
    return BlockScaleResult(scales, tuple(boundary), fitted)
