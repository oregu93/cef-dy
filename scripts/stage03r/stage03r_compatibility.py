#!/usr/bin/env python3
"""Deterministic Stage03R compatibility kernel.

This module implements set-valued, assignment-aware compatibility checks
defined by STAGE03R-IMPLEMENTATION-SPEC v1.0.  It intentionally contains no
optimizer, likelihood, detector-data reader, or production CEF inversion.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml


SCHEMA_VERSION = "1.0"
IMPLEMENTATION_SPEC_ID = "STAGE03R-IMPLEMENTATION-SPEC"
IMPLEMENTATION_SPEC_SHA256 = (
    "3d6ea0a6255681a29268950d14accef15028359fe845cd09dcdc1ccdbc6e95ec"
)
SCIENTIFIC_SPEC_ID = "STAGE03R-INFERENCE-SPEC"
SCIENTIFIC_SPEC_SHA256 = (
    "aa67a08bbfd1894dfaad13488cb48ab57b6cf0f44d51567a9c61191e55f2e2ac"
)
B001_SHA256 = "f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5"

ALLOWED_MODELS = {
    "MOD-PCM-FORMAL",
    "MOD-PCM-M0",
    "MOD-PCM-M1",
    "MOD-CEF-CS15",
}
OUTPUT_SCHEMAS = (
    "input_manifest.yaml",
    "observation_table.yaml",
    "assignment_families.yaml",
    "model_compatibility.yaml",
    "identifiability_summary.yaml",
)
FORBIDDEN_OBSERVATION_FIELDS = {
    "centroid",
    "centroid_meV",
    "sigma",
    "sigma_meV",
    "Gaussian_energy",
    "physical_fwhm",
    "transition_energy",
    "measured_peak_energy",
}
LEGACY_OBSERVATION_IDS = {"F002", "F004"}


class ContractError(ValueError):
    """A deterministic frozen-contract validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ContractError(code, message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def validate_config(config: Mapping[str, Any]) -> None:
    _require(config.get("schema_type") == "stage03r_compatibility_config",
             "INVALID_PROVENANCE", "unexpected config schema_type")
    _require(str(config.get("schema_version")) == SCHEMA_VERSION,
             "INVALID_PROVENANCE", "unexpected config schema_version")
    identities = config.get("canonical_identities", {})
    expected = {
        "implementation_specification": (IMPLEMENTATION_SPEC_ID, IMPLEMENTATION_SPEC_SHA256),
        "scientific_specification": (SCIENTIFIC_SPEC_ID, SCIENTIFIC_SPEC_SHA256),
        "B001_catalogue": (None, B001_SHA256),
    }
    for key, (expected_id, expected_sha) in expected.items():
        record = identities.get(key, {})
        if expected_id is not None:
            _require(record.get("id") == expected_id, "INVALID_PROVENANCE",
                     f"{key} identity mismatch")
        _require(record.get("sha256") == expected_sha, "INVALID_PROVENANCE",
                 f"{key} SHA-256 mismatch")
    _require(set(config.get("allowed_models", [])) == ALLOWED_MODELS,
             "INVALID_PROVENANCE", "model scope differs from frozen v1.0")
    _require(config.get("active_observation_roles") == ["SUPPORT_REGION"],
             "INVALID_OBSERVATION_ROLE", "only SUPPORT_REGION may be active")
    _require(config.get("real_assignment_families") == [], "CIRCULAR_ASSIGNMENT",
             "implementation acceptance requires an empty real assignment catalogue")
    _require(config.get("real_FORMAL_bundle") is None, "INVALID_PROVENANCE",
             "real FORMAL bundle is not admitted")
    _require(config.get("real_CS15_ensemble") is None, "INVALID_PROVENANCE",
             "real CS15 ensemble is not admitted")
    _require(config.get("real_convention_transformations") == [],
             "CONVENTION_CONTRACT_INCOMPLETE",
             "real convention transformations are not admitted")
    _require(tuple(config.get("output_schemas", [])) == OUTPUT_SCHEMAS,
             "INVALID_PROVENANCE", "exactly five frozen output schemas are required")
    norms = config.get("comparison_norms", {})
    _require(norms == {
        "hamiltonian": "Frobenius",
        "projector": "Frobenius",
        "matrix_or_tensor_invariant": "Frobenius",
        "scalar_invariant": "absolute_plus_relative",
    }, "NUMERICAL_DIAGNOSTIC_FAILURE", "comparison norms differ from frozen v1.0")
    gates = config.get("execution_gates", {})
    for key in (
        "Stage03R_execution_authorized", "W03_authorized",
        "production_CEF_fit_authorized", "raw_detector_access_authorized",
        "holdout_reanalysis_authorized", "Stage03D_resumed",
        "optimizer_authorized", "likelihood_authorized",
        "normalization_authorized", "exchange_authorized",
    ):
        _require(gates.get(key) is False, "INVALID_PROVENANCE",
                 f"execution gate {key} must remain false")
    tolerances(config)


def tolerances(config: Mapping[str, Any]) -> Mapping[str, Any]:
    values = config.get("numerical_tolerances", {})
    required_positive = [
        values.get("interval_boundary_abs_meV"),
        values.get("interval_merge", {}).get("absolute"),
        values.get("interval_merge", {}).get("relative"),
        values.get("hamiltonian_comparison", {}).get("absolute_meV"),
        values.get("hamiltonian_comparison", {}).get("relative"),
        values.get("projector_comparison", {}).get("absolute_frobenius"),
        values.get("invariant_comparison", {}).get("absolute"),
        values.get("invariant_comparison", {}).get("relative"),
    ]
    _require(all(isinstance(v, (int, float)) and v > 0 for v in required_positive),
             "NUMERICAL_DIAGNOSTIC_FAILURE", "all numerical tolerances must be positive")
    semantics = config.get("tolerance_semantics", {})
    for key in (
        "physical_uncertainty_meaning", "linewidth_meaning",
        "TAS_resolution_meaning", "statistical_confidence_meaning",
    ):
        _require(semantics.get(key) == "none", "NUMERICAL_DIAGNOSTIC_FAILURE",
                 f"tolerance semantic {key} must be none")
    _require(semantics.get("real_model_compatibility_used_for_tuning") is False,
             "NUMERICAL_DIAGNOSTIC_FAILURE",
             "real model compatibility cannot calibrate tolerances")
    return values


def validate_repository_identities(root: Path, config: Mapping[str, Any]) -> None:
    validate_config(config)
    identities = config["canonical_identities"]
    for key in ("implementation_specification", "scientific_specification", "B001_catalogue"):
        record = identities[key]
        path = root / record["path"]
        _require(path.is_file(), "INVALID_PROVENANCE", f"missing {key}: {record['path']}")
        _require(sha256_file(path) == record["sha256"], "INVALID_PROVENANCE",
                 f"{key} content SHA-256 mismatch")
    catalogue = load_yaml(root / identities["B001_catalogue"]["path"])
    widths = [float(item["discovery_energy_interval"][1]) -
              float(item["discovery_energy_interval"][0])
              for item in catalogue.get("features", [])]
    _require(widths and min(widths) > 0, "INVALID_PROVENANCE",
             "B001 does not provide positive support widths")
    boundary = config["numerical_tolerances"]["interval_boundary_abs_meV"]
    _require(boundary <= 1e-6 * min(widths), "NUMERICAL_DIAGNOSTIC_FAILURE",
             "interval boundary tolerance exceeds the frozen B001 width bound")


def validate_support_region(record: Mapping[str, Any]) -> dict[str, Any]:
    _require(record.get("schema_type") == "stage03r_support_region",
             "INVALID_OBSERVATION_ROLE", "invalid support-region schema_type")
    _require(str(record.get("schema_version")) == SCHEMA_VERSION,
             "INVALID_OBSERVATION_ROLE", "invalid support-region schema_version")
    observation_id = record.get("observation_id")
    _require(observation_id not in LEGACY_OBSERVATION_IDS,
             "LEGACY_NAMESPACE_VIOLATION", "legacy IDs cannot be active observations")
    _require(isinstance(observation_id, str) and observation_id.startswith("BF-"),
             "INVALID_OBSERVATION_ROLE", "observation_id must be a BF ID")
    _require(record.get("role") == "SUPPORT_REGION", "INVALID_OBSERVATION_ROLE",
             "only SUPPORT_REGION is active")
    _require(record.get("source_bf_id") == observation_id, "INVALID_PROVENANCE",
             "observation_id must equal source_bf_id")
    _require(not (FORBIDDEN_OBSERVATION_FIELDS & set(record)),
             "INVALID_OBSERVATION_ROLE", "derived point-observation field is forbidden")
    region = record.get("energy_region_meV", {})
    lower, upper = region.get("lower"), region.get("upper")
    _require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lower, upper)),
             "INVALID_OBSERVATION_ROLE", "support bounds must be finite numbers")
    _require(lower <= upper, "INVALID_OBSERVATION_ROLE", "support lower exceeds upper")
    semantics = record.get("interval_semantics", {})
    expected_false = (
        "probability_density_defined", "confidence_interval", "centroid_measurement",
        "linewidth_measurement", "likelihood_defined",
    )
    _require(semantics.get("closed_lower") is True and semantics.get("closed_upper") is True,
             "INVALID_OBSERVATION_ROLE", "support intervals must be closed")
    _require(all(semantics.get(key) is False for key in expected_false),
             "INVALID_OBSERVATION_ROLE", "support region has prohibited statistical meaning")
    provenance = record.get("provenance", {}).get("source_artifact", {})
    _require(bool(provenance.get("path")) and bool(provenance.get("sha256")),
             "INVALID_PROVENANCE", "support-region provenance identity is required")
    _require(record.get("assignment_status") == "unassigned",
             "INVALID_OBSERVATION_ROLE", "canonical support must remain unassigned")
    return dict(record)


def validate_prediction_bundle(bundle: Mapping[str, Any], *, synthetic_only: bool = True) -> dict[str, Any]:
    _require(bundle.get("schema_type") == "stage03r_prediction_bundle",
             "INVALID_PROVENANCE", "invalid PredictionBundle schema_type")
    _require(str(bundle.get("schema_version")) == SCHEMA_VERSION,
             "INVALID_PROVENANCE", "invalid PredictionBundle schema_version")
    _require(bundle.get("model_id") in ALLOWED_MODELS, "INVALID_PROVENANCE",
             "unknown model_id")
    for key in ("prediction_bundle_id", "parameter_set_id", "parameter_source",
                "provenance", "convention", "levels", "transitions",
                "transition_inventory", "derived"):
        _require(key in bundle, "INVALID_PROVENANCE", f"PredictionBundle missing {key}")
    if synthetic_only:
        _require(bundle.get("parameter_source") == "synthetic_fixture",
                 "INVALID_PROVENANCE", "implementation acceptance accepts synthetic bundles only")
    provenance = bundle.get("provenance", {})
    for key in ("source_artifact", "source_identity", "generator_name",
                "generator_version", "generation_method", "evidence_used_to_generate"):
        _require(key in provenance, "INVALID_PROVENANCE", f"PredictionBundle provenance missing {key}")
    _require(provenance.get("generated_from_current_stage03r_observations") is False,
             "CIRCULAR_ASSIGNMENT", "prediction was generated from current Stage03R observations")
    inventory = bundle.get("transition_inventory", {})
    _require(inventory.get("status") in {"complete_for_declared_scope", "partial"},
             "INVALID_PROVENANCE", "invalid transition inventory status")
    _require(bool(inventory.get("declared_scope")), "INVALID_PROVENANCE",
             "transition inventory requires declared_scope")
    convention = bundle.get("convention", {})
    for key in ("cef_convention_id", "stevens_normalization_id", "coefficient_units",
                "crystallographic_setting", "global_frame_id", "local_frame_id",
                "local_to_global_matrix", "canonical_parameter_order"):
        _require(key in convention, "CONVENTION_CONTRACT_INCOMPLETE",
                 f"PredictionBundle convention missing {key}")
    transitions = bundle.get("transitions")
    _require(isinstance(transitions, list), "INVALID_PROVENANCE", "transitions must be a list")
    ids: set[str] = set()
    for transition in transitions:
        tid = transition.get("transition_id")
        energy = transition.get("energy_meV")
        _require(isinstance(tid, str) and tid and tid not in ids,
                 "INVALID_PROVENANCE", "transition IDs must be unique nonempty strings")
        _require(isinstance(energy, (int, float)) and math.isfinite(energy) and energy > 0,
                 "INVALID_PROVENANCE", f"transition {tid} requires positive finite energy")
        ids.add(tid)
    return dict(bundle)


def _components(family: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [component for complex_record in family.get("complexes", [])
            for component in complex_record.get("components", [])]


def validate_assignment_family(
    family: Mapping[str, Any], support_ids: set[str], transition_ids: set[str],
    *, allow_real: bool = False,
) -> list[Mapping[str, Any]]:
    _require(family.get("schema_type") == "stage03r_assignment_family",
             "CIRCULAR_ASSIGNMENT", "invalid assignment-family schema_type")
    _require(str(family.get("schema_version")) == SCHEMA_VERSION,
             "CIRCULAR_ASSIGNMENT", "invalid assignment-family schema_version")
    origin = family.get("origin")
    _require(origin in {"synthetic_test", "real_scientific"}, "CIRCULAR_ASSIGNMENT",
             "invalid assignment origin")
    _require(allow_real or origin == "synthetic_test", "CIRCULAR_ASSIGNMENT",
             "real assignment families are not admitted")
    if origin == "real_scientific":
        _require(family.get("review_status") == "reviewed", "CIRCULAR_ASSIGNMENT",
                 "real assignment family must be explicitly reviewed")
    required: list[Mapping[str, Any]] = []
    component_ids: set[str] = set()
    for component in _components(family):
        cid = component.get("component_id")
        _require(isinstance(cid, str) and cid and cid not in component_ids,
                 "CIRCULAR_ASSIGNMENT", "component IDs must be unique")
        component_ids.add(cid)
        constraint = component.get("source_support_constraint", {})
        _require(constraint.get("mode") in {"ALL_OF", "ANY_OF"},
                 "CIRCULAR_ASSIGNMENT", f"invalid support mode for {cid}")
        supplied_supports = constraint.get("support_ids", [])
        _require(isinstance(supplied_supports, list) and supplied_supports,
                 "CIRCULAR_ASSIGNMENT", f"component {cid} requires explicit support IDs")
        _require(set(supplied_supports) <= support_ids, "CIRCULAR_ASSIGNMENT",
                 f"component {cid} references undeclared support")
        mapping = component.get("cef_transition_mapping", {})
        _require(mapping.get("mode") in {"ONE_OF", "UNASSIGNED"},
                 "CIRCULAR_ASSIGNMENT", f"invalid transition mapping for {cid}")
        candidates = mapping.get("candidate_transition_ids", [])
        if component.get("required_cef_explanation") is True:
            _require(mapping.get("mode") == "ONE_OF" and isinstance(candidates, list) and candidates,
                     "CIRCULAR_ASSIGNMENT", f"required component {cid} needs candidates")
            _require(set(candidates) <= transition_ids, "CIRCULAR_ASSIGNMENT",
                     f"component {cid} references undeclared transition")
            required.append(component)
        else:
            _require(mapping.get("mode") == "UNASSIGNED" or set(candidates) <= transition_ids,
                     "CIRCULAR_ASSIGNMENT", f"invalid optional component {cid}")
    _require(set(family.get("unassigned_support_ids", [])) <= support_ids,
             "CIRCULAR_ASSIGNMENT", "undeclared unassigned support ID")
    return required


def enumerate_joint_mappings(required_components: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Enumerate only explicitly supplied candidate IDs with injective assignment."""
    if not required_components:
        return []
    component_ids = [str(item["component_id"]) for item in required_components]
    choices = [item["cef_transition_mapping"]["candidate_transition_ids"]
               for item in required_components]
    mappings: list[dict[str, str]] = []
    for selected in itertools.product(*choices):
        if len(set(selected)) != len(selected):
            continue
        mappings.append(dict(zip(component_ids, selected)))
    return mappings


def distance_to_region(energy: float, lower: float, upper: float, tau: float) -> dict[str, Any]:
    _require(lower <= upper and tau >= 0, "NUMERICAL_DIAGNOSTIC_FAILURE",
             "invalid region or tolerance")
    if lower - tau <= energy <= upper + tau:
        return {"relation": "INSIDE", "distance_meV": 0.0}
    if energy < lower - tau:
        return {"relation": "BELOW_REGION", "distance_meV": lower - energy}
    return {"relation": "ABOVE_REGION", "distance_meV": energy - upper}


Interval = tuple[float, float]


def _near(a: float, b: float, absolute: float, relative: float) -> bool:
    return abs(a - b) <= absolute + relative * max(1.0, abs(a), abs(b))


def canonicalize_intervals(
    intervals: Iterable[Sequence[float]], *, absolute: float = 0.0, relative: float = 0.0,
) -> list[Interval]:
    normalized: list[Interval] = []
    for pair in intervals:
        _require(len(pair) == 2, "NUMERICAL_DIAGNOSTIC_FAILURE", "interval needs two bounds")
        lower, upper = float(pair[0]), float(pair[1])
        _require(math.isfinite(lower) and math.isfinite(upper),
                 "NUMERICAL_DIAGNOSTIC_FAILURE", "interval bounds must be finite")
        _require(lower <= upper or _near(lower, upper, absolute, relative),
                 "NUMERICAL_DIAGNOSTIC_FAILURE", "interval lower exceeds upper")
        normalized.append((min(lower, upper), max(lower, upper)))
    normalized.sort()
    merged: list[Interval] = []
    for lower, upper in normalized:
        if not merged:
            merged.append((lower, upper))
            continue
        previous_lower, previous_upper = merged[-1]
        if lower <= previous_upper or _near(lower, previous_upper, absolute, relative):
            merged[-1] = (previous_lower, max(previous_upper, upper))
        else:
            merged.append((lower, upper))
    return merged


def intersect_interval_sets(left: Sequence[Interval], right: Sequence[Interval]) -> list[Interval]:
    intersections: list[Interval] = []
    for a0, a1 in left:
        for b0, b1 in right:
            lower, upper = max(a0, b0), min(a1, b1)
            if lower <= upper:
                intersections.append((lower, upper))
    return canonicalize_intervals(intersections)


def _scale_set_for_component(
    component: Mapping[str, Any], transition_id: str,
    supports: Mapping[str, Mapping[str, Any]], reference_gaps: Mapping[str, float],
    *, absolute: float, relative: float,
) -> list[Interval]:
    delta = reference_gaps.get(transition_id)
    _require(isinstance(delta, (int, float)) and delta > 0,
             "NUMERICAL_DIAGNOSTIC_FAILURE", f"invalid M0 reference gap {transition_id}")
    constraint = component["source_support_constraint"]
    sets = []
    for support_id in constraint["support_ids"]:
        region = supports[support_id]["energy_region_meV"]
        lower, upper = float(region["lower"]) / delta, float(region["upper"]) / delta
        sets.append([(max(lower, 0.0), upper)] if upper > 0 else [])
    if constraint["mode"] == "ANY_OF":
        return canonicalize_intervals(
            [interval for interval_set in sets for interval in interval_set],
            absolute=absolute, relative=relative,
        )
    current: list[Interval] = [(0.0, math.inf)]
    for interval_set in sets:
        current = intersect_interval_sets(current, interval_set)
    return canonicalize_intervals(current, absolute=absolute, relative=relative)


def m0_family_compatibility(
    family: Mapping[str, Any], supports: Mapping[str, Mapping[str, Any]],
    reference_gaps: Mapping[str, float], merge_tolerance: Mapping[str, float],
    *, allow_real_family: bool = False,
) -> dict[str, Any]:
    for support in supports.values():
        validate_support_region(support)
    required = validate_assignment_family(
        family, set(supports), set(reference_gaps), allow_real=allow_real_family,
    )
    if not required:
        return {"status": "NOT_TESTABLE", "compatible_s": [], "joint_mappings": []}
    mappings = enumerate_joint_mappings(required)
    components = {item["component_id"]: item for item in required}
    compatible: list[Interval] = []
    accepted: list[dict[str, str]] = []
    absolute = float(merge_tolerance["absolute"])
    relative = float(merge_tolerance["relative"])
    for mapping in mappings:
        joint: list[Interval] = [(0.0, math.inf)]
        for component_id, transition_id in mapping.items():
            current = _scale_set_for_component(
                components[component_id], transition_id, supports, reference_gaps,
                absolute=absolute, relative=relative,
            )
            joint = intersect_interval_sets(joint, current)
        if joint:
            accepted.append(mapping)
            compatible.extend(joint)
    result = canonicalize_intervals(compatible, absolute=absolute, relative=relative)
    return {
        "status": "FAMILY_COMPATIBLE" if result else "FAMILY_INCOMPATIBLE",
        "compatible_s": result,
        "joint_mappings": accepted,
    }


def fixed_forward_compatibility(
    family: Mapping[str, Any], supports: Mapping[str, Mapping[str, Any]],
    bundle: Mapping[str, Any], boundary_tolerance: float, *,
    allow_real_family: bool = False, allow_real_bundle: bool = False,
) -> dict[str, Any]:
    validate_prediction_bundle(bundle, synthetic_only=not allow_real_bundle)
    for support in supports.values():
        validate_support_region(support)
    transitions = {item["transition_id"]: item for item in bundle["transitions"]}
    required = validate_assignment_family(family, set(supports), set(transitions),
                                          allow_real=allow_real_family)
    if not required:
        return {"status": "NOT_TESTABLE", "joint_mappings": [], "pairwise_relations": []}
    components = {item["component_id"]: item for item in required}
    accepted: list[dict[str, str]] = []
    accepted_relations: list[list[dict[str, Any]]] = []
    for mapping in enumerate_joint_mappings(required):
        mapping_relations: list[dict[str, Any]] = []
        valid = True
        for component_id, transition_id in mapping.items():
            component = components[component_id]
            energy = transitions[transition_id]["energy_meV"]
            relations = []
            for support_id in component["source_support_constraint"]["support_ids"]:
                region = supports[support_id]["energy_region_meV"]
                diagnostic = distance_to_region(
                    energy, region["lower"], region["upper"], boundary_tolerance,
                )
                relations.append({"transition_id": transition_id, "support_id": support_id,
                                  **diagnostic})
            if component["source_support_constraint"]["mode"] == "ALL_OF":
                component_valid = all(item["relation"] == "INSIDE" for item in relations)
            else:
                component_valid = any(item["relation"] == "INSIDE" for item in relations)
            valid = valid and component_valid
            mapping_relations.extend(relations)
        if valid:
            accepted.append(mapping)
            accepted_relations.append(mapping_relations)
    return {
        "status": "FAMILY_COMPATIBLE" if accepted else "FAMILY_INCOMPATIBLE",
        "joint_mappings": accepted,
        "pairwise_relations": accepted_relations,
        "unmatched_predicted_transitions": sorted(set(transitions) - {
            transition for mapping in accepted for transition in mapping.values()
        }),
    }


def model_status(
    family_results: Sequence[Mapping[str, Any]], *, real_families_admitted: bool,
    inventories_complete: bool = True, convention_valid: bool = True,
) -> dict[str, Any]:
    statuses = [item.get("status") for item in family_results]
    if not real_families_admitted or not statuses:
        return {"model_status": "NOT_TESTABLE", "assignment_ambiguity": False}
    if "FAMILY_COMPATIBLE" in statuses:
        return {"model_status": "MODEL_COMPATIBLE",
                "assignment_ambiguity": any(status != "FAMILY_COMPATIBLE" for status in statuses)}
    if "NOT_TESTABLE" in statuses:
        return {"model_status": "NOT_TESTABLE", "assignment_ambiguity": False}
    if all(status == "FAMILY_INCOMPATIBLE" for status in statuses):
        return {"model_status": "MODEL_FALSIFIED" if inventories_complete and convention_valid
                else "NOT_TESTABLE", "assignment_ambiguity": False}
    return {"model_status": "NOT_TESTABLE", "assignment_ambiguity": False}


def validate_execution_request(request: Mapping[str, Any]) -> None:
    for key in ("raw_detector_path", "holdout_detector_path"):
        _require(not request.get(key), "INVALID_PROVENANCE", f"{key} is forbidden")
    for key, code in (
        ("normalization", "NORMALIZATION_GATE_VIOLATION"),
        ("exchange", "EXCHANGE_GATE_VIOLATION"),
        ("optimizer", "INVALID_PROVENANCE"),
        ("likelihood", "INVALID_PROVENANCE"),
        ("production_fit", "INVALID_PROVENANCE"),
    ):
        _require(not request.get(key), code, f"{key} is not authorized")
    _require(not request.get("physical_absence_from_C002_numerical_failure"),
             "INVALID_OBSERVATION_ROLE", "C002 numerical failure has no absence-evidence role")
    _require(not request.get("zero_intensity_from_missing_support"),
             "INVALID_OBSERVATION_ROLE", "missing support is not zero intensity")


def frobenius_norm(matrix: Sequence[Sequence[complex]]) -> float:
    return math.sqrt(sum(abs(value) ** 2 for row in matrix for value in row))


def matrix_difference(left: Sequence[Sequence[complex]], right: Sequence[Sequence[complex]]) -> list[list[complex]]:
    _require(len(left) == len(right) and all(len(a) == len(b) for a, b in zip(left, right)),
             "NUMERICAL_DIAGNOSTIC_FAILURE", "matrix dimensions differ")
    return [[a - b for a, b in zip(left_row, right_row)]
            for left_row, right_row in zip(left, right)]


def frobenius_equivalent(
    left: Sequence[Sequence[complex]], right: Sequence[Sequence[complex]],
    absolute: float, relative: float = 0.0,
) -> bool:
    difference = frobenius_norm(matrix_difference(left, right))
    threshold = absolute + relative * max(frobenius_norm(left), frobenius_norm(right))
    return difference <= threshold


def scalar_equivalent(left: float, right: float, absolute: float, relative: float) -> bool:
    return abs(left - right) <= absolute + relative * max(1.0, abs(left), abs(right))


def conjugate_transpose(matrix: Sequence[Sequence[complex]]) -> list[list[complex]]:
    return [[complex(matrix[row][column]).conjugate() for row in range(len(matrix))]
            for column in range(len(matrix[0]))]


def matmul(left: Sequence[Sequence[complex]], right: Sequence[Sequence[complex]]) -> list[list[complex]]:
    _require(left and right and len(left[0]) == len(right),
             "NUMERICAL_DIAGNOSTIC_FAILURE", "incompatible matrix dimensions")
    return [[sum(left[i][k] * right[k][j] for k in range(len(right)))
             for j in range(len(right[0]))] for i in range(len(left))]


def projector_from_columns(vectors: Sequence[Sequence[complex]]) -> list[list[complex]]:
    """Return V V† for a matrix whose columns span a subspace."""
    return matmul(vectors, conjugate_transpose(vectors))


def transition_tensor(
    projector_a: Sequence[Sequence[complex]], projector_b: Sequence[Sequence[complex]],
    operators: Sequence[Sequence[Sequence[complex]]],
) -> list[list[complex]]:
    tensor: list[list[complex]] = []
    for op_a in operators:
        row = []
        for op_b in operators:
            product = matmul(matmul(matmul(projector_a, op_a), projector_b), op_b)
            row.append(sum(product[i][i] for i in range(len(product))))
        tensor.append(row)
    return tensor


def validate_convention_transform(transform: Mapping[str, Any], *, real: bool = False) -> None:
    _require(transform.get("status") in {"active", "synthetic_only", "inactive"},
             "CONVENTION_CONTRACT_INCOMPLETE", "invalid transform status")
    if real:
        _require(transform.get("status") == "active" and
                 transform.get("provenance", {}).get("review_status") == "reviewed",
                 "CONVENTION_CONTRACT_INCOMPLETE", "real transform is not reviewed and active")
    else:
        _require(transform.get("status") == "synthetic_only",
                 "CONVENTION_CONTRACT_INCOMPLETE", "test transform must be synthetic_only")
    for key in ("transform_id", "from", "to", "parameter_transform", "frame_transform", "provenance"):
        _require(key in transform, "CONVENTION_CONTRACT_INCOMPLETE", f"missing {key}")


def registered_hamiltonian_equivalence(
    left: Sequence[Sequence[complex]], transformed_right: Sequence[Sequence[complex]],
    transform: Mapping[str, Any], comparison: Mapping[str, float],
) -> bool:
    validate_convention_transform(transform)
    return frobenius_equivalent(left, transformed_right,
                                float(comparison["absolute_meV"]),
                                float(comparison["relative"]))


def derived_observable_diagnostic(
    values: Sequence[float], absolute: float, relative: float,
) -> dict[str, Any]:
    _require(bool(values), "NUMERICAL_DIAGNOSTIC_FAILURE", "derived observable set is empty")
    minimum, maximum = min(values), max(values)
    return {
        "minimum": minimum,
        "maximum": maximum,
        "spread": maximum - minimum,
        "stable": scalar_equivalent(minimum, maximum, absolute, relative),
        "set_size": len(values),
    }


def matrix_rank(matrix: Sequence[Sequence[float]], tolerance: float = 1e-12) -> int:
    """Deterministic row-reduction rank for compact synthetic sensitivities."""
    rows = [list(map(float, row)) for row in matrix]
    if not rows:
        return 0
    columns = len(rows[0])
    _require(all(len(row) == columns for row in rows),
             "NUMERICAL_DIAGNOSTIC_FAILURE", "ragged sensitivity matrix")
    rank = 0
    for column in range(columns):
        pivot = next((index for index in range(rank, len(rows))
                      if abs(rows[index][column]) > tolerance), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        pivot_value = rows[rank][column]
        rows[rank] = [value / pivot_value for value in rows[rank]]
        for index in range(len(rows)):
            if index == rank:
                continue
            factor = rows[index][column]
            rows[index] = [value - factor * pivot_value
                           for value, pivot_value in zip(rows[index], rows[rank])]
        rank += 1
        if rank == len(rows):
            break
    return rank


def m1_extended_manifold(points: Sequence[Sequence[float]]) -> dict[str, Any]:
    unique = sorted({tuple(map(float, point)) for point in points})
    _require(all(len(point) == 2 for point in unique),
             "NUMERICAL_DIAGNOSTIC_FAILURE", "SYN-M1-E requires two-parameter points")
    return {
        "compatible_points": unique,
        "parameter_point_identified": len(unique) == 1,
        "scientific_status": "PARAMETER_NONIDENTIFIABLE" if len(unique) > 1 else "MODEL_COMPATIBLE",
    }


def build_output_package(payloads: Mapping[str, Any]) -> dict[str, str]:
    _require(set(payloads) == set(OUTPUT_SCHEMAS), "INVALID_PROVENANCE",
             "output package must contain exactly five schemas")
    return {name: deterministic_yaml(payloads[name]) for name in OUTPUT_SCHEMAS}


def deterministic_yaml(value: Any) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=True,
                          default_flow_style=False, width=1000)


__all__ = [name for name in globals() if not name.startswith("_")]
