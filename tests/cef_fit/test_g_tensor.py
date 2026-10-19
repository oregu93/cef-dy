import numpy as np

from cef_fit.cef_model import CEFModel
from cef_fit.conventions import (
    DIRECT_LM,
    R_CAN_FROM_DIRECT,
    hamiltonian_from_coefficients,
    rotate_direct_hamiltonian_to_canonical,
    rotate_tensor,
)
from cef_fit.g_tensor import g_tensor


def test_pure_plus_minus_j_doublet_has_ising_g_tensor():
    pair = np.zeros((16, 2), dtype=complex)
    pair[0, 0] = 1.0   # m=-J in ascending basis
    pair[-1, 1] = 1.0  # m=+J
    result = g_tensor(pair)
    assert np.allclose(result.principal_values, [20.0, 0.0, 0.0], atol=1e-12)
    assert np.isclose(abs(result.principal_axes[2, 0]), 1.0)


def test_r7_principal_g_regression(r7_bundle):
    pair = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).eigensystem().pair(0)
    calculated = g_tensor(pair).principal_values
    reference = np.array(r7_bundle["derived"]["principal_g_values"])
    assert np.max(np.abs(calculated - reference)) < 1e-10


def test_all_doublet_g_tensors_rotate_direct_to_canonical(r7_bundle):
    direct_hamiltonian = hamiltonian_from_coefficients(7.5, r7_bundle["parameters"], DIRECT_LM)
    canonical_hamiltonian = rotate_direct_hamiltonian_to_canonical(direct_hamiltonian, 7.5)
    direct_system = CEFModel(direct_hamiltonian).eigensystem()
    canonical_system = CEFModel(canonical_hamiltonian).eigensystem()

    for doublet in range(len(direct_system.doublet_energies_meV)):
        direct = g_tensor(direct_system.pair(doublet))
        canonical = g_tensor(canonical_system.pair(doublet))
        assert np.allclose(canonical.principal_values, direct.principal_values, atol=1e-10)
        direct_metric = direct.matrix @ direct.matrix.T
        canonical_metric = canonical.matrix @ canonical.matrix.T
        assert np.allclose(
            canonical_metric,
            rotate_tensor(direct_metric, R_CAN_FROM_DIRECT),
            atol=2e-10,
        )

        # Compare eigenspaces, not signed eigenvectors. This remains valid for
        # a degenerate principal-value subspace as well as for isolated axes.
        start = 0
        while start < len(direct.principal_values):
            stop = start + 1
            while stop < len(direct.principal_values) and np.isclose(
                direct.principal_values[stop], direct.principal_values[start], atol=1e-9
            ):
                stop += 1
            expected_axes = R_CAN_FROM_DIRECT @ direct.principal_axes[:, start:stop]
            expected_projector = expected_axes @ expected_axes.T
            canonical_axes = canonical.principal_axes[:, start:stop]
            canonical_projector = canonical_axes @ canonical_axes.T
            assert np.allclose(canonical_projector, expected_projector, atol=2e-10)
            start = stop
