import numpy as np
from scipy.special import ndtr

from cef_fit.objectives import (
    assemble_objective,
    censored_gaussian_deviance,
    detected_intensity_deviance,
    energy_deviance,
)


def test_additive_objective_components():
    components = assemble_objective(energy=1.0, detected_intensity=2.0, censored=3.0, prior=4.0)
    assert components.total == 10.0


def test_gaussian_terms():
    assert np.isclose(energy_deviance([18.0], [18.2], [0.1]), 4.0)
    assert np.isclose(detected_intensity_deviance([2.0], [5.0], [0.5], scale=2.0), 4.0)


def test_censored_term_uses_one_sided_gaussian_probability():
    value = censored_gaussian_deviance([2.0], [1.0], [0.5], scale=1.0)
    expected = -2.0 * np.log(ndtr(-2.0))
    assert np.isclose(value, expected)


def test_censored_term_is_numerically_stable():
    assert np.isfinite(censored_gaussian_deviance([1000.0], [0.0], [1.0]))
