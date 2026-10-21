import json
from pathlib import Path

import numpy as np
import pytest

from cef_fit.global_search import (
    SearchIdentity,
    deterministic_restart_seed,
    run_cmaes_multistart,
)


REPOSITORY = Path(__file__).resolve().parents[2]


def _identity(label: str) -> SearchIdentity:
    return SearchIdentity(
        f"config-{label}",
        "synthetic-dataset",
        "synthetic-mask",
        "SYNTHETIC_OBJECTIVE",
        "test-commit",
        "synthetic-feature-table",
        "synthetic-assignment-set",
        search_profile="SYNTHETIC_PARALLEL_TEST",
    )


def _search_config(
    *,
    workers: int,
    assignments: tuple[int, ...],
    restarts: int,
    max_evaluations: int = 4,
) -> dict[str, object]:
    return {
        "backend": "CMA_ES",
        "run_exploratory_search": True,
        "workers": workers,
        "assignment_branches": list(assignments),
        "assignment_ids": {
            str(assignment): f"SYNTHETIC_D0-D{assignment}"
            for assignment in assignments
        },
        "restarts_per_assignment": restarts,
        "population": 4,
        "max_evaluations_per_restart": max_evaluations,
        "base_seed": 20261021,
        "h_bounds_meV": [-8.0, 8.0],
        "sigma0_meV": 0.2,
        "maximum_retained_candidates": len(assignments) * restarts,
        "boundary_fraction": 0.02,
        "output_status": "SYNTHETIC_TEST_ONLY",
    }


def _initialization_plan(restarts: int) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "initialization_family": f"SYNTHETIC_{restart:03d}",
            "initial_mean_h": np.zeros(15).tolist(),
            "source_role": "INITIALIZATION_ONLY",
        }
        for restart in range(1, restarts + 1)
    )


def _evaluator(parameters, assignment):
    return {
        "total": float(
            sum(value * value for value in parameters.values()) + 0.01 * assignment
        )
    }


def _run(
    directory: Path,
    r7_bundle,
    *,
    workers: int,
    assignments: tuple[int, ...],
    restarts: int,
    max_evaluations: int = 4,
    resume: bool = False,
):
    return run_cmaes_multistart(
        search_config=_search_config(
            workers=workers,
            assignments=assignments,
            restarts=restarts,
            max_evaluations=max_evaluations,
        ),
        seed_parameters=r7_bundle["parameters"],
        identity=_identity("shared"),
        repository=REPOSITORY,
        output_directory=directory,
        evaluator=_evaluator,
        initialization_plan=_initialization_plan(restarts),
        explicit_cli_enable=True,
        resume=resume,
    )


def _candidate_map(path: Path) -> dict[tuple[int, int], dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {
        (int(row["assignment_hypothesis_index"]), int(row["restart"])): row
        for row in rows
    }


def test_workers_one_preserves_serial_and_parallel_best_results_match(
    tmp_path, r7_bundle
):
    pytest.importorskip("cma")
    serial_directory = tmp_path / "serial"
    parallel_directory = tmp_path / "parallel"
    serial = _run(
        serial_directory,
        r7_bundle,
        workers=1,
        assignments=(1, 2),
        restarts=2,
        max_evaluations=8,
    )
    parallel = _run(
        parallel_directory,
        r7_bundle,
        workers=4,
        assignments=(1, 2),
        restarts=2,
        max_evaluations=8,
    )
    assert serial["worker_model"] == "SERIAL_RESTART_TRAJECTORIES"
    assert serial["configured_workers"] == serial["effective_workers"] == 1
    assert not (serial_directory / "restart_checkpoints").exists()
    assert parallel["worker_model"] == "PROCESS_PER_INDEPENDENT_RESTART_TRAJECTORY"
    assert parallel["configured_workers"] == parallel["effective_workers"] == 4
    serial_candidates = _candidate_map(serial_directory / "retained_candidates.jsonl")
    parallel_candidates = _candidate_map(parallel_directory / "retained_candidates.jsonl")
    assert serial_candidates.keys() == parallel_candidates.keys()
    for key in serial_candidates:
        serial_row = serial_candidates[key]
        parallel_row = parallel_candidates[key]
        assert serial_row["candidate_id"] == parallel_row["candidate_id"]
        assert serial_row["seed"] == parallel_row["seed"]
        assert serial_row["loss"] == pytest.approx(parallel_row["loss"], abs=1.0e-12)
        assert serial_row["h_coordinates_meV"] == pytest.approx(
            parallel_row["h_coordinates_meV"], abs=1.0e-12
        )


def test_parallel_7_by_8_restart_set_is_complete_unique_and_uncorrupted(
    tmp_path, r7_bundle
):
    pytest.importorskip("cma")
    assignments = tuple(range(1, 8))
    summary = _run(
        tmp_path,
        r7_bundle,
        workers=4,
        assignments=assignments,
        restarts=8,
    )
    expected = {
        f"D{assignment}:R{restart}"
        for assignment in assignments
        for restart in range(1, 9)
    }
    checkpoint = json.loads(
        (tmp_path / "search_checkpoint.json").read_text(encoding="utf-8")
    )
    assert summary["completed_restarts"] == 56
    assert set(checkpoint["completed_restarts"]) == expected
    assert len(checkpoint["completed_restarts"]) == len(expected)
    candidates = _candidate_map(tmp_path / "retained_candidates.jsonl")
    assert len(candidates) == 56
    assert len({row["candidate_id"] for row in candidates.values()}) == 56
    assert len(
        {
            deterministic_restart_seed(20261021, assignment, restart)
            for assignment in assignments
            for restart in range(1, 9)
        }
    ) == 56
    restart_files = sorted((tmp_path / "restart_checkpoints").glob("*.json"))
    assert len(restart_files) == 56
    for path in restart_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["status"] == "COMPLETE"
        assert payload["result"]["restart_key"] in expected
    assert not list((tmp_path / "restart_checkpoints").glob("*.tmp"))


def test_interrupted_parallel_restart_is_rerun_from_same_seed(tmp_path, r7_bundle):
    pytest.importorskip("cma")
    first = _run(
        tmp_path,
        r7_bundle,
        workers=4,
        assignments=(1, 2),
        restarts=2,
        max_evaluations=8,
    )
    original_candidates = _candidate_map(tmp_path / "retained_candidates.jsonl")
    interrupted_keys = {"D2:R1", "D2:R2"}
    checkpoint_path = tmp_path / "search_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["completed_restarts"] = [
        key for key in checkpoint["completed_restarts"] if key not in interrupted_keys
    ]
    checkpoint["current_best_candidates"] = [
        row
        for row in checkpoint["current_best_candidates"]
        if not (
            int(row["assignment_hypothesis_index"]) == 2
            and int(row["restart"]) in {1, 2}
        )
    ]
    for restart in (1, 2):
        path = tmp_path / "restart_checkpoints" / f"D002_R{restart:03d}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        checkpoint["elapsed_evaluations"] -= int(
            payload["result"]["restart_evaluations"]
        )
        payload["status"] = "INCOMPLETE__RERUN_FROM_FIXED_SEED_ON_RESUME"
        payload.pop("result")
        path.write_text(json.dumps(payload), encoding="utf-8")
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    resumed = _run(
        tmp_path,
        r7_bundle,
        workers=4,
        assignments=(1, 2),
        restarts=2,
        max_evaluations=8,
        resume=True,
    )
    resumed_candidates = _candidate_map(tmp_path / "retained_candidates.jsonl")
    assert resumed["completed_restarts"] == 4
    assert resumed["elapsed_evaluations"] == first["elapsed_evaluations"]
    for key in ((2, 1), (2, 2)):
        assert resumed_candidates[key]["seed"] == original_candidates[key]["seed"]
        assert resumed_candidates[key]["candidate_id"] == original_candidates[key][
            "candidate_id"
        ]
        assert resumed_candidates[key]["loss"] == pytest.approx(
            original_candidates[key]["loss"], abs=1.0e-12
        )
    final_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert len(final_checkpoint["completed_restarts"]) == 4
    for path in (tmp_path / "restart_checkpoints").glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "COMPLETE"
