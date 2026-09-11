#!/usr/bin/env python3
"""Synthetic/semantic acceptance tests for Stage03R implementation v1.0."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import yaml

import stage03r_compatibility as kernel


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CONFIG_PATH = SCRIPT_DIR / "stage03r_compatibility_config.yaml"


def support(identifier: str, lower: float, upper: float, complex_id: str = "CX-TEST") -> dict:
    return {
        "schema_type": "stage03r_support_region",
        "schema_version": "1.0",
        "observation_id": identifier,
        "role": "SUPPORT_REGION",
        "energy_region_meV": {"lower": lower, "upper": upper},
        "source_bf_id": identifier,
        "complex_id": complex_id,
        "interval_semantics": {
            "closed_lower": True,
            "closed_upper": True,
            "probability_density_defined": False,
            "confidence_interval": False,
            "centroid_measurement": False,
            "linewidth_measurement": False,
            "likelihood_defined": False,
        },
        "assignment_status": "unassigned",
        "provenance": {"source_artifact": {"path": "synthetic.yaml", "sha256": "0" * 64}},
    }


def bundle(transitions: list[tuple[str, float]], model_id: str = "MOD-PCM-FORMAL") -> dict:
    return {
        "schema_type": "stage03r_prediction_bundle",
        "schema_version": "1.0",
        "prediction_bundle_id": "PB-SYN-001",
        "model_id": model_id,
        "parameter_set_id": "PS-SYN-001",
        "parameter_source": "synthetic_fixture",
        "provenance": {
            "source_artifact": "synthetic",
            "source_identity": "SYNTHETIC",
            "generator_name": "explicit-fixture",
            "generator_version": "1",
            "generation_method": "deterministic",
            "evidence_used_to_generate": [],
            "generated_from_current_stage03r_observations": False,
        },
        "convention": {
            "cef_convention_id": "SYN",
            "stevens_normalization_id": "SYN",
            "coefficient_units": "meV",
            "crystallographic_setting": "synthetic",
            "global_frame_id": "G-SYN",
            "local_frame_id": "L-SYN",
            "local_to_global_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "canonical_parameter_order": [],
        },
        "parameters": None,
        "levels": [],
        "transitions": [
            {"transition_id": identifier, "initial_level_id": "L0", "final_level_id": identifier,
             "energy_meV": energy, "strength": None, "transition_tensor": None}
            for identifier, energy in transitions
        ],
        "transition_inventory": {"status": "complete_for_declared_scope", "declared_scope": "synthetic"},
        "derived": {"principal_g_values": None, "other_invariants": None},
    }


def component(identifier: str, supports: list[str], transitions: list[str], *,
              support_mode: str = "ALL_OF", required: bool = True) -> dict:
    return {
        "component_id": identifier,
        "source_support_constraint": {"mode": support_mode, "support_ids": supports},
        "classification": "CEF_CANDIDATE" if required else "NON_CEF_CANDIDATE",
        "cef_transition_mapping": {
            "mode": "ONE_OF" if transitions else "UNASSIGNED",
            "candidate_transition_ids": transitions,
        },
        "required_cef_explanation": required,
    }


def family(components: list[dict], unassigned: list[str] | None = None) -> dict:
    return {
        "schema_type": "stage03r_assignment_family",
        "schema_version": "1.0",
        "assignment_family_id": "AF-SYN-001",
        "origin": "synthetic_test",
        "review_status": "synthetic",
        "complexes": [{"complex_id": "CX-TEST", "multiplicity_hypothesis": "synthetic",
                       "components": components}],
        "unassigned_support_ids": unassigned or [],
        "status": {"admission_status": "synthetic_only"},
    }


def synthetic_transform() -> dict:
    endpoint = {
        "cef_convention_id": "SYN", "stevens_normalization_id": "SYN", "units": "meV",
        "crystallographic_setting": "SYN", "global_frame_id": "G", "local_frame_id": "L",
    }
    return {
        "transform_id": "TR-SYN-001", "from": endpoint, "to": endpoint,
        "parameter_transform": "identity", "frame_transform": "registered-synthetic",
        "provenance": {"source": "synthetic fixture", "review_status": "synthetic"},
        "status": "synthetic_only",
    }


class Stage03RCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        kernel.validate_config(cls.config)
        cls.tol = cls.config["numerical_tolerances"]

    def test_STAGE03R_T01_midpoint_prohibition(self) -> None:
        record = support("BF-901", 1.0, 2.0)
        record["centroid_meV"] = 1.5
        with self.assertRaisesRegex(kernel.ContractError, "INVALID_OBSERVATION_ROLE"):
            kernel.validate_support_region(record)

    def test_STAGE03R_T02_legacy_namespace(self) -> None:
        record = support("F002", 1.0, 2.0)
        with self.assertRaisesRegex(kernel.ContractError, "LEGACY_NAMESPACE_VIOLATION"):
            kernel.validate_support_region(record)

    def test_STAGE03R_T03_C002_numerical_failure_semantics(self) -> None:
        with self.assertRaisesRegex(kernel.ContractError, "INVALID_OBSERVATION_ROLE"):
            kernel.validate_execution_request({"physical_absence_from_C002_numerical_failure": True})

    def test_STAGE03R_T04_joint_mapping_and_zero_obligation(self) -> None:
        supports = {"BF-901": support("BF-901", 1.0, 1.2),
                    "BF-902": support("BF-902", 1.8, 2.2)}
        invalid = family([
            component("C1", ["BF-901"], ["T1"]),
            component("C2", ["BF-902"], ["T1"]),
        ])
        result = kernel.fixed_forward_compatibility(invalid, supports, bundle([("T1", 1.1)]), 1e-10)
        self.assertEqual(result["status"], "FAMILY_INCOMPATIBLE")
        valid = family([
            component("C1", ["BF-901"], ["T1", "T2"]),
            component("C2", ["BF-902"], ["T1", "T2"]),
        ])
        result = kernel.fixed_forward_compatibility(valid, supports,
                                                    bundle([("T1", 1.1), ("T2", 2.0)]), 1e-10)
        self.assertEqual(result["status"], "FAMILY_COMPATIBLE")
        self.assertEqual(result["joint_mappings"], [{"C1": "T1", "C2": "T2"}])
        zero = family([component("NC", ["BF-901"], [], required=False)])
        result = kernel.fixed_forward_compatibility(zero, supports, bundle([("T1", 1.1)]), 1e-10)
        self.assertEqual(result["status"], "NOT_TESTABLE")

    def test_STAGE03R_T05_missing_support_is_not_zero_intensity(self) -> None:
        with self.assertRaisesRegex(kernel.ContractError, "INVALID_OBSERVATION_ROLE"):
            kernel.validate_execution_request({"zero_intensity_from_missing_support": True})

    def test_STAGE03R_T06_normalization_gate(self) -> None:
        with self.assertRaisesRegex(kernel.ContractError, "NORMALIZATION_GATE_VIOLATION"):
            kernel.validate_execution_request({"normalization": True})

    def test_STAGE03R_T07_optimizer_is_not_identifiability(self) -> None:
        with self.assertRaisesRegex(kernel.ContractError, "INVALID_PROVENANCE"):
            kernel.validate_execution_request({"optimizer": True})
        self.assertEqual(kernel.matrix_rank([[1, 0, 1], [0, 1, 1]]), 2)

    def test_STAGE03R_T08_circular_assignment(self) -> None:
        circular = bundle([("T1", 1.0)])
        circular["provenance"]["generated_from_current_stage03r_observations"] = True
        with self.assertRaisesRegex(kernel.ContractError, "CIRCULAR_ASSIGNMENT"):
            kernel.validate_prediction_bundle(circular)

    def test_STAGE03R_T09_exchange_gate(self) -> None:
        with self.assertRaisesRegex(kernel.ContractError, "EXCHANGE_GATE_VIOLATION"):
            kernel.validate_execution_request({"exchange": True})

    def test_STAGE03R_T10_interval_boundary_and_nonstatistical_semantics(self) -> None:
        tau = self.tol["interval_boundary_abs_meV"]
        for energy in (1.0, 2.0, 1.0 - tau / 2, 2.0 + tau / 2):
            self.assertEqual(kernel.distance_to_region(energy, 1.0, 2.0, tau),
                             {"relation": "INSIDE", "distance_meV": 0.0})
        below = kernel.distance_to_region(1.0 - 2 * tau, 1.0, 2.0, tau)
        above = kernel.distance_to_region(2.0 + 2 * tau, 1.0, 2.0, tau)
        self.assertEqual(below["relation"], "BELOW_REGION")
        self.assertGreater(below["distance_meV"], 0)
        self.assertEqual(above["relation"], "ABOVE_REGION")
        self.assertGreater(above["distance_meV"], 0)
        invalid = support("BF-901", 1.0, 2.0)
        invalid["interval_semantics"]["confidence_interval"] = True
        with self.assertRaises(kernel.ContractError):
            kernel.validate_support_region(invalid)

    def test_STAGE03R_T11_convention_equivalence(self) -> None:
        comparison = self.tol["hamiltonian_comparison"]
        transform = synthetic_transform()
        h = [[0.0, 0.0], [0.0, 1.0]]
        theta = math.pi / 5
        unitary = [[math.cos(theta), -math.sin(theta)],
                   [math.sin(theta), math.cos(theta)]]
        transformed = kernel.unitary_similarity_transform(h, unitary)
        self.assertFalse(kernel.frobenius_equivalent(h, transformed, 1e-12))
        common_frame = kernel.unitary_similarity_transform(
            transformed, kernel.conjugate_transpose(unitary),
        )
        self.assertTrue(kernel.registered_hamiltonian_equivalence(
            h, common_frame, transform, comparison,
        ))
        isospectral_distinct = [[1.0, 0.0], [0.0, 0.0]]
        self.assertFalse(kernel.registered_hamiltonian_equivalence(
            h, isospectral_distinct, transform, comparison))

    def test_STAGE03R_T12_Kramers_gauge(self) -> None:
        vectors = [[1 + 0j, 0j], [0j, 1 + 0j], [0j, 0j], [0j, 0j]]
        unitary = [[1 / math.sqrt(2), 1j / math.sqrt(2)],
                   [1j / math.sqrt(2), 1 / math.sqrt(2)]]
        rotated_vectors = kernel.matmul(vectors, unitary)
        self.assertNotEqual(vectors, rotated_vectors)
        p1 = kernel.projector_from_columns(vectors)
        p2 = kernel.projector_from_columns(rotated_vectors)
        self.assertEqual((len(p1), len(p1[0])), (4, 4))
        projector_tol = self.tol["projector_comparison"]["absolute_frobenius"]
        self.assertTrue(kernel.frobenius_equivalent(p1, p2, projector_tol))
        other_vectors = [[0j, 0j], [0j, 0j], [1 + 0j, 0j], [0j, 1 + 0j]]
        p_other = kernel.projector_from_columns(other_vectors)
        coupling = [[0, 0, 1, 0], [0, 0, 0, 2],
                    [1, 0, 0, 0], [0, 2, 0, 0]]
        t1 = kernel.transition_tensor(p1, p_other, [coupling])
        t2 = kernel.transition_tensor(p2, p_other, [coupling])
        self.assertGreater(abs(t1[0][0]), 0)
        invariant = self.tol["invariant_comparison"]
        self.assertTrue(kernel.frobenius_equivalent(t1, t2,
                                                    invariant["absolute"], invariant["relative"]))

    def test_SYN_M0_exact_interval_algebra(self) -> None:
        supports = {"BF-901": support("BF-901", 1.0, 2.0),
                    "BF-902": support("BF-902", 4.0, 5.0)}
        connected = family([component("C0", ["BF-901"], ["T1"])])
        connected_result = kernel.m0_family_compatibility(
            connected, supports, {"T1": 2.0}, self.tol["interval_merge"])
        self.assertEqual(connected_result["compatible_s"], [(0.5, 1.0)])
        assignment = family([component("C1", ["BF-901", "BF-902"], ["T1"],
                                       support_mode="ANY_OF")])
        result = kernel.m0_family_compatibility(
            assignment, supports, {"T1": 2.0}, self.tol["interval_merge"])
        self.assertEqual(result["status"], "FAMILY_COMPATIBLE")
        self.assertEqual(result["compatible_s"], [(0.5, 1.0), (2.0, 2.5)])
        empty = family([
            component("C1", ["BF-901"], ["T1"]),
            component("C2", ["BF-902"], ["T2"]),
        ])
        empty_result = kernel.m0_family_compatibility(
            empty, supports, {"T1": 1.0, "T2": 1.0}, self.tol["interval_merge"])
        self.assertEqual(empty_result["status"], "FAMILY_INCOMPATIBLE")
        self.assertEqual(empty_result["compatible_s"], [])
        merge = self.tol["interval_merge"]
        self.assertEqual(kernel.canonicalize_intervals(
            [(0.5, 1.0), (0.8, 1.2), (1.2 + merge["absolute"] / 2, 1.5)],
            absolute=merge["absolute"], relative=merge["relative"]), [(0.5, 1.5)])
        zero = family([component("NC", ["BF-901"], [], required=False)])
        self.assertEqual(kernel.m0_family_compatibility(
            zero, supports, {"T1": 2.0}, self.tol["interval_merge"])["status"],
            "NOT_TESTABLE")

    def test_RC_01_tolerance_aware_M0_intersections(self) -> None:
        tolerance = self.tol["interval_merge"]
        absolute, relative = tolerance["absolute"], tolerance["relative"]
        overlap = kernel.intersect_interval_sets(
            [(1.0, 2.0)], [(1.5, 3.0)], absolute=absolute, relative=relative,
        )
        self.assertEqual(overlap, [(1.5, 2.0)])
        touching = kernel.intersect_interval_sets(
            [(1.0, 2.0)], [(2.0, 3.0)], absolute=absolute, relative=relative,
        )
        self.assertEqual(touching, [(2.0, 2.0)])
        numerical_gap = absolute / 2
        near_touch = kernel.intersect_interval_sets(
            [(1.0, 2.0)], [(2.0 + numerical_gap, 3.0)],
            absolute=absolute, relative=relative,
        )
        expected_touch = 2.0 + numerical_gap / 2
        self.assertEqual(near_touch, [(expected_touch, expected_touch)])
        finite_gap = 10 * (absolute + relative * 3.0)
        self.assertEqual(kernel.intersect_interval_sets(
            [(1.0, 2.0)], [(2.0 + finite_gap, 3.0)],
            absolute=absolute, relative=relative,
        ), [])
        disconnected = kernel.intersect_interval_sets(
            [(1.0, 1.5), (2.5, 3.0)], [(0.5, 3.5)],
            absolute=absolute, relative=relative,
        )
        self.assertEqual(disconnected, [(1.0, 1.5), (2.5, 3.0)])

    def test_RC_02_M0_strict_positive_domain(self) -> None:
        tolerance = self.tol["interval_merge"]
        ordinary = kernel.m0_family_compatibility(
            family([component("C1", ["BF-901"], ["T1"])]),
            {"BF-901": support("BF-901", 1.0, 2.0)},
            {"T1": 2.0}, tolerance,
        )
        self.assertEqual(ordinary["compatible_s"], [(0.5, 1.0)])
        self.assertTrue(all(lower > 0 for lower, _ in ordinary["compatible_s"]))
        with self.assertRaisesRegex(kernel.ContractError, "NUMERICAL_DIAGNOSTIC_FAILURE"):
            kernel.m0_family_compatibility(
                family([component("C1", ["BF-901"], ["T1"])]),
                {"BF-901": support("BF-901", 0.0, 2.0)},
                {"T1": 2.0}, tolerance,
            )

    def test_SYN_M1_E_extended_manifold(self) -> None:
        result = kernel.m1_linear_sum_compatibility(
            [(0.2, 0.8), (0.4, 0.6), (0.8, 0.2), (0.9, 0.4)],
            (1.0, 1.0), self.tol["interval_boundary_abs_meV"],
        )
        self.assertEqual(result["forward_relation"], "s1_plus_s2")
        self.assertEqual(result["compatible_points"], [(0.2, 0.8), (0.4, 0.6), (0.8, 0.2)])
        self.assertEqual(result["compatible_observables"], [1.0, 1.0, 1.0])
        self.assertFalse(result["parameter_point_identified"])
        self.assertIsNone(result["preferred_point"])
        self.assertEqual(result["scientific_status"], "PARAMETER_NONIDENTIFIABLE")

    def test_SYN_CS15_E7_rank_bound(self) -> None:
        jacobian = [[1.0 if column == row else 0.0 for column in range(15)] for row in range(7)]
        rank = kernel.matrix_rank(jacobian)
        self.assertEqual(rank, 7)
        self.assertLess(rank, 15)

    def test_convention_equivalence_fixture_norms(self) -> None:
        norms = self.config["comparison_norms"]
        self.assertEqual(norms["hamiltonian"], "Frobenius")
        self.assertEqual(norms["projector"], "Frobenius")
        self.assertEqual(norms["matrix_or_tensor_invariant"], "Frobenius")
        self.assertEqual(norms["scalar_invariant"], "absolute_plus_relative")

    def test_Kramers_gauge_fixture_raw_vectors_not_authoritative(self) -> None:
        vectors = [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0], [0.0, 0.0]]
        theta = math.pi / 7
        unitary = [[math.cos(theta), -math.sin(theta)],
                   [math.sin(theta), math.cos(theta)]]
        rotated = kernel.matmul(vectors, unitary)
        self.assertNotEqual(rotated, vectors)
        self.assertTrue(kernel.frobenius_equivalent(
            kernel.projector_from_columns(rotated), kernel.projector_from_columns(vectors), 1e-12))

    def test_prediction_bundle_validation_and_partial_inventory(self) -> None:
        partial = bundle([("T1", 1.0)])
        partial["transition_inventory"]["status"] = "partial"
        self.assertEqual(kernel.validate_prediction_bundle(partial)["prediction_bundle_id"], "PB-SYN-001")

    def test_fixed_forward_multiple_support_structures(self) -> None:
        supports = {"BF-901": support("BF-901", 0.9, 1.1),
                    "BF-902": support("BF-902", 0.95, 1.05)}
        assignment = family([component("C1", list(supports), ["T1"], support_mode="ALL_OF")])
        result = kernel.fixed_forward_compatibility(assignment, supports, bundle([("T1", 1.0)]), 1e-10)
        self.assertEqual(result["status"], "FAMILY_COMPATIBLE")

    def test_model_status_strict_falsification(self) -> None:
        explicit = {"inventories_complete": True, "convention_valid": True}
        self.assertEqual(kernel.model_status([], real_families_admitted=False,
                                             **explicit)["model_status"], "NOT_TESTABLE")
        self.assertEqual(kernel.model_status([{"status": "NOT_TESTABLE"}],
                                             real_families_admitted=True,
                                             **explicit)["model_status"], "NOT_TESTABLE")
        self.assertEqual(kernel.model_status([{"status": "FAMILY_INCOMPATIBLE"}],
                                             real_families_admitted=True,
                                             **explicit)["model_status"], "MODEL_FALSIFIED")
        incomplete = kernel.model_status(
            [{"status": "FAMILY_INCOMPATIBLE"}], real_families_admitted=True,
            inventories_complete=False, convention_valid=True,
        )
        self.assertEqual(incomplete["model_status"], "NOT_TESTABLE")
        invalid_convention = kernel.model_status(
            [{"status": "FAMILY_INCOMPATIBLE"}], real_families_admitted=True,
            inventories_complete=True, convention_valid=False,
        )
        self.assertEqual(invalid_convention["model_status"], "NOT_TESTABLE")
        with self.assertRaises(TypeError):
            kernel.model_status([{"status": "FAMILY_INCOMPATIBLE"}],
                                real_families_admitted=True)
        mixed = kernel.model_status([{"status": "FAMILY_COMPATIBLE"},
                                     {"status": "FAMILY_INCOMPATIBLE"}],
                                    real_families_admitted=True, **explicit)
        self.assertEqual(mixed, {"model_status": "MODEL_COMPATIBLE", "assignment_ambiguity": True})
        compatible_with_untestable = kernel.model_status(
            [{"status": "FAMILY_COMPATIBLE"}, {"status": "NOT_TESTABLE"}],
            real_families_admitted=True, **explicit)
        self.assertEqual(compatible_with_untestable,
                         {"model_status": "MODEL_COMPATIBLE", "assignment_ambiguity": True})

    def test_deterministic_serialization_and_exact_outputs(self) -> None:
        payloads = {name: {"artifact": name, "values": [2, 1]} for name in kernel.OUTPUT_SCHEMAS}
        first = kernel.build_output_package(payloads)
        second = kernel.build_output_package(payloads)
        self.assertEqual(first, second)
        self.assertEqual(tuple(first), kernel.OUTPUT_SCHEMAS)
        with self.assertRaises(kernel.ContractError):
            kernel.build_output_package({**payloads, "sixth.yaml": {}})

    def test_tolerance_calibration_contract(self) -> None:
        tau = self.tol["interval_boundary_abs_meV"]
        minimum_synthetic_width = 1.0
        self.assertLessEqual(tau, 1e-6 * minimum_synthetic_width)
        self.assertFalse(self.config["tolerance_semantics"]["real_model_compatibility_used_for_tuning"])

    def test_derived_observable_diagnostic(self) -> None:
        diagnostic = kernel.derived_observable_diagnostic([2.0, 2.0 + 1e-13], 1e-10, 1e-12)
        self.assertTrue(diagnostic["stable"])
        self.assertEqual(diagnostic["set_size"], 2)

    def test_repository_frozen_identity_validation(self) -> None:
        kernel.validate_repository_identities(ROOT, self.config)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Stage03RCompatibilityTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print("STAGE03R_IMPLEMENTATION_TESTS")
    print(f"passed={passed}")
    print(f"failed={len(result.failures) + len(result.errors)}")
    print(f"status={'PASS' if result.wasSuccessful() else 'FAIL'}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
