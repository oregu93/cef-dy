from pathlib import Path

import numpy as np

from cef_fit.backends.mcphase_export import (
    compare_mcphase_levels,
    compare_mcphase_observables,
    export_parameter_lines,
    parse_parameter_lines,
    write_mcphase_bundle,
)
from cef_fit.conventions import direct_parameters_to_canonical
from cef_fit.solution_clustering import (
    DEFAULT_WEIGHTS,
    SolutionObservables,
    cluster_observable_distances,
    observable_distance_matrix,
)


def _solution(name: str, shift: float) -> SolutionObservables:
    projectors = np.zeros((8, 16, 16), dtype=complex)
    for index in range(8):
        projectors[index, 2 * index, 2 * index] = 1.0
        projectors[index, 2 * index + 1, 2 * index + 1] = 1.0
    return SolutionObservables(
        solution_id=name,
        h_coordinates_meV=np.full(15, shift),
        doublet_energies_meV=np.arange(8, dtype=float) + shift,
        projectors=projectors,
        transition_strengths=np.arange(1, 8, dtype=float) + shift,
        g_principal_values=np.array([10.0, 2.0, 1.0]) + shift,
        g_principal_axes=np.eye(3),
        mh_predictions=np.array([1.0, 2.0, 3.0]) + shift,
    )


def test_observable_aware_clustering_uses_all_feature_blocks():
    solutions = [_solution("A", 0.0), _solution("B", 0.01), _solution("C", 3.0)]
    scales = {
        "parameter_meV": 1.0,
        "energy_meV": 1.0,
        "transition_strength": 1.0,
        "g_value": 1.0,
        "magnetization_muB": 1.0,
    }
    matrix, components = observable_distance_matrix(solutions, DEFAULT_WEIGHTS, scales)
    assert set(components) == {
        "parameter", "energy", "projector", "neutron", "g_tensor", "magnetization"
    }
    assert matrix[0, 1] < matrix[0, 2]
    labels = cluster_observable_distances(matrix, distance_threshold=0.2)
    assert labels[0] == labels[1]
    assert labels[2] != labels[0]


def test_mcphase_export_round_trip_and_mismatch_never_refits(r7_bundle, tmp_path):
    canonical = direct_parameters_to_canonical(r7_bundle["parameters"])
    text = export_parameter_lines(canonical.coefficients)
    parsed = parse_parameter_lines(text)
    assert parsed.keys() == canonical.coefficients.keys()
    assert all(
        np.isclose(parsed[key], canonical.coefficients[key], atol=1e-14, rtol=0)
        for key in parsed
    )
    parameter_path, metadata_path = write_mcphase_bundle(
        tmp_path,
        "R7",
        canonical.coefficients,
        {"scientific_status": "TEST_ONLY"},
    )
    assert parameter_path.exists() and metadata_path.exists()
    passed = compare_mcphase_levels([0, 1, 2], [0, 1, 2])
    assert passed["status"] == "PASS"
    failed = compare_mcphase_levels([0, 1, 2], [0, 1, 2.1])
    assert failed["status"] == "MISMATCH_REVIEW_CONVENTIONS"
    assert failed["automatic_refit_performed"] is False
    observables = compare_mcphase_observables(
        project_levels_meV=[0, 1, 2],
        project_canonical_hamiltonian_meV=np.eye(3),
        project_g_principal_values=[10, 2, 1],
        project_mh_muB_per_Dy=[0, 1],
        external={
            "levels_meV": [0, 1, 2],
            "frame_axes": ["b", "-a", "c"],
            "canonical_hamiltonian_real": np.eye(3).tolist(),
            "g_principal_values": [1, 2, 10],
            "mh_muB_per_Dy": [0, 1],
        },
    )
    assert observables["status"] == "PASS_AVAILABLE_CHECKS"
    assert observables["checks"]["hamiltonian_convention"]["status"] == "PASS"
