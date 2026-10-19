import csv
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from cef_fit.conditional_energy import (
    PRIMARY_ROLE,
    SCIENTIFIC_LABEL,
    STRESS_ROLE,
    assign_parameter_families,
    conditional_deviance,
    load_energy_variants,
    run_cs15_global_search,
    run_pcm_conditional,
    select_cs15_variants,
    summarize_pcm_robustness,
)
from cef_fit.provenance import sha256_file


VARIANTS_PATH = Path("data/manuscript_v1/energy_admission_v1/w03_energy_variants.csv")


def test_w02_artifact_identity_and_variant_contract():
    assert sha256_file(VARIANTS_PATH) == "b6a809e5e25b733383a6c9fc9daea15ec2d872451480c8eef96051ab50167f63"
    assert sha256_file(
        "data/manuscript_v1/energy_admission_v1/energy_admission_summary.yaml"
    ) == "523ab9768f62edf6a7b7825f941fc287b3936748a13082cbf48b5f238b84a05a"
    assert sha256_file(
        "data/manuscript_v1/energy_admission_v1/source_scans.csv"
    ) == "86621a54df13609a27ca433871c4784babd199884968abb39ff3b5efba2d890c"
    variants = load_energy_variants(VARIANTS_PATH)
    assert sum(item.role == PRIMARY_ROLE for item in variants) == 18
    assert sum(item.role == STRESS_ROLE for item in variants) == 18
    assert all(item.conditional_sigma_meV > 0 for item in variants)


def test_cs15_variant_selection_is_deterministic_and_fit_quality_independent():
    selected = select_cs15_variants(load_energy_variants(VARIANTS_PATH))
    assert [item["energy_variant_id"] for item in selected] == [
        "block_inst_4615972084_w6.0_b2",
        "block_inst_4615972084_w7.0_b0",
        "block_inst_f4703b6bd8_w5.0_b0",
        "block_inst_f4703b6bd8_w5.0_b2",
        "joint_w6.0_b1_per_block",
        "joint_w6.0_b2_per_block",
        "joint_w7.0_b0_per_block",
    ]
    medoid = next(item for item in selected if "PRIMARY_METADATA_MEDOID" in item["selection_reasons"])
    assert medoid["energy_variant_id"] == "joint_w6.0_b1_per_block"


def test_pcm_conditional_runs_each_variant_separately_and_keeps_labels():
    manuscript = yaml.safe_load(Path("configs/manuscript_fit_v1.yaml").read_text(encoding="utf-8"))
    variants = load_energy_variants(VARIANTS_PATH)
    rows = run_pcm_conditional(
        variants,
        manuscript["pcm"]["formal_parameters_meV"],
        range(1, 8),
        (0.25, 2.0),
    )
    assert len(rows) == 36 * 7
    assert all(row["scientific_labels"] == SCIENTIFIC_LABEL for row in rows)
    assert len({row["energy_variant_id"] for row in rows}) == 36
    summary = summarize_pcm_robustness(rows, range(1, 8))
    assert [row["assignment"] for row in summary if row["robust_across_primary_variants"]] == [
        "D0->D1", "D0->D2", "D0->D3", "D0->D4", "D0->D5"
    ]
    assert all(row["primary_boundary_variant_count"] == 18 for row in summary[5:])


def test_conditional_objective_has_no_variant_collection_api():
    variant = load_energy_variants(VARIANTS_PATH)[0]
    assert np.isclose(conditional_deviance(variant.energy_meV, variant), 0.0)
    assert conditional_deviance(variant.energy_meV + variant.conditional_sigma_meV, variant) == pytest.approx(1.0)


def test_scalar_energy_targets_are_not_active_likelihood_rows():
    with Path("data/manuscript_v1/manuscript_observables.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert not [row for row in rows if row["likelihood_role"] == "ENERGY_CANDIDATE"]
    legacy = next(row for row in rows if row["observation_id"] == "TAIPAN-18P247-ENERGY")
    assert legacy["likelihood_role"] == "EXCLUDED_FROM_SCALAR_ENERGY_LIKELIHOOD"


def test_conditional_config_does_not_enable_production_or_exchange():
    manuscript = yaml.safe_load(Path("configs/manuscript_fit_v1.yaml").read_text(encoding="utf-8"))
    conditional = yaml.safe_load(
        Path("configs/model_dependent_energy_conditional_v1.yaml").read_text(encoding="utf-8")
    )
    assert manuscript["profiles"]["production"]["enabled"] is False
    assert manuscript["scientific_scope"]["exchange_enabled"] is False
    assert conditional["execution_class"] == "MODEL_DEPENDENT_ENERGY_CONDITIONAL"
    assert conditional["scientific_labels"] == SCIENTIFIC_LABEL.split("|")


def test_cma_path_reevaluates_candidates_with_project_kernel():
    pytest.importorskip("cma")
    variants = load_energy_variants(VARIANTS_PATH)
    selected = [next(item for item in variants if item.energy_variant_id == "joint_w6.0_b1_per_block")]
    rows, cache = run_cs15_global_search(
        selected,
        [2],
        (-8.0, 8.0),
        sigma0=1.0,
        max_cma_evaluations=20,
        max_polish_evaluations=10,
        restart_seeds=[101, 202],
        fit_acceptance_q_max=1e12,
    )
    assert len(rows) == 2
    for row in rows:
        system = cache[row["solution_id"]]["system"]
        expected = conditional_deviance(float(system.doublet_energies_meV[2]), selected[0])
        assert float(row["conditional_q"]) == pytest.approx(expected)
        assert len(json.loads(row["direct_parameters_meV"])) == 15
    families = assign_parameter_families(rows, cache, (-8.0, 8.0), 0.08)
    assert families
