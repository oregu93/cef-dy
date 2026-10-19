import numpy as np

from cef_fit.cef_model import CEFModel
from cef_fit.conventions import DIRECT_LM
from cef_fit.operators import angular_momentum_operators, stevens_operator


def test_angular_momentum_commutator():
    jx, jy, jz = angular_momentum_operators(7.5)
    assert np.max(np.abs(jx @ jy - jy @ jx - 1j * jz)) < 1e-12


def test_all_cs15_operators_are_hermitian():
    for rank in (2, 4, 6):
        for m in range(-rank, rank + 1):
            operator = stevens_operator(7.5, rank, m)
            assert np.allclose(operator, operator.conj().T, atol=1e-11)


def test_r7_level_and_kramers_regression(r7_bundle):
    model = CEFModel.from_coefficients(r7_bundle["parameters"], DIRECT_LM)
    system = model.eigensystem()
    reference = np.array([row["energy_meV"] for row in r7_bundle["levels"]])
    assert np.max(np.abs(system.doublet_energies_meV - reference)) < 1e-10
    assert np.max(system.doublet_splittings_meV) < 1e-10
