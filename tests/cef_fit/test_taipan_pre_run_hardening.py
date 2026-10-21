import csv
from pathlib import Path

import numpy as np
import pytest
import yaml

from cef_fit.cef_transition_model import (
    PBNM_DY_4C_ROTATIONS_CEF,
    boltzmann_doublet_populations,
    calculate_cef_transitions,
    pbnm_dy_four_site_tensor_sum,
    transition_strengths_at_q,
)
from cef_fit.global_search import deterministic_initialization_plan
from cef_fit.ins_forward import tas_kinematic_factors
from cef_fit.eq_data import audit_eq_dataset, load_eq_dataset
from cef_fit.ins_objective import eq_map_exploratory_objective
from cef_fit.polarization_factor import orthorhombic_hkl_to_q_direct
from cef_fit.taipan_materializer import materialize_taipan_eq_dataset


REPOSITORY = Path(__file__).resolve().parents[2]
REUSE_CONFIG = REPOSITORY / "configs/taipan_prior_artifact_reuse_v1.yaml"
PIPELINE_CONFIG = REPOSITORY / "configs/manuscript_cef_fit_10k_exploratory_v1.yaml"


def test_stage02r_materializer_is_reproducible_discovery_only_and_holdout_clean(tmp_path):
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    first = materialize_taipan_eq_dataset(REUSE_CONFIG, REPOSITORY, first_path)
    second = materialize_taipan_eq_dataset(REUSE_CONFIG, REPOSITORY, second_path)
    assert first.output_sha256 == second.output_sha256
    assert first.output_rows == first.discovery_points == 520
    assert first.holdout_points_used == 0
    assert first.holdout_detector_access_count == 0
    assert first.ten_k_block_status == "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"
    assert first.ten_k_scan_count == len(first.ten_k_scan_record_ids) == 20
    assert first.effective_temperature_K == pytest.approx(9.998965)
    assert first.count_control_modes == ("monitor_controlled",)
    assert first.q_direction_unavailable_points == 0
    assert first.mandatory_cef_assignments_from_b001 == ()
    assert len(first.blind_feature_windows) == 8
    assert first.feature_overlaps

    with first_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["discovery_holdout_role"] for row in rows} == {"discovery"}
    assert {row["temperature_status"] for row in rows} == {
        "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"
    }
    assert all(9.95 <= float(row["temperature_K_if_verified"]) <= 10.05 for row in rows)
    assert all(
        float(row["temperature_scan_max_K"]) - float(row["temperature_scan_min_K"])
        <= 0.05
        for row in rows
    )
    assert {row["temperature_source_field"] for row in rows} == {"T1_Sensor1"}
    assert all(np.isclose(float(row["intensity_linear"]), float(row["detector_counts"]) / float(row["monitor"])) for row in rows)
    assert any(";" in row["feature_id"] for row in rows)
    assert not any(
        "DIAGNOSTIC_OR_POSSIBLY_MIXED_44_MEV_REGION" in row["mask_flags"]
        for row in rows
    )

    blind_rows = list(
        csv.DictReader(
            (REPOSITORY / "04_Results/Stage02R/W02-02R-B-001/blind_split.csv").open(
                newline="", encoding="utf-8"
            )
        )
    )
    holdout = {row["scan_record_id"] for row in blind_rows if row["split_role"] == "holdout"}
    assert not holdout.intersection({row["scan_record_id"] for row in rows})

    config = yaml.safe_load(PIPELINE_CONFIG.read_text(encoding="utf-8"))
    config["inputs"]["taipan_eq_dataset"] = str(first_path)
    audit = audit_eq_dataset(config, REPOSITORY, first.as_dict())
    assert audit["status"] == "READY_FOR_EXPLORATORY_SANITY_RUN"
    assert audit["blockers"] == []
    assert audit["search_blockers"] == []
    assert audit["assignment_branch_count"] == 21
    assert audit["holdout_detector_access_count"] == 0
    assert audit["four_dy_site_intensity"]["status"] == "IMPLEMENTED_AND_TESTED"


def test_materialized_q_uses_each_lattice_state_and_direct_b_c_a_frame(tmp_path):
    output = tmp_path / "eq.csv"
    materialize_taipan_eq_dataset(REUSE_CONFIG, REPOSITORY, output)
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    lattices = yaml.safe_load(
        (REPOSITORY / "04_Results/Stage02R/W02-02R-A-002/lattice_states.yaml").read_text(
            encoding="utf-8"
        )
    )
    for row in (rows[0], rows[-1]):
        lattice = lattices[row["lattice_state_id"]]
        magnitude, qhat = orthorhombic_hkl_to_q_direct(
            [float(row["h_pbnm"]), float(row["k_pbnm"]), float(row["l_pbnm"])],
            [float(lattice["a_A"]), float(lattice["b_A"]), float(lattice["c_A"])],
        )
        assert float(row["Q_Ainv"]) == pytest.approx(magnitude)
        assert [float(row[f"qhat_direct_{axis}"]) for axis in "xyz"] == pytest.approx(qhat)


def test_kf_over_ki_is_explicit_and_energy_dependent():
    ki, kf, ratio = tas_kinematic_factors(
        np.asarray([14.87, 24.87, 44.87]), np.asarray([14.87, 14.87, 14.87])
    )
    assert np.allclose(ratio, np.sqrt([1.0, 14.87 / 24.87, 14.87 / 44.87]))
    assert np.all(np.diff(ratio) < 0)
    assert np.allclose(ratio, kf / ki)


def test_finite_temperature_populations_and_zero_temperature_limit(r7_bundle):
    ground = calculate_cef_transitions(
        r7_bundle["parameters"], population_mode="GROUND_DOUBLET_ONLY"
    )
    thermal = calculate_cef_transitions(
        r7_bundle["parameters"],
        population_mode="BOLTZMANN_ALL_CEF_STATES",
        temperature_K=10.0,
    )
    assert len(ground.transition_energies_meV) == 7
    assert len(thermal.transition_energies_meV) == 28
    assert np.isclose(np.sum(thermal.doublet_populations), 1.0)
    assert np.array_equal(
        boltzmann_doublet_populations(ground.doublet_energies_meV, 0.0),
        np.asarray([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    )
    with pytest.raises(ValueError, match="silent powder averaging"):
        transition_strengths_at_q(ground, None, 1)


def test_reviewed_pbnm_four_dy_site_tensor_sum_is_explicit_and_directional(r7_bundle):
    tensor = np.asarray(
        [[2.0, 1.0 + 0.5j, -0.3j], [1.0 - 0.5j, 3.0, 0.7], [0.3j, 0.7, 5.0]],
        dtype=complex,
    )
    summed = pbnm_dy_four_site_tensor_sum(tensor)
    assert PBNM_DY_4C_ROTATIONS_CEF.shape == (4, 3, 3)
    assert summed == pytest.approx(np.diag([8.0, 12.0, 20.0]))
    assert not summed.flags.writeable

    transitions = calculate_cef_transitions(
        r7_bundle["parameters"], population_mode="GROUND_DOUBLET_ONLY"
    )
    directional = transition_strengths_at_q(
        transitions,
        np.asarray([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        2,
        four_site_pbnm_sum=True,
    )
    assert directional.shape == (2, 7)
    assert np.isfinite(directional).all()


def test_deterministic_initializations_are_diverse_and_not_scientific_acceptance():
    seeds = {
        "PCM_FORMAL": np.zeros(15),
        "PCM_M0": np.ones(15),
        "HISTORICAL_R3": np.full(15, 2.0),
        "HISTORICAL_R5": np.full(15, 3.0),
        "HISTORICAL_R7": np.full(15, 4.0),
    }
    first = deterministic_initialization_plan(
        seeds, restart_count=8, lower=-8.0, upper=8.0, base_seed=20261020
    )
    second = deterministic_initialization_plan(
        seeds, restart_count=8, lower=-8.0, upper=8.0, base_seed=20261020
    )
    assert first == second
    assert [row["initialization_family"] for row in first[:5]] == list(seeds)
    assert all(str(row["initialization_family"]).startswith("LATIN_HYPERCUBE") for row in first[5:])
    assert len({tuple(row["initial_mean_h"]) for row in first}) == 8

    config = yaml.safe_load(PIPELINE_CONFIG.read_text(encoding="utf-8"))
    assert config["ensemble"]["retention_status"] == "SEARCH_RETAINED_CANDIDATE"
    assert config["ensemble"]["scientific_compatibility_status"] == "NOT_ASSESSED"
    assert "compatibility_loss_threshold" not in config["ensemble"]
    assert "retention_loss_threshold" not in config["search"]
    assert config["assignments"]["automatic_nearest_level_assignment"] is False
    assert config["assignments"]["automatic_nearest_level_assignment"] is False


def test_objective_components_are_dimensionless_means_not_point_count_sums(tmp_path):
    path = tmp_path / "objective.csv"
    columns = [
        "point_id",
        "energy_meV",
        "Q_Ainv",
        "normalized_intensity",
        "instrument_block_id",
        "scan_id",
        "mask_status",
        "normalization_metadata",
        "constraint_class",
        "feature_id",
    ]
    rows = []
    for index in range(100):
        rows.append(
            [f"shape-{index}", 5.0, 2.0, 2.0, "A", "s1", "INCLUDE", "n", "SPECTRAL_SHAPE_CONSTRAINT", "BF-003"]
        )
    rows.append(
        ["relative-0", 10.0, 2.0, 2.0, "A", "s1", "INCLUDE", "n", "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT", ""]
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    dataset = load_eq_dataset(path, "LINEAR_PRE_DISPLAY")
    result = eq_map_exploratory_objective(
        dataset,
        np.ones(dataset.size, dtype=bool),
        np.zeros(dataset.size),
        {
            "uncertainties_statistically_calibrated": False,
            "nuisance_scale_bounds": [1.0e-4, 1.0e4],
            "component_weights": {
                "energy": 1.0,
                "shape": 1.0,
                "relative_intensity": 1.0,
            },
        },
    )
    assert result.raw_components["L_shape"] == pytest.approx(100 * 4.0)
    assert result.raw_components["L_relative_intensity"] == pytest.approx(4.0)
    assert result.normalized_components["L_shape"] == pytest.approx(1.0)
    assert result.normalized_components["L_relative_intensity"] == pytest.approx(1.0)
    assert result.component_weights == {
        "energy": 1.0,
        "shape": 1.0,
        "relative_intensity": 1.0,
    }
    assert result.total == pytest.approx(2.0)


def test_resolution_background_and_temperature_provenance_are_explicit():
    reuse = yaml.safe_load(REUSE_CONFIG.read_text(encoding="utf-8"))
    pipeline = yaml.safe_load(PIPELINE_CONFIG.read_text(encoding="utf-8"))
    assert reuse["temperature_mapping"]["ten_k_block_status"] == (
        "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"
    )
    assert len(reuse["temperature_mapping"]["ten_k_scan_record_ids"]) == 20
    assert reuse["temperature_mapping"]["effective_temperature_K"] == pytest.approx(9.998965)
    assert reuse["resolution"]["baseline_fwhm_meV"] == pytest.approx(0.894)
    assert reuse["resolution"]["fit_uncertainty_fwhm_meV"] == pytest.approx(0.025)
    decisions = reuse["reuse_decisions"]
    assert decisions["elastic_scan_104062"]["classification"] == "REUSE_AS_EXPLORATORY_ANCHOR"
    assert decisions["legacy_44p4_q_diagnostic"]["classification"] == "REUSE_FOR_VALIDATION_ONLY"
    assert decisions["modern_w02_energy_result"]["status"] == "MODEL_DEPENDENT_ENERGY"
    assert decisions["modern_w02_energy_result"]["admitted_energy_meV"] is None
    assert decisions["legacy_scalar_energy_hypotheses"]["classification"] == "SUPERSEDED"
    assert decisions["private_repository_taipan_entry"]["classification"] == (
        "NOT_APPLICABLE_TO_CURRENT_OBJECTIVE"
    )
    assert pipeline["forward_model"]["resolution"]["status"] == (
        "EMPIRICAL_ELASTIC_ANCHOR__NOT_FULL_TAS_RESOLUTION"
    )
    assert pipeline["forward_model"]["background"]["model"] == "LOCAL_LINEAR_BACKGROUND"
    assert pipeline["forward_model"]["background"]["dataset_already_background_subtracted"] is False
    assert pipeline["forward_model"]["population"]["mode"] == "BOLTZMANN_ALL_CEF_STATES"
    assert pipeline["forward_model"]["dy_site_intensity"]["status"] == "IMPLEMENTED_AND_TESTED"
    assert pipeline["objective"]["component_weights"] == {
        "energy": 1.0,
        "shape": 1.0,
        "relative_intensity": 1.0,
    }


def test_cx02_priority_preflight_is_metadata_only_and_temperature_blocked():
    payload = yaml.safe_load(
        (REPOSITORY / "configs/taipan_cx02_priority_scan_preflight_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "METADATA_AUDIT_COMPLETE__TEMPERATURE_UNRESOLVED__NO_NEW_FIT"
    assert payload["scope"]["detector_reanalysis_performed"] is False
    assert payload["scope"]["fit_performed"] is False
    assert [row["raw_scan_id"] for row in payload["scans"]] == [
        104095,
        104098,
        104099,
        104215,
        104225,
    ]
    assert {row["b001_support"]["feature_id"] for row in payload["scans"]} == {
        "BF-004",
        "BF-005",
    }
    assert payload["terminal_status"] == "BLOCKED_BY_UNVERIFIED_SAMPLE_TEMPERATURE_MAPPING"
