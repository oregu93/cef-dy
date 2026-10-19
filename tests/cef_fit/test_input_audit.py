from pathlib import Path

from cef_fit.taipan_observables import audit_observations, load_observations


def test_current_table_fails_closed_for_production_intensity_fit():
    rows = load_observations(Path("data/manuscript_v1/manuscript_observables.csv"))
    audit = audit_observations(rows)
    assert audit.status == "DRAFT_PROVENANCE_INCOMPLETE"
    assert audit.admitted_energy_count == 1
    assert audit.admitted_detected_intensity_count == 0
    assert audit.admitted_censored_count == 0
    assert "NO_PROVENANCE_QUALIFIED_DETECTED_INTENSITY_ROWS" in audit.blockers
