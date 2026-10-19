import numpy as np

from cef_fit.g_tensor import g_tensor


def test_pure_plus_minus_j_doublet_has_ising_g_tensor():
    pair = np.zeros((16, 2), dtype=complex)
    pair[0, 0] = 1.0   # m=-J in ascending basis
    pair[-1, 1] = 1.0  # m=+J
    result = g_tensor(pair)
    assert np.allclose(result.principal_values, [20.0, 0.0, 0.0], atol=1e-12)
    assert np.isclose(abs(result.principal_axes[2, 0]), 1.0)


def test_r7_principal_g_regression(r7_bundle):
    from cef_fit.cef_model import CEFModel
    from cef_fit.conventions import DIRECT_LM

    pair = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).eigensystem().pair(0)
    calculated = g_tensor(pair).principal_values
    reference = np.array(r7_bundle["derived"]["principal_g_values"])
    assert np.max(np.abs(calculated - reference)) < 1e-10
