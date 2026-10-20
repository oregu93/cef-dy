import csv
from pathlib import Path

import numpy as np
import pytest
import yaml

from cef_fit.background_model import evaluate_background
from cef_fit.eq_data import apply_masks, audit_eq_dataset, load_eq_dataset, load_mask_definition
from cef_fit.ins_forward import predict_eq_map
from cef_fit.magnetic_form_factor import dy3_j0_form_factor
from cef_fit.normalization_nuisance import profile_block_scales
from cef_fit.polarization_factor import (
    orthorhombic_hkl_to_q_direct,
    polarized_transition_strength,
    polarization_matrix,
    powder_transition_strength,
)
from cef_fit.resolution_model import FWHM_TO_SIGMA, gaussian_line_shape, resolution_sigma_meV


REPOSITORY = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPOSITORY / "configs/user_executed_joint_cef_pipeline_v1.yaml"


def _write_dataset(path: Path, *, include_log_column: bool = False) -> None:
    columns = [
        "point_id",
        "energy_meV",
        "Q_Ainv",
        "normalized_intensity",
        "instrument_block_id",
        "scan_id",
        "mask_status",
        "normalization_metadata",
        "normalized_intensity_sigma",
        "constraint_class",
        "Ei_meV",
        "Ef_meV",
        "qhat_direct_x",
        "qhat_direct_y",
        "qhat_direct_z",
        "temperature_status",
        "temperature_K_if_verified",
        "discovery_holdout_role",
        "count_control_mode",
        "normalization_compatibility_group_id",
        "lattice_state_id",
        "UB_state_id",
        "feature_id",
    ]
    if include_log_column:
        columns.append("log_intensity")
    rows = [
        ["p0", "0.0", "1.0", "1.0", "A", "s1", "INCLUDE", "monitor_norm_v1", "0.2", "SPECTRAL_SHAPE_CONSTRAINT", "14.87", "14.87", "1", "0", "0", "VERIFIED", "10", "discovery", "monitor_controlled", "N1", "L1", "U1", ""],
        ["p1", "6.0", "1.5", "2.0", "A", "s1", "INCLUDE", "monitor_norm_v1", "0.2", "ENERGY_CONSTRAINT", "20.87", "14.87", "0", "1", "0", "VERIFIED", "10", "discovery", "monitor_controlled", "N1", "L1", "U1", "BF-003"],
        ["p2", "18.0", "2.0", "3.0", "B", "s2", "EXCLUDE_DETECTOR_ARTIFACT", "monitor_norm_v1", "0.3", "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT", "32.87", "14.87", "0", "0", "1", "VERIFIED", "10", "discovery", "monitor_controlled", "N1", "L1", "U1", "BF-004"],
    ]
    if include_log_column:
        for row in rows:
            row.append("0.0")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def _write_mask(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "mask_id": "TEST_MASK",
                "rules": [
                    {
                        "rule_id": "ELASTIC",
                        "kind": "ENERGY_RANGE",
                        "reason": "elastic",
                        "enabled": True,
                        "min_meV": -1.0,
                        "max_meV": 1.0,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_eq_dataset_is_linear_numerical_and_masks_are_immutable(tmp_path):
    dataset_path = tmp_path / "eq.csv"
    mask_path = tmp_path / "mask.yaml"
    _write_dataset(dataset_path)
    _write_mask(mask_path)
    dataset = load_eq_dataset(dataset_path, "LINEAR_PRE_DISPLAY")
    applied = apply_masks(dataset, load_mask_definition(mask_path))
    assert dataset.size == 3
    assert applied.include.tolist() == [False, True, False]
    assert applied.excluded_by_rule == {"ELASTIC": 1}
    assert not applied.include.flags.writeable
    with pytest.raises(ValueError):
        applied.include[1] = False


def test_log_or_display_intensity_fails_closed(tmp_path):
    path = tmp_path / "eq.csv"
    _write_dataset(path, include_log_column=True)
    with pytest.raises(ValueError, match="Display/log"):
        load_eq_dataset(path, "LINEAR_PRE_DISPLAY")
    _write_dataset(path)
    with pytest.raises(ValueError, match="LINEAR_PRE_DISPLAY"):
        load_eq_dataset(path, "LOG10_DISPLAY")


def test_audit_reports_ready_and_missing_states(tmp_path):
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    config["inputs"]["taipan_eq_dataset"] = str(tmp_path / "missing.csv")
    missing = audit_eq_dataset(config, REPOSITORY)
    assert missing["status"] == "NOT_READY"
    assert missing["manuscript_intensity_gate"] == "FAIL_CLEANLY"
    assert missing["exploratory_eq_map_use"] == "AUTHORIZED"

    dataset_path = tmp_path / "eq.csv"
    mask_path = tmp_path / "mask.yaml"
    _write_dataset(dataset_path)
    _write_mask(mask_path)
    config["inputs"]["taipan_eq_dataset"] = str(dataset_path)
    config["inputs"]["taipan_mask_definition"] = str(mask_path)
    ready = audit_eq_dataset(config, REPOSITORY)
    assert ready["status"] == "READY_FOR_EXPLORATORY_SANITY_RUN"
    assert ready["number_of_points"] == 3
    assert ready["included_points"] == 1
    assert ready["number_of_instrument_blocks"] == 2
    assert ready["included_constraint_counts"]["ENERGY_CONSTRAINT"] == 1


def test_magnetic_form_factor_polarization_resolution_and_background():
    form = dy3_j0_form_factor([0.0, 2.0, 4.0])
    assert np.isclose(form[0], 0.9999)
    assert np.all(np.diff(form) < 0)
    polarization = polarization_matrix([0, 0, 2])
    assert np.allclose(polarization, np.diag([1, 1, 0]))
    tensor = np.eye(3, dtype=complex)
    assert np.isclose(polarized_transition_strength(tensor, [0, 0, 1]), 2.0)
    assert np.isclose(powder_transition_strength(tensor), 2.0)
    sigma = resolution_sigma_meV([10.0], {"model": "GAUSSIAN_FIXED_FWHM", "fwhm_meV": 1.0})
    assert np.isclose(sigma[0], FWHM_TO_SIGMA)
    grid = np.linspace(-5, 5, 20001)
    assert np.isclose(np.trapezoid(gaussian_line_shape(grid, 0.0, 0.5), grid), 1.0, atol=1e-8)
    background = evaluate_background(
        [10.0, 12.0],
        [1.0, 2.0],
        {
            "model": "SMOOTH_Q_ENERGY",
            "coefficients": {
                "constant": 1.0,
                "energy_reference_meV": 10.0,
                "energy_slope": 0.5,
                "q_reference_Ainv": 1.0,
                "q_slope": 2.0,
                "q_quadratic": 0.0,
            },
        },
    )
    assert np.allclose(background, [1.0, 4.0])


def test_hkl_to_q_uses_internal_b_c_a_axis_order():
    magnitude, qhat = orthorhombic_hkl_to_q_direct([1, 0, 0], [5.0, 6.0, 7.0])
    assert np.isclose(magnitude, 2.0 * np.pi / 5.0)
    assert np.array_equal(qhat, [0.0, 0.0, 1.0])
    _, qhat_b = orthorhombic_hkl_to_q_direct([0, 1, 0], [5.0, 6.0, 7.0])
    assert np.array_equal(qhat_b, [1.0, 0.0, 0.0])


def test_one_nuisance_scale_per_explicit_block():
    result = profile_block_scales(
        calculated=[1.0, 2.0, 1.0, 3.0],
        observed=[2.0, 4.0, 3.0, 9.0],
        blocks=["A", "A", "B", "B"],
        include_mask=[True, True, True, True],
        bounds=(0.1, 10.0),
    )
    assert result.scales == pytest.approx({"A": 2.0, "B": 3.0})
    assert np.allclose(result.fitted, [2.0, 4.0, 3.0, 9.0])


def test_forward_model_is_finite_bounded_sanity_only(r7_bundle, tmp_path):
    path = tmp_path / "eq.csv"
    _write_dataset(path)
    dataset = load_eq_dataset(path, "LINEAR_PRE_DISPLAY")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    prediction = predict_eq_map(r7_bundle["parameters"], dataset, config["forward_model"])
    assert prediction.signal.shape == (3,)
    assert np.isfinite(prediction.total_unscaled).all()
    assert prediction.transitions.transition_tensors.shape == (28, 3, 3)
    assert np.all(prediction.kf_over_ki <= 1.0)
    assert len(prediction.transitions.doublet_energies_meV) == 8
