from pathlib import Path

import yaml

from cef_fit.taipan_observables import (
    REQUIRED_COLUMNS,
    AdmissionPolicy,
    ObjectiveReadiness,
    Observation,
    audit_observations,
    load_observations,
)


POLICY = AdmissionPolicy.from_mapping({
    "accepted_energy_provenance_statuses": ["W02_LIN_ENERGY_ACCEPTED"],
    "accepted_intensity_provenance_statuses": ["W02_LIN_PROVENANCE_ACCEPTED"],
    "accepted_censor_provenance_statuses": ["W02_LIN_PROVENANCE_ACCEPTED"],
    "accepted_normalization_statuses": ["W02_LIN_ONE_SCALE_COMPATIBLE"],
})


def _row(observation_id: str, likelihood_role: str, **values: str) -> Observation:
    raw = {name: "" for name in REQUIRED_COLUMNS}
    raw.update(observation_id=observation_id, likelihood_role=likelihood_role)
    raw.update(values)
    return Observation(raw)


def _aggregate_energy() -> Observation:
    return _row(
        "TAIPAN-18P247-ENERGY",
        "ENERGY_CANDIDATE",
        observable_type="energy",
        energy_meV="18.247178",
        energy_sigma_meV="0.119021",
        source_artifact="results/taipan_18p247_energy.yaml",
        provenance_status="W02_LIN_ENERGY_ACCEPTED",
        aggregation_status="AGGREGATE",
        source_scan_set="SCAN-A;SCAN-B;SCAN-C",
    )


def _detected(index: int) -> Observation:
    return _row(
        f"DET-{index}",
        "DETECTED_INTENSITY",
        source_scan_id=f"SCAN-{index}",
        instrument_block_id="BLOCK-A",
        observable_type="integrated_intensity",
        Q_Ainv=str(1.5 + index),
        intensity_value=str(10.0 + index),
        intensity_sigma="0.5",
        source_artifact=f"results/scan_{index}_area.yaml",
        provenance_status="W02_LIN_PROVENANCE_ACCEPTED",
        normalization_status="W02_LIN_ONE_SCALE_COMPATIBLE",
        grouping_rationale="same configuration; one multiplicative nuisance scale",
    )


def _censored() -> Observation:
    return _row(
        "CENSOR-1",
        "CENSORED_NONDETECTION",
        source_scan_id="SCAN-CENSOR",
        instrument_block_id="BLOCK-A",
        observable_type="upper_limit",
        Q_Ainv="4.2",
        censor_threshold="0.3",
        censor_sigma="0.1",
        source_artifact="results/scan_censor_limit.yaml",
        provenance_status="W02_LIN_PROVENANCE_ACCEPTED",
        normalization_status="W02_LIN_ONE_SCALE_COMPATIBLE",
        grouping_rationale="same configuration; one multiplicative nuisance scale",
    )


def test_energy_only_is_diagnostic_not_manuscript_intensity_ready():
    audit = audit_observations([_aggregate_energy()], POLICY)
    assert audit.status == ObjectiveReadiness.ENERGY_ONLY.value
    assert not audit.manuscript_intensity_ready
    assert not audit.full_joint_ready


def test_two_review_admitted_detected_rows_make_intensity_ready():
    audit = audit_observations([_aggregate_energy(), _detected(1), _detected(2)], POLICY)
    assert audit.status == ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY.value
    assert audit.manuscript_intensity_ready
    assert not audit.full_joint_ready
    assert audit.admissible_instrument_blocks == ("BLOCK-A",)
    assert audit.admitted_detected_intensity_count == 2


def test_censored_row_upgrades_intensity_ready_input_to_full_joint_ready():
    rows = [_aggregate_energy(), _detected(1), _detected(2), _censored()]
    audit = audit_observations(rows, POLICY)
    assert audit.status == (
        ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING.value
    )
    assert audit.manuscript_intensity_ready
    assert audit.full_joint_ready
    assert audit.admitted_censored_count == 1


def test_malformed_censored_row_fails_closed():
    malformed = Observation({**_censored().raw, "censor_sigma": ""})
    rows = [_aggregate_energy(), _detected(1), _detected(2), malformed]
    audit = audit_observations(rows, POLICY)
    assert audit.status == "INPUT_INVALID"
    assert not audit.manuscript_intensity_ready
    assert "CENSOR-1:INVALID_CENSOR_MODEL" in audit.blockers


def test_aggregate_energy_and_detected_rows_need_no_fake_single_temperature_or_q():
    energy = _aggregate_energy()
    assert energy.raw["temperature_K"] == ""
    assert energy.raw["Q_Ainv"] == ""
    audit = audit_observations([energy, _detected(1), _detected(2)], POLICY)
    assert audit.status == ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY.value
    assert audit.admitted_energy_count == 1


def test_current_table_has_no_admitted_scalar_energy_after_w02_adjudication():
    rows = load_observations(Path("data/manuscript_v1/manuscript_observables.csv"))
    audit = audit_observations(rows)
    assert audit.status == "INPUT_INVALID"
    assert not audit.production_ready
    assert audit.admitted_energy_count == 0
    assert "NO_ADMITTED_ENERGY_CANDIDATE" in audit.blockers


def test_production_profile_remains_disabled():
    config = yaml.safe_load(Path("configs/manuscript_fit_v1.yaml").read_text(encoding="utf-8"))
    assert config["profiles"]["production"]["enabled"] is False
    assert (
        config["profiles"]["production"]["requires_input_readiness"]
        == ObjectiveReadiness.ENERGY_PLUS_DETECTED_INTENSITY.value
    )
