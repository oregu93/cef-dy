"""User-visible 12-stage exploratory CEF pipeline for VS Code and Colab.

No stage is executed on import. The real search requires both version-controlled
configuration authorization and an explicit command-line flag.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
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
from .g_tensor import g_tensor
from .global_search import SearchIdentity, run_cmaes_multistart
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
from .wavefunctions import export_wavefunctions


STAGES = (
    "01_data_audit",
    "02_cef_forward",
    "03_ins_objective",
    "04_global_search",
    "05_build_ins_ensemble",
    "06_calculate_mh",
    "07_compare_mh",
    "08_joint_objective",
    "09_cluster_solutions",
    "10_export_wavefunctions",
    "11_export_mcphase",
    "12_validate_mcphase",
)


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


def _load_seed(config: Mapping[str, Any], repository: Path) -> dict[str, float]:
    path = _resolve(repository, str(config["inputs"]["historical_seed_bundle"]))
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    parameters = {str(key): float(value) for key, value in payload["parameters"].items()}
    return parameters


def _load_ready_dataset(
    config: Mapping[str, Any], repository: Path
) -> tuple[EQDataset, AppliedMask, dict[str, object]]:
    audit = audit_eq_dataset(config, repository)
    if audit["status"] != "READY_FOR_EXPLORATORY_SEARCH":
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


def stage_01_data_audit(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    report = {
        **audit_eq_dataset(config, repository),
        "config_path": str(config_path),
        "config_hash": sha256_file(config_path),
        "git": git_provenance(repository),
    }
    destination = _output(config, repository, "audit")
    write_json(destination, report)
    return {**report, "report_path": str(destination)}


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
        "transition_energies_meV": prediction.transitions.transition_energies_meV.tolist(),
        "powder_transition_strengths": prediction.transitions.powder_strengths.tolist(),
        "calculated_signal_range": [float(np.min(prediction.signal)), float(np.max(prediction.signal))],
        "background_range": [float(np.min(prediction.background)), float(np.max(prediction.background))],
        "fit_executed": False,
        "audit_status": audit["status"],
        "provenance": _provenance(config_path, repository),
    }
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
        dataset, mask.include, prediction.total_unscaled, config["objective"]
    )
    payload = {
        "status": "OBJECTIVE_SANITY_COMPLETE__NO_OPTIMIZATION",
        "mode": mode.value,
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "objective": objective.as_dict(),
        "mask_hash": audit_eq_dataset(config, repository)["mask_hash"],
        "optimizer_executed": False,
        "provenance": _provenance(config_path, repository),
    }
    destination = _output(config, repository, "objective")
    write_json(destination, payload)
    return {**payload, "output": str(destination)}


def _energy_branch_penalty(
    dataset: EQDataset,
    mask: AppliedMask,
    doublet_energies_meV: np.ndarray,
    branch: int,
    tolerance_meV: float,
) -> tuple[float, float | None]:
    classes = np.asarray(dataset.constraint_classes, dtype=str)
    selected = mask.include & (classes == "ENERGY_CONSTRAINT")
    if not np.any(selected):
        return 0.0, None
    weights = np.maximum(dataset.intensity[selected], 0.0)
    if float(np.sum(weights)) <= 0:
        weights = np.ones(np.count_nonzero(selected))
    centroid = float(np.average(dataset.energy_meV[selected], weights=weights))
    penalty = float(((doublet_energies_meV[branch] - centroid) / tolerance_meV) ** 2)
    return penalty, centroid


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
    identity = SearchIdentity(
        config_hash=sha256_file(config_path),
        dataset_hash=dataset.sha256,
        mask_hash=mask_hash,
        objective_mode=mode.value,
        code_commit=code_commit,
    )

    def evaluator(parameters: Mapping[str, float], branch: int) -> Mapping[str, object]:
        prediction = predict_eq_map(parameters, dataset, config["forward_model"])
        result = eq_map_exploratory_objective(
            dataset, mask.include, prediction.total_unscaled, config["objective"]
        ).as_dict()
        penalty, centroid = _energy_branch_penalty(
            dataset,
            mask,
            prediction.transitions.doublet_energies_meV,
            branch,
            float(config["objective"].get("assignment_energy_tolerance_meV", 1.0)),
        )
        result["energy_constraint"] = float(result["energy_constraint"]) + penalty
        result["total"] = float(result["total"]) + penalty
        result["assignment_branch"] = f"D0->D{branch}"
        result["dataset_energy_centroid_meV"] = centroid
        return result

    search_config = dict(config["search"])
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
        explicit_cli_enable=bool(args.enable_exploratory_search),
        resume=bool(args.resume),
        j=float(config["scientific_scope"]["J"]),
    )


def stage_05_build_ins_ensemble(config: dict[str, Any], config_path: Path, repository: Path, args: argparse.Namespace) -> dict[str, object]:
    candidates_path = _output(config, repository, "search") / "retained_candidates.jsonl"
    if not candidates_path.exists():
        raise FileNotFoundError("Run user stage 04_global_search first")
    candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    threshold = float(config["ensemble"]["compatibility_loss_threshold"])
    by_id: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        if float(candidate["loss"]) <= threshold:
            by_id[str(candidate["candidate_id"])] = candidate
    retained = sorted(by_id.values(), key=lambda row: (str(row["assignment"]), float(row["loss"])))
    payload = {
        "status": "INS_COMPATIBLE_ENSEMBLE_BUILT",
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
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
        "component_distance_matrices": {key: value.tolist() for key, value in components.items()},
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


STAGE_FUNCTIONS: dict[str, Callable[[dict[str, Any], Path, Path, argparse.Namespace], dict[str, object]]] = {
    "01_data_audit": stage_01_data_audit,
    "02_cef_forward": stage_02_cef_forward,
    "03_ins_objective": stage_03_ins_objective,
    "04_global_search": stage_04_global_search,
    "05_build_ins_ensemble": stage_05_build_ins_ensemble,
    "06_calculate_mh": stage_06_calculate_mh,
    "07_compare_mh": stage_07_compare_mh,
    "08_joint_objective": stage_08_joint_objective,
    "09_cluster_solutions": stage_09_cluster_solutions,
    "10_export_wavefunctions": stage_10_export_wavefunctions,
    "11_export_mcphase": stage_11_export_mcphase,
    "12_validate_mcphase": stage_12_validate_mcphase,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cef_fit.user_pipeline")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--config", required=True)
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
