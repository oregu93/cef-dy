"""Gauge-invariant projectors and deterministic Kramers-pair presentation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .g_tensor import g_tensor
from .operators import angular_momentum_operators


@dataclass(frozen=True)
class GaugeFixedDoublet:
    plus: NDArray[np.complex128]
    minus: NDArray[np.complex128]
    projector: NDArray[np.complex128]
    gauge_axis: NDArray[np.float64]
    axis_degenerate: bool


def doublet_projector(vectors: NDArray[np.complex128]) -> NDArray[np.complex128]:
    pair = np.asarray(vectors, dtype=complex)
    return pair @ pair.conj().T


def time_reverse(state: NDArray[np.complex128], j: float = 7.5) -> NDArray[np.complex128]:
    """Apply Theta|J,m> = (-1)^(J-m)|J,-m> in ascending-m basis."""
    vector = np.asarray(state, dtype=complex)
    m_values = np.arange(-j, j + 1.0, 1.0)
    if vector.shape != m_values.shape:
        raise ValueError("State dimension does not match J")
    phases = np.array([(-1.0) ** int(round(j - m)) for m in m_values], dtype=float)
    return phases[::-1] * vector.conj()[::-1]


def _phase_fix(state: NDArray[np.complex128]) -> NDArray[np.complex128]:
    fixed = np.array(state, dtype=complex, copy=True)
    index = int(np.argmax(np.abs(fixed)))
    if abs(fixed[index]) > 0:
        fixed *= np.exp(-1j * np.angle(fixed[index]))
    if fixed[index].real < 0:
        fixed *= -1.0
    return fixed


def gauge_fix_doublet(
    vectors: NDArray[np.complex128],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
    degeneracy_tolerance: float = 1e-8,
) -> GaugeFixedDoublet:
    pair = np.asarray(vectors, dtype=complex)
    tensor = g_tensor(pair, j=j, g_j=g_j)
    principal = tensor.principal_values
    axis_degenerate = bool(abs(principal[0] - principal[1]) <= degeneracy_tolerance * max(1.0, principal[0]))
    axis = np.array([1.0, 0.0, 0.0]) if axis_degenerate else tensor.principal_axes[:, 0]
    if axis[int(np.argmax(np.abs(axis)))] < 0:
        axis = -axis
    j_axis = sum(component * operator for component, operator in zip(axis, angular_momentum_operators(j)))
    projected = pair.conj().T @ j_axis @ pair
    moments, internal_vectors = np.linalg.eigh(0.5 * (projected + projected.conj().T))
    plus = pair @ internal_vectors[:, int(np.argmax(moments))]
    plus = _phase_fix(plus)
    minus = time_reverse(plus, j=j)
    minus -= plus * np.vdot(plus, minus)
    minus /= np.linalg.norm(minus)
    # Preserve the exact time-reversal convention after any numerical cleanup.
    reference = time_reverse(plus, j=j)
    minus *= np.exp(-1j * np.angle(np.vdot(reference, minus)))
    return GaugeFixedDoublet(
        plus=plus,
        minus=minus,
        projector=doublet_projector(pair),
        gauge_axis=axis,
        axis_degenerate=axis_degenerate,
    )


def projector_overlap(first: NDArray[np.complex128], second: NDArray[np.complex128]) -> float:
    """Normalized subspace overlap Tr(PQ)/2 for Kramers doublets."""
    return float(np.trace(first @ second).real / 2.0)


def _complex_payload(array: NDArray[np.complex128]) -> dict[str, list]:
    values = np.asarray(array, dtype=complex)
    return {"real": values.real.tolist(), "imag": values.imag.tolist()}


def export_wavefunctions(
    path_stem: str | Path,
    doublet_pairs: tuple[NDArray[np.complex128], ...],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> tuple[Path, Path]:
    """Save projector-primary and gauge-fixed representations as NPZ + JSON."""
    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    fixed = tuple(gauge_fix_doublet(pair, j=j, g_j=g_j) for pair in doublet_pairs)
    projectors = np.stack([item.projector for item in fixed])
    plus = np.stack([item.plus for item in fixed])
    minus = np.stack([item.minus for item in fixed])
    axes = np.stack([item.gauge_axis for item in fixed])
    npz_path = stem.with_suffix(".npz")
    json_path = stem.with_suffix(".json")
    np.savez_compressed(
        npz_path,
        m_j=np.arange(-j, j + 1.0, 1.0),
        projectors=projectors,
        plus=plus,
        minus=minus,
        gauge_axes=axes,
        gauge_axis_degenerate=np.array([item.axis_degenerate for item in fixed], dtype=bool),
    )
    payload = {
        "basis": {"J": j, "order": "ascending_mJ", "m_j": np.arange(-j, j + 1.0, 1.0).tolist()},
        "doublets": [
            {
                "doublet": index,
                "projector": _complex_payload(item.projector),
                "plus": _complex_payload(item.plus),
                "minus": _complex_payload(item.minus),
                "gauge_axis": item.gauge_axis.tolist(),
                "gauge_axis_degenerate": item.axis_degenerate,
            }
            for index, item in enumerate(fixed)
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return npz_path, json_path
