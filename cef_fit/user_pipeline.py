"""User-visible 12-stage exploratory CEF pipeline for VS Code and Colab.

No stage is executed on import. The real search requires both version-controlled
configuration authorization and an explicit command-line flag.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import yaml

from .backends.mcphase_export import compare_mcphase_observables, write_mcphase_bundle
from .cef_model import CEFModel
from .conventions import (
    DIRECT_LM,
    direct_parameters_to_canonical,
    rotate_direct_hamiltonian_to_canonical,
)
from .eq_data import EQDataset, AppliedMask, apply_masks, audit_eq_dataset, load_eq_dataset, load_mask_definition
from .fit_cs15 import parameters_to_h
from .feature_assignments import (
    enumerate_assignment_hypotheses,
    feature_table_identity,
    load_feature_table,
)
from .g_tensor import g_tensor
from .global_search import SearchIdentity, deterministic_initialization_plan, run_cmaes_multistart
from .ins_forward import predict_eq_map
from .ins_objective import eq_map_exploratory_objective, joint_mh_interface, require_objective_mode
from .literature_compare import (
    calculate_frozen_dy_mh,
    load_literature_mh,
    mh_anisotropy_diagnostics,
    mh_curve_diagnostics,
)
from .provenance import git_provenance, sha256_file, write_json
from .solution_clustering import SolutionObservables, cluster_observable_distances, observable_distance_matrix
from .taipan_materializer import MaterializationReport, materialize_taipan_eq_dataset
from .wavefunctions import export_wavefunctions


STAGES = (
    "00_materialize_10k",
    "01_data_audit",
    "02_forward_review",
    "03_objective_review",
    "04_global_search",
    "05_ensemble_summary",
    "06_frozen_mh_screen",
    "07_cluster",
    "08_wavefunctions",
    "09_mcphase_export",
)

DEFAULT_CONFIG = "configs/manuscript_cef_fit_10k_exploratory_v1.yaml"


def load_pipeline_config(path: str | Path) -> tuple[dict[str, Any], Path, Path]:
    config_path = Path(path).expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    repository = config_path.parent.parent
    if config.get("pipeline_id") != "USER_EXECUTED_JOINT_CEF_PIPELINE_V1":
        raise ValueError("Unexpected pipeline_id")
    if bool(config["scientific_scope"].get("exchange_enabled")):
        raise ValueError("Exchange must remain disabled")
    return config, config_path, repository


def _resolve(repository: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else repository / candidate


def _output(config: Mapping[str, Any], repository: Path, key: str) -> Path:
    root = _resolve(repository, str(config["outputs"]["root"]))
    return root / str(config["outputs"][key])


def _feature_table_path(config: Mapping[str, Any], repository: Path) -> Path:
    return _resolve(repository, str(config["inputs"]["feature_table"]))


def _assignment_hypotheses(
    config: Mapping[str, Any], repository: Path
) -> tuple[dict[str, object], ...]:
    features = load_feature_table(_feature_table_path(config, repository))
    final_doublets = tuple(map(int, config["assignments"]["final_doublets"]))
    return tuple(
        hypothesis.as_dict()
        for hypothesis in enumerate_assignment_hypotheses(
            features, final_doublets=final_doublets
        )
    )


def _resolved_search_config(
    config: Mapping[str, Any], profile_override: str | None = None
) -> dict[str, object]:
    raw = config["search"]
    profile = str(profile_override or raw["active_profile"])
    profiles = raw["profiles"]
    if profile not in profiles:
        raise ValueError(f"Unknown search profile {profile}")
    resolved = {
        key: value
        for key, value in raw.items()
        if key not in {"profiles", "active_profile", "retention"}
    }
    resolved.update(dict(profiles[profile]))
    resolved.update(dict(raw.get("retention", {})))
    resolved["profile_id"] = profile
    resolved["h_bounds_meV"] = list(config["parameterization"]["bounds_h_meV"])
    resolved["boundary_fraction"] = float(config["parameterization"]["boundary_fraction"])
    return resolved


def _load_seed(config: Mapping[str, Any], repository: Path) -> dict[str, float]:
    path = _resolve(repository, str(config["inputs"]["historical_seed_bundle"]))
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    parameters = {str(key): float(value) for key, value in payload["parameters"].items()}
    return parameters


def _initialization_plan(
    config: Mapping[str, Any], repository: Path, search: Mapping[str, object]
) -> tuple[dict[str, object], ...]:
    formal_config = yaml.safe_load(
        (repository / "configs/manuscript_fit_v1.yaml").read_text(encoding="utf-8")
    )
    formal = {
        str(key): float(value)
        for key, value in formal_config["pcm"]["formal_parameters_meV"].items()
    }
    seeds: dict[str, np.ndarray] = {
        "PCM_FORMAL": parameters_to_h(formal),
    }
    m0_path = repository / (
        "04_Results/ManuscriptCEFFitV1/MODEL_DEPENDENT_ENERGY_CONDITIONAL_V1/"
        "pcm_conditional_results.csv"
    )
    with m0_path.open(newline="", encoding="utf-8") as handle:
        m0_rows = {
            row["solution_id"]: row for row in csv.DictReader(handle)
        }
    m0_id = "PCM-M0__joint_w6.0_b1_per_block__D1"
    seeds["PCM_M0"] = parameters_to_h(
        {name: value * float(m0_rows[m0_id]["scale"]) for name, value in formal.items()}
    )
    bundle_root = repository / (
        "04_Results/Stage03R/STAGE03R-CS15-PREDICTION-BUNDLE-MATERIALIZATION-001"
    )
    for label in ("R3", "R5", "R7"):
        payload = yaml.safe_load(
            (bundle_root / f"PB-CS15-HIST-B2-{label}.yaml").read_text(encoding="utf-8")
        )
        seeds[f"HISTORICAL_{label}"] = parameters_to_h(
            {str(key): float(value) for key, value in payload["parameters"].items()}
        )
    lower, upper = map(float, search["h_bounds_meV"])
    return deterministic_initialization_plan(
        seeds,
        restart_count=int(search["restarts_per_assignment"]),
        lower=lower,
        upper=upper,
        base_seed=int(search["base_seed"]),
    )


def _load_ready_dataset(
    config: Mapping[str, Any], repository: Path
) -> tuple[EQDataset, AppliedMask, dict[str, object]]:
    materialization = _materialize_if_configured(config, repository)
    audit = audit_eq_dataset(
        config,
        repository,
        materialization.as_dict() if materialization is not None else None,
    )
    if audit["status"] != "READY_FOR_EXPLORATORY_SANITY_RUN":
        raise RuntimeError(f"TAIPAN dataset is not ready: {audit.get('blockers', [])}")
    inputs = config["inputs"]
    dataset = load_eq_dataset(
        _resolve(repository, str(inputs["taipan_eq_dataset"])),
        str(inputs["intensity_domain"]),
    )
    mask = apply_masks(
        dataset,
        load_mask_definition(_resolve(repository, str(inputs["taipan_mask_definition"]))),
    )
    return dataset, mask, audit


def _materialize_if_configured(
    config: Mapping[str, Any], repository: Path
) -> MaterializationReport | None:
    inputs = config["inputs"]
    if not bool(inputs.get("auto_materialize_stage02r", False)):
        return None
    reuse_path = _resolve(repository, str(inputs["taipan_reuse_map"]))
    output_path = _resolve(repository, str(inputs["taipan_eq_dataset"]))
    return materialize_taipan_eq_dataset(reuse_path, repository, output_path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _provenance(config_path: Path, repository: Path) -> dict[str, object]:
    return {
        "config_path": str(config_path),
        "config_hash": sha256_file(config_path),
        "git": git_provenance(repository),
    }


def _parameters(candidate: Mapping[str, object]) -> dict[str, float]:
    raw = candidate["direct_parameters_meV"]
    if not isinstance(raw, Mapping):
        raise ValueError("Candidate direct_parameters_meV must be a mapping")
    return {str(key): float(value) for key, value in raw.items()}


def _write_dataset_diagnostic_figure(
    dataset: EQDataset,
    mask: AppliedMask,
    audit: Mapping[str, object],
    destination: Path,
) -> Path:
    """Plot the materialized dataset without a temperature or model claim."""

    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "Install the optional 'cef' dependencies to create the dataset diagnostic figure"
        ) from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(10, 6))
    plotted = axis.scatter(
        dataset.q_ainv,
        dataset.energy_meV,
        c=dataset.intensity,
        s=15,
        cmap="viridis",
        label="materialized discovery points",
    )
    excluded = ~np.asarray(mask.include, dtype=bool)
    if np.any(excluded):
        axis.scatter(
            dataset.q_ainv[excluded],
            dataset.energy_meV[excluded],
            facecolors="none",
            edgecolors="0.45",
            linewidths=0.35,
            s=25,
            label="excluded from model use",
        )
    diagnostic_44 = np.asarray(
        [
            bool({"BF-006", "BF-007", "BF-008"}.intersection(identifiers))
            for identifiers in dataset.feature_ids
        ],
        dtype=bool,
    )
    if np.any(diagnostic_44):
        axis.scatter(
            dataset.q_ainv[diagnostic_44],
            dataset.energy_meV[diagnostic_44],
            marker="x",
            s=18,
            color="tab:red",
            linewidths=0.6,
            label="44 meV diagnostic / possibly mixed",
        )
    for window in audit.get("blind_feature_windows", []):
        if not isinstance(window, Mapping):
            continue
        feature_id = str(window["feature_id"])
        axis.axhspan(
            float(window["energy_min_meV"]),
            float(window["energy_max_meV"]),
            color=(
                "tab:gray"
                if feature_id in {"BF-006", "BF-007", "BF-008"}
                else "tab:orange"
            ),
            alpha=0.055,
        )
    axis.text(
        0.01,
        0.99,
        "Temperature unresolved; no model overlay; no fitting",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "0.8"},
    )
    axis.set_xlabel(r"$|Q|$ ($\AA^{-1}$)")
    axis.set_ylabel("Energy transfer (meV)")
    axis.set_title("TAIPAN discovery-only materialized dataset diagnostic")
    axis.legend(loc="best")
    figure.colorbar(plotted, ax=axis, label="detector / monitor (linear)")
    figure.tight_layout()
    figure.savefig(destination, dpi=180)
    plt.close(figure)
    return destination


def stage_00_materialize_10k(
    config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace
) -> dict[str, object]:
    """Materialize only the accepted discovery 10-K block; never touch holdout detectors."""

    report = materialize_taipan_eq_dataset(
        _resolve(repository, str(config["inputs"]["taipan_reuse_map"])),
        repository,
        _resolve(repository, str(config["inputs"]["taipan_eq_dataset"])),
    )
    if report.ten_k_scan_count != 20 or report.holdout_detector_access_count != 0:
        raise RuntimeError("10-K materialization identity or holdout safety check failed")
    table_path = _feature_table_path(config, repository)
    table_payload = yaml.safe_load(table_path.read_text(encoding="utf-8"))
    if str(table_payload["source_dataset_sha256"]) != report.output_sha256:
        raise RuntimeError("Feature table is not bound to the materialized 10-K dataset")
    hypotheses = _assignment_hypotheses(config, repository)
    payload = {
        **report.as_dict(),
        "DISCOVERY_ONLY": True,
        "HOLDOUT_DETECTOR_ACCESS_COUNT": 0,
        "feature_table": feature_table_identity(table_path),
        "assignment_branch_count": len(hypotheses),
        "real_scientific_optimization_executed": False,
        "provenance": _provenance(config_path, repository),
    }
    destination = _output(config, repository, "materialization")
    write_json(destination, payload)
    return {**payload, "report_path": str(destination)}


def stage_01_data_audit(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    materialization = _materialize_if_configured(config, repository)
    audit = audit_eq_dataset(
        config,
        repository,
        materialization.as_dict() if materialization is not None else None,
    )
    dataset_figure: str | None = None
    dataset_path = _resolve(repository, str(config["inputs"]["taipan_eq_dataset"]))
    mask_path = _resolve(repository, str(config["inputs"]["taipan_mask_definition"]))
    if dataset_path.exists() and mask_path.exists():
        dataset = load_eq_dataset(dataset_path, str(config["inputs"]["intensity_domain"]))
        mask = apply_masks(dataset, load_mask_definition(mask_path))
        dataset_figure = str(
            _write_dataset_diagnostic_figure(
                dataset,
                mask,
                audit,
                _output(config, repository, "dataset_diagnostic_figure"),
            )
        )
    report = {
        **audit,
        "materialization": materialization.as_dict() if materialization is not None else None,
        "data_materialization_status": (
            "PASS"
            if materialization is not None and materialization.output_rows > 0
            else "NOT_MATERIALIZED"
        ),
        "scientific_search_readiness": audit["status"],
        "q_geometry_status": (
            "PASS"
            if audit.get("q_direction_status") == "PER_POINT_DIRECT_B_C_A"
            else "BLOCKED"
        ),
        "discovery_holdout_status": (
            "PASS"
            if audit.get("holdout_points_used") == 0
            and audit.get("holdout_detector_access_count") == 0
            else "FAIL"
        ),
        "temperature_mapping_status": (
            "PASS"
            if audit.get("ten_k_block_status")
            in {"VERIFIED", "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"}
            else "BLOCKED"
        ),
        "exploratory_search_status": (
            "READY"
            if audit["status"] == "READY_FOR_EXPLORATORY_SANITY_RUN"
            and not audit.get("search_blockers")
            else "NOT_READY"
        ),
        "feature_44p4_status": (
            "VISIBLE_DIAGNOSTIC__DIAGNOSTIC_OR_POSSIBLY_MIXED__OBJECTIVE_EXCLUDED"
        ),
        "primary_count_control_mode": "monitor_controlled",
        "mandatory_cef_assignments_from_b001": [],
        "dataset_diagnostic_figure": dataset_figure,
        "model_overlay_generated": False,
        "pre_search_diagnostic_figure": (
            "PENDING_02_CEF_FORWARD"
            if audit["status"] == "READY_FOR_EXPLORATORY_SANITY_RUN"
            else "BLOCKED_BY_TEMPERATURE_MAPPING"
        ),
        "RUN_EXPLORATORY_SEARCH": False,
        "NEW_BLM_RESULT_GENERATED": False,
        "config_path": str(config_path),
        "config_hash": sha256_file(config_path),
        "git": git_provenance(repository),
    }
    destination = _output(config, repository, "audit")
    write_json(destination, report)
    return {**report, "report_path": str(destination)}


def _write_pre_search_figure(
    dataset: EQDataset,
    mask: AppliedMask,
    prediction,
    audit: Mapping[str, object],
    destination: Path,
) -> Path:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError("Install the optional 'cef' dependencies to create the diagnostic figure") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(10, 6))
    included = np.asarray(mask.include, dtype=bool)
    plotted = axis.scatter(
        dataset.q_ainv[included],
        dataset.energy_meV[included],
        c=dataset.intensity[included],
        s=13,
        cmap="viridis",
        label="verified-temperature discovery points",
    )
    excluded = ~included
    if np.any(excluded):
        axis.scatter(
            dataset.q_ainv[excluded],
            dataset.energy_meV[excluded],
            marker="x",
            s=12,
            color="0.65",
            alpha=0.6,
            label="excluded / diagnostic",
        )
    windows = audit.get("blind_feature_windows", [])
    for window in windows:
        if isinstance(window, Mapping):
            feature_id = str(window["feature_id"])
            axis.axhspan(
                float(window["energy_min_meV"]),
                float(window["energy_max_meV"]),
                color="tab:gray" if feature_id in {"BF-006", "BF-007", "BF-008"} else "tab:orange",
                alpha=0.07,
            )
    for energy in prediction.transitions.transition_energies_meV:
        axis.axhline(float(energy), color="tab:red", linewidth=0.7, alpha=0.5)
    axis.set_xlabel(r"$|Q|$ ($\AA^{-1}$)")
    axis.set_ylabel("Energy transfer (meV)")
    axis.set_title("TAIPAN verified-temperature review; frozen seed, no fitted Blm")
    axis.legend(loc="best")
    figure.colorbar(plotted, ax=axis, label="detector / monitor (linear)")
    figure.tight_layout()
    figure.savefig(destination, dpi=180)
    plt.close(figure)
    return destination


def stage_02_cef_forward(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    dataset, mask, audit = _load_ready_dataset(config, repository)
    parameters = _load_seed(config, repository)
    prediction = predict_eq_map(
        parameters,
        dataset,
        config["forward_model"],
        j=float(config["scientific_scope"]["J"]),
        g_j=float(config["scientific_scope"]["gJ"]),
    )
    payload = {
        "status": "FORWARD_SANITY_COMPLETE__NO_FIT",
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "seed_role": config["inputs"]["historical_seed_role"],
        "dataset_hash": dataset.sha256,
        "included_points": int(np.count_nonzero(mask.include)),
        "doublet_energies_meV": prediction.transitions.doublet_energies_meV.tolist(),
        "population_mode": prediction.transitions.population_mode,
        "temperature_K": prediction.transitions.temperature_K,
        "thermal_populations": prediction.transitions.doublet_populations.tolist(),
        "transition_initial_doublets": prediction.transitions.initial_doublets.tolist(),
        "transition_final_doublets": prediction.transitions.final_doublets.tolist(),
        "transition_energies_meV": prediction.transitions.transition_energies_meV.tolist(),
        "powder_transition_strengths": prediction.transitions.powder_strengths.tolist(),
        "transition_population_factors": prediction.transitions.transition_population_factors.tolist(),
        "kf_over_ki_range": [float(np.min(prediction.kf_over_ki)), float(np.max(prediction.kf_over_ki))],
        "ki_Ainv_range": [float(np.min(prediction.ki_Ainv)), float(np.max(prediction.ki_Ainv))],
        "kf_Ainv_range": [float(np.min(prediction.kf_Ainv)), float(np.max(prediction.kf_Ainv))],
        "q_polarization_status": audit["q_direction_status"],
        "resolution_settings": config["forward_model"]["resolution"],
        "background_settings": config["forward_model"]["background"],
        "calculated_signal_range": [float(np.min(prediction.signal)), float(np.max(prediction.signal))],
        "background_range": [float(np.min(prediction.background)), float(np.max(prediction.background))],
        "fit_executed": False,
        "audit_status": audit["status"],
        "provenance": _provenance(config_path, repository),
    }
    figure_path = _write_pre_search_figure(
        dataset,
        mask,
        prediction,
        audit,
        _output(config, repository, "pre_search_figure"),
    )
    payload["pre_search_diagnostic_figure"] = str(figure_path)
    destination = _output(config, repository, "forward")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def stage_03_ins_objective(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    mode = require_objective_mode(
        str(config["objective"]["mode"]),
        bool(config["switches"]["ENABLE_MANUSCRIPT_OBJECTIVE"]),
    )
    dataset, mask, _ = _load_ready_dataset(config, repository)
    parameters = _load_seed(config, repository)
    prediction = predict_eq_map(parameters, dataset, config["forward_model"])
    objective = eq_map_exploratory_objective(
        dataset,
        mask.include,
        prediction.signal,
        config["objective"],
        background_config=config["forward_model"]["background"],
    )
    hypotheses = _assignment_hypotheses(config, repository)
    branch_reviews = []
    for hypothesis in hypotheses:
        energy, diagnostics = _explicit_feature_energy_penalty(
            dataset, mask, prediction.transitions, hypothesis
        )
        weights = objective.component_weights
        total = (
            weights["energy"] * energy
            + weights["shape"] * objective.spectral_shape_constraint
            + weights["relative_intensity"]
            * objective.exploratory_relative_intensity_constraint
        )
        branch_reviews.append(
            {
                "assignment_id": hypothesis["assignment_id"],
                "L_energy": energy,
                "L_shape": objective.spectral_shape_constraint,
                "L_relative_intensity": objective.exploratory_relative_intensity_constraint,
                "L_total": float(total),
                "feature_residuals": diagnostics,
            }
        )
    payload = {
        "status": "OBJECTIVE_SANITY_COMPLETE__NO_OPTIMIZATION",
        "mode": mode.value,
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "objective": objective.as_dict(),
        "weight_policy": config["objective"]["weight_policy"],
        "calibration_status": config["objective"]["calibration_status"],
        "assignment_branch_count": len(hypotheses),
        "assignment_branch_reviews": branch_reviews,
        "mask_hash": audit_eq_dataset(config, repository)["mask_hash"],
        "optimizer_executed": False,
        "provenance": _provenance(config_path, repository),
    }
    destination = _output(config, repository, "objective")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def _explicit_feature_energy_penalty(
    dataset: EQDataset,
    mask: AppliedMask,
    transitions,
    hypothesis: Mapping[str, object],
) -> tuple[float, list[dict[str, object]]]:
    mappings = hypothesis.get("mappings", [])
    if not isinstance(mappings, (list, tuple)) or not mappings:
        raise ValueError("Each assignment hypothesis requires explicit feature mappings")
    diagnostics: list[dict[str, object]] = []
    losses: list[float] = []
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise ValueError("Feature assignment mapping must be a mapping")
        feature_id = str(mapping["feature_id"])
        initial = int(mapping["initial_doublet"])
        final = int(mapping["final_doublet"])
        sigma = float(mapping["sigma_meV"])
        if sigma <= 0:
            raise ValueError("Explicit feature energy sigma must be positive")
        selected = mask.include & np.asarray(
            [feature_id in identifiers for identifiers in dataset.feature_ids], dtype=bool
        )
        if not np.any(selected):
            raise ValueError(f"Assigned feature {feature_id} has no included measured points")
        observed = float(mapping["observed_energy_meV"])
        transition_match = np.flatnonzero(
            (transitions.initial_doublets == initial) & (transitions.final_doublets == final)
        )
        if transition_match.size != 1:
            raise ValueError(f"Calculated transition D{initial}->D{final} is unavailable")
        predicted = float(transitions.transition_energies_meV[int(transition_match[0])])
        loss = float(((predicted - observed) / sigma) ** 2)
        losses.append(loss)
        diagnostics.append(
            {
                "feature_id": feature_id,
                "assignment": f"D{initial}->D{final}",
                "observed_feature_reference_meV": observed,
                "predicted_transition_meV": predicted,
                "sigma_meV": sigma,
                "sigma_semantics": "EXPLORATORY_FEATURE_WINDOW_SCALE_NOT_STATISTICAL_SIGMA",
                "support_point_count": int(np.count_nonzero(selected)),
                "loss": loss,
            }
        )
    return float(np.mean(losses)), diagnostics


def stage_04_global_search(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    mode = require_objective_mode(
        str(config["objective"]["mode"]),
        bool(config["switches"]["ENABLE_MANUSCRIPT_OBJECTIVE"]),
    )
    if mode.value != "EQ_MAP_EXPLORATORY_OBJECTIVE":
        raise ValueError("The initial real search is configured for EQ_MAP_EXPLORATORY_OBJECTIVE")
    dataset, mask, audit = _load_ready_dataset(config, repository)
    mask_hash = str(audit["mask_hash"])
    code_commit = str(git_provenance(repository)["head"])
    hypotheses = _assignment_hypotheses(config, repository)
    feature_path = _feature_table_path(config, repository)
    search_config = _resolved_search_config(config, args.search_profile)
    assignment_set_hash = hashlib.sha256(
        json.dumps(hypotheses, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    identity = SearchIdentity(
        config_hash=sha256_file(config_path),
        dataset_hash=dataset.sha256,
        mask_hash=mask_hash,
        objective_mode=mode.value,
        code_commit=code_commit,
        feature_table_hash=sha256_file(feature_path),
        assignment_set_hash=assignment_set_hash,
        parameter_convention=str(config["parameterization"]["search_coordinates"]),
        resolution_variant=str(config["forward_model"]["resolution"]["variant_id"]),
        background_variant=str(config["forward_model"]["background"]["variant_id"]),
        search_profile=str(search_config["profile_id"]),
    )

    def evaluator(parameters: Mapping[str, float], branch: int) -> Mapping[str, object]:
        prediction = predict_eq_map(parameters, dataset, config["forward_model"])
        result = eq_map_exploratory_objective(
            dataset,
            mask.include,
            prediction.signal,
            config["objective"],
            background_config=config["forward_model"]["background"],
        ).as_dict()
        penalty, diagnostics = _explicit_feature_energy_penalty(
            dataset,
            mask,
            prediction.transitions,
            hypotheses[branch - 1],
        )
        weight = float(result["component_weights"]["energy"])
        result["energy_constraint"] = penalty
        result["raw_components"]["L_energy"] = float(
            sum(float(row["loss"]) for row in diagnostics)
        )
        result["normalized_components"]["L_energy"] = penalty
        result["total"] = float(result["total"]) + weight * penalty
        result["assignment_hypothesis"] = hypotheses[branch - 1]["assignment_id"]
        result["explicit_feature_assignments"] = diagnostics
        result["doublet_energies_meV"] = prediction.transitions.doublet_energies_meV.tolist()
        result["transition_list"] = [
            {
                "initial_doublet": int(initial),
                "final_doublet": int(final),
                "energy_meV": float(energy),
                "initial_population": float(
                    prediction.transitions.doublet_populations[int(initial)]
                ),
                "population_factor": float(population),
                "predicted_powder_strength": float(strength),
            }
            for initial, final, energy, population, strength in zip(
                prediction.transitions.initial_doublets,
                prediction.transitions.final_doublets,
                prediction.transitions.transition_energies_meV,
                prediction.transitions.transition_population_factors,
                prediction.transitions.powder_strengths,
                strict=True,
            )
        ]
        return result

    search_config["assignment_branches"] = list(range(1, len(hypotheses) + 1))
    search_config["assignment_ids"] = {
        str(index): hypothesis["assignment_id"]
        for index, hypothesis in enumerate(hypotheses, start=1)
    }
    search_config["run_exploratory_search"] = bool(
        config["switches"]["RUN_EXPLORATORY_SEARCH"]
        and search_config.get("run_exploratory_search", False)
    )
    return run_cmaes_multistart(
        search_config=search_config,
        seed_parameters=_load_seed(config, repository),
        identity=identity,
        repository=repository,
        output_directory=_output(config, repository, "search"),
        evaluator=evaluator,
        initialization_plan=_initialization_plan(config, repository, search_config),
        explicit_cli_enable=bool(args.enable_exploratory_search),
        resume=bool(args.resume),
        j=float(config["scientific_scope"]["J"]),
    )


def stage_05_build_ins_ensemble(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    candidates_path = _output(config, repository, "search") / "retained_candidates.jsonl"
    if not candidates_path.exists():
        raise FileNotFoundError("Run user stage 04_global_search first")
    candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        if candidate.get("candidate_status") == "SEARCH_RETAINED_CANDIDATE":
            by_id[str(candidate["candidate_id"])] = candidate
    retained = sorted(by_id.values(), key=lambda row: (str(row["assignment"]), float(row["loss"])))
    payload = {
        "status": "SEARCH_RETAINED_ENSEMBLE_PENDING_SCIENTIFIC_REVIEW",
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "scientific_compatibility_status": "NOT_ASSESSED",
        "single_best_selected": False,
        "secondary_minima_retained": True,
        "source_candidates_hash": sha256_file(candidates_path),
        "source_candidates_path": str(candidates_path),
        "candidate_count": len(retained),
        "candidates": retained,
        "provenance": _provenance(config_path, repository),
    }
    destination = _output(config, repository, "ensemble")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def _literature(config: Mapping[str, Any], repository: Path):
    return load_literature_mh(
        _resolve(repository, str(config["inputs"]["literature_magnetization"])),
        _resolve(repository, str(config["inputs"]["literature_magnetization_inventory"])),
    )


def stage_06_calculate_mh(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    ensemble = _load_json(_output(config, repository, "ensemble"))
    ensemble_path = _output(config, repository, "ensemble")
    literature = _literature(config, repository)
    rows: list[dict[str, object]] = []
    for candidate in ensemble["candidates"]:
        rows.extend(
            calculate_frozen_dy_mh(
                _parameters(candidate),
                literature,
                str(candidate["candidate_id"]),
                j=float(config["scientific_scope"]["J"]),
                g_j=float(config["scientific_scope"]["gJ"]),
            )
        )
    payload = {
        "status": "FROZEN_SINGLE_ION_MH_COMPLETE",
        "blm_refit_performed": False,
        "exchange_enabled": False,
        "formal_mh_ranking_performed": False,
        "source_commit": literature.source_commit,
        "unavailable_comparators": list(literature.unavailable_comparators),
        "input_hashes": {
            "ensemble": sha256_file(ensemble_path),
            "literature_points": sha256_file(
                _resolve(repository, str(config["inputs"]["literature_magnetization"]))
            ),
            "literature_inventory": sha256_file(
                _resolve(
                    repository,
                    str(config["inputs"]["literature_magnetization_inventory"]),
                )
            ),
        },
        "provenance": _provenance(config_path, repository),
        "rows": rows,
    }
    destination = _output(config, repository, "mh")
    write_json(destination, payload)
    return {"status": payload["status"], "row_count": len(rows), "output": str(destination)}


def stage_07_compare_mh(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    mh = _load_json(_output(config, repository, "mh"))
    mh_path = _output(config, repository, "mh")
    diagnostics = mh_curve_diagnostics(mh["rows"])
    anisotropy = mh_anisotropy_diagnostics(mh["rows"])
    payload = {
        "status": "MH_VALIDATION_DIAGNOSTICS_COMPLETE",
        "formal_chi_square_ranking_performed": False,
        "families_screened_or_selected": False,
        "semantic_boundary": "DY_ONLY_CALCULATION_VS_TOTAL_BULK_EXPERIMENT",
        "diagnostics": diagnostics,
        "anisotropy_diagnostics": anisotropy,
        "input_mh_hash": sha256_file(mh_path),
        "provenance": _provenance(config_path, repository),
    }
    destination = _output(config, repository, "mh_comparison")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def stage_08_joint_objective(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    joint = config["joint_mh"]
    payload: dict[str, object] = {
        "status": "JOINT_MH_INTERFACE_DISABLED",
        "ENABLE_JOINT_MH_FIT": bool(config["switches"]["ENABLE_JOINT_MH_FIT"]),
        "accepted_bulk_contribution_model": joint["accepted_bulk_contribution_model"],
        "arbitrary_offset_allowed": False,
        "arbitrary_normalization_allowed": False,
        "fit_executed": False,
        "provenance": _provenance(config_path, repository),
    }
    if bool(config["switches"]["ENABLE_JOINT_MH_FIT"]):
        joint_mh_interface(
            0.0,
            0.0,
            float(joint["lambda_M"]),
            enabled=True,
            accepted_bulk_contribution_model=joint["accepted_bulk_contribution_model"],
        )
    destination = _output(config, repository, "joint_interface")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def _mh_vectors(path: Path) -> dict[str, np.ndarray]:
    payload = _load_json(path)
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in payload["rows"]:
        grouped.setdefault(str(row["candidate_id"]), []).append(row)
    result = {}
    for candidate, rows in grouped.items():
        rows.sort(key=lambda row: (str(row["axis_abc"]), float(row["temperature_K"]), float(row["field_T"])))
        result[candidate] = np.asarray([float(row["M_Dy_CEF_muB_per_Dy"]) for row in rows])
    return result


def stage_09_cluster_solutions(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    ensemble = _load_json(_output(config, repository, "ensemble"))
    mh_vectors = _mh_vectors(_output(config, repository, "mh"))
    candidates = ensemble["candidates"]
    solutions: list[SolutionObservables] = []
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        parameters = _parameters(candidate)
        model = CEFModel.from_coefficients(parameters, DIRECT_LM)
        system = model.eigensystem()
        transitions = model.ground_transitions(system)
        ground_g = g_tensor(system.pair(0))
        solutions.append(
            SolutionObservables(
                solution_id=candidate_id,
                h_coordinates_meV=np.asarray(parameters_to_h(parameters)),
                doublet_energies_meV=system.doublet_energies_meV,
                projectors=np.stack(system.projectors),
                transition_strengths=np.asarray([row.powder_strength for row in transitions]),
                g_principal_values=ground_g.principal_values,
                g_principal_axes=ground_g.principal_axes,
                mh_predictions=mh_vectors[candidate_id],
            )
        )
    clustering = config["clustering"]
    distances, components = observable_distance_matrix(
        solutions, clustering["weights"], clustering["scales"]
    )
    labels = cluster_observable_distances(
        distances,
        float(clustering["distance_threshold"]),
        str(clustering["method"]),
        (
            int(clustering["cluster_count"])
            if clustering.get("cluster_count") is not None
            else None
        ),
    )
    physical_weights = {
        name: float(weight)
        for name, weight in clustering["weights"].items()
        if name != "parameter"
    }
    physical_norm = max(sum(physical_weights.values()), np.finfo(float).eps)
    physical_distances = np.sqrt(
        sum(
            (weight / physical_norm) * np.square(components[name])
            for name, weight in physical_weights.items()
        )
    )
    clusters = []
    for cluster_id in sorted(set(map(int, labels))):
        member_indices = np.flatnonzero(labels == cluster_id)
        submatrix = distances[np.ix_(member_indices, member_indices)]
        medoid_index = int(member_indices[int(np.argmin(np.sum(submatrix, axis=1)))])
        clusters.append(
            {
                "cluster_id": f"FAMILY-{cluster_id:03d}",
                "members": [solutions[index].solution_id for index in member_indices],
                "representative_candidate_id": solutions[medoid_index].solution_id,
                "representative_rule": "OBSERVABLE_DISTANCE_MEDOID__REQUIRES_USER_REVIEW",
            }
        )
    payload = {
        "status": "PRELIMINARY_OBSERVABLE_AWARE_CLUSTERING",
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "features": list(clustering["weights"]),
        "weights": clustering["weights"],
        "solution_ids": [solution.solution_id for solution in solutions],
        "distance_matrix": distances.tolist(),
        "parameter_similarity_distance_matrix": components["parameter"].tolist(),
        "physical_observable_similarity_distance_matrix": physical_distances.tolist(),
        "component_distance_matrices": {key: value.tolist() for key, value in components.items()},
        "feature_standardization": {
            "enabled": bool(clustering.get("standardize_features", True)),
            "method": "DECLARED_PHYSICAL_SCALES",
            "scales": clustering["scales"],
        },
        "cluster_selection": {
            "distance_threshold": clustering["distance_threshold"],
            "cluster_count": clustering.get("cluster_count"),
        },
        "clusters": clusters,
        "physical_family_review_required": True,
        "input_hashes": {
            "ensemble": sha256_file(_output(config, repository, "ensemble")),
            "frozen_mh": sha256_file(_output(config, repository, "mh")),
        },
        "provenance": _provenance(config_path, repository),
    }
    destination = _output(config, repository, "clustering")
    write_json(destination, payload)
    return {"status": payload["status"], "cluster_count": len(clusters), "output": str(destination)}


def _representatives(config: Mapping[str, Any], repository: Path) -> list[dict[str, object]]:
    ensemble = _load_json(_output(config, repository, "ensemble"))
    clusters = _load_json(_output(config, repository, "clustering"))
    by_id = {str(row["candidate_id"]): row for row in ensemble["candidates"]}
    return [by_id[str(cluster["representative_candidate_id"])] for cluster in clusters["clusters"]]


def stage_10_export_wavefunctions(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    destination = _output(config, repository, "wavefunctions")
    rows = []
    for candidate in _representatives(config, repository):
        candidate_id = str(candidate["candidate_id"])
        model = CEFModel.from_coefficients(_parameters(candidate), DIRECT_LM)
        system = model.eigensystem()
        transitions = model.ground_transitions(system)
        g_tensors = [g_tensor(system.pair(index)) for index in range(8)]
        npz_path, json_path = export_wavefunctions(
            destination / candidate_id,
            tuple(system.pair(index) for index in range(8)),
            metadata={
                "candidate_id": candidate_id,
                "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
                "projectors_are_primary": True,
                "individual_kramers_states_are_gauge_conventional": True,
            },
        )
        summary = {
            "candidate_id": candidate_id,
            "doublet_energies_meV": system.doublet_energies_meV.tolist(),
            "transition_tensors": [
                {"real": row.tensor.real.tolist(), "imag": row.tensor.imag.tolist()}
                for row in transitions
            ],
            "transition_strengths": [row.powder_strength for row in transitions],
            "g_tensors": [
                {
                    "matrix": tensor.matrix.tolist(),
                    "principal_values": tensor.principal_values.tolist(),
                    "principal_axes_direct": tensor.principal_axes.tolist(),
                }
                for tensor in g_tensors
            ],
            "wavefunction_npz": str(npz_path),
            "wavefunction_json": str(json_path),
        }
        write_json(destination / f"{candidate_id}.observables.json", summary)
        rows.append(summary)
    manifest = {
        "status": "REPRESENTATIVE_WAVEFUNCTION_EXPORT_COMPLETE",
        "count": len(rows),
        "candidate_ids": [row["candidate_id"] for row in rows],
        "input_clustering_hash": sha256_file(_output(config, repository, "clustering")),
        "provenance": _provenance(config_path, repository),
    }
    write_json(destination / "export_manifest.json", manifest)
    return {**manifest, "output": str(destination)}


def stage_11_export_mcphase(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    destination = _output(config, repository, "mcphase")
    exports = []
    for candidate in _representatives(config, repository):
        candidate_id = str(candidate["candidate_id"])
        canonical = direct_parameters_to_canonical(_parameters(candidate))
        parameter_path, metadata_path = write_mcphase_bundle(
            destination,
            candidate_id,
            canonical.coefficients,
            {
                "canonical_projection_relative_residual": canonical.relative_residual,
                "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
                "mcphase_execution_performed": False,
            },
        )
        exports.append({"candidate_id": candidate_id, "parameters": str(parameter_path), "metadata": str(metadata_path)})
    manifest = {
        "status": "MCPHASE_EXPORT_COMPLETE__VALIDATION_NOT_RUN",
        "mismatch_status": "VALIDATION_BLOCKER",
        "automatic_blm_modification_allowed": False,
        "count": len(exports),
        "exports": exports,
        "input_clustering_hash": sha256_file(_output(config, repository, "clustering")),
        "provenance": _provenance(config_path, repository),
    }
    write_json(destination / "export_manifest.json", manifest)
    return manifest


def stage_12_validate_mcphase(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    if not args.mcphase_levels:
        raise ValueError("Provide --mcphase-levels from a visible independent user McPhase run")
    external = _load_json(Path(args.mcphase_levels).expanduser().resolve())
    mh_vectors = _mh_vectors(_output(config, repository, "mh"))
    results = []
    for candidate in _representatives(config, repository):
        candidate_id = str(candidate["candidate_id"])
        model = CEFModel.from_coefficients(_parameters(candidate), DIRECT_LM)
        project = model.eigensystem()
        ground_g = g_tensor(project.pair(0))
        result = compare_mcphase_observables(
            project_levels_meV=project.doublet_energies_meV,
            project_canonical_hamiltonian_meV=rotate_direct_hamiltonian_to_canonical(
                model.hamiltonian_meV, float(config["scientific_scope"]["J"])
            ),
            project_g_principal_values=ground_g.principal_values,
            project_mh_muB_per_Dy=mh_vectors[candidate_id],
            external=external[candidate_id],
            level_tolerance_meV=float(config["mcphase"]["level_tolerance_meV"]),
        )
        results.append({"candidate_id": candidate_id, **result})
    payload = {
        "status": "MCPHASE_OBSERVABLE_VALIDATION_COMPLETE",
        "automatic_refit_performed": False,
        "external_result_path": str(Path(args.mcphase_levels).expanduser().resolve()),
        "external_result_hash": sha256_file(Path(args.mcphase_levels).expanduser().resolve()),
        "provenance": _provenance(config_path, repository),
        "results": results,
    }
    destination = _output(config, repository, "mcphase_validation")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def stage_06_frozen_mh_screen(
    config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace
) -> dict[str, object]:
    calculated = stage_06_calculate_mh(config, config_path, repository, args)
    compared = stage_07_compare_mh(config, config_path, repository, args)
    return {
        "status": "INDEPENDENT_FROZEN_CANDIDATE_SCREEN_COMPLETE",
        "blm_refit_performed": False,
        "joint_mh_fit_enabled": False,
        "calculation": calculated,
        "diagnostics": compared,
    }


STAGE_FUNCTIONS: dict[str, Callable[[dict[str, Any], Path, Path, argparse.Namespace], dict[str, object]]] = {
    "00_materialize_10k": stage_00_materialize_10k,
    "01_data_audit": stage_01_data_audit,
    "02_forward_review": stage_02_cef_forward,
    "03_objective_review": stage_03_ins_objective,
    "04_global_search": stage_04_global_search,
    "05_ensemble_summary": stage_05_build_ins_ensemble,
    "06_frozen_mh_screen": stage_06_frozen_mh_screen,
    "07_cluster": stage_09_cluster_solutions,
    "08_wavefunctions": stage_10_export_wavefunctions,
    "09_mcphase_export": stage_11_export_mcphase,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cef_fit.user_pipeline")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument(
        "--search-profile",
        choices=("SMOKE_SEARCH", "FIRST_EXPLORATORY_SEARCH", "EXTENDED_SEARCH"),
    )
    parser.add_argument("--enable-exploratory-search", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--mcphase-levels")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config, config_path, repository = load_pipeline_config(args.config)
    payload = STAGE_FUNCTIONS[args.stage](config, config_path, repository, args)
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
