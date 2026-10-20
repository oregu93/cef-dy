"""Visible project-owned numerical E-Q forward model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .background_model import evaluate_background
from .cef_transition_model import (
    CEFTransitions,
    PBNM_DY_4C_TENSOR_CONTRACT_ID,
    calculate_cef_transitions,
    transition_strengths_at_q,
)
from .eq_data import EQDataset
from .magnetic_form_factor import dy3_form_factor_intensity
from .resolution_model import broaden_discrete_transitions


@dataclass(frozen=True)
class EQPrediction:
    signal: NDArray[np.float64]
    background: NDArray[np.float64]
    total_unscaled: NDArray[np.float64]
    transitions: CEFTransitions
    kf_over_ki: NDArray[np.float64]
    ki_Ainv: NDArray[np.float64]
    kf_Ainv: NDArray[np.float64]


NEUTRON_K_AINV_PER_SQRT_MEV = 0.694692


def tas_kinematic_factors(
    ei_meV: NDArray[np.float64], ef_meV: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return explicit TAS ``ki``, ``kf`` and energy-loss ``kf/ki`` factors."""

    ei = np.asarray(ei_meV, dtype=float)
    ef = np.asarray(ef_meV, dtype=float)
    if ei.shape != ef.shape or np.any(~np.isfinite(ei)) or np.any(~np.isfinite(ef)):
        raise ValueError("Ei and Ef must be matching finite arrays")
    if np.any(ei <= 0) or np.any(ef <= 0):
        raise ValueError("Ei and Ef must be positive")
    ki = NEUTRON_K_AINV_PER_SQRT_MEV * np.sqrt(ei)
    kf = NEUTRON_K_AINV_PER_SQRT_MEV * np.sqrt(ef)
    ratio = kf / ki
    for values in (ki, kf, ratio):
        values.setflags(write=False)
    return ki, kf, ratio


def predict_eq_map(
    direct_parameters_meV: Mapping[str, float],
    dataset: EQDataset,
    config: Mapping[str, object],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> EQPrediction:
    """Calculate CEF lines + polarization + form factor + resolution + background."""

    population = config.get("population", {})
    if not isinstance(population, Mapping):
        raise ValueError("forward_model.population must be a mapping")
    mode = str(population.get("mode", "GROUND_DOUBLET_ONLY"))
    temperature: float | None = None
    if mode == "BOLTZMANN_ALL_CEF_STATES":
        if dataset.temperature_K is not None:
            if not np.allclose(dataset.temperature_K, dataset.temperature_K[0], atol=1e-9):
                raise ValueError("Forward model requires one temperature block at a time")
            temperature = float(dataset.temperature_K[0])
        elif population.get("temperature_K") is not None:
            temperature = float(population["temperature_K"])
        else:
            raise ValueError("Boltzmann forward model requires a verified sample temperature")
    transitions = calculate_cef_transitions(
        direct_parameters_meV,
        j=j,
        g_j=g_j,
        population_mode=mode,
        temperature_K=temperature,
    )
    site_model = config.get("dy_site_intensity")
    if not isinstance(site_model, Mapping):
        raise ValueError("forward_model.dy_site_intensity must be a mapping")
    if str(site_model.get("status")) != "IMPLEMENTED_AND_TESTED":
        raise ValueError("Four-Dy-site intensity transport is not implemented and tested")
    if str(site_model.get("contract_id")) != PBNM_DY_4C_TENSOR_CONTRACT_ID:
        raise ValueError("Unexpected four-Dy-site tensor contract")
    if str(site_model.get("combination")) != "INDEPENDENT_LOCALIZED_SITE_SUM":
        raise ValueError("Only the reviewed independent localized four-site sum is supported")
    if bool(site_model.get("inter_site_dynamical_cross_correlations", True)):
        raise ValueError("The current CEF-only forward model cannot include inter-site cross terms")
    strengths = transition_strengths_at_q(
        transitions,
        dataset.qhat_direct,
        dataset.size,
        allow_powder_average=str(config.get("q_direction_policy")) == "EXPLICIT_POWDER_AVERAGE",
        four_site_pbnm_sum=True,
    )
    kinematic = config.get("kinematic_factor", {})
    if not isinstance(kinematic, Mapping):
        raise ValueError("forward_model.kinematic_factor must be a mapping")
    if dataset.ei_meV is not None and dataset.ef_meV is not None:
        ei, ef = dataset.ei_meV, dataset.ef_meV
    elif kinematic.get("fixed_ef_meV") is not None and not bool(
        kinematic.get("require_measured_ei_ef", True)
    ):
        ef = np.full(dataset.size, float(kinematic["fixed_ef_meV"]), dtype=float)
        ei = ef + dataset.energy_meV
    else:
        raise ValueError("Measured Ei_meV and Ef_meV are required for the TAS kf/ki factor")
    ki, kf, kf_over_ki = tas_kinematic_factors(ei, ef)
    amplitudes = (
        strengths
        * transitions.transition_population_factors[None, :]
        * dy3_form_factor_intensity(dataset.q_ainv)[:, None]
        * kf_over_ki[:, None]
    )
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
    return EQPrediction(signal, background, total, transitions, kf_over_ki, ki, kf)
