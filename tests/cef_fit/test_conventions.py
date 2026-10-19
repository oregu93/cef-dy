import numpy as np

from cef_fit.conventions import (
    CANONICAL_CS_LM,
    DIRECT_LM,
    R_CAN_FROM_DIRECT,
    direct_parameters_to_canonical,
    hamiltonian_from_coefficients,
    rotate_direct_hamiltonian_to_canonical,
)


def test_frame_rotation_is_proper_orthogonal():
    assert np.allclose(R_CAN_FROM_DIRECT @ R_CAN_FROM_DIRECT.T, np.eye(3))
    assert np.isclose(np.linalg.det(R_CAN_FROM_DIRECT), 1.0)


def test_direct_to_canonical_hamiltonian_regression(r7_bundle):
    direct = hamiltonian_from_coefficients(7.5, r7_bundle["parameters"], DIRECT_LM)
    expected = rotate_direct_hamiltonian_to_canonical(direct, 7.5)
    projection = direct_parameters_to_canonical(r7_bundle["parameters"], 7.5)
    rebuilt = hamiltonian_from_coefficients(7.5, projection.coefficients, CANONICAL_CS_LM)
    assert projection.relative_residual < 2e-12
    assert np.max(np.abs(expected - rebuilt)) < 1e-10


def test_direct_labels_are_not_negative_m_aliases():
    assert (2, 1) in DIRECT_LM
    assert (2, -2) in CANONICAL_CS_LM
    assert DIRECT_LM != CANONICAL_CS_LM
