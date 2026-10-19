import numpy as np
import yaml

from cef_fit.fit_pcm import run_pcm_smoke


def test_pcm_smoke_enumerates_all_assignments():
    config = yaml.safe_load(open("configs/manuscript_fit_v1.yaml", encoding="utf-8"))
    result = run_pcm_smoke(
        config["pcm"]["formal_parameters_meV"], 18.247178, 0.119021,
        [1, 2, 3, 4, 5, 6, 7], tuple(config["pcm"]["A1_scale_bounds"]),
    )
    assert result["profile"] == "SMOKE_ONLY"
    assert [row["assignment"] for row in result["branches"]] == [f"D0->D{i}" for i in range(1, 8)]
    assert result["branches"][0]["objective"]["total"] < 1e-20
    reference = np.array([0.0, 19.878753, 41.543081, 54.593419, 61.618910, 70.534673, 75.507639, 82.335365])
    assert np.max(np.abs(np.array(result["formal_doublet_energies_meV"]) - reference)) < 1e-6


def test_pcm_uniform_scaling_preserves_level_ratios():
    config = yaml.safe_load(open("configs/manuscript_fit_v1.yaml", encoding="utf-8"))
    result = run_pcm_smoke(
        config["pcm"]["formal_parameters_meV"], 18.247178, 0.119021, [1], (0.25, 2.0)
    )
    formal = np.array(result["formal_doublet_energies_meV"])
    row = result["branches"][0]
    assert np.isclose(row["calculated_energy_meV"], row["scale"] * formal[1])
