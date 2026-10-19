"""Small observable-space distance helpers; no production clustering policy yet."""

from __future__ import annotations

import numpy as np

from .wavefunctions import projector_overlap


def projector_distance(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.sqrt(max(0.0, 1.0 - projector_overlap(first, second))))


def normalized_observable_distance(first: np.ndarray, second: np.ndarray, scale: np.ndarray) -> float:
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    scale = np.asarray(scale, dtype=float)
    if first.shape != second.shape or first.shape != scale.shape or np.any(scale <= 0):
        raise ValueError("Observable vectors and positive scales must have the same shape")
    return float(np.linalg.norm((first - second) / scale))
