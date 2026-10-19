import numpy as np
import pytest

from cef_fit.backends import cfe_backend, pcf_backend
from cef_fit.cef_model import CEFModel
from cef_fit.conventions import DIRECT_LM


@pytest.mark.skipif(not pcf_backend.available(), reason="optional PyCrystalField backend not installed")
def test_pcf_hamiltonian_matrix_crosscheck(r7_bundle):
    authoritative = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).hamiltonian_meV
    assert np.max(np.abs(authoritative - pcf_backend.direct_hamiltonian(r7_bundle["parameters"]))) < 1e-10


@pytest.mark.skipif(not cfe_backend.available(), reason="optional CrysFieldExplorer backend not installed")
def test_cfe_hamiltonian_matrix_crosscheck(r7_bundle):
    authoritative = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM).hamiltonian_meV
    assert np.max(np.abs(authoritative - cfe_backend.direct_hamiltonian(r7_bundle["parameters"]))) < 1e-10
