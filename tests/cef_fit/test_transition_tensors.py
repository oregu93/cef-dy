import numpy as np

from cef_fit.cef_model import CEFModel
from cef_fit.conventions import DIRECT_LM


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
