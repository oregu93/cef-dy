import csv
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from cef_fit.eq_data import apply_masks, load_eq_dataset, load_mask_definition
from cef_fit.global_search import (
    SearchCheckpoint,
    SearchIdentity,
    deterministic_restart_seed,
    require_search_authorization,
    validate_checkpoint_identity,
)
from cef_fit.ins_objective import (
    eq_map_exploratory_objective,
    feature_objective,
    joint_mh_interface,
    require_objective_mode,
)
from cef_fit.literature_compare import (
    MH_SOURCE_COMMIT,
    calculate_frozen_dy_mh,
    load_literature_mh,
    mh_anisotropy_diagnostics,
    mh_curve_diagnostics,
)
from cef_fit.user_pipeline import STAGES, build_parser, load_pipeline_config
from cef_fit.provenance import sha256_file


REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPOSITORY / "configs/manuscript_cef_fit_10k_exploratory_v1.yaml"


def _objective_dataset(tmp_path: Path):
    table = tmp_path / "eq.csv"
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "point_id", "energy_meV", "Q_Ainv", "normalized_intensity",
                "instrument_block_id", "scan_id", "mask_status",
                "normalization_metadata", "constraint_class",
            ]
        )
        writer.writerows(
            [
                ["p1", 5, 1, 2, "A", "s1", "INCLUDE", "n1", "ENERGY_CONSTRAINT"],
                ["p2", 6, 1, 6, "A", "s1", "INCLUDE", "n1", "SPECTRAL_SHAPE_CONSTRAINT"],
                ["p3", 7, 1, 4, "B", "s2", "INCLUDE", "n1", "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT"],
            ]
        )
    mask = tmp_path / "mask.yaml"
    mask.write_text("mask_id: T\nrules: []\n", encoding="utf-8")
    dataset = load_eq_dataset(table, "LINEAR_PRE_DISPLAY")
    applied = apply_masks(dataset, load_mask_definition(mask))
    return dataset, applied


def test_exploratory_objective_has_three_residual_classes_and_no_chi_square_claim(tmp_path):
    dataset, mask = _objective_dataset(tmp_path)
    original_mask = mask.include.copy()
    result = eq_map_exploratory_objective(
        dataset,
        mask.include,
        calculated_unscaled=[1.0, 2.0, 1.0],
        config={
            "uncertainties_statistically_calibrated": False,
            "nuisance_scale_bounds": [0.1, 10.0],
        },
    )
    assert result.mode == "EQ_MAP_EXPLORATORY_OBJECTIVE"
    assert result.energy_constraint >= 0
    assert result.spectral_shape_constraint >= 0
    assert result.exploratory_relative_intensity_constraint >= 0
    assert result.loss_interpretation == "EXPLORATORY_WEIGHTED_LOSS_NOT_STATISTICAL_CHI_SQUARE"
    assert np.array_equal(mask.include, original_mask)


def test_feature_objective_is_a_separate_compact_mode():
    result = feature_objective([5.1, 10.0], [5.0, 10.2], [0.1, 0.2])
    assert result.mode == "FEATURE_OBJECTIVE"
    assert np.isclose(result.energy_constraint, 2.0)
    assert result.spectral_shape_constraint == 0.0


def test_manuscript_and_joint_objectives_fail_closed():
    with pytest.raises(PermissionError, match="MANUSCRIPT_OBJECTIVE"):
        require_objective_mode("MANUSCRIPT_OBJECTIVE", manuscript_enabled=False)
    with pytest.raises(PermissionError, match="ENABLE_JOINT_MH_FIT"):
        joint_mh_interface(1.0, 2.0, 0.5, enabled=False, accepted_bulk_contribution_model=None)
    with pytest.raises(PermissionError, match="bulk contribution"):
        joint_mh_interface(1.0, 2.0, 0.5, enabled=True, accepted_bulk_contribution_model=None)


def test_search_requires_config_and_explicit_user_switches():
    with pytest.raises(PermissionError, match="configuration"):
        require_search_authorization(False, True)
    with pytest.raises(PermissionError, match="--enable"):
        require_search_authorization(True, False)
    require_search_authorization(True, True)
    assert deterministic_restart_seed(10, 2, 3) == deterministic_restart_seed(10, 2, 3)
    assert deterministic_restart_seed(10, 2, 3) != deterministic_restart_seed(10, 2, 4)


def test_checkpoint_resume_identity_is_strict():
    identity = SearchIdentity("c", "d", "m", "EQ_MAP_EXPLORATORY_OBJECTIVE", "g")
    checkpoint = SearchCheckpoint(1, identity, None, None, None, 0, (), (), "RESTART", {}, {})
    validate_checkpoint_identity(checkpoint, identity)
    with pytest.raises(ValueError, match="dataset_hash"):
        validate_checkpoint_identity(
            checkpoint,
            SearchIdentity("c", "changed", "m", "EQ_MAP_EXPLORATORY_OBJECTIVE", "g"),
        )


def test_pipeline_config_and_notebook_default_to_no_search_and_no_joint_fit():
    config, _, _ = load_pipeline_config(CONFIG_PATH)
    assert config["switches"]["RUN_EXPLORATORY_SEARCH"] is False
    assert config["search"]["run_exploratory_search"] is False
    assert config["switches"]["ENABLE_JOINT_MH_FIT"] is False
    notebook = json.loads(
        (REPOSITORY / "notebooks/DyFeO3_joint_cef_fit_user_run.ipynb").read_text(encoding="utf-8")
    )
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    assert "RUN_EXPLORATORY_SEARCH = False" in source
    assert "ENABLE_JOINT_MH_FIT = False" in source
    assert set(STAGES) == set(build_parser()._actions[1].choices)


def test_reviewed_literature_loader_has_only_a_b_at_10_20_K(r7_bundle):
    data = load_literature_mh(
        REPOSITORY / "data/manuscript_v1/literature_magnetization.csv",
        REPOSITORY / "data/manuscript_v1/literature_magnetization_curve_inventory.csv",
    )
    assert data.source_commit == MH_SOURCE_COMMIT
    assert {(curve.axis, curve.temperature_K) for curve in data.curves} == {
        ("a", 10.0), ("a", 20.0), ("b", 10.0), ("b", 20.0)
    }
    assert sum(len(curve.fields_T) for curve in data.curves) == 135
    assert set(data.unavailable_comparators) == {
        "c,10K:AMBIGUOUS_CURVE_IDENTITY",
        "c,20K:AMBIGUOUS_CURVE_IDENTITY",
    }
    rows = calculate_frozen_dy_mh(r7_bundle["parameters"], data, "R7")
    assert len(rows) == 135
    assert {row["experimental_quantity"] for row in rows} == {"TOTAL_BULK_MAGNETIZATION"}
    assert {row["calculated_quantity"] for row in rows} == {"SINGLE_ION_DY_CEF_CONTRIBUTION"}
    assert all(row["blm_frozen"] and not row["exchange_enabled"] for row in rows)
    assert all("diagnostic_residual_bulk_muB_per_fu_minus_Dy_muB_per_Dy" in row for row in rows)
    diagnostics = mh_curve_diagnostics(rows)
    assert len(diagnostics) == 4
    assert all(row["formal_chi_square"] is None and not row["ranking_allowed"] for row in diagnostics)
    anisotropy = mh_anisotropy_diagnostics(rows)
    assert len(anisotropy) == 2
    assert all(row["formal_score"] is None and not row["ranking_allowed"] for row in anisotropy)


def test_reviewed_literature_files_match_source_commit_hashes():
    assert sha256_file(REPOSITORY / "data/manuscript_v1/literature_magnetization.csv") == (
        "2909ad44b4abc150dae603c89a5e9b5b08a182d99009e111055d942a1d6da4ea"
    )
    assert sha256_file(
        REPOSITORY / "data/manuscript_v1/literature_magnetization_curve_inventory.csv"
    ) == "403951d723731eba7f0eac84511ce765bccdd5537c5530ee809e90ae1af146f1"
