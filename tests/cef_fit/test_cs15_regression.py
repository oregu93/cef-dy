import numpy as np

from cef_fit.fit_cs15 import h_to_parameters, parameters_to_h, run_cs15_smoke


def test_scaled_search_coordinate_roundtrip(r7_bundle):
    h = parameters_to_h(r7_bundle["parameters"])
    recovered = h_to_parameters(h)
    assert np.allclose(list(recovered.values()), list(r7_bundle["parameters"].values()))


def test_cs15_smoke_records_assignment_and_no_unique_claim(r7_bundle):
    result = run_cs15_smoke(
        r7_bundle["parameters"], 18.247178, 0.119021, [2], (-8.0, 8.0), 20, 17
    )
    assert result["profile"] == "SMOKE_ONLY"
    assert "NO_UNIQUE_HAMILTONIAN_CLAIM" in result["scientific_interpretation"]
    assert result["branches"][0]["assignment"] == "D0->D2"
    assert result["branches"][0]["canonical_projection_relative_residual"] < 1e-10
