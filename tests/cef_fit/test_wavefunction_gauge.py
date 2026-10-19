import numpy as np

from cef_fit.cef_model import CEFModel
from cef_fit.conventions import DIRECT_LM
from cef_fit.wavefunctions import doublet_projector, export_wavefunctions, gauge_fix_doublet, time_reverse


def test_projector_is_invariant_under_internal_doublet_rotation(r7_bundle):
    pair = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).eigensystem().pair(0)
    unitary = np.array([[1, 1], [-1, 1]], dtype=complex) / np.sqrt(2)
    assert np.allclose(doublet_projector(pair), doublet_projector(pair @ unitary), atol=1e-12)


def test_gauge_fixed_partner_uses_time_reversal(r7_bundle):
    pair = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).eigensystem().pair(0)
    fixed = gauge_fix_doublet(pair)
    reference = time_reverse(fixed.plus)
    assert abs(abs(np.vdot(reference, fixed.minus)) - 1.0) < 1e-12
    assert np.allclose(fixed.projector, doublet_projector(np.column_stack((fixed.plus, fixed.minus))), atol=1e-11)


def test_wavefunction_export_contains_projectors_and_gauge_fixed_states(r7_bundle, tmp_path):
    system = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).eigensystem()
    npz_path, json_path = export_wavefunctions(tmp_path / "R7", tuple(system.pair(i) for i in range(8)))
    archive = np.load(npz_path)
    assert archive["projectors"].shape == (8, 16, 16)
    assert archive["plus"].shape == (8, 16)
    assert json_path.exists()
