import numpy as np

from cef_fit.cef_model import CEFModel
from cef_fit.conventions import (
    DIRECT_LM,
    R_CAN_FROM_DIRECT,
    hamiltonian_from_coefficients,
    rotate_direct_hamiltonian_to_canonical,
    rotate_tensor,
)


def test_r7_transition_strength_regression(r7_bundle):
    model = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM)
    calculated = np.array([transition.powder_strength for transition in model.ground_transitions()])
    reference = np.array([row["strength"] for row in r7_bundle["transitions"]])
    assert np.max(np.abs(calculated - reference)) < 1e-10


def test_transition_tensor_is_hermitian_in_cartesian_indices(r7_bundle):
    model = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM)
    tensor = model.transition_tensor(0, 2)
    assert np.allclose(tensor, tensor.conj().T, atol=1e-11)
    assert np.trace(tensor).real > 0


def test_all_ground_transition_tensors_rotate_direct_to_canonical(r7_bundle):
    direct_hamiltonian = hamiltonian_from_coefficients(7.5, r7_bundle["parameters"], DIRECT_LM)
    canonical_hamiltonian = rotate_direct_hamiltonian_to_canonical(direct_hamiltonian, 7.5)
    direct_model = CEFModel(direct_hamiltonian)
    canonical_model = CEFModel(canonical_hamiltonian)

    # Each model diagonalizes its own Hamiltonian; no rotated tensor is used as
    # input to the canonical calculation.
    direct_system = direct_model.eigensystem()
    canonical_system = canonical_model.eigensystem()
    assert np.allclose(
        canonical_system.doublet_energies_meV,
        direct_system.doublet_energies_meV,
        atol=1e-10,
    )
    for final_doublet in range(1, len(direct_system.doublet_energies_meV)):
        direct_tensor = direct_model.transition_tensor(0, final_doublet, direct_system)
        canonical_tensor = canonical_model.transition_tensor(0, final_doublet, canonical_system)
        expected = rotate_tensor(direct_tensor, R_CAN_FROM_DIRECT)
        assert np.allclose(canonical_tensor, expected, atol=2e-10)
