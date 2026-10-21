"""Guarded user-executed CMA-ES multistart search with strict checkpoint identity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
import platform
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike

from .fit_cs15 import h_to_parameters, parameters_to_h
from .provenance import git_provenance, write_json


@dataclass(frozen=True)
class SearchIdentity:
    config_hash: str
    dataset_hash: str
    mask_hash: str
    objective_mode: str
    code_commit: str
    feature_table_hash: str = "NOT_BOUND"
    assignment_set_hash: str = "NOT_BOUND"
    parameter_convention: str = "DIRECT_CS15_H_EQUALS_KAPPA_B"
    resolution_variant: str = "NOT_BOUND"
    background_variant: str = "NOT_BOUND"
    search_profile: str = "NOT_BOUND"


@dataclass(frozen=True)
class SearchCheckpoint:
    schema_version: int
    identity: SearchIdentity
    assignment_branch: int | None
    restart_number: int | None
    seed: int | None
    elapsed_evaluations: int
    completed_restarts: tuple[str, ...]
    current_best_candidates: tuple[dict[str, object], ...]
    optimizer_state_policy: str
    optimizer_state: dict[str, object]
    environment: dict[str, str]
    assignment_id: str | None = None
    initialization_family: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["identity"] = asdict(self.identity)
        return payload


def deterministic_restart_seed(base_seed: int, assignment_branch: int, restart_number: int) -> int:
    if assignment_branch < 1 or restart_number < 1:
        raise ValueError("assignment_branch and restart_number must be positive")
    return int(base_seed + 1009 * assignment_branch + 104729 * restart_number)


def deterministic_initialization_plan(
    seed_families: Mapping[str, ArrayLike],
    *,
    restart_count: int,
    lower: float,
    upper: float,
    base_seed: int,
) -> tuple[dict[str, object], ...]:
    """Mix reviewed seed families with deterministic space-filling points."""

    if restart_count < 1 or not lower < upper:
        raise ValueError("restart_count must be positive and lower < upper")
    converted: list[tuple[str, np.ndarray]] = []
    dimension: int | None = None
    for family, raw in seed_families.items():
        vector = np.asarray(raw, dtype=float)
        if vector.ndim != 1 or np.any(~np.isfinite(vector)):
            raise ValueError(f"Initialization family {family} must be a finite vector")
        if dimension is None:
            dimension = vector.size
        elif vector.size != dimension:
            raise ValueError("Initialization families must have the same dimension")
        converted.append((str(family), np.clip(vector, lower, upper)))
    if dimension is None:
        raise ValueError("At least one reviewed initialization family is required")
    plan: list[dict[str, object]] = []
    for family, vector in converted[:restart_count]:
        plan.append(
            {
                "initialization_family": family,
                "initial_mean_h": vector.tolist(),
                "source_role": "INITIALIZATION_ONLY",
            }
        )
    generator = np.random.default_rng(int(base_seed))
    remaining = restart_count - len(plan)
    latin = np.empty((remaining, dimension), dtype=float)
    for coordinate in range(dimension):
        latin[:, coordinate] = (
            generator.permutation(remaining) + generator.random(remaining)
        ) / remaining
    for index, unit_point in enumerate(latin):
        point = lower + (upper - lower) * unit_point
        plan.append(
            {
                "initialization_family": f"LATIN_HYPERCUBE_{index + 1:03d}",
                "initial_mean_h": point.tolist(),
                "source_role": "INITIALIZATION_ONLY",
            }
        )
    return tuple(plan)


def load_checkpoint(path: str | Path) -> SearchCheckpoint:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = SearchIdentity(**payload["identity"])
    return SearchCheckpoint(
        schema_version=int(payload["schema_version"]),
        identity=identity,
        assignment_branch=payload.get("assignment_branch"),
        restart_number=payload.get("restart_number"),
        seed=payload.get("seed"),
        elapsed_evaluations=int(payload.get("elapsed_evaluations", 0)),
        completed_restarts=tuple(payload.get("completed_restarts", ())),
        current_best_candidates=tuple(payload.get("current_best_candidates", ())),
        optimizer_state_policy=str(payload["optimizer_state_policy"]),
        optimizer_state=dict(payload.get("optimizer_state", {})),
        environment=dict(payload.get("environment", {})),
        assignment_id=payload.get("assignment_id"),
        initialization_family=payload.get("initialization_family"),
    )


def validate_checkpoint_identity(
    checkpoint: SearchCheckpoint,
    expected: SearchIdentity,
) -> None:
    mismatches = [
        name
        for name in asdict(expected)
        if getattr(checkpoint.identity, name) != getattr(expected, name)
    ]
    if mismatches:
        raise ValueError(
            "Checkpoint identity mismatch; refusing resume for: " + ", ".join(mismatches)
        )


def require_search_authorization(config_enabled: bool, explicit_cli_enable: bool) -> None:
    if not config_enabled:
        raise PermissionError("RUN_EXPLORATORY_SEARCH is false in configuration")
    if not explicit_cli_enable:
        raise PermissionError("Pass --enable-exploratory-search for an explicit user execution")


def boundary_diagnostics(
    h_coordinates: ArrayLike,
    lower: float,
    upper: float,
    boundary_fraction: float,
) -> dict[str, object]:
    h = np.asarray(h_coordinates, dtype=float)
    if h.ndim != 1 or np.any(~np.isfinite(h)) or not lower < upper:
        raise ValueError("Finite 1-D coordinates and lower < upper are required")
    if not 0.0 <= boundary_fraction < 0.5:
        raise ValueError("boundary_fraction must be in [0, 0.5)")
    distances = np.minimum(h - lower, upper - h)
    occupied = bool(np.any(distances <= boundary_fraction * (upper - lower)))
    return {
        "boundary_distances_h_meV": distances.tolist(),
        "minimum_boundary_distance_h_meV": float(np.min(distances)),
        "search_boundary_occupied": occupied,
        "boundary_status": (
            "SEARCH_DOMAIN_SENSITIVITY_REVIEW_REQUIRED"
            if occupied
            else "WITHIN_SEARCH_DOMAIN_INTERIOR"
        ),
    }


def _environment() -> dict[str, str]:
    packages = {}
    for name in ("numpy", "scipy", "cma", "dyfeo3-cef-fit"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "NOT_INSTALLED"
    return {"python": platform.python_version(), **packages}


def _restart_key(assignment: int, restart: int) -> str:
    return f"D{assignment}:R{restart}"


_FORKED_EVALUATOR: Callable[[Mapping[str, float], int], Mapping[str, object]] | None = None


def _atomic_write_json(path: str | Path, payload: object) -> Path:
    """Replace one JSON artifact atomically, including under process interruption."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def _atomic_write_jsonl(path: str | Path, rows: Sequence[Mapping[str, object]]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def _restart_checkpoint_path(directory: Path, assignment: int, restart: int) -> Path:
    return directory / f"D{assignment:03d}_R{restart:03d}.json"


def _candidate_sort_key(candidate: Mapping[str, object]) -> tuple[object, ...]:
    return (
        float(candidate["loss"]),
        int(candidate["assignment_hypothesis_index"]),
        int(candidate["restart"]),
        int(candidate.get("retention_rank_within_restart", 1)),
        str(candidate["candidate_id"]),
    )


def _merge_candidates(
    candidates: Sequence[Mapping[str, object]], maximum_retained: int
) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    for raw in candidates:
        candidate = dict(raw)
        by_id[str(candidate["candidate_id"])] = candidate
    return sorted(by_id.values(), key=_candidate_sort_key)[:maximum_retained]


def _write_restart_checkpoint(
    task: Mapping[str, object],
    *,
    status: str,
    restart_evaluations: int,
    candidates: Sequence[Mapping[str, object]],
    optimizer_state: Mapping[str, object],
    result: Mapping[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "identity": task["identity"],
        "restart_key": task["restart_key"],
        "assignment_branch": task["assignment"],
        "restart_number": task["restart"],
        "seed": task["seed"],
        "assignment_id": task["assignment_id"],
        "initialization_family": task["initialization_family"],
        "status": status,
        "restart_evaluations": restart_evaluations,
        "best_candidates": list(candidates),
        "optimizer_state_policy": "RESTART_INCOMPLETE_RESTART_FROM_FIXED_SEED",
        "optimizer_state": dict(optimizer_state),
        "environment": task["environment"],
    }
    if result is not None:
        payload["result"] = dict(result)
    _atomic_write_json(str(task["checkpoint_path"]), payload)


def _execute_restart_trajectory(
    task: Mapping[str, object],
    evaluator: Callable[[Mapping[str, float], int], Mapping[str, object]],
) -> dict[str, object]:
    """Run exactly one deterministic assignment/restart CMA-ES trajectory."""

    try:
        import cma  # type: ignore
    except ImportError as error:
        raise RuntimeError("Install the optional 'cef' dependencies to run CMA-ES") from error

    assignment = int(task["assignment"])
    restart = int(task["restart"])
    seed = int(task["seed"])
    population = int(task["population"])
    max_evaluations = int(task["max_evaluations"])
    lower = float(task["lower"])
    upper = float(task["upper"])
    sigma0 = float(task["sigma0"])
    retained_per_restart = int(task["retained_per_restart"])
    boundary_fraction = float(task["boundary_fraction"])
    j = float(task["j"])
    restart_initial_h = np.asarray(task["initial_mean_h"], dtype=float)
    options = {
        "bounds": [lower, upper],
        "seed": seed,
        "popsize": population,
        "maxfevals": max_evaluations,
        "verb_disp": 0,
        "verbose": -9,
    }
    strategy = cma.CMAEvolutionStrategy(restart_initial_h.tolist(), sigma0, options)
    restart_evaluations = 0
    restart_candidates: list[dict[str, object]] = []
    while not strategy.stop() and restart_evaluations < max_evaluations:
        proposed = strategy.ask()
        evaluated: list[tuple[float, dict[str, object], np.ndarray]] = []
        for h_values in proposed:
            h = np.clip(np.asarray(h_values, dtype=float), lower, upper)
            parameters = h_to_parameters(h, j=j)
            diagnostics = dict(evaluator(parameters, assignment))
            loss = float(diagnostics["total"])
            if not np.isfinite(loss):
                loss = float(np.finfo(float).max / 1.0e100)
            evaluated.append((loss, diagnostics, h))
        strategy.tell(proposed, [row[0] for row in evaluated])
        restart_evaluations += len(evaluated)
        for loss, diagnostics, h in evaluated:
            if (
                len(restart_candidates) < retained_per_restart
                or loss < float(restart_candidates[-1]["loss"])
            ):
                boundary_report = boundary_diagnostics(h, lower, upper, boundary_fraction)
                candidate = {
                    "candidate_id": (
                        f"D{assignment}-R{restart}-"
                        + hashlib.sha256(np.asarray(h, dtype="<f8").tobytes()).hexdigest()[:16]
                    ),
                    "candidate_status": "SEARCH_RETAINED_CANDIDATE",
                    "scientific_compatibility_status": "NOT_ASSESSED",
                    "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
                    "assignment": task["assignment_id"],
                    "assignment_id": task["assignment_id"],
                    "assignment_hypothesis_index": assignment,
                    "restart": restart,
                    "seed": seed,
                    "initialization_family": task["initialization_family"],
                    "initial_mean_h": restart_initial_h.tolist(),
                    "bounds_h_meV": [lower, upper],
                    "loss": loss,
                    "objective_total": loss,
                    "objective": diagnostics,
                    "L_energy": diagnostics.get("energy_constraint"),
                    "L_shape": diagnostics.get("spectral_shape_constraint"),
                    "L_relative_intensity": diagnostics.get(
                        "exploratory_relative_intensity_constraint"
                    ),
                    "raw_component_diagnostics": diagnostics.get("raw_components"),
                    "nuisance_signal_scales": diagnostics.get("block_scales"),
                    "background_parameters": diagnostics.get("background_parameters"),
                    "feature_wise_residuals": diagnostics.get(
                        "explicit_feature_assignments"
                    ),
                    "doublet_energies_meV": diagnostics.get("doublet_energies_meV"),
                    "transition_list": diagnostics.get("transition_list"),
                    "direct_parameters_meV": h_to_parameters(h, j=j),
                    "h_coordinates_meV": h.tolist(),
                    **boundary_report,
                    "search_budget": {
                        "population": population,
                        "max_evaluations_per_restart": max_evaluations,
                    },
                    "project_owned_kernel_reevaluated": True,
                }
                restart_candidates.append(candidate)
                restart_candidates.sort(key=lambda row: float(row["loss"]))
                del restart_candidates[retained_per_restart:]
        _write_restart_checkpoint(
            task,
            status="INCOMPLETE__RERUN_FROM_FIXED_SEED_ON_RESUME",
            restart_evaluations=restart_evaluations,
            candidates=restart_candidates,
            optimizer_state={
                "generation": int(strategy.countiter),
                "mean_h_coordinates_meV": np.asarray(strategy.mean, dtype=float).tolist(),
                "sigma_meV": float(strategy.sigma),
                "covariance": np.asarray(strategy.sm.C, dtype=float).tolist(),
                "resume_semantics": (
                    "INSPECTION_ONLY__INCOMPLETE_RESTART_REPEATED_FROM_SEED"
                ),
                "initialization_family": task["initialization_family"],
                "initial_mean_h": restart_initial_h.tolist(),
                "bounds_h_meV": [lower, upper],
                "current_restart_best_candidates": restart_candidates,
            },
        )
    for rank, candidate in enumerate(restart_candidates, start=1):
        candidate["retention_rank_within_restart"] = rank
    result = {
        "restart_key": task["restart_key"],
        "assignment_branch": assignment,
        "restart_number": restart,
        "seed": seed,
        "restart_evaluations": restart_evaluations,
        "candidates": restart_candidates,
    }
    _write_restart_checkpoint(
        task,
        status="COMPLETE",
        restart_evaluations=restart_evaluations,
        candidates=restart_candidates,
        optimizer_state={
            "restart_complete": True,
            "restart_key": task["restart_key"],
        },
        result=result,
    )
    return result


def _execute_forked_restart(task: Mapping[str, object]) -> dict[str, object]:
    if _FORKED_EVALUATOR is None:
        raise RuntimeError("Forked evaluator context was not initialized")
    return _execute_restart_trajectory(task, _FORKED_EVALUATOR)


def _load_completed_restart(
    path: Path,
    identity: SearchIdentity,
    expected_keys: set[str],
) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        observed_identity = SearchIdentity(**payload["identity"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"Restart checkpoint corruption: {path}") from error
    validate_checkpoint_identity(
        SearchCheckpoint(
            1,
            observed_identity,
            None,
            None,
            None,
            0,
            (),
            (),
            "RESTART_INCOMPLETE_RESTART_FROM_FIXED_SEED",
            {},
            {},
        ),
        identity,
    )
    if str(payload.get("status")) != "COMPLETE":
        return None
    result = dict(payload["result"])
    key = str(result["restart_key"])
    if key not in expected_keys or key != str(payload["restart_key"]):
        raise ValueError(f"Unexpected restart identity in {path}")
    return result


def _run_cmaes_multistart_serial(
    *,
    search_config: Mapping[str, object],
    seed_parameters: Mapping[str, float],
    identity: SearchIdentity,
    repository: str | Path,
    output_directory: str | Path,
    evaluator: Callable[[Mapping[str, float], int], Mapping[str, object]],
    initialization_plan: Sequence[Mapping[str, object]] | None = None,
    explicit_cli_enable: bool,
    resume: bool = False,
    j: float = 7.5,
) -> dict[str, object]:
    """Run the real campaign only after two independent user safety switches.

    An incomplete restart is repeated from its deterministic seed on resume.
    Completed restarts and retained candidates are recoverable from JSON. Every
    external CMA-ES candidate is re-evaluated by the supplied project evaluator.
    """

    require_search_authorization(
        bool(search_config.get("run_exploratory_search", False)), explicit_cli_enable
    )
    if str(search_config.get("backend")) != "CMA_ES":
        raise ValueError("This entrypoint currently supports backend=CMA_ES")
    try:
        import cma  # type: ignore
    except ImportError as error:
        raise RuntimeError("Install the optional 'cef' dependencies to run CMA-ES") from error
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "search_checkpoint.json"
    candidates_path = output / "retained_candidates.jsonl"
    completed: set[str] = set()
    retained: list[dict[str, object]] = []
    total_evaluations = 0
    if resume:
        if not checkpoint_path.exists():
            raise FileNotFoundError("--resume requested but search_checkpoint.json is absent")
        prior = load_checkpoint(checkpoint_path)
        validate_checkpoint_identity(prior, identity)
        completed.update(prior.completed_restarts)
        retained.extend(prior.current_best_candidates)
        total_evaluations = prior.elapsed_evaluations
    elif checkpoint_path.exists():
        raise FileExistsError("Checkpoint exists; use --resume or choose a new output directory")

    assignments = tuple(int(value) for value in search_config["assignment_branches"])
    if not assignments:
        raise ValueError("No explicit feature-to-transition assignment hypotheses are configured")
    if any(value < 1 for value in assignments) or len(assignments) != len(set(assignments)):
        raise ValueError("assignment_branches must be unique positive indices")
    restart_count = int(search_config["restarts_per_assignment"])
    population = int(search_config["population"])
    max_evaluations = int(search_config["max_evaluations_per_restart"])
    base_seed = int(search_config["base_seed"])
    lower, upper = map(float, search_config["h_bounds_meV"])
    sigma0 = float(search_config["sigma0_meV"])
    maximum_retained = int(search_config.get("maximum_retained_candidates", 10000))
    additional_near_best = int(search_config.get("additional_near_best_per_restart", 0))
    if additional_near_best < 0:
        raise ValueError("additional_near_best_per_restart must be non-negative")
    retained_per_restart = 1 + additional_near_best
    if maximum_retained < len(assignments) * restart_count * retained_per_restart:
        raise ValueError(
            "maximum_retained_candidates is too small for the configured per-restart retention"
        )
    boundary_fraction = float(search_config.get("boundary_fraction", 0.02))
    if not 0.0 <= boundary_fraction < 0.5:
        raise ValueError("boundary_fraction must be in [0, 0.5)")
    initial_h = np.clip(parameters_to_h(seed_parameters, j=j), lower, upper)
    plan = tuple(initialization_plan or ())
    if plan and len(plan) != restart_count:
        raise ValueError("initialization_plan must contain exactly one entry per restart")
    provenance = git_provenance(repository)

    def save_checkpoint(
        assignment: int | None,
        restart: int | None,
        seed: int | None,
        assignment_id: str | None = None,
        initialization_family: str | None = None,
        optimizer_state: Mapping[str, object] | None = None,
    ) -> None:
        checkpoint = SearchCheckpoint(
            schema_version=1,
            identity=identity,
            assignment_branch=assignment,
            restart_number=restart,
            seed=seed,
            elapsed_evaluations=total_evaluations,
            completed_restarts=tuple(sorted(completed)),
            current_best_candidates=tuple(retained[-maximum_retained:]),
            optimizer_state_policy="RESTART_INCOMPLETE_RESTART_FROM_FIXED_SEED",
            optimizer_state=dict(optimizer_state or {}),
            environment=_environment(),
            assignment_id=assignment_id,
            initialization_family=initialization_family,
        )
        write_json(checkpoint_path, checkpoint.as_dict())

    for assignment in assignments:
        for restart in range(1, restart_count + 1):
            key = _restart_key(assignment, restart)
            if key in completed:
                continue
            seed = deterministic_restart_seed(base_seed, assignment, restart)
            initialization = (
                plan[restart - 1]
                if plan
                else {
                    "initialization_family": "LEGACY_SINGLE_SEED",
                    "initial_mean_h": initial_h.tolist(),
                    "source_role": "INITIALIZATION_ONLY",
                }
            )
            restart_initial_h = np.asarray(initialization["initial_mean_h"], dtype=float)
            if restart_initial_h.shape != initial_h.shape:
                raise ValueError("initial_mean_h shape does not match the Cs15 dimension")
            options = {
                "bounds": [lower, upper],
                "seed": seed,
                "popsize": population,
                "maxfevals": max_evaluations,
                "verb_disp": 0,
                "verbose": -9,
            }
            strategy = cma.CMAEvolutionStrategy(restart_initial_h.tolist(), sigma0, options)
            restart_evaluations = 0
            restart_candidates: list[dict[str, object]] = []
            assignment_ids = search_config.get("assignment_ids", {})
            if not isinstance(assignment_ids, Mapping):
                raise ValueError("assignment_ids must map branch indices to stable IDs")
            assignment_id = str(
                assignment_ids.get(str(assignment), f"EXPLICIT_HYPOTHESIS_{assignment}")
            )
            while not strategy.stop() and restart_evaluations < max_evaluations:
                proposed = strategy.ask()
                evaluated: list[tuple[float, dict[str, object], np.ndarray]] = []
                for h_values in proposed:
                    h = np.clip(np.asarray(h_values, dtype=float), lower, upper)
                    parameters = h_to_parameters(h, j=j)
                    diagnostics = dict(evaluator(parameters, assignment))
                    loss = float(diagnostics["total"])
                    if not np.isfinite(loss):
                        loss = float(np.finfo(float).max / 1.0e100)
                    evaluated.append((loss, diagnostics, h))
                strategy.tell(proposed, [row[0] for row in evaluated])
                total_evaluations += len(evaluated)
                restart_evaluations += len(evaluated)
                for loss, diagnostics, h in evaluated:
                    if (
                        len(restart_candidates) < retained_per_restart
                        or loss < float(restart_candidates[-1]["loss"])
                    ):
                        boundary_report = boundary_diagnostics(
                            h, lower, upper, boundary_fraction
                        )
                        candidate = {
                            "candidate_id": (
                                f"D{assignment}-R{restart}-"
                                + hashlib.sha256(np.asarray(h, dtype="<f8").tobytes()).hexdigest()[:16]
                            ),
                            "candidate_status": "SEARCH_RETAINED_CANDIDATE",
                            "scientific_compatibility_status": "NOT_ASSESSED",
                            "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
                            "assignment": assignment_id,
                            "assignment_id": assignment_id,
                            "assignment_hypothesis_index": assignment,
                            "restart": restart,
                            "seed": seed,
                            "initialization_family": initialization["initialization_family"],
                            "initial_mean_h": restart_initial_h.tolist(),
                            "bounds_h_meV": [lower, upper],
                            "loss": loss,
                            "objective_total": loss,
                            "objective": diagnostics,
                            "L_energy": diagnostics.get("energy_constraint"),
                            "L_shape": diagnostics.get("spectral_shape_constraint"),
                            "L_relative_intensity": diagnostics.get(
                                "exploratory_relative_intensity_constraint"
                            ),
                            "raw_component_diagnostics": diagnostics.get("raw_components"),
                            "nuisance_signal_scales": diagnostics.get("block_scales"),
                            "background_parameters": diagnostics.get("background_parameters"),
                            "feature_wise_residuals": diagnostics.get(
                                "explicit_feature_assignments"
                            ),
                            "doublet_energies_meV": diagnostics.get("doublet_energies_meV"),
                            "transition_list": diagnostics.get("transition_list"),
                            "direct_parameters_meV": h_to_parameters(h, j=j),
                            "h_coordinates_meV": h.tolist(),
                            **boundary_report,
                            "search_budget": {
                                "population": population,
                                "max_evaluations_per_restart": max_evaluations,
                            },
                            "project_owned_kernel_reevaluated": True,
                        }
                        restart_candidates.append(candidate)
                        restart_candidates.sort(key=lambda row: float(row["loss"]))
                        del restart_candidates[retained_per_restart:]
                save_checkpoint(
                    assignment,
                    restart,
                    seed,
                    assignment_id,
                    str(initialization["initialization_family"]),
                    {
                        "generation": int(strategy.countiter),
                        "mean_h_coordinates_meV": np.asarray(strategy.mean, dtype=float).tolist(),
                        "sigma_meV": float(strategy.sigma),
                        "covariance": np.asarray(strategy.sm.C, dtype=float).tolist(),
                        "resume_semantics": "INSPECTION_ONLY__INCOMPLETE_RESTART_REPEATED_FROM_SEED",
                        "initialization_family": initialization["initialization_family"],
                        "initial_mean_h": restart_initial_h.tolist(),
                        "bounds_h_meV": [lower, upper],
                        "current_restart_best_candidates": restart_candidates,
                    },
                )
            if restart_candidates:
                for rank, candidate in enumerate(restart_candidates, start=1):
                    candidate["retention_rank_within_restart"] = rank
                retained.extend(restart_candidates)
                retained[:] = sorted(retained, key=lambda row: float(row["loss"]))[
                    :maximum_retained
                ]
            completed.add(key)
            save_checkpoint(
                assignment,
                restart,
                seed,
                assignment_id,
                str(initialization["initialization_family"]),
                {"restart_complete": True, "restart_key": key},
            )

    with candidates_path.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in retained:
            handle.write(json.dumps(candidate, sort_keys=True) + "\n")
    summary = {
        "status": str(
            search_config.get("output_status", "USER_EXECUTED_EXPLORATORY_SEARCH_COMPLETE")
        ),
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "retention_status": "SEARCH_RETAINED_CANDIDATE",
        "scientific_compatibility_status": "NOT_ASSESSED",
        "unique_solution_claim": False,
        "physical_clusters_selected": False,
        "identity": asdict(identity),
        "backend": "CMA_ES_WITH_PROJECT_OWNED_REEVALUATION",
        "worker_model": "SERIAL_RESTART_TRAJECTORIES",
        "configured_workers": 1,
        "effective_workers": 1,
        "completed_restarts": len(completed),
        "elapsed_evaluations": total_evaluations,
        "retained_candidate_count": len(retained),
        "checkpoint": str(checkpoint_path),
        "candidates": str(candidates_path),
        "git": provenance,
    }
    write_json(output / "search_summary.json", summary)
    return summary


def _run_cmaes_parallel_coordinator(
    *,
    search_config: Mapping[str, object],
    seed_parameters: Mapping[str, float],
    identity: SearchIdentity,
    repository: str | Path,
    output_directory: str | Path,
    evaluator: Callable[[Mapping[str, float], int], Mapping[str, object]],
    initialization_plan: Sequence[Mapping[str, object]] | None,
    explicit_cli_enable: bool,
    resume: bool,
    workers: int,
    j: float,
) -> dict[str, object]:
    """Coordinate isolated deterministic restart trajectories across forked processes."""

    require_search_authorization(
        bool(search_config.get("run_exploratory_search", False)), explicit_cli_enable
    )
    if str(search_config.get("backend")) != "CMA_ES":
        raise ValueError("This entrypoint currently supports backend=CMA_ES")
    try:
        import cma  # type: ignore  # noqa: F401
    except ImportError as error:
        raise RuntimeError("Install the optional 'cef' dependencies to run CMA-ES") from error
    if workers < 1:
        raise ValueError("workers must be a positive integer")

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "search_checkpoint.json"
    candidates_path = output / "retained_candidates.jsonl"
    restart_directory = output / "restart_checkpoints"
    existing_restart_files = tuple(restart_directory.glob("*.json"))
    if not resume and (checkpoint_path.exists() or existing_restart_files):
        raise FileExistsError(
            "Checkpoint exists; use --resume or choose a new output directory"
        )
    restart_directory.mkdir(parents=True, exist_ok=True)

    assignments = tuple(int(value) for value in search_config["assignment_branches"])
    if not assignments:
        raise ValueError("No explicit feature-to-transition assignment hypotheses are configured")
    if any(value < 1 for value in assignments) or len(assignments) != len(set(assignments)):
        raise ValueError("assignment_branches must be unique positive indices")
    restart_count = int(search_config["restarts_per_assignment"])
    population = int(search_config["population"])
    max_evaluations = int(search_config["max_evaluations_per_restart"])
    base_seed = int(search_config["base_seed"])
    lower, upper = map(float, search_config["h_bounds_meV"])
    sigma0 = float(search_config["sigma0_meV"])
    maximum_retained = int(search_config.get("maximum_retained_candidates", 10000))
    additional_near_best = int(search_config.get("additional_near_best_per_restart", 0))
    if restart_count < 1 or population < 1 or max_evaluations < 1:
        raise ValueError("restart, population, and evaluation counts must be positive")
    if additional_near_best < 0:
        raise ValueError("additional_near_best_per_restart must be non-negative")
    retained_per_restart = 1 + additional_near_best
    if maximum_retained < len(assignments) * restart_count * retained_per_restart:
        raise ValueError(
            "maximum_retained_candidates is too small for the configured per-restart retention"
        )
    boundary_fraction = float(search_config.get("boundary_fraction", 0.02))
    if not 0.0 <= boundary_fraction < 0.5:
        raise ValueError("boundary_fraction must be in [0, 0.5)")
    initial_h = np.clip(parameters_to_h(seed_parameters, j=j), lower, upper)
    plan = tuple(initialization_plan or ())
    if plan and len(plan) != restart_count:
        raise ValueError("initialization_plan must contain exactly one entry per restart")
    assignment_ids = search_config.get("assignment_ids", {})
    if not isinstance(assignment_ids, Mapping):
        raise ValueError("assignment_ids must map branch indices to stable IDs")

    environment = _environment()
    tasks: list[dict[str, object]] = []
    for assignment in assignments:
        for restart in range(1, restart_count + 1):
            initialization = (
                plan[restart - 1]
                if plan
                else {
                    "initialization_family": "LEGACY_SINGLE_SEED",
                    "initial_mean_h": initial_h.tolist(),
                    "source_role": "INITIALIZATION_ONLY",
                }
            )
            restart_initial_h = np.asarray(initialization["initial_mean_h"], dtype=float)
            if restart_initial_h.shape != initial_h.shape:
                raise ValueError("initial_mean_h shape does not match the Cs15 dimension")
            key = _restart_key(assignment, restart)
            tasks.append(
                {
                    "restart_key": key,
                    "assignment": assignment,
                    "restart": restart,
                    "seed": deterministic_restart_seed(base_seed, assignment, restart),
                    "assignment_id": str(
                        assignment_ids.get(
                            str(assignment), f"EXPLICIT_HYPOTHESIS_{assignment}"
                        )
                    ),
                    "initialization_family": str(
                        initialization["initialization_family"]
                    ),
                    "initial_mean_h": restart_initial_h.tolist(),
                    "population": population,
                    "max_evaluations": max_evaluations,
                    "lower": lower,
                    "upper": upper,
                    "sigma0": sigma0,
                    "retained_per_restart": retained_per_restart,
                    "boundary_fraction": boundary_fraction,
                    "j": j,
                    "checkpoint_path": str(
                        _restart_checkpoint_path(restart_directory, assignment, restart)
                    ),
                    "identity": asdict(identity),
                    "environment": environment,
                }
            )
    task_by_key = {str(task["restart_key"]): task for task in tasks}
    if len(task_by_key) != len(tasks):
        raise ValueError("Duplicate assignment/restart trajectory identity")
    expected_keys = set(task_by_key)

    completed: set[str] = set()
    retained: list[dict[str, object]] = []
    total_evaluations = 0
    if resume:
        if not checkpoint_path.exists():
            raise FileNotFoundError("--resume requested but search_checkpoint.json is absent")
        prior = load_checkpoint(checkpoint_path)
        validate_checkpoint_identity(prior, identity)
        completed.update(prior.completed_restarts)
        if not completed.issubset(expected_keys):
            raise ValueError("Checkpoint contains unknown assignment/restart identities")
        retained = _merge_candidates(prior.current_best_candidates, maximum_retained)
        total_evaluations = prior.elapsed_evaluations

    for path in sorted(restart_directory.glob("*.json")):
        result = _load_completed_restart(path, identity, expected_keys)
        if result is None:
            continue
        key = str(result["restart_key"])
        task = task_by_key[key]
        if (
            int(result["assignment_branch"]) != int(task["assignment"])
            or int(result["restart_number"]) != int(task["restart"])
            or int(result["seed"]) != int(task["seed"])
        ):
            raise ValueError(f"Restart identity or seed mismatch in {path}")
        if key not in completed:
            completed.add(key)
            total_evaluations += int(result["restart_evaluations"])
            retained = _merge_candidates(
                [*retained, *result.get("candidates", [])], maximum_retained
            )

    provenance = git_provenance(repository)

    def save_coordinator_checkpoint(
        task: Mapping[str, object] | None,
        optimizer_state: Mapping[str, object],
    ) -> None:
        checkpoint = SearchCheckpoint(
            schema_version=1,
            identity=identity,
            assignment_branch=(int(task["assignment"]) if task is not None else None),
            restart_number=(int(task["restart"]) if task is not None else None),
            seed=(int(task["seed"]) if task is not None else None),
            elapsed_evaluations=total_evaluations,
            completed_restarts=tuple(sorted(completed)),
            current_best_candidates=tuple(retained),
            optimizer_state_policy="RESTART_INCOMPLETE_RESTART_FROM_FIXED_SEED",
            optimizer_state=dict(optimizer_state),
            environment=environment,
            assignment_id=(str(task["assignment_id"]) if task is not None else None),
            initialization_family=(
                str(task["initialization_family"]) if task is not None else None
            ),
        )
        _atomic_write_json(checkpoint_path, checkpoint.as_dict())

    save_coordinator_checkpoint(
        None,
        {
            "coordinator_status": "READY",
            "worker_model": "PROCESS_PER_INDEPENDENT_RESTART_TRAJECTORY",
        },
    )
    pending = [task for task in tasks if str(task["restart_key"]) not in completed]
    effective_workers = min(workers, max(1, len(pending)))

    def record_completion(result: Mapping[str, object]) -> None:
        nonlocal retained, total_evaluations
        key = str(result["restart_key"])
        if key in completed:
            raise ValueError(f"Duplicate completed restart returned by worker: {key}")
        task = task_by_key[key]
        if int(result["seed"]) != int(task["seed"]):
            raise ValueError(f"Worker seed mismatch for {key}")
        completed.add(key)
        total_evaluations += int(result["restart_evaluations"])
        retained = _merge_candidates(
            [*retained, *result.get("candidates", [])], maximum_retained
        )
        save_coordinator_checkpoint(
            task,
            {
                "coordinator_status": "RUNNING",
                "last_completed_restart": key,
                "completed_restart_count": len(completed),
                "worker_model": "PROCESS_PER_INDEPENDENT_RESTART_TRAJECTORY",
            },
        )

    if effective_workers == 1:
        for task in pending:
            record_completion(_execute_restart_trajectory(task, evaluator))
    elif pending:
        if "fork" not in multiprocessing.get_all_start_methods():
            raise RuntimeError(
                "workers>1 requires the POSIX fork start method for the project evaluator"
            )
        global _FORKED_EVALUATOR
        _FORKED_EVALUATOR = evaluator
        context = multiprocessing.get_context("fork")
        try:
            with context.Pool(processes=effective_workers) as pool:
                for result in pool.imap_unordered(
                    _execute_forked_restart, pending, chunksize=1
                ):
                    record_completion(result)
        finally:
            _FORKED_EVALUATOR = None

    if completed != expected_keys:
        missing = sorted(expected_keys - completed)
        raise RuntimeError(f"Search ended with incomplete restart trajectories: {missing}")
    final_task = tasks[-1] if tasks else None
    save_coordinator_checkpoint(
        final_task,
        {
            "coordinator_status": "COMPLETE",
            "completed_restart_count": len(completed),
            "worker_model": "PROCESS_PER_INDEPENDENT_RESTART_TRAJECTORY",
        },
    )
    _atomic_write_jsonl(candidates_path, retained)
    summary = {
        "status": str(
            search_config.get("output_status", "USER_EXECUTED_EXPLORATORY_SEARCH_COMPLETE")
        ),
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "retention_status": "SEARCH_RETAINED_CANDIDATE",
        "scientific_compatibility_status": "NOT_ASSESSED",
        "unique_solution_claim": False,
        "physical_clusters_selected": False,
        "identity": asdict(identity),
        "backend": "CMA_ES_WITH_PROJECT_OWNED_REEVALUATION",
        "worker_model": "PROCESS_PER_INDEPENDENT_RESTART_TRAJECTORY",
        "configured_workers": workers,
        "effective_workers": effective_workers,
        "completed_restarts": len(completed),
        "elapsed_evaluations": total_evaluations,
        "retained_candidate_count": len(retained),
        "checkpoint": str(checkpoint_path),
        "restart_checkpoint_directory": str(restart_directory),
        "candidates": str(candidates_path),
        "git": provenance,
    }
    _atomic_write_json(output / "search_summary.json", summary)
    return summary


def run_cmaes_multistart(
    *,
    search_config: Mapping[str, object],
    seed_parameters: Mapping[str, float],
    identity: SearchIdentity,
    repository: str | Path,
    output_directory: str | Path,
    evaluator: Callable[[Mapping[str, float], int], Mapping[str, object]],
    initialization_plan: Sequence[Mapping[str, object]] | None = None,
    explicit_cli_enable: bool,
    resume: bool = False,
    j: float = 7.5,
) -> dict[str, object]:
    """Run serially by default or isolate complete restarts across worker processes."""

    workers = int(search_config.get("workers", 1))
    if workers < 1:
        raise ValueError("workers must be a positive integer")
    restart_directory = Path(output_directory) / "restart_checkpoints"
    resuming_parallel_run = resume and restart_directory.exists()
    if workers == 1 and not resuming_parallel_run:
        return _run_cmaes_multistart_serial(
            search_config=search_config,
            seed_parameters=seed_parameters,
            identity=identity,
            repository=repository,
            output_directory=output_directory,
            evaluator=evaluator,
            initialization_plan=initialization_plan,
            explicit_cli_enable=explicit_cli_enable,
            resume=resume,
            j=j,
        )
    return _run_cmaes_parallel_coordinator(
        search_config=search_config,
        seed_parameters=seed_parameters,
        identity=identity,
        repository=repository,
        output_directory=output_directory,
        evaluator=evaluator,
        initialization_plan=initialization_plan,
        explicit_cli_enable=explicit_cli_enable,
        resume=resume,
        workers=workers,
        j=j,
    )
