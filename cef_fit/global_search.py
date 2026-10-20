"""Guarded user-executed CMA-ES multistart search with strict checkpoint identity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np

from .fit_cs15 import h_to_parameters, parameters_to_h
from .provenance import git_provenance, write_json


@dataclass(frozen=True)
class SearchIdentity:
    config_hash: str
    dataset_hash: str
    mask_hash: str
    objective_mode: str
    code_commit: str


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

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["identity"] = asdict(self.identity)
        return payload


def deterministic_restart_seed(base_seed: int, assignment_branch: int, restart_number: int) -> int:
    if assignment_branch not in range(1, 8) or restart_number < 1:
        raise ValueError("assignment must be D1..D7 and restart_number must be positive")
    return int(base_seed + 1009 * assignment_branch + 104729 * restart_number)


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


def run_cmaes_multistart(
    *,
    search_config: Mapping[str, object],
    seed_parameters: Mapping[str, float],
    identity: SearchIdentity,
    repository: str | Path,
    output_directory: str | Path,
    evaluator: Callable[[Mapping[str, float], int], Mapping[str, object]],
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
    if set(assignments) - set(range(1, 8)):
        raise ValueError("assignment_branches must be a subset of 1..7")
    restart_count = int(search_config["restarts_per_assignment"])
    population = int(search_config["population"])
    max_evaluations = int(search_config["max_evaluations_per_restart"])
    base_seed = int(search_config["base_seed"])
    lower, upper = map(float, search_config["h_bounds_meV"])
    sigma0 = float(search_config["sigma0_meV"])
    threshold = float(search_config.get("retention_loss_threshold", np.inf))
    maximum_retained = int(search_config.get("maximum_retained_candidates", 10000))
    initial_h = np.clip(parameters_to_h(seed_parameters, j=j), lower, upper)
    provenance = git_provenance(repository)

    def save_checkpoint(
        assignment: int | None,
        restart: int | None,
        seed: int | None,
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
        )
        write_json(checkpoint_path, checkpoint.as_dict())

    for assignment in assignments:
        for restart in range(1, restart_count + 1):
            key = _restart_key(assignment, restart)
            if key in completed:
                continue
            seed = deterministic_restart_seed(base_seed, assignment, restart)
            options = {
                "bounds": [lower, upper],
                "seed": seed,
                "popsize": population,
                "maxfevals": max_evaluations,
                "verb_disp": 0,
                "verbose": -9,
            }
            strategy = cma.CMAEvolutionStrategy(initial_h.tolist(), sigma0, options)
            restart_evaluations = 0
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
                    if loss <= threshold:
                        width = upper - lower
                        boundary = bool(
                            np.any(np.minimum(h - lower, upper - h) <= 0.02 * width)
                        )
                        retained.append(
                            {
                                "candidate_id": (
                                    f"D{assignment}-R{restart}-"
                                    + hashlib.sha256(
                                        np.asarray(h, dtype="<f8").tobytes()
                                    ).hexdigest()[:16]
                                ),
                                "candidate_status": "RETAINED_UNCLUSTERED_EXPLORATORY",
                                "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
                                "assignment": f"D0->D{assignment}",
                                "assignment_final_doublet": assignment,
                                "restart": restart,
                                "seed": seed,
                                "loss": loss,
                                "objective": diagnostics,
                                "direct_parameters_meV": h_to_parameters(h, j=j),
                                "h_coordinates_meV": h.tolist(),
                                "search_boundary_occupied": boundary,
                                "project_owned_kernel_reevaluated": True,
                            }
                        )
                        retained[:] = sorted(retained, key=lambda row: float(row["loss"]))[
                            :maximum_retained
                        ]
                save_checkpoint(
                    assignment,
                    restart,
                    seed,
                    {
                        "generation": int(strategy.countiter),
                        "mean_h_coordinates_meV": np.asarray(strategy.mean, dtype=float).tolist(),
                        "sigma_meV": float(strategy.sigma),
                        "covariance": np.asarray(strategy.sm.C, dtype=float).tolist(),
                        "resume_semantics": "INSPECTION_ONLY__INCOMPLETE_RESTART_REPEATED_FROM_SEED",
                    },
                )
            completed.add(key)
            save_checkpoint(None, None, None)

    with candidates_path.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in retained:
            handle.write(json.dumps(candidate, sort_keys=True) + "\n")
    summary = {
        "status": "USER_EXECUTED_EXPLORATORY_SEARCH_COMPLETE",
        "scientific_status": "EXPLORATORY_NOT_MANUSCRIPT_ADMITTED",
        "unique_solution_claim": False,
        "physical_clusters_selected": False,
        "identity": asdict(identity),
        "backend": "CMA_ES_WITH_PROJECT_OWNED_REEVALUATION",
        "completed_restarts": len(completed),
        "elapsed_evaluations": total_evaluations,
        "retained_candidate_count": len(retained),
        "checkpoint": str(checkpoint_path),
        "candidates": str(candidates_path),
        "git": provenance,
    }
    write_json(output / "search_summary.json", summary)
    return summary
