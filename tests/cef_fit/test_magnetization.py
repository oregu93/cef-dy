from pathlib import Path

import numpy as np
import yaml

from cef_fit.magnetization import (
    abc_direction_in_direct_frame,
    configured_directions_in_direct_frame,
    magnetization_curve,
)


def test_free_ion_magnetization_is_odd_and_bounded():
    hamiltonian = np.zeros((16, 16), dtype=complex)
    curve = magnetization_curve(hamiltonian, [-2.0, 0.0, 2.0], 5.0, [0, 0, 1])
    assert np.isclose(curve.magnetization_muB_per_ion[0], -curve.magnetization_muB_per_ion[2])
    assert abs(curve.magnetization_muB_per_ion[1]) < 1e-12
    assert np.max(np.abs(curve.magnetization_muB_per_ion)) <= 10.0


def test_crystallographic_direction_mapping():
    assert np.array_equal(abc_direction_in_direct_frame("a"), [0, 0, 1])
    assert np.array_equal(abc_direction_in_direct_frame("b"), [1, 0, 0])
    assert np.array_equal(abc_direction_in_direct_frame("c"), [0, 1, 0])


def test_configured_crystallographic_directions_use_direct_frame_mapping():
    repository = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(
        (repository / "configs/manuscript_fit_v1.yaml").read_text(encoding="utf-8")
    )
    assert config["magnetization"]["directions"] == ["a", "b", "c"]
    assert "directions_abc" not in config["magnetization"]
    directions = configured_directions_in_direct_frame(config["magnetization"])
    assert np.array_equal(directions["a"], [0, 0, 1])
    assert np.array_equal(directions["b"], [1, 0, 0])
    assert np.array_equal(directions["c"], [0, 1, 0])
