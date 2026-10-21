from pathlib import Path

import numpy as np
import pytest
import yaml

from cef_fit.feature_assignments import (
    discovery_window_containment_penalty,
    enumerate_assignment_hypotheses,
    load_feature_table,
)
from cef_fit.global_search import (
    SearchCheckpoint,
    SearchIdentity,
    boundary_diagnostics,
    run_cmaes_multistart,
    validate_checkpoint_identity,
)
from cef_fit.ins_forward import predict_eq_map
from cef_fit.eq_data import (
    apply_feature_roles,
    apply_masks,
    load_eq_dataset,
    load_mask_definition,
)
from cef_fit.ins_objective import eq_map_exploratory_objective
from cef_fit.taipan_materializer import materialize_taipan_eq_dataset
from cef_fit.user_pipeline import STAGES, _resolved_search_config, load_pipeline_config


REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPOSITORY / "configs/manuscript_cef_fit_10k_exploratory_v1.yaml"
FEATURE_PATH = REPOSITORY / "configs/manuscript_cef_fit_feature_table_v1.yaml"
REUSE_PATH = REPOSITORY / "configs/taipan_prior_artifact_reuse_v1.yaml"


def test_feature_table_roles_and_explicit_ordered_assignments():
    features = load_feature_table(FEATURE_PATH)
    assert {row.feature_id: row.fit_role for row in features} == {
        "BF-001": "DIAGNOSTIC_ONLY",
        "BF-002": "DIAGNOSTIC_ONLY",
        "BF-003": "DIAGNOSTIC_ONLY",
        "BF-004": "SHAPE_ONLY",
        "BF-005": "ACTIVE_CEF_FEATURE",
        "BF-006": "DIAGNOSTIC_ONLY",
        "BF-007": "DIAGNOSTIC_ONLY",
        "BF-008": "DIAGNOSTIC_ONLY",
    }
    hypotheses = enumerate_assignment_hypotheses(features)
    assert len(hypotheses) == 7
    assert hypotheses[0].assignment_id == "ASSIGN__BF005_D0-D1"
    assert hypotheses[-1].assignment_id == "ASSIGN__BF005_D0-D7"
    for hypothesis in hypotheses:
        assert len(hypothesis.mappings) == 1
        assert hypothesis.mappings[0]["feature_id"] == "BF-005"
        finals = [int(row["final_doublet"]) for row in hypothesis.mappings]
        assert finals == sorted(finals)
        assert len(finals) == len(set(finals))
        assert all(int(row["initial_doublet"]) == 0 for row in hypothesis.mappings)
        assert "observed_energy_meV" not in hypothesis.mappings[0]
        assert "sigma_meV" not in hypothesis.mappings[0]


def test_bf005_energy_penalty_is_flat_inside_frozen_discovery_window():
    lower, upper, scale = 17.4983, 20.49835, 1.500025
    for energy in (lower, 18.0, (lower + upper) / 2.0, 20.0, upper):
        loss, distance = discovery_window_containment_penalty(
            energy, lower, upper, scale
        )
        assert loss == 0.0
        assert distance == 0.0
    epsilon = 1.0e-6
    below, below_distance = discovery_window_containment_penalty(
        lower - epsilon, lower, upper, scale
    )
    above, above_distance = discovery_window_containment_penalty(
        upper + epsilon, lower, upper, scale
    )
    assert below == pytest.approx((epsilon / scale) ** 2)
    assert above == pytest.approx((epsilon / scale) ** 2)
    assert below_distance == pytest.approx(epsilon)
    assert above_distance == pytest.approx(epsilon)


def test_low_energy_diagnostic_features_cannot_leak_into_primary_losses(tmp_path):
    output = tmp_path / "ten_k.csv"
    materialize_taipan_eq_dataset(REUSE_PATH, REPOSITORY, output)
    dataset = load_eq_dataset(output, "LINEAR_PRE_DISPLAY")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    base_mask = apply_masks(
        dataset,
        load_mask_definition(REPOSITORY / config["inputs"]["taipan_mask_definition"]),
    )
    mask = apply_feature_roles(dataset, base_mask, load_feature_table(FEATURE_PATH))
    low_energy = np.asarray(
        [
            bool({"BF-001", "BF-002", "BF-003"}.intersection(identifiers))
            for identifiers in dataset.feature_ids
        ],
        dtype=bool,
    )
    frozen_low_energy_region = (
        (dataset.energy_meV >= 2.4987) & (dataset.energy_meV <= 6.99865)
    )
    assert np.any(low_energy)
    assert np.array_equal(low_energy, frozen_low_energy_region)
    assert not np.any(mask.include & low_energy)
    assert not np.any(mask.include & frozen_low_energy_region)
    result = eq_map_exploratory_objective(
        dataset,
        mask.include,
        np.zeros(dataset.size),
        config["objective"],
    )
    assert not {"BF-001", "BF-002", "BF-003"}.intersection(
        result.included_points_by_feature
    )
    assert result.included_points_by_class["ENERGY_CONSTRAINT"] == 0


def test_historical_scalar_energies_are_absent_from_primary_likelihood_contract():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    feature_text = FEATURE_PATH.read_text(encoding="utf-8")
    assignments = yaml.safe_dump(
        [row.as_dict() for row in enumerate_assignment_hypotheses(load_feature_table(FEATURE_PATH))]
    )
    primary_contract = config_text + feature_text + assignments
    assert "18.247178" not in primary_contract
    assert "18.2257" not in primary_contract


def test_primary_cli_stages_and_search_profiles_are_frozen():
    config, _, _ = load_pipeline_config(CONFIG_PATH)
    assert STAGES == (
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
    smoke = _resolved_search_config(config, "SMOKE_SEARCH")
    first = _resolved_search_config(config, "FIRST_EXPLORATORY_SEARCH")
    extended = _resolved_search_config(config, "EXTENDED_SEARCH")
    assert (smoke["population"], smoke["restarts_per_assignment"], smoke["output_status"]) == (
        4,
        1,
        "SMOKE_ONLY",
    )
    assert (first["population"], first["restarts_per_assignment"], first["max_evaluations_per_restart"]) == (
        32,
        8,
        20000,
    )
    assert (extended["restarts_per_assignment"], extended["max_evaluations_per_restart"]) == (
        16,
        50000,
    )
    assert (
        smoke["maximum_retained_candidates"],
        first["maximum_retained_candidates"],
        extended["maximum_retained_candidates"],
    ) == (7, 56, 112)
    assert config["switches"]["RUN_EXPLORATORY_SEARCH"] is False
    assert config["search"]["run_exploratory_search"] is False


def test_checkpoint_identity_binds_feature_assignment_and_model_variants():
    identity = SearchIdentity(
        "config",
        "dataset",
        "mask",
        "EQ_MAP_EXPLORATORY_OBJECTIVE",
        "commit",
        "features",
        "assignments",
        "DIRECT_CS15_H_EQUALS_KAPPA_B",
        "BASELINE_0P894_MEV",
        "LOCAL_LINEAR_BASELINE",
        "FIRST_EXPLORATORY_SEARCH",
    )
    checkpoint = SearchCheckpoint(
        1,
        identity,
        3,
        2,
        123,
        10,
        (),
        (),
        "RESTART_INCOMPLETE_RESTART_FROM_FIXED_SEED",
        {},
        {},
        "ASSIGN__BF005_D0-D4",
        "HISTORICAL_R3",
    )
    validate_checkpoint_identity(checkpoint, identity)
    changed = SearchIdentity(**{**identity.__dict__, "feature_table_hash": "changed"})
    with pytest.raises(ValueError, match="feature_table_hash"):
        validate_checkpoint_identity(checkpoint, changed)
    assert checkpoint.assignment_id and checkpoint.initialization_family == "HISTORICAL_R3"


def test_boundary_diagnostics_flag_but_do_not_reject():
    interior = boundary_diagnostics(np.zeros(15), -8.0, 8.0, 0.02)
    boundary = boundary_diagnostics(np.r_[7.9, np.zeros(14)], -8.0, 8.0, 0.02)
    assert interior["boundary_status"] == "WITHIN_SEARCH_DOMAIN_INTERIOR"
    assert boundary["boundary_status"] == "SEARCH_DOMAIN_SENSITIVITY_REVIEW_REQUIRED"
    assert boundary["minimum_boundary_distance_h_meV"] == pytest.approx(0.1)


def test_materialized_exact_scan_temperatures_and_block_boltzmann_temperature(tmp_path, r7_bundle):
    output = tmp_path / "ten_k.csv"
    report = materialize_taipan_eq_dataset(REUSE_PATH, REPOSITORY, output)
    dataset = load_eq_dataset(output, "LINEAR_PRE_DISPLAY")
    assert report.ten_k_scan_count == 20
    assert dataset.size == 520
    assert float(np.ptp(dataset.temperature_K)) > 0
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    prediction = predict_eq_map(r7_bundle["parameters"], dataset, config["forward_model"])
    assert prediction.transitions.temperature_K == pytest.approx(9.998965)
    assert np.sum(prediction.transitions.doublet_populations) == pytest.approx(1.0)


def test_tiny_synthetic_cma_checkpoint_and_resume(tmp_path, r7_bundle):
    pytest.importorskip("cma")
    identity = SearchIdentity(
        "synthetic-config",
        "synthetic-dataset",
        "synthetic-mask",
        "SYNTHETIC_OBJECTIVE",
        "test-commit",
        "synthetic-feature-table",
        "synthetic-assignment-set",
        search_profile="SMOKE_SEARCH",
    )
    search = {
        "backend": "CMA_ES",
        "run_exploratory_search": True,
        "assignment_branches": [1],
        "assignment_ids": {"1": "SYNTHETIC_D0-D1"},
        "restarts_per_assignment": 1,
        "population": 4,
        "max_evaluations_per_restart": 8,
        "base_seed": 7,
        "h_bounds_meV": [-8.0, 8.0],
        "sigma0_meV": 0.2,
        "maximum_retained_candidates": 1,
        "boundary_fraction": 0.02,
        "output_status": "SMOKE_ONLY",
    }
    plan = (
        {
            "initialization_family": "SYNTHETIC_ZERO",
            "initial_mean_h": np.zeros(15).tolist(),
            "source_role": "INITIALIZATION_ONLY",
        },
    )

    def evaluator(parameters, assignment):
        assert assignment == 1
        return {"total": float(sum(value * value for value in parameters.values()))}

    first = run_cmaes_multistart(
        search_config=search,
        seed_parameters=r7_bundle["parameters"],
        identity=identity,
        repository=REPOSITORY,
        output_directory=tmp_path,
        evaluator=evaluator,
        initialization_plan=plan,
        explicit_cli_enable=True,
    )
    resumed = run_cmaes_multistart(
        search_config=search,
        seed_parameters=r7_bundle["parameters"],
        identity=identity,
        repository=REPOSITORY,
        output_directory=tmp_path,
        evaluator=evaluator,
        initialization_plan=plan,
        explicit_cli_enable=True,
        resume=True,
    )
    assert first["status"] == resumed["status"] == "SMOKE_ONLY"
    assert first["completed_restarts"] == resumed["completed_restarts"] == 1
    assert first["elapsed_evaluations"] == resumed["elapsed_evaluations"]
    checkpoint = yaml.safe_load((tmp_path / "search_checkpoint.json").read_text())
    assert checkpoint["assignment_id"] == "SYNTHETIC_D0-D1"
    assert checkpoint["initialization_family"] == "SYNTHETIC_ZERO"
