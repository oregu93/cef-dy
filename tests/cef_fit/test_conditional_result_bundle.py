import csv
import json
from pathlib import Path

import numpy as np
import yaml

from cef_fit.conditional_energy import SCIENTIFIC_LABEL, SCIENTIFIC_LABELS
from cef_fit.provenance import sha256_file


RESULT = Path("04_Results/ManuscriptCEFFitV1/MODEL_DEPENDENT_ENERGY_CONDITIONAL_V1")


def _rows(name: str) -> list[dict[str, str]]:
    with (RESULT / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_required_result_tables_have_expected_counts_and_labels():
    expected_counts = {
        "energy_variants_used.csv": 36,
        "pcm_conditional_results.csv": 252,
        "pcm_robustness_summary.csv": 7,
        "cs15_all_solutions.csv": 196,
        "cs15_family_summary.csv": 196,
        "historical_R3_R5_R7_variant_evaluation.csv": 378,
        "representative_levels.csv": 1648,
        "representative_transition_strengths.csv": 1442,
        "representative_g_tensors.csv": 4944,
        "robustness_matrix.csv": 10,
    }
    for name, count in expected_counts.items():
        rows = _rows(name)
        assert len(rows) == count
        assert all(row["scientific_labels"] == SCIENTIFIC_LABEL for row in rows)


def test_manifest_hashes_and_execution_guards_are_self_consistent():
    manifest = yaml.safe_load((RESULT / "RUN_MANIFEST.yaml").read_text(encoding="utf-8"))
    assert manifest["scientific_labels"] == list(SCIENTIFIC_LABELS)
    assert manifest["pre_execution_validation"]["full_tests"] == "PASS"
    assert manifest["pre_execution_validation"]["scalar_energy_admitted"] is False
    assert manifest["pre_execution_validation"]["normal_production_profile_enabled"] is False
    assert manifest["pre_execution_validation"]["exchange_enabled"] is False
    assert manifest["pcm"]["variant_objectives_summed"] is False
    assert manifest["cs15"]["project_owned_forward_kernel_reevaluation"] is True
    assert manifest["wavefunction_artifact_count"] == 618
    for name, expected in manifest["artifact_sha256"].items():
        assert sha256_file(RESULT / name) == expected


def test_every_wavefunction_artifact_contains_required_scientific_labels():
    files = sorted((RESULT / "wavefunctions").glob("*"))
    assert len(files) == 618
    json_files = [path for path in files if path.suffix == ".json"]
    base_npz = [path for path in files if path.suffix == ".npz" and not path.name.endswith("__observables.npz")]
    observable_npz = [path for path in files if path.name.endswith("__observables.npz")]
    assert len(json_files) == len(base_npz) == len(observable_npz) == 206

    for path in json_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["metadata"]["scientific_labels"] == list(SCIENTIFIC_LABELS)
    for path in base_npz:
        with np.load(path) as archive:
            metadata = json.loads(str(archive["metadata_json"]))
            assert metadata["scientific_labels"] == list(SCIENTIFIC_LABELS)
    for path in observable_npz:
        with np.load(path) as archive:
            assert archive["scientific_labels"].tolist() == list(SCIENTIFIC_LABELS)


def test_cs15_solutions_are_separate_conditional_fits_and_numerically_finite():
    rows = _rows("cs15_all_solutions.csv")
    assert len({(row["energy_variant_id"], row["assignment"], row["restart"]) for row in rows}) == 196
    q_values = np.array([float(row["conditional_q"]) for row in rows])
    assert np.isfinite(q_values).all()
    assert q_values.max() < 1.0
    assert all(row["fit_accepted"] == "True" for row in rows)
