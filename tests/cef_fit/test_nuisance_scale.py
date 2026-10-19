import numpy as np

from cef_fit.nuisance import profile_block_scale


def test_detected_only_profile_recovers_known_scale():
    result = profile_block_scale(
        detected_calculated=[1.0, 2.0, 3.0],
        detected_observed=[2.0, 4.0, 6.0],
        detected_sigma=[0.1, 0.1, 0.1],
    )
    assert result.converged
    assert np.isclose(result.scale, 2.0, rtol=1e-6)
    assert not result.boundary_occupied


def test_joint_detected_censored_profile_is_finite():
    result = profile_block_scale(
        detected_calculated=[1.0], detected_observed=[1.0], detected_sigma=[0.2],
        censored_calculated=[0.2], censor_limits=[0.5], censor_sigma=[0.1],
    )
    assert result.converged
    assert np.isfinite(result.deviance)
