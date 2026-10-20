"""Visible project-owned numerical E-Q forward model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .background_model import evaluate_background
from .cef_transition_model import CEFTransitions, calculate_cef_transitions, transition_strengths_at_q
from .eq_data import EQDataset
from .magnetic_form_factor import dy3_form_factor_intensity
from .resolution_model import broaden_discrete_transitions


@dataclass(frozen=True)
class EQPrediction:
    signal: NDArray[np.float64]
    background: NDArray[np.float64]
    total_unscaled: NDArray[np.float64]
    transitions: CEFTransitions


def predict_eq_map(
    direct_parameters_meV: Mapping[str, float],
    dataset: EQDataset,
    config: Mapping[str, object],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> EQPrediction:
    """Calculate CEF lines + polarization + form factor + resolution + background."""

    transitions = calculate_cef_transitions(direct_parameters_meV, j=j, g_j=g_j)
    strengths = transition_strengths_at_q(transitions, dataset.qhat_direct, dataset.size)
    amplitudes = strengths * dy3_form_factor_intensity(dataset.q_ainv)[:, None]
    resolution = config["resolution"]
    if not isinstance(resolution, Mapping):
        raise ValueError("forward_model.resolution must be a mapping")
    signal = broaden_discrete_transitions(
        dataset.energy_meV,
        transitions.transition_energies_meV,
        amplitudes,
        resolution,
    )
    background_config = config["background"]
    if not isinstance(background_config, Mapping):
        raise ValueError("forward_model.background must be a mapping")
    background = evaluate_background(dataset.energy_meV, dataset.q_ainv, background_config)
    total = signal + background
    for values in (signal, background, total):
        values.setflags(write=False)
    return EQPrediction(signal, background, total, transitions)
