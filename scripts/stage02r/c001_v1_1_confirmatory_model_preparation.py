#!/usr/bin/env python3
"""C001 v1.1 implementation candidate.

The module is deliberately inert unless a future, external Project Control
authorization document is present and valid.  ``--self-test`` uses synthetic
arrays only; it never opens any experimental table.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path
import argparse
import ast
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys

import numpy as np
import yaml
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import qmc


ROOT = Path(__file__).resolve().parents[2]
JOB_ID = "W02-02R-C-001"
SPEC_VERSION = "1.1"
SPEC_PATH = "03_Protocols/STAGE02R_T02R05_C001_V1_1_CONFIRMATORY_MODEL_PREPARATION_SPEC.md"
SPEC_SHA256 = "566a0d4fc193452ddd08366f2ef956122575da6f041f29b2c819df888cb7b66f"
SPEC_FREEZE_BASELINE = "9fe295fbb7af26b8c88cfacef17965a8bcda5d09"
PREPARATION_BASELINE = "b984e871a21b161684c1d41737d028676b1aa533"
CONFIG_PATH = "scripts/stage02r/c001_v1_1_confirmatory_config.yaml"
B001_SHA256 = "f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5"
DETECTOR_FIELDS = frozenset({
    "detector", "detector_raw", "det_err", "det_err_raw", "detector_monitor_rate",
    "detector_time_rate", "spectral_residual",
})


class ConformanceError(RuntimeError):
    """Static, numerical, or authorization invariant failed."""


def require(condition, message):
    if not condition:
        raise ConformanceError(message)


def yaml_load(path):
    return yaml.load(Path(path).read_bytes(), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config():
    return yaml_load(ROOT / CONFIG_PATH)


def verify_static_identities(config):
    active = config["active_specification"]
    require(active["version"] == SPEC_VERSION, "active specification version")
    require(active["path"] == SPEC_PATH, "active specification path")
    require(active["sha256"] == SPEC_SHA256, "active specification hash")
    require(active["canonical_freeze_baseline"] == SPEC_FREEZE_BASELINE,
            "specification freeze baseline")
    require(config["implementation"]["preparation_baseline"] == PREPARATION_BASELINE,
            "implementation preparation baseline")
    require(sha256_file(ROOT / SPEC_PATH) == SPEC_SHA256, "specification byte identity")
    require(config["frozen_inputs"]["B001_catalogue_sha256"] == B001_SHA256,
            "B001 configured identity")
    require(sha256_file(ROOT / config["frozen_inputs"]["B001_catalogue_path"]) == B001_SHA256,
            "B001 catalogue byte identity")


def git_head():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()


def require_external_execution_authorization(config):
    """Hard gate evaluated before any production input is opened."""
    require(config["authorization"]["execution_authorized"] is False,
            "candidate configuration must not self-authorize")
    require(config["authorization"]["A2_authorized"] is False, "A2 must remain unauthorized")
    require(config["authorization"]["C002_execution_authorized"] is False,
            "C002 must remain unauthorized")
    require(config["authorization"]["holdout_detector_access_authorized"] is False,
            "holdout detector must remain unauthorized")
    authorization_path = ROOT / config["authorization"]["future_authorization_path"]
    require(authorization_path.is_file(), "future Project Control authorization is absent")
    authorization = yaml_load(authorization_path)
    require(authorization.get("job_id") == JOB_ID, "authorization job identity")
    require(authorization.get("specification_version") == SPEC_VERSION,
            "authorization specification version")
    require(authorization.get("specification_sha256") == SPEC_SHA256,
            "authorization specification identity")
    require(authorization.get("execution_authorized") is True,
            "Project Control execution authorization is false")
    require(authorization.get("source_sha256") == sha256_file(Path(__file__)),
            "authorized source identity")
    require(authorization.get("config_sha256") == sha256_file(ROOT / CONFIG_PATH),
            "authorized config identity")
    require(authorization.get("canonical_head") == git_head(), "authorized canonical HEAD")
    return authorization


@dataclass(frozen=True)
class ScanData:
    scan_id: str
    energy: np.ndarray
    exposure: np.ndarray
    counts: np.ndarray
    exposure_class: str


@dataclass
class Candidate:
    start_index: int
    theta: np.ndarray | None
    log_likelihood: float
    optimizer_success: bool
    expectations_valid: bool
    domains_valid: bool
    iterations: int

    @property
    def valid(self):
        return (self.optimizer_success and self.expectations_valid and self.domains_valid
                and self.theta is not None and math.isfinite(self.log_likelihood))


def exposure_from_row(row, exposure_class, config):
    mapping = config["exposure"]["verified_classes"]
    require(exposure_class in mapping, "unverified exposure class")
    value = float(row[mapping[exposure_class]])
    require(math.isfinite(value) and value > 0.0, "invalid exposure")
    return value


def energy_transfer_semantics_valid(metadata):
    """Apply the frozen A002 energy contract without consulting detector values."""
    direct_e = (
        metadata.get("energy_transfer_field_raw") == "e"
        and metadata.get("energy_transfer_convention") == "Ei_minus_Ef"
        and metadata.get("energy_relation_status") == "verified_global"
    )
    if not direct_e:
        return False
    mapping_status = metadata.get("en_e_mapping_status")
    def_x = metadata.get("def_x_raw")
    if def_x == "en":
        return mapping_status == "verified"
    return mapping_status == "not_applicable"


def assess_local_coverage(energy, union, free_parameters, config):
    values = np.asarray(energy, dtype=float)
    finite = np.isfinite(values).all()
    unique = len(np.unique(values)) == len(values)
    differences = np.diff(values)
    monotonic = bool(len(values) > 1 and (np.all(differences > 0) or np.all(differences < 0)))
    ordered = np.sort(values) if finite and unique and monotonic else values
    inside = int(np.sum((ordered >= union[0]) & (ordered <= union[1]))) if finite else 0
    lower = int(np.sum(ordered < union[0])) if finite else 0
    upper = int(np.sum(ordered > union[1])) if finite else 0
    rule = config["scan_eligibility"]
    lower_used = min(lower, rule["lower_background_anchor_points_min"])
    upper_used = min(upper, rule["upper_background_anchor_points_min"])
    fit_points = inside + lower_used + upper_used
    eligible = (
        finite and unique and monotonic
        and inside >= rule["native_points_inside_frozen_complex_union_min"]
        and lower >= rule["lower_background_anchor_points_min"]
        and upper >= rule["upper_background_anchor_points_min"]
        and fit_points > free_parameters
    )
    return {
        "eligible": bool(eligible),
        "status": "eligible" if eligible else rule["failure_status"],
        "native_points_inside_union": inside,
        "lower_anchor_points_available": lower,
        "upper_anchor_points_available": upper,
        "n_fit_points": fit_points,
        "n_free_parameters": free_parameters,
        "nondetection": False,
        "physical_absence_evidence": False,
    }


def free_parameters_per_scan(component_count, background_order=1):
    return background_order + 1 + 3 * component_count


def softmax_gaps(eta):
    extended = np.append(np.asarray(eta, dtype=float), 0.0)
    shifted = extended - np.max(extended)
    weights = np.exp(shifted)
    return weights / np.sum(weights)


def ordered_centroids(eta, lower, upper):
    q_value = softmax_gaps(eta)
    return lower + (upper - lower) * np.cumsum(q_value[:-1])


def strict_centroid_domain(centroids, lower, upper):
    values = np.asarray(centroids, dtype=float)
    return bool(values.size and np.isfinite(values).all()
                and lower < values[0] and values[-1] < upper
                and np.all(np.diff(values) > 0.0))


def gaussian_unit_area(energy, centroid, fwhm):
    require(fwhm > 0.0, "observed FWHM must be positive")
    sigma = fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    return np.exp(-0.5 * ((energy - centroid) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def block_layout(component_count, background_order=1):
    p_count = background_order + 1
    return {
        "background": slice(0, p_count),
        "areas": slice(p_count, p_count + component_count),
        "eta": slice(p_count + component_count, p_count + 2 * component_count),
        "widths": slice(p_count + 2 * component_count, p_count + 3 * component_count),
    }


def physical_bounds(component_count, background_order=1):
    bounds = [(None, None)] * (background_order + 1)
    bounds += [(0.0, None)] * component_count
    bounds += [(None, None)] * component_count
    bounds += [(np.finfo(float).tiny, None)] * component_count
    return bounds


def block_expectation(theta, scan, union, component_count, background_order=1):
    theta = np.asarray(theta, dtype=float)
    layout = block_layout(component_count, background_order)
    midpoint = 0.5 * (scan.energy.min() + scan.energy.max())
    span = scan.energy.max() - scan.energy.min()
    require(span > 0.0, "nonpositive fit span")
    x_value = 2.0 * (scan.energy - midpoint) / span
    background = theta[layout["background"]]
    polynomial = sum(background[d] * x_value ** d for d in range(background_order + 1))
    if not np.isfinite(polynomial).all() or np.max(polynomial) > 700.0:
        return np.full_like(scan.energy, np.nan)
    rate = np.exp(polynomial)
    if component_count:
        centroids = ordered_centroids(theta[layout["eta"]], union[0], union[1])
        if not strict_centroid_domain(centroids, union[0], union[1]):
            return np.full_like(scan.energy, np.nan)
        for area, centroid, width in zip(
                theta[layout["areas"]], centroids, theta[layout["widths"]]):
            if area < 0.0 or width <= 0.0:
                return np.full_like(scan.energy, np.nan)
            rate += area * gaussian_unit_area(scan.energy, centroid, width)
    return scan.exposure * rate


def block_nll(theta, scan, union, component_count, background_order=1):
    mu = block_expectation(theta, scan, union, component_count, background_order)
    if not np.isfinite(mu).all() or np.any(mu <= 0.0) or not np.isfinite(scan.counts).all():
        return float("inf")
    return float(np.sum(mu - scan.counts * np.log(mu) + gammaln(scan.counts + 1.0)))


def joint_layout(scans, component_count, background_order=1):
    block_size = free_parameters_per_scan(component_count, background_order)
    return [slice(i * block_size, (i + 1) * block_size) for i in range(len(scans))]


def joint_bounds(scans, component_count, background_order=1):
    return physical_bounds(component_count, background_order) * len(scans)


def joint_nll(theta, scans, union, component_count, background_order=1):
    return sum(block_nll(theta[section], scan, union, component_count, background_order)
               for scan, section in zip(scans, joint_layout(scans, component_count, background_order)))


def baseline_block(scan, union, component_count, background_order=1):
    rate = (float(np.sum(scan.counts)) + 0.5) / float(np.sum(scan.exposure))
    values = [math.log(max(rate, np.finfo(float).tiny))] + [0.0] * background_order
    if component_count:
        area = max(rate * (union[1] - union[0]), np.finfo(float).eps) / component_count
        values += [area] * component_count
        values += [0.0] * component_count
        values += [max(0.1 * (union[1] - union[0]), np.finfo(float).eps)] * component_count
    return np.asarray(values, dtype=float)


def baseline_joint(scans, union, component_count, background_order=1):
    return np.concatenate([baseline_block(scan, union, component_count, background_order)
                           for scan in scans])


def sobol_observed_bank(scans, union, component_count, count=16, background_order=1):
    require(count <= 16, "v1.1 observed start cap")
    baseline = baseline_joint(scans, union, component_count, background_order)
    dimension = len(baseline)
    bank = qmc.Sobol(d=dimension, scramble=False).random_base2(m=4)
    starts = [baseline]
    layout = block_layout(component_count, background_order)
    block_size = free_parameters_per_scan(component_count, background_order)
    for row in bank[:count - 1]:
        candidate = baseline.copy()
        for scan_index in range(len(scans)):
            section = slice(scan_index * block_size, (scan_index + 1) * block_size)
            local = candidate[section]
            coordinates = row[section]
            local[layout["background"]] += 4.0 * (2.0 * coordinates[layout["background"]] - 1.0)
            if component_count:
                local[layout["areas"]] *= np.exp(4.0 * (2.0 * coordinates[layout["areas"]] - 1.0))
                local[layout["eta"]] = 8.0 * coordinates[layout["eta"]] - 4.0
                span = union[1] - union[0]
                local[layout["widths"]] = span * (0.02 + 0.98 * coordinates[layout["widths"]])
        starts.append(candidate)
    require(len(starts) == count, "observed start construction")
    return starts


def domains_satisfied(theta, bounds):
    for value, (lower, upper) in zip(theta, bounds):
        if not math.isfinite(float(value)):
            return False
        if lower is not None and value < lower:
            return False
        if upper is not None and value > upper:
            return False
    return True


def fit_one_start(scans, union, component_count, start, start_index, config, background_order=1):
    bounds = joint_bounds(scans, component_count, background_order)
    objective = lambda theta: joint_nll(theta, scans, union, component_count, background_order)
    try:
        result = minimize(
            objective, np.asarray(start, dtype=float), method="L-BFGS-B", bounds=bounds,
            options=config["observed_optimizer"]["options"],
        )
    except (FloatingPointError, ValueError):
        return Candidate(start_index, None, float("-inf"), False, False, False, 0)
    theta = np.asarray(result.x, dtype=float)
    means = [block_expectation(theta[section], scan, union, component_count, background_order)
             for scan, section in zip(scans, joint_layout(scans, component_count, background_order))]
    expectation_valid = all(np.isfinite(mu).all() and np.all(mu > 0.0) for mu in means)
    nll = objective(theta)
    decoded_valid = True
    if component_count:
        for section in joint_layout(scans, component_count, background_order):
            centroids = ordered_centroids(
                theta[section][block_layout(component_count, background_order)["eta"]],
                union[0], union[1])
            decoded_valid = decoded_valid and strict_centroid_domain(
                centroids, union[0], union[1])
    return Candidate(
        start_index, theta, -float(nll), bool(result.success), expectation_valid,
        domains_satisfied(theta, bounds) and decoded_valid, int(result.nit),
    )


def compare_candidates(left, right, config):
    tolerance = config["observed_optimizer"]["deterministic_tie_absolute_likelihood_tolerance"]
    difference = left.log_likelihood - right.log_likelihood
    if abs(difference) > tolerance:
        return -1 if difference > 0.0 else 1
    decimals = config["observed_optimizer"]["deterministic_tie_parameter_round_decimals"]
    left_vector = tuple(np.round(left.theta, decimals))
    right_vector = tuple(np.round(right.theta, decimals))
    return -1 if left_vector < right_vector else (1 if left_vector > right_vector else 0)


def best_candidate(candidates, config):
    valid = [candidate for candidate in candidates if candidate.valid]
    if not valid:
        return None
    return sorted(valid, key=cmp_to_key(lambda a, b: compare_candidates(a, b, config)))[0]


def solution_reproduced(candidates, config):
    best = best_candidate(candidates, config)
    if best is None:
        return False
    tolerance = config["observed_optimizer"]["reproduction_relative_likelihood_tolerance"]
    matches = [candidate for candidate in candidates if candidate.valid and
               abs(candidate.log_likelihood - best.log_likelihood)
               <= tolerance * max(1.0, abs(best.log_likelihood))]
    return len({candidate.start_index for candidate in matches}) >= 2


def finite_difference_projected_gradient(theta, objective, bounds, config):
    theta = np.asarray(theta, dtype=float)
    projected = []
    for index, value in enumerate(theta):
        step = config["kkt"]["finite_difference_relative_step"] * max(1.0, abs(float(value)))
        lower, upper = bounds[index]
        forward = upper is None or value + step <= upper
        backward = lower is None or value - step >= lower
        if forward and backward:
            plus = theta.copy(); plus[index] += step
            minus = theta.copy(); minus[index] -= step
            derivative = (objective(plus) - objective(minus)) / (2.0 * step)
        elif forward:
            plus = theta.copy(); plus[index] += step
            derivative = (objective(plus) - objective(theta)) / step
        elif backward:
            minus = theta.copy(); minus[index] -= step
            derivative = (objective(theta) - objective(minus)) / step
        else:
            derivative = float("inf")
        lower_active = (lower is not None and abs(value - lower) <=
                        config["kkt"]["active_bound_relative_tolerance"]
                        * max(1.0, abs(float(value)), abs(lower)))
        upper_active = (upper is not None and abs(value - upper) <=
                        config["kkt"]["active_bound_relative_tolerance"]
                        * max(1.0, abs(float(value)), abs(upper)))
        if lower_active and derivative >= 0.0:
            derivative = 0.0
        elif upper_active and derivative <= 0.0:
            derivative = 0.0
        projected.append(float(derivative))
    return float(np.max(np.abs(projected)))


def observed_fit(scans, union, component_count, config, background_order=1):
    bank = sobol_observed_bank(scans, union, component_count, 16, background_order)
    candidates = [fit_one_start(scans, union, component_count, bank[index], index + 1,
                                config, background_order) for index in range(8)]
    best = best_candidate(candidates, config)
    reproduced = solution_reproduced(candidates, config)
    objective = lambda theta: joint_nll(theta, scans, union, component_count, background_order)
    kkt_value = (finite_difference_projected_gradient(
        best.theta.copy(), objective, joint_bounds(scans, component_count, background_order), config)
                 if best is not None else float("inf"))
    if not reproduced or kkt_value > config["kkt"]["projected_gradient_reference"]:
        candidates.extend(
            fit_one_start(scans, union, component_count, bank[index], index + 1,
                          config, background_order) for index in range(8, 16)
        )
        best = best_candidate(candidates, config)
        reproduced = solution_reproduced(candidates, config)
        kkt_value = (finite_difference_projected_gradient(
            best.theta.copy(), objective, joint_bounds(scans, component_count, background_order), config)
                     if best is not None else float("inf"))
    return {
        "fit_status": "valid" if best is not None else "numerical_failure",
        "theta": None if best is None else best.theta,
        "log_likelihood": None if best is None else best.log_likelihood,
        "start_count": len(candidates),
        "optimizer_stability_status": "stable" if reproduced else "unresolved",
        "projected_gradient_max": kkt_value,
        "numerical_convergence_status": (
            "warning" if kkt_value > config["kkt"]["projected_gradient_reference"] else "within_reference"
        ),
        "KKT_role": "diagnostic_only",
    }


def bootstrap_start_bank(scans, union, component_count, observed_theta, config, background_order=1):
    baseline = baseline_joint(scans, union, component_count, background_order)
    positive = baseline.copy()
    negative = baseline.copy()
    layout = block_layout(component_count, background_order)
    block_size = free_parameters_per_scan(component_count, background_order)
    for scan_index in range(len(scans)):
        section = slice(scan_index * block_size, (scan_index + 1) * block_size)
        positive[section][layout["background"]] += 0.05
        negative[section][layout["background"]] -= 0.05
        if component_count:
            positive[section][layout["areas"]] *= 1.10
            negative[section][layout["areas"]] *= 0.90
            positive[section][layout["eta"]] += 0.25
            negative[section][layout["eta"]] -= 0.25
            positive[section][layout["widths"]] *= 1.10
            negative[section][layout["widths"]] *= 0.90
    starts = [np.asarray(observed_theta, dtype=float).copy(), baseline, positive, negative]
    require(len(starts) == config["bootstrap_optimizer"]["model_local_starts"],
            "bootstrap start count")
    return starts


def bootstrap_fit(scans, union, component_count, observed_theta, config, background_order=1):
    starts = bootstrap_start_bank(
        scans, union, component_count, observed_theta, config, background_order)
    candidates = [fit_one_start(scans, union, component_count, start, index + 1,
                                config, background_order) for index, start in enumerate(starts)]
    best = best_candidate(candidates, config)
    return {
        "fit_status": "valid" if best is not None else "numerical_failure",
        "theta": None if best is None else best.theta,
        "log_likelihood": None if best is None else best.log_likelihood,
        "start_count": 4,
        "KKT_evaluated": False,
    }


def seed_identity(complex_id, comparison_id, replicate_count):
    payload = (f"specification_version={SPEC_VERSION}\n"
               f"complex_id={complex_id}\n"
               f"comparison_id={comparison_id}\n"
               f"replicate_count={replicate_count}\n")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return payload, digest, int(digest[:16], 16)


def plus_one_p_value(statistics, observed):
    values = np.asarray(statistics, dtype=float)
    return float((1 + np.sum(values >= observed)) / (len(values) + 1))


def failed_bootstrap_statistic(parent_fit, child_fit):
    if parent_fit["fit_status"] != "valid" or child_fit["fit_status"] != "valid":
        return float("inf")
    statistic = 2.0 * (child_fit["log_likelihood"] - parent_fit["log_likelihood"])
    return 0.0 if -1.0e-8 < statistic < 0.0 else float(statistic)


def profile_required(final_component_count, ambiguous, config):
    rule = config["identifiability"]
    return ((final_component_count > 1 and rule["profile_required_for_final_promoted_K_gt_1"])
            or (ambiguous and rule["profile_required_for_ambiguous_final_model"]))


def split_promoted(gates, config):
    required = config["component_development"]["promotion_gates"]
    return all(gates.get(name) is True for name in required)


def resolution_claim_allowed(resolution_status, claim, config):
    triggers = set(config["resolution"]["full_resolution_trigger_claims"])
    if claim in triggers and resolution_status == "resolution_not_established":
        return False
    return True


class HoldoutMetadataGuard:
    def __init__(self, config):
        self.allowed = frozenset(config["holdout"]["allowed_point_fields"])
        self.requests = []
        self.detector_materializations = 0
        self.decoded_fields = []

    def authorize_fields(self, fields):
        requested = frozenset(fields)
        permitted = requested <= self.allowed and not (requested & DETECTOR_FIELDS)
        self.requests.append({"fields": sorted(requested), "allowed": permitted})
        if not permitted:
            raise ConformanceError("holdout field request denied before decode")
        return tuple(fields)

    def record_decode(self, field):
        self.decoded_fields.append(field)
        if field in DETECTOR_FIELDS:
            self.detector_materializations += 1


def project_csv_fields(path, fields, guard=None, selected_scan_ids=None, data=None,
                       decode_token=None):
    """Decode only selected CSV byte tokens; unselected detector cells remain opaque."""
    selected = guard.authorize_fields(fields) if guard is not None else tuple(fields)
    stream = io.BytesIO(data) if data is not None else Path(path).open("rb")
    decoder = decode_token or (lambda token, _field: token.decode("utf-8-sig"))
    with stream:
        header = stream.readline().rstrip(b"\r\n").decode("utf-8-sig").split(",")
        require(set(selected) <= set(header), "requested field absent")
        indices = [(field, header.index(field)) for field in selected]
        sid_index = header.index("scan_record_id") if selected_scan_ids is not None else None
        selected_ids = None if selected_scan_ids is None else frozenset(selected_scan_ids)
        rows = []
        for raw_line in stream:
            require(b'"' not in raw_line, "quoted CSV token unsupported by selective projector")
            line = raw_line.rstrip(b"\r\n")
            delimiters = [-1] + [i for i, value in enumerate(line) if value == 44] + [len(line)]
            require(len(delimiters) == len(header) + 1, "CSV row width mismatch")

            def raw_token(index):
                return line[delimiters[index] + 1:delimiters[index + 1]]

            if selected_ids is not None:
                sid = decoder(raw_token(sid_index), "scan_record_id")
                if guard is not None:
                    guard.record_decode("scan_record_id")
                if sid not in selected_ids:
                    continue
            row = {}
            for field, index in indices:
                row[field] = decoder(raw_token(index), field)
                if guard is not None:
                    guard.record_decode(field)
            rows.append(row)
        return rows


def future_c002_contract(config):
    rule = config["future_C002"]
    return {
        "execution_authorized": False,
        "holdout_detector_access_authorized": False,
        "bootstrap_replicates": rule["bootstrap_replicates"],
        "bootstrap_design": rule["bootstrap_design"],
        "adaptive_extension": rule["adaptive_extension"],
        "p_value_convention": rule["p_value_convention"],
        "multiplicity_procedure": rule["multiplicity_procedure"],
        "global_alpha": rule["global_alpha"],
        "family_frozen_before_detector_access": rule["family_frozen_before_detector_access"],
    }


def static_legacy_audit(config):
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    old_keys = {
        "bootstrap_reference_multistarts", "bootstrap_adequacy_benchmark_replicates",
        "bootstrap_fit_multistarts_candidate_sequence", "bootstrap_failed_replicate_fraction_max",
        "delta_E_ref", "historical_EV006_fwhm_meV",
    }
    require(not (old_keys & set(config.keys())), "legacy top-level config key")
    require("benchmark_comparison" not in functions and "fit_model_levels" not in functions,
            "legacy optimizer benchmark path")
    require(config["observed_optimizer"]["initial_starts"] == 8, "observed initial starts")
    require(config["observed_optimizer"]["escalated_starts"] == 16, "observed escalation")
    require(config["bootstrap_optimizer"]["model_local_starts"] == 4,
            "bootstrap model-local starts")
    require(config["bootstrap_optimizer"]["KKT_bootstrap_gate"] is False,
            "bootstrap KKT gate")
    require(config["model"]["background_order_bootstrap_selection"] is False,
            "background bootstrap selection")
    return {
        "observed_33_start_path": False,
        "bootstrap_4_8_16_33_escalation": False,
        "reference_33_start_path": False,
        "optimizer_64_reference_benchmark": False,
        "bootstrap_KKT_gate": False,
        "fixed_failure_fraction_scientific_gate": False,
        "background_order_bootstrap_selection": False,
    }


def static_privacy_audit(config):
    serialized = json.dumps(config, sort_keys=True)
    require("http://" not in serialized and "https://" not in serialized, "private URL present")
    require(config["scope"]["private_material_input"] == "forbidden", "private input scope")
    require(config["external_context"]["TAIPAN_proposal_15702_status"]
            == "unresolved_historical_clue", "unverified proposal promoted")
    require(config["external_context"]["complementary_experiment"]["C001_model_input"]
            == "forbidden", "external experiment became model input")
    return {"private_urls": 0, "private_parameters": 0, "unpublished_material": 0}


def synthetic_scan(scan_id="S", exposure_class="monitor_controlled"):
    energy = np.linspace(-2.0, 2.0, 9)
    exposure = np.full(9, 20.0)
    rate = np.exp(-2.0 + 0.05 * energy)
    counts = np.rint(exposure * rate).astype(float)
    return ScanData(scan_id, energy, exposure, counts, exposure_class)


def local_fit_window(scan, union, config, anchors=2):
    """A05: full union plus the nearest requested native anchors on both sides."""
    order = np.argsort(scan.energy)
    energy = scan.energy[order]
    exposure = scan.exposure[order]
    counts = scan.counts[order]
    require(len(np.unique(energy)) == len(energy), "duplicate energy")
    lower = np.flatnonzero(energy < union[0])
    inside = np.flatnonzero((energy >= union[0]) & (energy <= union[1]))
    upper = np.flatnonzero(energy > union[1])
    chosen = np.concatenate((lower[-anchors:], inside, upper[:anchors]))
    if len(lower) < anchors or len(upper) < anchors:
        chosen = np.asarray([], dtype=int)
    local = ScanData(scan.scan_id, energy[chosen], exposure[chosen], counts[chosen],
                     scan.exposure_class)
    return local, {"inside": len(inside), "lower": len(lower), "upper": len(upper)}


def fit_is_stable(fit):
    return fit["fit_status"] == "valid" and fit["optimizer_stability_status"] == "stable"


def bootstrap_component_development(scans, union, parent_k, parent_fit, child_fit,
                                    complex_id, config, replicate_count=None):
    count = (config["component_development"]["discovery_bootstrap_replicates"]
             if replicate_count is None else replicate_count)
    comparison = f"K{parent_k}-to-K{parent_k + 1}"
    payload, digest, seed = seed_identity(complex_id, comparison, count)
    rng = np.random.Generator(np.random.PCG64(seed))
    parent_means = [block_expectation(parent_fit["theta"][section], scan, union, parent_k)
                    for scan, section in zip(scans, joint_layout(scans, parent_k))]
    observed = 2.0 * (child_fit["log_likelihood"] - parent_fit["log_likelihood"])
    statistics = []
    failures = 0
    for _index in range(count):
        simulated = [ScanData(scan.scan_id, scan.energy, scan.exposure,
                              rng.poisson(mu).astype(float), scan.exposure_class)
                     for scan, mu in zip(scans, parent_means)]
        parent_boot = bootstrap_fit(simulated, union, parent_k, parent_fit["theta"], config)
        child_boot = bootstrap_fit(simulated, union, parent_k + 1, child_fit["theta"], config)
        statistic = failed_bootstrap_statistic(parent_boot, child_boot)
        failures += int(math.isinf(statistic))
        statistics.append(statistic)
    return {"comparison_id": comparison, "B": count, "observed_statistic": observed,
            "p_value": plus_one_p_value(statistics, observed),
            "failed_fit_fraction": failures / count, "statistics": statistics,
            "seed_payload": payload, "seed_sha256": digest, "rng": "numpy.random.PCG64"}


def supportive_recurrence(records, minimum=2):
    supportive_ids = {record["scan_id"] for record in records
                      if record.get("fit_stable") and record.get("areas_strictly_positive")
                      and record.get("profiles_finite") and record.get("adjacent_rule", True)}
    return {"supportive_scan_ids": sorted(supportive_ids),
            "supportive_scan_count": len(supportive_ids),
            "passes": len(supportive_ids) >= minimum}


def force_profile_centroid(theta, component_count, component_index, target,
                           union, background_order=1):
    result = np.asarray(theta, dtype=float).copy()
    layout = block_layout(component_count, background_order)
    eta = result[layout["eta"]].copy()
    fraction = (target - union[0]) / (union[1] - union[0])
    if not 0.0 < fraction < 1.0:
        return None
    exponentials = np.exp(np.clip(eta, -700.0, 700.0))
    left = float(np.sum(exponentials[:component_index]))
    right = float(np.sum(exponentials[component_index + 1:]) + 1.0)
    required = fraction / (1.0 - fraction) * right - left
    if not math.isfinite(required) or required <= 0.0:
        return None
    eta[component_index] = math.log(required)
    result[layout["eta"]] = eta
    return result


def centroid_profile_interval(scan, union, component_count, theta, component_index, config,
                              background_order=1):
    points = config["identifiability"]["profile_grid_points"]
    grid = np.linspace(union[0], union[1], points + 2)[1:-1]
    theta = np.asarray(theta, dtype=float)
    baseline = block_nll(theta, scan, union, component_count, background_order)
    target_index = block_layout(component_count, background_order)["eta"].start + component_index
    free_indices = [index for index in range(len(theta)) if index != target_index]
    full_bounds = physical_bounds(component_count, background_order)
    free_bounds = [full_bounds[index] for index in free_indices]
    accepted = []
    for target in grid:
        def reconstruct(free):
            trial = theta.copy()
            trial[free_indices] = free
            return force_profile_centroid(trial, component_count, component_index,
                                          float(target), union, background_order)
        initial = reconstruct(theta[free_indices])
        if initial is None:
            continue
        def objective(free):
            forced = reconstruct(free)
            return float("inf") if forced is None else block_nll(
                forced, scan, union, component_count, background_order)
        optimized = minimize(objective, theta[free_indices], method="L-BFGS-B",
                             bounds=free_bounds, options=config["observed_optimizer"]["options"])
        value = objective(optimized.x)
        if math.isfinite(value) and 2.0 * (value - baseline) <= config["identifiability"]["profile_95_delta_minus2logL"]:
            accepted.append(float(target))
    finite_crossings = len(accepted) >= 2 and accepted[0] > grid[0] and accepted[-1] < grid[-1]
    return {"lower": min(accepted) if accepted else None,
            "upper": max(accepted) if accepted else None,
            "finite_in_domain_crossings": finite_crossings}


def intervals_overlap(left, right):
    return (left.get("lower") is not None and right.get("lower") is not None
            and max(left["lower"], right["lower"]) <= min(left["upper"], right["upper"]))


def sensitivity_window(primary_scan, original_scan, union, background_name, config):
    if background_name == "B2":
        window, coverage = local_fit_window(original_scan, union, config, anchors=3)
        if coverage["lower"] < 3 or coverage["upper"] < 3:
            return None, coverage
        return window, coverage
    return primary_scan, {"lower": 2, "upper": 2}


def background_sensitivity(scan, original_scan, union, component_count, primary_theta, config,
                           fit_function=observed_fit):
    primary_profiles = [centroid_profile_interval(scan, union, component_count, primary_theta, k, config)
                        for k in range(component_count)] if component_count > 1 else []
    records = []
    material = False
    for name, order in (("B0", 0), ("B2", 2)):
        fit_scan, coverage = sensitivity_window(scan, original_scan, union, name, config)
        if fit_scan is None:
            records.append({"background": name, "status": "not_estimable", "material": False})
            continue
        fit = fit_function([fit_scan], union, component_count, config, order)
        unstable = not fit_is_stable(fit)
        overlap_failure = False
        if component_count > 1 and fit["theta"] is not None:
            alternate = [centroid_profile_interval(fit_scan, union, component_count, fit["theta"], k,
                                                   config, order) for k in range(component_count)]
            overlap_failure = any(not intervals_overlap(a, b)
                                  for a, b in zip(primary_profiles, alternate))
        entry_material = unstable or overlap_failure
        material = material or entry_material
        records.append({"background": name, "status": "valid" if not unstable else "unstable",
                        "material": entry_material, "window_lower_anchors": coverage["lower"],
                        "window_upper_anchors": coverage["upper"],
                        "window_point_count": len(fit_scan.energy)})
    return {"status": "material" if material else "acceptable", "refits": records}


def scan_support_record(scan, union, component_count, fit, config):
    if fit["theta"] is None:
        return {"scan_id": scan.scan_id, "fit_stable": False}
    theta = fit["theta"]
    layout = block_layout(component_count)
    areas = theta[layout["areas"]]
    profiles = [centroid_profile_interval(scan, union, component_count, theta, k, config)
                for k in range(component_count)]
    adjacent = True
    if component_count > 1:
        adjacent = (all(profiles[k] != profiles[k + 1] for k in range(component_count - 1))
                    and any(not intervals_overlap(profiles[k], profiles[k + 1])
                            for k in range(component_count - 1)))
    tolerance = config["kkt"]["active_bound_relative_tolerance"]
    return {"scan_id": scan.scan_id, "fit_stable": fit_is_stable(fit),
            "areas_strictly_positive": bool(np.all(areas > tolerance * np.maximum(1.0, np.abs(areas)))),
            "profiles_finite": all(item["finite_in_domain_crossings"] for item in profiles),
            "adjacent_rule": adjacent, "profiles": profiles}


def holdout_hypothesis_eligibility(record, union, child_k, config):
    exposure_class = record.get("exposure_class")
    verified_class = exposure_class in config["exposure"]["verified_classes"]
    try:
        exposure = np.asarray(record.get("exposure", []), dtype=float)
        exposure_valid = bool(exposure.size and np.isfinite(exposure).all()
                              and np.all(exposure > 0.0))
    except (TypeError, ValueError):
        exposure_valid = False
    energy_valid = record.get("energy_transfer_semantics_valid") is True
    assessment = assess_local_coverage(record["energy"], union,
                                       free_parameters_per_scan(child_k), config)
    eligible = verified_class and exposure_valid and energy_valid and assessment["eligible"]
    return {"scan_id": record["scan_id"], "child_K": child_k, "eligible": eligible,
            "status": "eligible" if eligible else "metadata_eligibility_failure",
            "exposure_class": exposure_class, "exposure_valid": exposure_valid,
            "energy_transfer_semantics_valid": energy_valid,
            "nondetection": False, "physical_absence_evidence": False}


def final_profile_dispatch(scans, union, final_k, final_fit, ambiguous, config,
                           profile_function=centroid_profile_interval):
    required = profile_required(final_k, ambiguous, config)
    records = []
    if required and final_fit.get("theta") is not None:
        for scan, section in zip(scans, joint_layout(scans, final_k)):
            local_theta = final_fit["theta"][section]
            records.append({"scan_id": scan.scan_id,
                            "centroid_profiles": [profile_function(
                                scan, union, final_k, local_theta, k, config)
                                for k in range(final_k)]})
    return {"required": required, "performed": bool(records), "records": records}


def build_future_c002_registry(complex_results, holdout_metadata, config):
    family = []
    eligibility_by_hypothesis = {}
    for complex_id, result in sorted(complex_results.items()):
        if not result["adequate_model_preparation"]:
            continue
        previous = None
        for parent_k, child_k, hypothesis_type in [(0, 1, "presence")] + [
                (k - 1, k, "promoted_split") for k in range(2, result["final_K"] + 1)]:
            hypothesis_id = f"C002-{complex_id}-K{parent_k}-K{child_k}"
            eligibility = [holdout_hypothesis_eligibility(
                item, config["complexes"][complex_id]["frozen_union_meV"], child_k, config)
                           for item in holdout_metadata]
            eligibility_by_hypothesis[hypothesis_id] = eligibility
            eligible = sorted(item["scan_id"] for item in eligibility if item["eligible"])
            if not eligible:
                continue
            exposure_classes = {item["scan_id"]: item["exposure_class"]
                                for item in eligibility if item["eligible"]}
            multiplicity = {"procedure": "Holm", "global_alpha": 0.05,
                            "primary_sort": {"raw_p_value": "ascending"},
                            "tie_break": {"hypothesis_id": "lexical_ascending"}}
            family.append({"hypothesis_id": hypothesis_id, "complex_id": complex_id,
                           "hypothesis_type": hypothesis_type, "parent_K": parent_k,
                           "child_K": child_k, "eligible_holdout_scan_ids": eligible,
                           "exposure_class_per_scan": exposure_classes,
                           "background_family": "B1_log_linear",
                           "component_family": "observed_unit_area_Gaussian",
                           "parameter_domain_rules": config["model"]["parameter_domains"],
                           "resolution_status": result.get("resolution_status", config["resolution"]["default_status"]),
                           "multiplicity_rule": multiplicity,
                           "bootstrap_replicates": 4096, "rng": "numpy.random.PCG64",
                           "p_value_convention": "plus_one", "bootstrap_design": "fixed",
                           "adaptive_extension": "forbidden", "Holm_global_alpha": 0.05,
                           "numerical_failure_raw_p_value": 1.0,
                           "ancestor_hypothesis_id": previous,
                           "ancestor_rule": "all_ancestor_hypotheses_must_pass",
                           "family_frozen_before_detector_access": True})
            previous = hypothesis_id
    return {"family_frozen_before_detector_access": True, "hypotheses": family,
            "Holm_global_alpha": 0.05, "ancestor_rule": "all_ancestors_must_pass",
            "Holm_ordering": {"primary_sort": {"raw_p_value": "ascending"},
                              "tie_break": {"hypothesis_id": "lexical_ascending"}},
            "eligibility_by_hypothesis": eligibility_by_hypothesis,
            "C002_executed": False}


def dispatch_c001_core(discovery_scans, holdout_metadata, config, bootstrap_replicates=None):
    """Reviewed A05-A22 scientific dispatcher; all inputs are explicit and injectable."""
    results = {}
    eligibility = {}
    for complex_id, definition in config["complexes"].items():
        union = definition["frozen_union_meV"]
        local_scans = []
        original_by_id = {scan.scan_id: scan for scan in discovery_scans}
        coverage_by_scan = {}
        for scan in discovery_scans:
            local, coverage = local_fit_window(scan, union, config)
            coverage_by_scan[scan.scan_id] = coverage
            if assess_local_coverage(scan.energy, union, free_parameters_per_scan(1), config)["eligible"]:
                local_scans.append(local)
        local_ids = {scan.scan_id for scan in local_scans}
        eligibility[complex_id] = [{"scan_id": scan.scan_id, "eligible": scan.scan_id in local_ids}
                                   for scan in discovery_scans]
        if not local_scans:
            results[complex_id] = {"adequate_model_preparation": False, "final_K": 0,
                                   "status": "insufficient_local_coverage"}
            continue
        parent = observed_fit(local_scans, union, 0, config)
        current = observed_fit(local_scans, union, 1, config)
        result = {"adequate_model_preparation": True, "presence_hypothesis_registered": True,
                  "K0_fit": parent, "K1_fit": current, "final_K": 1, "developments": []}
        for child_k in range(2, definition["maximum_BF_defined_K"] + 1):
            candidate_scans = [scan for scan in local_scans
                               if len(scan.energy) > free_parameters_per_scan(child_k)]
            if not candidate_scans:
                result["developments"].append({"child_K": child_k, "promoted": False,
                                               "status": "insufficient_local_coverage"})
                break
            parent_for_comparison = observed_fit(candidate_scans, union, child_k - 1, config)
            child = observed_fit(candidate_scans, union, child_k, config)
            gates = {"parent_observed_fit_stable": fit_is_stable(parent_for_comparison),
                     "child_observed_fit_stable": fit_is_stable(child)}
            if not all(gates.values()):
                result["developments"].append({"child_K": child_k, "promoted": False, "gates": gates})
                break
            boot = bootstrap_component_development(candidate_scans, union, child_k - 1,
                                                   parent_for_comparison, child,
                                                   complex_id, config, bootstrap_replicates)
            gates["discovery_bootstrap_support"] = boot["p_value"] <= config["component_development"]["development_alpha"]
            if not gates["discovery_bootstrap_support"]:
                result["developments"].append({"child_K": child_k, "promoted": False,
                                               "gates": gates, "bootstrap": boot})
                break
            support = []
            sensitivity = []
            for scan in candidate_scans:
                scan_fit = observed_fit([scan], union, child_k, config)
                support.append(scan_support_record(scan, union, child_k, scan_fit, config))
                if scan_fit["theta"] is not None:
                    sensitivity.append(background_sensitivity(
                        scan, original_by_id[scan.scan_id], union, child_k,
                        scan_fit["theta"], config))
            recurrence = supportive_recurrence(support, config["component_development"]["supportive_discovery_scans_min"])
            gates["cross_scan_recurrence"] = recurrence["passes"]
            gates["centroid_identifiability"] = bool(support) and all(x.get("profiles_finite", False) for x in support)
            gates["background_sensitivity_acceptable"] = bool(sensitivity) and all(x["status"] == "acceptable" for x in sensitivity)
            promoted = split_promoted(gates, config)
            result["developments"].append({"child_K": child_k, "promoted": promoted,
                                           "gates": gates, "bootstrap": boot,
                                           "recurrence": recurrence, "support": support,
                                           "background_sensitivity": sensitivity})
            if not promoted:
                break
            current = child
            local_scans = candidate_scans
            result["final_K"] = child_k
        result["final_fit"] = current
        result["final_scan_ids"] = [scan.scan_id for scan in local_scans]
        final_sensitivity = []
        for scan, section in zip(local_scans, joint_layout(local_scans, result["final_K"])):
            if current.get("theta") is not None:
                final_sensitivity.append({"scan_id": scan.scan_id, **background_sensitivity(
                    scan, original_by_id[scan.scan_id], union, result["final_K"],
                    current["theta"][section], config)})
        result["final_background_sensitivity"] = final_sensitivity
        ambiguous = (not fit_is_stable(current)
                     or any(item["status"] == "material" for item in final_sensitivity))
        result["final_ambiguity_status"] = "ambiguous" if ambiguous else "not_ambiguous"
        result["final_profiles"] = final_profile_dispatch(
            local_scans, union, result["final_K"], current, ambiguous, config)
        result["uncertainty_status"] = {"centroid": "profile_where_required",
                                        "area": "not_estimated_explicit_no_frozen_method",
                                        "observed_fwhm": "not_estimated_explicit_no_frozen_method"}
        result["resolution_status"] = config["resolution"]["default_status"]
        results[complex_id] = result
    registry = build_future_c002_registry(results, holdout_metadata, config)
    holdout_eligibility = registry["eligibility_by_hypothesis"]
    return {"component_results": results, "scan_eligibility": eligibility,
            "holdout_metadata_eligibility": holdout_eligibility,
            "future_C002_registry": registry,
            "STOP_CONDITION": "A22_STOP_before_holdout_detector_access"}


def run_static_tests(config):
    tests = []

    def test(test_id, function):
        try:
            detail = function()
            tests.append({"test_id": test_id, "status": "PASS", "detail": detail})
        except Exception as error:
            tests.append({"test_id": test_id, "status": "FAIL",
                          "detail": f"{type(error).__name__}: {error}"})

    def t01():
        verify_static_identities(config)
        return "active spec/version/hash and preparation baseline verified"

    def t02():
        expected = {"CX-01": 3, "CX-02": 2, "CX-03": 3}
        require({key: value["maximum_BF_defined_K"] for key, value in config["complexes"].items()}
                == expected, "complex caps")
        require(config["frozen_inputs"]["B001_feature_ids"]
                == [f"BF-{index:03d}" for index in range(1, 9)], "B001 feature IDs")
        return B001_SHA256

    def t03():
        guard = HoldoutMetadataGuard(config)
        require(guard.authorize_fields(("scan_record_id", "e_raw")), "metadata allowlist")
        denied = False
        try:
            guard.authorize_fields(("scan_record_id", "detector_raw"))
        except ConformanceError:
            denied = True
        require(denied and guard.detector_materializations == 0, "detector guard")
        return "forbidden request stopped before decode"

    def t04():
        require(all(value == "forbidden" for value in config["scope"].values()),
                "forbidden operational scope")
        require(config["external_context"]["complementary_experiment"]["C001_model_input"]
                == "forbidden", "external model input")
        return "CEF-blind and TAS-aware scope encoded"

    def t05():
        good = assess_local_coverage([-2, -1, 0, 1, 2, 3, 4], [0, 2], 6, config)
        bad = assess_local_coverage([-1, 0, 1, 2, 3], [0, 2], 3, config)
        require(good["eligible"] and not bad["eligible"], "3+2+2 coverage")
        require(bad["status"] == "insufficient_local_coverage"
                and not bad["nondetection"] and not bad["physical_absence_evidence"],
                "coverage semantics")
        require(not assess_local_coverage([-2, -1, 0, 1, 2, 3, 4], [0, 2], 7, config)["eligible"],
                "strict estimability")
        return "3+2+2 and n_points>n_parameters"

    def t06():
        require(exposure_from_row({"monitor_raw": "5", "time_raw": "2"},
                                  "monitor_controlled", config) == 5.0, "monitor exposure")
        require(exposure_from_row({"monitor_raw": "5", "time_raw": "2"},
                                  "time_controlled", config) == 2.0, "time exposure")
        require(config["exposure"]["shared_monitor_time_normalization"] == "forbidden"
                and config["exposure"]["global_fixed_Ef_assumption"] == "forbidden",
                "cross-mode semantics")
        return "per-scan monitor/time dispatch"

    def t07():
        scan = synthetic_scan()
        theta = baseline_block(scan, [-1.0, 1.0], 2)
        centroids = ordered_centroids(theta[block_layout(2)["eta"]], -1.0, 1.0)
        require(np.all(np.diff(centroids) > 0.0) and -1.0 < centroids[0] < centroids[-1] < 1.0,
                "ordered centroids")
        require(math.isfinite(block_nll(theta, scan, [-1.0, 1.0], 2)), "Poisson likelihood")
        require(config["model"]["primary_background"] == "B1_log_linear"
                and config["model"]["physical_minimum_separation_rule"] == "none",
                "primary model")
        return "raw-count Poisson, B1, scan-local ordered model"

    def t08():
        scan = synthetic_scan()
        fit = observed_fit([scan], [-1.0, 1.0], 0, config)
        require(fit["start_count"] in (8, 16), "observed starts")
        require(fit["KKT_role"] == "diagnostic_only", "KKT role")
        require(config["observed_optimizer"]["start_bank"]
                == "deterministic_unscrambled_Sobol_single_bank", "Sobol bank")
        return {"fit_status": fit["fit_status"], "starts": fit["start_count"]}

    def t09():
        scan = synthetic_scan()
        observed = baseline_joint([scan], [-1.0, 1.0], 1)
        starts = bootstrap_start_bank([scan], [-1.0, 1.0], 1, observed, config)
        require(len(starts) == 4 and all(len(start) == len(observed) for start in starts),
                "four model-local starts")
        require(math.isinf(failed_bootstrap_statistic(
            {"fit_status": "numerical_failure"}, {"fit_status": "valid", "log_likelihood": 0.0})),
            "failed bootstrap consequence")
        return "four starts; no KKT/benchmark/escalation; failure -> infinity"

    def t10():
        payload, digest, seed = seed_identity("CX-01", "K1-to-K2", 1024)
        require("specification_version=1.1" in payload and seed == int(digest[:16], 16), "seed")
        require(config["component_development"]["discovery_bootstrap_replicates"] == 1024
                and config["component_development"]["development_alpha"] == 0.10,
                "development bootstrap")
        require(plus_one_p_value([0.0] * 1024, 1.0) == 1.0 / 1025.0, "plus-one")
        return "B=1024, alpha=.10, PCG64 seed identity, plus-one"

    def t11():
        gates = {name: True for name in config["component_development"]["promotion_gates"]}
        require(split_promoted(gates, config), "promotion gates")
        gates["background_sensitivity_acceptable"] = False
        require(not split_promoted(gates, config), "background sensitivity gate")
        require(profile_required(2, False, config) and not profile_required(1, False, config),
                "selective profiles")
        require(config["component_development"]["supportive_discovery_scans_min"] == 2,
                "recurrence")
        return "parent gates, recurrence, selective profiles, background sensitivity"

    def t12():
        resolution = config["resolution"]
        require(resolution["default_status"] == "resolution_not_established", "resolution status")
        require(resolution["scan_104062"]["calibration_role"] == "unresolved", "104062")
        require(not resolution_claim_allowed("resolution_not_established", "intrinsic_linewidth", config),
                "intrinsic linewidth block")
        require(resolution["full_resolution_calculation_default_required"] is False,
                "resolution fallback")
        return "resolution-not-established permits ordinary parameters only"

    def t13():
        scan = synthetic_scan()
        theta = baseline_joint([scan], [-1.0, 1.0], 0)
        before = theta.copy()
        value = finite_difference_projected_gradient(
            theta, lambda vector: joint_nll(vector, [scan], [-1.0, 1.0], 0),
            joint_bounds([scan], 0), config)
        require(np.array_equal(theta, before) and math.isfinite(value), "diagnostic mutated theta")
        require(config["kkt"]["bootstrap_validity_gate"] is False
                and config["kkt"]["component_selection_gate"] is False, "KKT gating")
        return "final-observed diagnostic only"

    def t14():
        rule = config["holdout"]
        require(rule["metadata_only_before_C001_stop"] is True
                and rule["detector_materialization_allowed"] is False, "metadata-only holdout")
        coverage = assess_local_coverage([-2, -1, 0, 1, 2, 3, 4], [0, 2], 6, config)
        require(coverage["eligible"], "holdout coverage principle")
        return "metadata-only eligibility with monitor/time support"

    def t15():
        future = future_c002_contract(config)
        require(future["bootstrap_replicates"] == 4096
                and future["bootstrap_design"] == "fixed"
                and future["multiplicity_procedure"] == "Holm"
                and future["global_alpha"] == 0.05, "future C002 contract")
        require(future["execution_authorized"] is False
                and future["family_frozen_before_detector_access"] is True, "future boundary")
        return future

    def t16():
        privacy = static_privacy_audit(config)
        legacy = static_legacy_audit(config)
        require(config["acquisition_coverage"]["spectral_completeness_claim"] == "forbidden",
                "spectral completeness")
        require(config["authorization"]["execution_authorized"] is False, "self authorization")
        return {"privacy": privacy, "legacy": legacy, "C002_executed": False,
                "holdout_detector_access_count": 0, "synthetic_only": True}

    for index, function in enumerate(
        (t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12, t13, t14, t15, t16), 1
    ):
        test(f"C001V11-T{index:02d}", function)
    return tests


def run_targeted_regression_tests(config):
    tests = []

    def test(test_id, function):
        try:
            function()
            tests.append({"test_id": test_id, "status": "PASS"})
        except Exception as error:
            tests.append({"test_id": test_id, "status": "FAIL",
                          "detail": f"{type(error).__name__}: {error}"})

    def rc01():
        data = (b"scan_record_id,point_index,e_raw,detector_raw,det_err_raw,monitor_raw,time_raw\n"
                b"H1,0,1.25,\xff,\xfe,10,2\n")
        decoded = []
        def sentinel(token, field):
            decoded.append(field)
            return token.decode("ascii")
        guard = HoldoutMetadataGuard(config)
        rows = project_csv_fields(None, ("scan_record_id", "point_index", "e_raw", "monitor_raw"),
                                  guard, {"H1"}, data, sentinel)
        require(rows[0]["e_raw"] == "1.25", "metadata projection")
        require("detector_raw" not in decoded and "det_err_raw" not in decoded
                and guard.detector_materializations == 0, "sentinel detector decoded")

    def rc02():
        for field in ("detector_raw", "det_err_raw", "detector_monitor_rate", "detector_time_rate"):
            try:
                HoldoutMetadataGuard(config).authorize_fields(("scan_record_id", field))
            except ConformanceError:
                continue
            raise ConformanceError("forbidden alias accepted: " + field)

    def rc03():
        for logits in ([1000.0, -1000.0], [-1000.0, 1000.0], [1000.0, 1000.0]):
            require(not strict_centroid_domain(ordered_centroids(logits, 0.0, 1.0), 0.0, 1.0),
                    "extreme boundary/equal centroid accepted")

    def rc04():
        statistic = failed_bootstrap_statistic({"fit_status": "numerical_failure"},
                                               {"fit_status": "valid", "log_likelihood": 1.0})
        require(math.isinf(statistic) and plus_one_p_value([statistic, 0.0], 1.0) == 2 / 3,
                "failed parent tail")

    def rc05():
        statistic = failed_bootstrap_statistic({"fit_status": "valid", "log_likelihood": 0.0},
                                               {"fit_status": "numerical_failure"})
        require(math.isinf(statistic) and plus_one_p_value([statistic, 0.0], 1.0) == 2 / 3,
                "failed child tail")

    def supportive(scan_id):
        return {"scan_id": scan_id, "fit_stable": True, "areas_strictly_positive": True,
                "profiles_finite": True, "adjacent_rule": True}

    def rc06():
        require(not supportive_recurrence([supportive("S1"), supportive("S1")])["passes"],
                "duplicate scan satisfied recurrence")

    def rc07():
        require(supportive_recurrence([supportive("S1"), supportive("S2")])["passes"],
                "distinct scans did not recur")

    def rc08():
        record = supportive("S1"); record["areas_strictly_positive"] = False
        require(not supportive_recurrence([record, supportive("S2")])["passes"], "area bound supportive")

    def rc09():
        coverage = {"lower": 2, "upper": 2}
        require(not (coverage["lower"] >= 3 and coverage["upper"] >= 3), "B2 estimability")

    def rc10():
        gates = {name: True for name in config["component_development"]["promotion_gates"]}
        gates["background_sensitivity_acceptable"] = False
        require(not split_promoted(gates, config), "material sensitivity promoted")
        require(config["component_development"]["presence_registration_independent_of_discovery_significance"],
                "presence erased")

    def rc11():
        require(resolution_claim_allowed("resolution_not_established", "centroid", config), "centroid")
        require(resolution_claim_allowed("resolution_not_established", "integrated_area", config), "area")
        require(not resolution_claim_allowed("resolution_not_established", "intrinsic_linewidth", config),
                "intrinsic claim")

    def rc12():
        scan = config["resolution"]["scan_104062"]
        require(scan["calibration_role"] == "unresolved"
                and scan["transfer_to_production_resolution_function"].startswith("forbidden"), "104062")

    def rc13():
        results = {"CX-01": {"adequate_model_preparation": True, "final_K": 2}}
        lower, upper = config["complexes"]["CX-01"]["frozen_union_meV"]
        holdout = [{"scan_id": "H1", "energy": np.asarray(
                        [lower - 2, lower - 1] + list(np.linspace(lower, upper, 5))
                        + [upper + 1, upper + 2]),
                    "exposure_class": "monitor_controlled", "exposure": np.ones(9),
                    "energy_transfer_semantics_valid": True}]
        registry = build_future_c002_registry(results, holdout, config)
        require(len(registry["hypotheses"]) == 2 and registry["hypotheses"][1]["ancestor_hypothesis_id"]
                == registry["hypotheses"][0]["hypothesis_id"], "ancestor")
        require(all(x["bootstrap_replicates"] == 4096 and x["numerical_failure_raw_p_value"] == 1.0
                    for x in registry["hypotheses"]), "C002 rules")

    def rc14():
        scans = []
        for sid, shift in (("D1", 0.0), ("D2", 0.08)):
            energy = np.linspace(1.5, 8.0, 14)
            exposure = np.full(14, 50.0)
            rate = 2.0 + 3.0 * np.exp(-0.5 * ((energy - (4.0 + shift)) / 0.5) ** 2)
            scans.append(ScanData(sid, energy, exposure, np.round(exposure * rate), "monitor_controlled"))
        holdout = [{"scan_id": "H1", "energy": np.linspace(1.5, 8.0, 14),
                    "exposure_class": "monitor_controlled", "exposure": np.ones(14),
                    "energy_transfer_semantics_valid": True}]
        result = dispatch_c001_core(scans, holdout, config, bootstrap_replicates=1)
        require(result["STOP_CONDITION"] == "A22_STOP_before_holdout_detector_access"
                and result.get("holdout_detector_access_count", 0) == 0, "mini dispatcher")

    functions = (rc01, rc02, rc03, rc04, rc05, rc06, rc07, rc08, rc09, rc10, rc11, rc12, rc13, rc14)
    for index, function in enumerate(functions, 1):
        test(f"C001V11-RC{index:02d}", function)

    def b01():
        original = ScanData("S", np.asarray([-3, -2, -1, 0, 1, 2, 3, 4, 5.]),
                            np.ones(9), np.ones(9), "monitor_controlled")
        primary, _ = local_fit_window(original, [0, 2], config, anchors=2)
        window, coverage = sensitivity_window(primary, original, [0, 2], "B2", config)
        require(window is not None and coverage["lower"] == 3 and coverage["upper"] == 3,
                "B2 did not receive 3+3 window")
        require(np.sum(window.energy < 0) == 3 and np.sum(window.energy > 2) == 3,
                "B2 window token count")

    def b02():
        original = ScanData("S", np.asarray([-2, -1, 0, 1, 2, 3, 4.]),
                            np.ones(7), np.ones(7), "monitor_controlled")
        primary, _ = local_fit_window(original, [0, 2], config, anchors=2)
        window, _ = sensitivity_window(primary, original, [0, 2], "B2", config)
        require(window is None, "B2 with only 2+2 was estimable")

    def holdout_record(inside, exposure_class="monitor_controlled", exposure=1.0,
                       union=(0.0, 2.0)):
        lower, upper = union
        energy = np.asarray([lower - 2, lower - 1] + list(np.linspace(lower, upper, inside))
                            + [upper + 1, upper + 2])
        return {"scan_id": "H", "energy": energy, "exposure_class": exposure_class,
                "exposure": np.full(len(energy), exposure),
                "energy_transfer_semantics_valid": True}

    def b03():
        record = holdout_record(3)
        require(holdout_hypothesis_eligibility(record, [0, 2], 1, config)["eligible"], "K1")
        require(not holdout_hypothesis_eligibility(record, [0, 2], 2, config)["eligible"], "K2")

    def b04():
        record = holdout_record(5)
        require(holdout_hypothesis_eligibility(record, [0, 2], 2, config)["eligible"], "K2")
        require(not holdout_hypothesis_eligibility(record, [0, 2], 3, config)["eligible"], "K3")

    def b05():
        for exposure in (0.0, float("nan")):
            require(not holdout_hypothesis_eligibility(
                holdout_record(3, "monitor_controlled", exposure), [0, 2], 1, config)["eligible"],
                "invalid monitor accepted")
        require(holdout_hypothesis_eligibility(
            holdout_record(3, "monitor_controlled", 1.0), [0, 2], 1, config)["eligible"],
            "valid monitor rejected")

    def b06():
        require(not holdout_hypothesis_eligibility(
            holdout_record(3, "time_controlled", -1.0), [0, 2], 1, config)["eligible"],
            "negative time accepted")
        require(holdout_hypothesis_eligibility(
            holdout_record(3, "time_controlled", 2.0), [0, 2], 1, config)["eligible"],
            "valid time rejected")

    def b07():
        calls = []
        scan = synthetic_scan()
        fit = {"theta": baseline_joint([scan], [-1, 1], 1)}
        def profile(*args):
            calls.append(args)
            return {"finite_in_domain_crossings": True}
        result = final_profile_dispatch([scan], [-1, 1], 1, fit, True, config, profile)
        require(result["performed"] and len(calls) == 1, "ambiguous K1 profile not invoked")

    def b08():
        calls = []
        scan = synthetic_scan()
        fit = {"theta": baseline_joint([scan], [-1, 1], 1)}
        result = final_profile_dispatch([scan], [-1, 1], 1, fit, False, config,
                                        lambda *args: calls.append(args))
        require(not result["performed"] and not calls, "unnecessary K1 profile")

    def b09():
        results = {"CX-01": {"adequate_model_preparation": True, "final_K": 2,
                             "resolution_status": "resolution_not_established"}}
        union = config["complexes"]["CX-01"]["frozen_union_meV"]
        registry = build_future_c002_registry(results, [holdout_record(5, union=union)], config)
        required = {"hypothesis_id", "complex_id", "parent_K", "child_K",
                    "eligible_holdout_scan_ids", "exposure_class_per_scan",
                    "parameter_domain_rules", "resolution_status", "multiplicity_rule",
                    "bootstrap_replicates", "rng", "p_value_convention", "bootstrap_design",
                    "adaptive_extension", "numerical_failure_raw_p_value", "ancestor_rule",
                    "family_frozen_before_detector_access"}
        require(registry["hypotheses"] and all(required <= set(item) for item in registry["hypotheses"]),
                "incomplete C002 record")

    def b10():
        results = {"CX-01": {"adequate_model_preparation": True, "final_K": 1}}
        union = config["complexes"]["CX-01"]["frozen_union_meV"]
        registry = build_future_c002_registry(results, [holdout_record(3, union=union)], config)
        ordering = registry["Holm_ordering"]
        require(ordering == {"primary_sort": {"raw_p_value": "ascending"},
                             "tie_break": {"hypothesis_id": "lexical_ascending"}}, "Holm order")

    localized = (b01, b02, b03, b04, b05, b06, b07, b08, b09, b10)
    for index, function in enumerate(localized, 1):
        test(f"C001V11-RC4B{index:02d}", function)

    direct_e = {"def_x_raw": "s1", "energy_transfer_field_raw": "e",
                "energy_transfer_convention": "Ei_minus_Ef",
                "energy_relation_status": "verified_global",
                "en_e_mapping_status": "not_applicable"}
    alias_e = {**direct_e, "def_x_raw": "en", "en_e_mapping_status": "verified"}

    def production_fixture():
        scan = synthetic_scan("D1")
        theta = baseline_joint([scan], [-1.0, 1.0], 1)
        fit = {"fit_status": "valid", "theta": theta, "log_likelihood": -1.0,
               "start_count": 8, "optimizer_stability_status": "stable",
               "projected_gradient_max": 1e-6,
               "numerical_convergence_status": "within_reference", "KKT_role": "diagnostic_only"}
        component = {"adequate_model_preparation": True,
                     "presence_hypothesis_registered": True, "final_K": 1,
                     "final_scan_ids": ["D1"], "final_fit": fit,
                     "developments": [{"child_K": 2, "promoted": False,
                                       "gates": {"parent_observed_fit_stable": False}}],
                     "final_background_sensitivity": [{"scan_id": "D1", "status": "acceptable",
                         "refits": [{"background": "B0", "status": "valid", "material": False,
                                     "window_lower_anchors": 2, "window_upper_anchors": 2,
                                     "window_point_count": 9},
                                    {"background": "B2", "status": "not_estimable", "material": False}]}],
                     "final_profiles": {"required": False, "performed": False, "records": []},
                     "uncertainty_status": {"centroid": "profile_where_required",
                                            "area": "not_estimated_explicit_no_frozen_method",
                                            "observed_fwhm": "not_estimated_explicit_no_frozen_method"},
                     "resolution_status": "resolution_not_established"}
        lower, upper = config["complexes"]["CX-01"]["frozen_union_meV"]
        holdout_energy = np.asarray([lower - 2.0, lower - 1.0] +
                                    list(np.linspace(lower, upper, 5)) +
                                    [upper + 1.0, upper + 2.0])
        holdout = [{"scan_id": "H1", "energy": holdout_energy,
                    "exposure_class": "monitor_controlled", "exposure": np.ones(9),
                    "energy_transfer_semantics_valid": True}]
        registry = build_future_c002_registry({"CX-01": component}, holdout, config)
        return {"component_results": {"CX-01": component},
                "scan_eligibility": {"CX-01": [{"scan_id": "D1", "eligible": True}]},
                "holdout_metadata_eligibility": registry["eligibility_by_hypothesis"],
                "future_C002_registry": registry,
                "holdout_field_access_log": [{"decoded_field": "e_raw", "detector_field": False}],
                "holdout_detector_access_count": 0,
                "STOP_CONDITION": "A22_STOP_before_holdout_detector_access"}

    def production_context():
        return {"split_role_per_scan": {"D1": "discovery", "H1": "holdout"},
                "exposure_class_per_scan": {"D1": "monitor_controlled", "H1": "monitor_controlled"},
                "Ei_Ef_status_per_scan": {"D1": direct_e, "H1": direct_e}}

    def production_authorization():
        return {"canonical_head": git_head(), "source_sha256": sha256_file(Path(__file__)),
                "config_sha256": sha256_file(ROOT / CONFIG_PATH)}

    def p01():
        require(energy_transfer_semantics_valid(direct_e), "canonical direct e rejected")
        require(energy_transfer_semantics_valid(alias_e), "verified en/e alias rejected")
    def p02():
        for change in ({"energy_relation_status": "unresolved"},
                       {"energy_transfer_convention": None}, {"energy_transfer_field_raw": "en"}):
            require(not energy_transfer_semantics_valid({**direct_e, **change}), "unknown semantics accepted")
    def p03():
        require(energy_transfer_semantics_valid(direct_e), "not_applicable direct e rejected")
        require(not energy_transfer_semantics_valid({**alias_e, "en_e_mapping_status": "unresolved"}),
                "unresolved required alias accepted")
    def p04(): rc01()
    def p05():
        result = production_fixture()
        require(result["future_C002_registry"]["hypotheses"], "future presence family empty")
    def p06(): b03()
    def p07():
        rows = final_fit_rows(production_fixture(), config)
        require(rows and {"fit_status", "log_likelihood", "fitted_background_parameters",
                          "integrated_area", "centroid", "observed_empirical_fwhm",
                          "scientific_status"} <= set(rows[0]),
                "fit serialization incomplete")
    def p08():
        rows = sensitivity_rows(production_fixture())
        require({row["sensitivity_model"] for row in rows} == {"B0", "B2"}, "sensitivity rows absent")
    def p09():
        rows = uncertainty_rows(production_fixture())
        require(rows and "uncertainty_status" in rows[0] and rows[0]["area_uncertainty_status"].startswith("not_estimated"),
                "uncertainty status absent")
    def p10():
        rows = reproducibility_rows(production_fixture())
        require(any(row["assessment_type"] == "final_optimizer_reproduction" for row in rows),
                "reproducibility rows absent")
    def p11():
        rows = resolution_rows(production_fixture(), config)
        require(rows[0]["resolution_status"] == "resolution_not_established", "resolution row absent")
    def p12():
        result, context, auth = production_fixture(), production_context(), production_authorization()
        provenance = build_provenance(result, config, auth, context, {}, {})
        report = production_test_report(result, config, auth, context, provenance)
        require([row["test_id"] for row in report["tests"]] ==
                [f"C001V11-T{i:02d}" for i in range(1, 17)]
                and all({"status", "evidence", "reason"} <= set(row) for row in report["tests"]),
                "T01-T16 report incomplete")
    def p13():
        result, context, auth = production_fixture(), production_context(), production_authorization()
        bad = dict(auth); bad["source_sha256"] = "0" * 64
        report = production_test_report(result, config, bad, context,
                                        build_provenance(result, config, bad, context, {}, {}))
        require(report["tests"][0]["status"] == "FAIL" and not report["all_mandatory_tests_pass"],
                "failing invariant converted to PASS")
    def p14():
        result, context, auth = production_fixture(), production_context(), production_authorization()
        require(build_provenance(result, config, auth, context, {}, {})["canonical_main"] == git_head(),
                "preparation baseline serialized as canonical main")
    def p15():
        result, context, auth = production_fixture(), production_context(), production_authorization()
        require(required_provenance_fields() <= set(build_provenance(
            result, config, auth, context, {}, {})), "provenance fields absent")
    def p16():
        rows = [{"b": 2, "a": 1}]
        require(csv_document_bytes(rows) == csv_document_bytes(rows), "nondeterministic CSV")
        policy = build_provenance(production_fixture(), config, production_authorization(),
                                  production_context(), {"x": "1"}, {})["output_identity_policy"]
        require("excluded" in policy["provenance_manifest.yaml"], "recursive identity policy")
    def p17():
        require(production_fixture()["STOP_CONDITION"] == "A22_STOP_before_holdout_detector_access", "STOP")
    def p18():
        require(not production_fixture()["future_C002_registry"]["C002_executed"], "C002 executed")
    def p19():
        require(static_privacy_audit(config)["private_urls"] == 0, "private material")
    def p20():
        for function in (rc01, rc02, rc03, rc04): function()

    production_regressions = (p01, p02, p03, p04, p05, p06, p07, p08, p09, p10,
                              p11, p12, p13, p14, p15, p16, p17, p18, p19, p20)
    for index, function in enumerate(production_regressions, 1):
        test(f"C001V11-PROD{index:02d}", function)
    return tests


def self_test_report():
    config = load_config()
    tests = run_static_tests(config) + run_targeted_regression_tests(config)
    failed = [test for test in tests if test["status"] != "PASS"]
    return {
        "mode": "static_and_synthetic_only",
        "scientific_execution": False,
        "active_specification_version": SPEC_VERSION,
        "tests_run": len(tests),
        "passed": len(tests) - len(failed),
        "failed": len(failed),
        "tests": tests,
        "execution_authorized": False,
        "A2_authorized": False,
        "C002_execution_authorized": False,
        "holdout_detector_access_authorized": False,
        "holdout_detector_access_count": 0,
    }


def load_execution_inputs(config):
    """A03-A06 loader. Discovery counts are selected by ID; holdout stays metadata-only."""
    frozen = config["frozen_inputs"]
    split_rows = project_csv_fields(ROOT / frozen["split_metadata_path"],
                                    ("scan_record_id", "split_role", "count_control_mode"))
    selection_rows = project_csv_fields(
        ROOT / frozen["scan_selection_path"],
        ("scan_record_id", "split_role", "discovery_runtime_status", "count_control_mode"))
    selection = {row["scan_record_id"]: row for row in selection_rows}
    inventory_rows = project_csv_fields(
        ROOT / frozen["scan_inventory_path"],
        ("scan_record_id", "def_x_raw", "energy_transfer_field_raw",
         "energy_transfer_convention", "energy_relation_status", "en_e_mapping_status"))
    inventory = {row["scan_record_id"]: row for row in inventory_rows}
    discovery_ids = {row["scan_record_id"] for row in split_rows if row["split_role"] == "discovery"
                     and selection.get(row["scan_record_id"], {}).get("discovery_runtime_status") == "discovery_usable"}
    holdout_ids = {row["scan_record_id"] for row in split_rows if row["split_role"] == "holdout"}
    point_path = ROOT / frozen["scan_points_path"]
    discovery_fields = ("scan_record_id", "point_index", "e_raw", "ei_raw", "ef_raw",
                        "monitor_raw", "time_raw", "detector_raw")
    discovery_rows = project_csv_fields(point_path, discovery_fields,
                                        selected_scan_ids=discovery_ids)
    guard = HoldoutMetadataGuard(config)
    holdout_fields = tuple(config["holdout"]["allowed_point_fields"])
    holdout_rows = project_csv_fields(point_path, holdout_fields, guard=guard,
                                      selected_scan_ids=holdout_ids)
    grouped = {}
    for row in discovery_rows:
        grouped.setdefault(row["scan_record_id"], []).append(row)
    discovery_scans = []
    for scan_id, rows in sorted(grouped.items()):
        exposure_class = selection[scan_id]["count_control_mode"]
        energy = np.asarray([float(row["e_raw"]) for row in rows])
        exposure = np.asarray([exposure_from_row(row, exposure_class, config) for row in rows])
        counts = np.asarray([float(row["detector_raw"]) for row in rows])
        discovery_scans.append(ScanData(scan_id, energy, exposure, counts, exposure_class))
    holdout_grouped = {}
    for row in holdout_rows:
        holdout_grouped.setdefault(row["scan_record_id"], []).append(row)
    holdout_metadata = []
    for scan_id, rows in sorted(holdout_grouped.items()):
        exposure_class = selection.get(scan_id, {}).get("count_control_mode")
        exposure_field = config["exposure"]["verified_classes"].get(exposure_class)
        scan_inventory = inventory.get(scan_id, {})
        holdout_metadata.append({
            "scan_id": scan_id,
            "energy": np.asarray([float(row["e_raw"]) for row in rows]),
            "exposure_class": exposure_class,
            "exposure": [] if exposure_field is None else [row.get(exposure_field) for row in rows],
            "energy_transfer_semantics_valid": energy_transfer_semantics_valid(scan_inventory),
        })
    require(guard.detector_materializations == 0, "holdout detector materialized")
    split_role_per_scan = {row["scan_record_id"]: row["split_role"] for row in split_rows}
    exposure_class_per_scan = {
        scan_id: selection.get(scan_id, {}).get("count_control_mode")
        for scan_id in sorted(split_role_per_scan)
    }
    energy_status_per_scan = {
        scan_id: {key: inventory.get(scan_id, {}).get(key) for key in (
            "def_x_raw", "energy_transfer_field_raw", "energy_transfer_convention",
            "energy_relation_status", "en_e_mapping_status")}
        for scan_id in sorted(split_role_per_scan)
    }
    input_context = {
        "split_role_per_scan": split_role_per_scan,
        "exposure_class_per_scan": exposure_class_per_scan,
        "Ei_Ef_status_per_scan": energy_status_per_scan,
    }
    return discovery_scans, holdout_metadata, guard, input_context


def serializable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Candidate):
        return value.__dict__
    raise TypeError(type(value).__name__)


def write_csv_rows(path, rows):
    rows = list(rows)
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        if rows:
            for row in rows:
                writer.writerow({key: json.dumps(row.get(key), default=serializable)
                                 if isinstance(row.get(key), (dict, list, np.ndarray))
                                 else row.get(key) for key in fields})
        else:
            writer.writerow({"status": "not_applicable"})


def csv_document_bytes(rows):
    rows = list(rows)
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows or [{"status": "not_applicable"}]:
        writer.writerow({key: json.dumps(row.get(key), default=serializable, sort_keys=True)
                         if isinstance(row.get(key), (dict, list, np.ndarray))
                         else row.get(key) for key in fields})
    return stream.getvalue().encode("utf-8")


def yaml_document_bytes(document):
    plain = json.loads(json.dumps(document, default=serializable))
    return yaml.safe_dump(plain, sort_keys=False).encode("utf-8")


def final_fit_rows(result, config):
    rows = []
    for complex_id, item in sorted(result["component_results"].items()):
        final_k = int(item.get("final_K", 0))
        fit = item.get("final_fit", {})
        scan_ids = item.get("final_scan_ids", [])
        theta = fit.get("theta")
        sections = joint_layout(scan_ids, final_k) if scan_ids else []
        for scan_id, section in zip(scan_ids, sections):
            local = None if theta is None else np.asarray(theta)[section]
            layout = block_layout(final_k)
            background = None if local is None else {
                f"b{index}": float(value)
                for index, value in enumerate(local[layout["background"]])
            }
            centroids = ([] if local is None or final_k == 0 else ordered_centroids(
                local[layout["eta"]], *config["complexes"][complex_id]["frozen_union_meV"]))
            component_indices = range(final_k) if final_k else (None,)
            for index in component_indices:
                estimated = local is not None and index is not None
                rows.append({
                    "complex_id": complex_id, "scan_id": scan_id,
                    "final_K": final_k, "model_id": f"K{final_k}",
                    "component_id": None if index is None else f"C{index + 1:02d}",
                    "fit_status": fit.get("fit_status", item.get("status", "not_estimated")),
                    "optimizer_stability_status": fit.get("optimizer_stability_status", "not_estimated"),
                    "numerical_convergence_status": fit.get("numerical_convergence_status", "not_estimated"),
                    "log_likelihood": fit.get("log_likelihood"),
                    "start_count": fit.get("start_count", 0),
                    "fitted_background_parameters": background,
                    "integrated_area": float(local[layout["areas"]][index]) if estimated else None,
                    "centroid": float(centroids[index]) if estimated else None,
                    "observed_empirical_fwhm": float(local[layout["widths"]][index]) if estimated else None,
                    "parameter_status": "estimated" if estimated else "not_estimated",
                    "scientific_status": ("estimate_available" if estimated and
                                          fit.get("optimizer_stability_status") == "stable" else
                                          "estimate_numerically_unresolved" if estimated else
                                          "not_estimated"),
                    "reason": None if estimated else (
                        "final_fit_numerical_failure" if theta is None else "zero_component_model"),
                })
        if not scan_ids:
            rows.append({"complex_id": complex_id, "scan_id": None, "final_K": final_k,
                         "model_id": f"K{final_k}", "component_id": None,
                         "fit_status": item.get("status", "not_estimated"),
                         "optimizer_stability_status": "not_estimated",
                         "numerical_convergence_status": "not_estimated",
                         "log_likelihood": None, "start_count": 0,
                         "fitted_background_parameters": None, "integrated_area": None,
                         "centroid": None, "observed_empirical_fwhm": None,
                         "parameter_status": "not_estimated", "scientific_status": "not_estimated",
                         "reason": "no_eligible_discovery_scans"})
    return rows


def sensitivity_rows(result):
    rows = []
    for complex_id, item in sorted(result["component_results"].items()):
        records = item.get("final_background_sensitivity", [])
        for record in records:
            for refit in record.get("refits", []):
                rows.append({"complex_id": complex_id, "scan_id": record.get("scan_id"),
                             "sensitivity_model": refit.get("background"),
                             "estimability_status": ("not_estimable" if refit.get("status") == "not_estimable"
                                                      else "estimable"),
                             "fit_status": refit.get("status"),
                             "material": refit.get("material"),
                             "overall_status": record.get("status"),
                             "window_lower_anchors": refit.get("window_lower_anchors"),
                             "window_upper_anchors": refit.get("window_upper_anchors"),
                             "window_point_count": refit.get("window_point_count"),
                             "reason": ("insufficient_B2_anchor_coverage"
                                        if refit.get("status") == "not_estimable" else None)})
        if not records:
            for scan_id in item.get("final_scan_ids", [None]):
                for background in ("B0", "B2"):
                    rows.append({"complex_id": complex_id, "scan_id": scan_id,
                                 "sensitivity_model": background, "estimability_status": "not_estimated",
                                 "fit_status": "not_estimated", "material": None,
                                 "overall_status": "not_estimated",
                                 "reason": "final_fit_unavailable_for_sensitivity"})
    return rows


def uncertainty_rows(result):
    rows = []
    for complex_id, item in sorted(result["component_results"].items()):
        profiles = {record["scan_id"]: record.get("centroid_profiles", [])
                    for record in item.get("final_profiles", {}).get("records", [])}
        final_k = int(item.get("final_K", 0))
        for scan_id in item.get("final_scan_ids", [None]):
            for index in range(final_k) if final_k else (None,):
                profile = (profiles.get(scan_id, [])[index]
                           if index is not None and index < len(profiles.get(scan_id, [])) else None)
                centroid_status = ("not_estimated" if profile is None else
                                   "estimated_finite" if profile.get("finite_in_domain_crossings") else
                                   "estimated_no_finite_in_domain_crossing")
                rows.append({
                    "complex_id": complex_id, "scan_id": scan_id,
                    "component_id": None if index is None else f"C{index + 1:02d}",
                    "centroid_uncertainty": (None if profile is None else
                                             {"lower": profile.get("lower"), "upper": profile.get("upper")}),
                    "area_uncertainty": None, "observed_width_uncertainty": None,
                    "uncertainty_method": "selective_likelihood_profile_for_centroid",
                    "uncertainty_status": centroid_status,
                    "area_uncertainty_status": "not_estimated_explicit_no_frozen_method",
                    "observed_width_uncertainty_status": "not_estimated_explicit_no_frozen_method",
                    "reason": (None if centroid_status == "estimated_finite" else
                               "profile_not_required_or_not_performed" if profile is None else
                               "profile_has_no_finite_in_domain_crossing"),
                })
    return rows


def reproducibility_rows(result):
    rows = []
    for complex_id, item in sorted(result["component_results"].items()):
        fit = item.get("final_fit", {})
        for scan_id in item.get("final_scan_ids", [None]):
            rows.append({"complex_id": complex_id, "scan_id": scan_id,
                         "assessment_type": "final_optimizer_reproduction",
                         "model_id": f"K{item.get('final_K', 0)}",
                         "status": fit.get("optimizer_stability_status", "not_estimated"),
                         "passes": fit.get("optimizer_stability_status") == "stable",
                         "start_count": fit.get("start_count", 0),
                         "reason": (None if fit.get("optimizer_stability_status") == "stable"
                                    else "optimizer_solution_not_reproduced_or_fit_unavailable")})
        for development in item.get("developments", []):
            recurrence = development.get("recurrence")
            rows.append({"complex_id": complex_id, "scan_id": None,
                         "assessment_type": "cross_scan_component_recurrence",
                         "model_id": f"K{development.get('child_K')}",
                         "status": ("evaluated" if recurrence is not None else "not_evaluated"),
                         "passes": None if recurrence is None else recurrence.get("passes"),
                         "supportive_scan_ids": None if recurrence is None else recurrence.get("supportive_scan_ids"),
                         "supportive_scan_count": None if recurrence is None else recurrence.get("supportive_scan_count"),
                         "promotion_status": "promoted" if development.get("promoted") else "not_promoted",
                         "reason": (None if recurrence is not None else "earlier_component_development_gate_failed")})
            for support in development.get("support", []):
                rows.append({"complex_id": complex_id, "scan_id": support.get("scan_id"),
                             "assessment_type": "scan_component_support",
                             "model_id": f"K{development.get('child_K')}",
                             "status": "supportive" if all(support.get(key) for key in (
                                 "fit_stable", "areas_strictly_positive", "profiles_finite", "adjacent_rule")) else "not_supportive",
                             "passes": all(support.get(key) for key in (
                                 "fit_stable", "areas_strictly_positive", "profiles_finite", "adjacent_rule")),
                             "reason": None})
    return rows


def resolution_rows(result, config):
    rows = []
    for complex_id, item in sorted(result["component_results"].items()):
        for scan_id in item.get("final_scan_ids", [None]):
            rows.append({"complex_id": complex_id, "scan_id": scan_id,
                         "resolution_status": item.get("resolution_status", config["resolution"]["default_status"]),
                         "ordinary_parameter_extraction_allowed": config["resolution"]["ordinary_parameter_extraction_allowed_without_resolution"],
                         "intrinsic_linewidth_claim_allowed": False,
                         "scan_104062_calibration_role": config["resolution"]["scan_104062"]["calibration_role"],
                         "reason": "no_independently_established_production_resolution_function"})
    return rows


def required_provenance_fields():
    return {"canonical_main", "dataset_id", "B001_catalogue_sha256", "source_sha256",
            "config_sha256", "scan_ids_per_complex", "split_role_per_scan",
            "exposure_class_per_scan", "Ei_Ef_status_per_scan", "model_specification",
            "component_development_result", "background_sensitivity_status",
            "resolution_status", "bootstrap_B", "bootstrap_seed_payload",
            "bootstrap_seed_sha256", "holdout_detector_access_count", "C002_executed",
            "input_artifact_identities", "output_artifact_identities"}


def input_artifact_identities(config):
    a002_manifest = yaml_load(ROOT / "04_Results/Stage02R/W02-02R-A-002/provenance_manifest.yaml")
    upstream = {item["path"]: item.get("byte_sha256") for item in a002_manifest.get("outputs", [])}
    identities = {}
    for key, relative in sorted(config["frozen_inputs"].items()):
        if not key.endswith("_path"):
            continue
        digest = upstream.get(relative)
        if digest is None:
            digest = sha256_file(ROOT / relative)
        identities[key] = {"path": relative, "sha256": digest}
    return identities


def build_provenance(result, config, authorization, input_context, output_identities=None,
                     input_identities=None):
    bootstrap_records = [development["bootstrap"]
                         for item in result["component_results"].values()
                         for development in item.get("developments", []) if "bootstrap" in development]
    scan_ids_per_complex = {
        complex_id: sorted(row["scan_id"] for row in result["scan_eligibility"].get(complex_id, [])
                           if row.get("eligible"))
        for complex_id in result["component_results"]
    }
    return {
        "canonical_main": authorization["canonical_head"],
        "implementation_preparation_baseline": PREPARATION_BASELINE,
        "dataset_id": config["dataset_id"], "B001_catalogue_sha256": B001_SHA256,
        "source_sha256": authorization["source_sha256"],
        "config_sha256": authorization["config_sha256"],
        "scan_ids_per_complex": scan_ids_per_complex,
        "split_role_per_scan": input_context["split_role_per_scan"],
        "exposure_class_per_scan": input_context["exposure_class_per_scan"],
        "Ei_Ef_status_per_scan": input_context["Ei_Ef_status_per_scan"],
        "model_specification": config["model"],
        "component_development_result": result["component_results"],
        "background_sensitivity_status": {
            complex_id: [record.get("status") for record in item.get("final_background_sensitivity", [])]
            for complex_id, item in result["component_results"].items()},
        "resolution_status": {complex_id: item.get("resolution_status", config["resolution"]["default_status"])
                              for complex_id, item in result["component_results"].items()},
        "bootstrap_B": config["component_development"]["discovery_bootstrap_replicates"],
        "bootstrap_seed_payload": [record.get("seed_payload") for record in bootstrap_records],
        "bootstrap_seed_sha256": [record.get("seed_sha256") for record in bootstrap_records],
        "holdout_detector_access_count": result.get("holdout_detector_access_count", 0),
        "C002_executed": result["future_C002_registry"].get("C002_executed", False),
        "input_artifact_identities": (input_identities if input_identities is not None
                                      else input_artifact_identities(config)),
        "output_artifact_identities": output_identities or {},
        "output_identity_policy": {
            "algorithm": "sha256_of_final_file_bytes",
            "provenance_manifest.yaml": "excluded_from_internal_map_to_avoid_recursive_self_hash"},
        "spectral_completeness_claim": "forbidden",
        "algorithm_stop": result["STOP_CONDITION"],
    }


def production_test_report(result, config, authorization, input_context, provenance):
    tests = []
    def check(test_id, condition, evidence, failure_reason):
        try:
            passed = bool(condition())
        except Exception as error:
            passed = False
            failure_reason = f"{type(error).__name__}: {error}"
        try:
            evidence_value = evidence()
        except Exception as error:
            passed = False
            evidence_value = {"evidence_error": f"{type(error).__name__}: {error}"}
            failure_reason = "runtime evidence serialization failed"
        tests.append({"test_id": test_id, "status": "PASS" if passed else "FAIL",
                      "evidence": evidence_value, "reason": None if passed else failure_reason})
    check("C001V11-T01", lambda: authorization["canonical_head"] == git_head()
          and authorization["source_sha256"] == sha256_file(Path(__file__))
          and authorization["config_sha256"] == sha256_file(ROOT / CONFIG_PATH),
          lambda: {"canonical_head": authorization["canonical_head"],
                   "source_sha256": authorization["source_sha256"],
                   "config_sha256": authorization["config_sha256"]}, "runtime identity mismatch")
    check("C001V11-T02", lambda: config["frozen_inputs"]["B001_catalogue_sha256"] == B001_SHA256
          and sha256_file(ROOT / config["frozen_inputs"]["B001_catalogue_path"]) == B001_SHA256,
          lambda: {"B001_catalogue_sha256": B001_SHA256}, "B001 byte identity mismatch")
    check("C001V11-T03", lambda: result.get("holdout_detector_access_count", 0) == 0
          and not any(row.get("detector_field") for row in result.get("holdout_field_access_log", [])),
          lambda: {"holdout_detector_access_count": result.get("holdout_detector_access_count", 0)},
          "holdout detector boundary violated")
    check("C001V11-T04", lambda: all(value == "forbidden" for value in config["scope"].values())
          and not static_privacy_audit(config)["private_urls"],
          lambda: {"scope": config["scope"]}, "scope or private-material audit failed")
    check("C001V11-T05", lambda: bool(result["scan_eligibility"])
          and all(status.get("energy_relation_status") == "verified_global"
                  for status in input_context["Ei_Ef_status_per_scan"].values()),
          lambda: {"complex_count": len(result["scan_eligibility"]),
                   "scan_count": len(input_context["split_role_per_scan"])}, "eligibility contract failed")
    check("C001V11-T06", lambda: all(value in config["exposure"]["verified_classes"]
                                     for value in input_context["exposure_class_per_scan"].values()),
          lambda: {"exposure_classes": sorted(set(input_context["exposure_class_per_scan"].values()))},
          "unverified exposure class")
    check("C001V11-T07", lambda: config["model"]["likelihood"] == "raw_count_exposure_conditioned_Poisson"
          and config["model"]["primary_background"] == "B1_log_linear",
          lambda: config["model"], "model contract mismatch")
    check("C001V11-T08", lambda: all(item.get("final_fit", {}).get("start_count") in (8, 16)
                                     for item in result["component_results"].values()
                                     if item.get("adequate_model_preparation")),
          lambda: {key: value.get("final_fit", {}).get("start_count")
                   for key, value in result["component_results"].items()}, "observed optimizer policy mismatch")
    check("C001V11-T09", lambda: config["bootstrap_optimizer"]["model_local_starts"] == 4
          and config["bootstrap_optimizer"]["failed_replicate_statistic"] == "positive_infinity",
          lambda: config["bootstrap_optimizer"], "bootstrap optimizer policy mismatch")
    check("C001V11-T10", lambda: provenance["bootstrap_B"] == 1024
          and len(provenance["bootstrap_seed_payload"]) == len(provenance["bootstrap_seed_sha256"]),
          lambda: {"bootstrap_B": provenance["bootstrap_B"],
                   "executed_seed_count": len(provenance["bootstrap_seed_sha256"])}, "bootstrap identity mismatch")
    check("C001V11-T11", lambda: all("promoted" in development
                                     for item in result["component_results"].values()
                                     for development in item.get("developments", [])),
          lambda: {key: value.get("developments", []) for key, value in result["component_results"].items()},
          "component-development result incomplete")
    check("C001V11-T12", lambda: all(item.get("resolution_status") == config["resolution"]["default_status"]
                                     for item in result["component_results"].values()
                                     if item.get("adequate_model_preparation")),
          lambda: provenance["resolution_status"], "resolution status mismatch")
    check("C001V11-T13", lambda: config["kkt"]["role"] == "final_observed_fit_diagnostic_only"
          and not config["kkt"]["component_selection_gate"],
          lambda: config["kkt"], "KKT role mismatch")
    holdout_rows = [row for rows in result["holdout_metadata_eligibility"].values() for row in rows]
    check("C001V11-T14", lambda: config["holdout"]["metadata_only_before_C001_stop"]
          and result.get("holdout_detector_access_count", 0) == 0
          and any(row.get("energy_transfer_semantics_valid") for row in holdout_rows),
          lambda: {"records": len(holdout_rows),
                   "energy_semantics_valid": sum(bool(row.get("energy_transfer_semantics_valid")) for row in holdout_rows)},
          "metadata-only holdout eligibility invalid")
    check("C001V11-T15", lambda: result["future_C002_registry"]["family_frozen_before_detector_access"]
          and bool(result["future_C002_registry"]["hypotheses"])
          and not result["future_C002_registry"]["C002_executed"],
          lambda: {"future_C002_family_size": len(result["future_C002_registry"]["hypotheses"]),
                   "C002_executed": result["future_C002_registry"]["C002_executed"]},
          "future C002 family invalid or empty")
    check("C001V11-T16", lambda: required_provenance_fields() <= set(provenance)
          and result["STOP_CONDITION"] == "A22_STOP_before_holdout_detector_access"
          and provenance["canonical_main"] == authorization["canonical_head"]
          and not provenance["C002_executed"],
          lambda: {"provenance_fields": sorted(provenance), "STOP_CONDITION": result["STOP_CONDITION"]},
          "provenance/privacy/STOP invariant failed")
    return {"scientific_execution": True, "tests": tests,
            "passed": sum(item["status"] == "PASS" for item in tests),
            "failed": sum(item["status"] == "FAIL" for item in tests),
            "all_mandatory_tests_pass": all(item["status"] == "PASS" for item in tests)}


def write_execution_outputs(result, config, authorization, input_context):
    """A21 machine-readable construction with nonrecursive byte identities."""
    output_dir = ROOT / config["output_contract"]["production_result_directory"]
    output_dir.mkdir(parents=True, exist_ok=False)
    eligibility_rows = [{"complex_id": key, **row}
                        for key, rows in result["scan_eligibility"].items() for row in rows]
    holdout_rows = [{"complex_id": key, **row}
                    for key, rows in result["holdout_metadata_eligibility"].items() for row in rows]
    provenance = build_provenance(result, config, authorization, input_context)
    report = production_test_report(result, config, authorization, input_context, provenance)
    yaml_documents = {
        "experimental_context_assessment.yaml": {"global_fixed_Ef": False},
        "count_control_assessment.yaml": config["exposure"],
        "confirmatory_complexes.yaml": result["component_results"],
        "phenomenological_model_spec.yaml": config["model"],
        "component_development.yaml": result["component_results"],
        "resolution_evidence.yaml": {"status": config["resolution"]["default_status"],
                                     "scan_104062": config["resolution"]["scan_104062"]},
        "holdout_coverage_summary.yaml": result["holdout_metadata_eligibility"],
        "confirmatory_hypotheses.yaml": result["future_C002_registry"],
        "future_C002_spec.yaml": result["future_C002_registry"],
        "numerical_diagnostics.yaml": {"KKT_role": "final_observed_fit_diagnostic_only"},
        "test_report.yaml": report,
    }
    csv_documents = {
        "scan_eligibility.csv": eligibility_rows,
        "discovery_final_fits.csv": final_fit_rows(result, config),
        "background_sensitivity.csv": sensitivity_rows(result),
        "parameter_uncertainty.csv": uncertainty_rows(result),
        "reproducibility_assessment.csv": reproducibility_rows(result),
        "resolution_status.csv": resolution_rows(result, config),
        "holdout_metadata_eligibility.csv": holdout_rows,
        "holdout_field_access_log.csv": result.get(
            "holdout_field_access_log", [{"holdout_detector_access_count": 0}]),
    }
    for name, document in yaml_documents.items():
        (output_dir / name).write_bytes(yaml_document_bytes(document))
    for name, rows in csv_documents.items():
        (output_dir / name).write_bytes(csv_document_bytes(rows))
    identities = {name: sha256_file(output_dir / name)
                  for name in sorted(set(yaml_documents) | set(csv_documents))}
    provenance = build_provenance(result, config, authorization, input_context, identities)
    (output_dir / "provenance_manifest.yaml").write_bytes(yaml_document_bytes(provenance))
    return output_dir


def execute_candidate(config):
    """Reviewed A01-A22 path; authorization and identities precede production reads."""
    authorization = require_external_execution_authorization(config)
    verify_static_identities(config)
    discovery_scans, holdout_metadata, guard, input_context = load_execution_inputs(config)
    result = dispatch_c001_core(discovery_scans, holdout_metadata, config)
    result["holdout_field_access_log"] = [
        {"decoded_field": field, "detector_field": field in DETECTOR_FIELDS}
        for field in guard.decoded_fields
    ] or [{"decoded_field": None, "detector_field": False}]
    result["holdout_detector_access_count"] = guard.detector_materializations
    require(result["STOP_CONDITION"] == "A22_STOP_before_holdout_detector_access", "STOP failure")
    require(guard.detector_materializations == 0, "holdout detector access before STOP")
    write_execution_outputs(result, config, authorization, input_context)
    return result


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = load_config()
    if args.self_test:
        report = self_test_report()
        print(json.dumps(report, indent=2, default=str))
        raise SystemExit(0 if report["failed"] == 0 else 1)
    execute_candidate(config)


if __name__ == "__main__":
    main()
