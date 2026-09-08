#!/usr/bin/env python3
"""C002 v1.0 internal-holdout confirmation executor.

The production path is fail-closed and cannot decode a holdout detector token
without a separate, exact Project Control authorization.  ``--self-test`` uses
only synthetic arrays, frozen metadata artifacts, and static identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import subprocess

import numpy as np
import yaml
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import qmc


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = "scripts/stage02r/c002_holdout_confirmation_config.yaml"
JOB_ID = "W02-02R-C-002"
SPEC_VERSION = "1.0"
SPEC_PATH = "03_Protocols/STAGE02R_T02R05_C002_EXECUTION_SPEC_V1_0.md"
SPEC_SHA256 = "49372420338753828be53bd4f04ca80369bc19951ad40b6223f9dc7a80f2a279"
DESIGN_FREEZE_MAIN = "122691ae7e69e40458509feec0dd2135aeb4108f"
C001_EXECUTION_BASELINE = "a8f5605177470d55de982227d9a9f36a7c801562"
FAMILY_PATH = "04_Results/Stage02R/W02-02R-C-001-v1.1/future_C002_spec.yaml"
FAMILY_SHA256 = "38fd01e53d539bc877a36f7cd8152faf372905ddf9ce68b1c3779874654f555b"
STOP_CONDITION = "C002_STOP_after_frozen_outputs_before_combined_reestimation_or_interpretation"
DETECTOR_FIELDS = frozenset({
    "detector", "detector_raw", "det_err", "det_err_raw", "detector_monitor_rate",
    "detector_time_rate", "spectral_residual", "residual",
})
EXPECTED_MEMBERSHIP = {
    "C002-CX-01-K0-K1": (
        "SCAN-02R-26cdfd757f62fb5b", "SCAN-02R-41d12941c2dac178",
        "SCAN-02R-42d0a4d8bd2d58cc", "SCAN-02R-4650765ebe11f415",
        "SCAN-02R-48f6ae0dc1c99d07", "SCAN-02R-54bfea84553b4c65",
        "SCAN-02R-58a76874c3967085", "SCAN-02R-5e02dde1da14be55",
        "SCAN-02R-79960ffd3b8a968b", "SCAN-02R-87edbdf74d1e5fb1",
        "SCAN-02R-a1d82bdc331e2df4", "SCAN-02R-b14e49e20117cb08",
        "SCAN-02R-c74434b3ed5fc9b8",
    ),
    "C002-CX-02-K0-K1": (
        "SCAN-02R-42d0a4d8bd2d58cc", "SCAN-02R-48f6ae0dc1c99d07",
        "SCAN-02R-54bfea84553b4c65", "SCAN-02R-58a76874c3967085",
        "SCAN-02R-5e02dde1da14be55", "SCAN-02R-5f553db9674e6d45",
        "SCAN-02R-79960ffd3b8a968b", "SCAN-02R-87edbdf74d1e5fb1",
        "SCAN-02R-a1d82bdc331e2df4", "SCAN-02R-b14e49e20117cb08",
        "SCAN-02R-baae22000a534323", "SCAN-02R-c74434b3ed5fc9b8",
    ),
    "C002-CX-03-K0-K1": (
        "SCAN-02R-42d0a4d8bd2d58cc", "SCAN-02R-5f553db9674e6d45",
        "SCAN-02R-a1d82bdc331e2df4", "SCAN-02R-a88a59b9d2315a05",
        "SCAN-02R-baae22000a534323",
    ),
}


class ConformanceError(RuntimeError):
    """A frozen identity, access, numerical, or output invariant failed."""


def require(condition, message):
    if not condition:
        raise ConformanceError(message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def yaml_load(path):
    return yaml.load(Path(path).read_bytes(), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


def load_config():
    return yaml_load(ROOT / CONFIG_PATH)


def git_head():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True).stdout.strip()


def load_family(config):
    return yaml_load(ROOT / config["frozen_family"]["path"])


def verify_family(family, config):
    require(family.get("family_frozen_before_detector_access") is True, "family not frozen")
    hypotheses = family.get("hypotheses", [])
    require(len(hypotheses) == 3, "family size")
    require([item.get("hypothesis_id") for item in hypotheses] == sorted(EXPECTED_MEMBERSHIP),
            "family order or identity")
    for item in hypotheses:
        hypothesis_id = item["hypothesis_id"]
        require(tuple(item.get("eligible_holdout_scan_ids", [])) == EXPECTED_MEMBERSHIP[hypothesis_id],
                f"eligible membership {hypothesis_id}")
        require(item.get("parent_K") == 0 and item.get("child_K") == 1,
                f"model levels {hypothesis_id}")
        require(item.get("hypothesis_type") == "presence", f"hypothesis type {hypothesis_id}")
        require(item.get("bootstrap_replicates") == 4096, f"bootstrap B {hypothesis_id}")
        require(item.get("rng") == "numpy.random.PCG64"
                and item.get("bootstrap_design") == "fixed"
                and item.get("adaptive_extension") == "forbidden"
                and item.get("p_value_convention") == "plus_one",
                f"bootstrap policy {hypothesis_id}")
        require(item.get("background_family") == "B1_log_linear"
                and item.get("component_family") == "observed_unit_area_Gaussian"
                and item.get("parameter_domain_rules") == config["model"]["parameter_domains"],
                f"model policy {hypothesis_id}")
        require(item.get("Holm_global_alpha") == 0.05
                and item.get("multiplicity_rule", {}).get("procedure") == "Holm",
                f"multiplicity policy {hypothesis_id}")
        require(item.get("resolution_status") == "resolution_not_established",
                f"resolution {hypothesis_id}")
    require(family.get("Holm_global_alpha") == 0.05
            and family.get("Holm_ordering") == {
                "primary_sort": {"raw_p_value": "ascending"},
                "tie_break": {"hypothesis_id": "lexical_ascending"}}
            and family.get("C002_executed") is False, "global family policy")
    require(config["frozen_family"]["eligible_scan_counts"] ==
            {key: len(value) for key, value in EXPECTED_MEMBERSHIP.items()}, "configured membership counts")
    return True


def upstream_scan_points_identity(config):
    provenance = yaml_load(ROOT / config["input_artifacts"]["a002_provenance"]["path"])
    matches = [item for item in provenance.get("outputs", [])
               if item.get("path") == config["input_artifacts"]["scan_points"]["path"]]
    require(len(matches) == 1, "scan_points upstream identity missing")
    return matches[0].get("byte_sha256")


def verify_static_identities(config):
    spec = config["execution_specification"]
    require(spec["version"] == SPEC_VERSION and spec["path"] == SPEC_PATH,
            "execution specification configuration")
    require(spec["sha256"] == SPEC_SHA256 and sha256_file(ROOT / SPEC_PATH) == SPEC_SHA256,
            "execution specification identity")
    require(spec["design_freeze_main"] == DESIGN_FREEZE_MAIN, "design freeze identity")
    require(spec["c001_execution_baseline"] == C001_EXECUTION_BASELINE, "C001 baseline identity")
    frozen = config["frozen_family"]
    require(frozen["path"] == FAMILY_PATH and frozen["sha256"] == FAMILY_SHA256,
            "family configuration identity")
    require(sha256_file(ROOT / FAMILY_PATH) == FAMILY_SHA256, "family byte identity")
    for key, item in config["input_artifacts"].items():
        if key == "scan_points":
            continue
        require(sha256_file(ROOT / item["path"]) == item["sha256"], f"input identity {key}")
    expected_points = config["input_artifacts"]["scan_points"]["sha256_from_upstream_manifest"]
    require(upstream_scan_points_identity(config) == expected_points, "scan_points upstream identity")
    verify_family(load_family(config), config)
    return True


def validate_authorization_document(document, config, source_sha256, config_sha256, head):
    require(isinstance(document, dict), "C002 external authorization missing")
    required = {
        "job_id": JOB_ID,
        "execution_specification_version": SPEC_VERSION,
        "execution_specification_sha256": SPEC_SHA256,
        "future_C002_spec_sha256": FAMILY_SHA256,
        "implementation_source_sha256": source_sha256,
        "implementation_config_sha256": config_sha256,
        "canonical_head": head,
        "C002_execution_authorized": True,
        "holdout_detector_access_authorized": True,
    }
    for key, expected in required.items():
        require(document.get(key) == expected, f"authorization mismatch: {key}")
    require(config["authorization"]["C002_execution_authorized"] is False,
            "candidate config self-authorizes C002")
    require(config["authorization"]["holdout_detector_access_authorized"] is False,
            "candidate config self-authorizes detector access")
    return document


def require_external_authorization(config):
    path = ROOT / config["authorization"]["external_authorization_path"]
    require(path.is_file(), "C002 external authorization absent")
    return validate_authorization_document(
        yaml_load(path), config, sha256_file(Path(__file__)),
        sha256_file(ROOT / CONFIG_PATH), git_head())


class HoldoutAccessGuard:
    """Append-only allowlist audit; denial always precedes token decoding."""

    def __init__(self, family, authorization_valid=False):
        self.membership = {item["hypothesis_id"]: frozenset(item["eligible_holdout_scan_ids"])
                           for item in family["hypotheses"]}
        self.authorization_valid = authorization_valid
        self._log = []
        self.detector_materializations = 0

    @property
    def log(self):
        return tuple(dict(item) for item in self._log)

    def _append(self, **entry):
        self._log.append({"event_index": len(self._log) + 1, **entry})

    def authorize_detector(self, hypothesis_id, scan_id, field):
        allowed = (self.authorization_valid and hypothesis_id in self.membership
                   and scan_id in self.membership[hypothesis_id]
                   and field == "detector_raw")
        self._append(event="field_request", hypothesis_id=hypothesis_id,
                     scan_id=scan_id, field=field, allowed=allowed)
        if not allowed:
            raise ConformanceError("holdout detector request denied before decode")

    def record_detector_decode(self, hypothesis_id, scan_id, field, point_index):
        require(self.authorization_valid and field == "detector_raw"
                and scan_id in self.membership.get(hypothesis_id, ()),
                "detector decode without authorization")
        self.detector_materializations += 1
        self._append(event="field_decode", hypothesis_id=hypothesis_id, scan_id=scan_id,
                     field=field, point_index=point_index, allowed=True)


@dataclass(frozen=True)
class ScanData:
    scan_id: str
    point_indices: tuple
    energy: np.ndarray
    exposure: np.ndarray
    counts: np.ndarray


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
        return (self.theta is not None and self.optimizer_success and self.expectations_valid
                and self.domains_valid and math.isfinite(self.log_likelihood))


def block_layout(component_count):
    return {"background": slice(0, 2), "areas": slice(2, 2 + component_count),
            "eta": slice(2 + component_count, 2 + 2 * component_count),
            "widths": slice(2 + 2 * component_count, 2 + 3 * component_count)}


def free_parameters(component_count):
    return 2 + 3 * component_count


def joint_layout(scans, component_count):
    size = free_parameters(component_count)
    return [slice(index * size, (index + 1) * size) for index in range(len(scans))]


def softmax_gaps(eta):
    extended = np.append(np.asarray(eta, dtype=float), 0.0)
    shifted = extended - np.max(extended)
    weights = np.exp(shifted)
    return weights / np.sum(weights)


def ordered_centroids(eta, lower, upper):
    return lower + (upper - lower) * np.cumsum(softmax_gaps(eta)[:-1])


def gaussian_unit_area(energy, centroid, fwhm):
    require(fwhm > 0.0, "nonpositive observed FWHM")
    sigma = fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    return np.exp(-0.5 * ((energy - centroid) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def block_expectation(theta, scan, union, component_count):
    theta = np.asarray(theta, dtype=float)
    layout = block_layout(component_count)
    span = float(np.max(scan.energy) - np.min(scan.energy))
    if not math.isfinite(span) or span <= 0.0:
        return np.full_like(scan.energy, np.nan)
    x_value = 2.0 * (scan.energy - np.min(scan.energy)) / span - 1.0
    background_log = theta[0] + theta[1] * x_value
    if not np.isfinite(background_log).all() or np.max(background_log) > 700.0:
        return np.full_like(scan.energy, np.nan)
    rate = np.exp(background_log)
    if component_count:
        centroids = ordered_centroids(theta[layout["eta"]], union[0], union[1])
        if not (np.isfinite(centroids).all() and union[0] < centroids[0] < union[1]):
            return np.full_like(scan.energy, np.nan)
        for area, centroid, width in zip(theta[layout["areas"]], centroids,
                                         theta[layout["widths"]]):
            if area < 0.0 or width <= 0.0:
                return np.full_like(scan.energy, np.nan)
            rate += area * gaussian_unit_area(scan.energy, centroid, width)
    return scan.exposure * rate


def block_nll(theta, scan, union, component_count):
    means = block_expectation(theta, scan, union, component_count)
    if not np.isfinite(means).all() or np.any(means <= 0.0):
        return float("inf")
    return float(np.sum(means - scan.counts * np.log(means) + gammaln(scan.counts + 1.0)))


def joint_nll(theta, scans, union, component_count):
    return sum(block_nll(theta[section], scan, union, component_count)
               for scan, section in zip(scans, joint_layout(scans, component_count)))


def baseline_block(scan, union, component_count):
    rate = (float(np.sum(scan.counts)) + 0.5) / float(np.sum(scan.exposure))
    values = [math.log(max(rate, np.finfo(float).tiny)), 0.0]
    if component_count:
        values.extend([max(rate * (union[1] - union[0]), np.finfo(float).eps),
                       0.0, max(0.1 * (union[1] - union[0]), np.finfo(float).eps)])
    return np.asarray(values, dtype=float)


def baseline_joint(scans, union, component_count):
    return np.concatenate([baseline_block(scan, union, component_count) for scan in scans])


def physical_bounds(scans, component_count):
    block = [(None, None), (None, None)]
    if component_count:
        block += [(0.0, None), (None, None), (np.finfo(float).tiny, None)]
    return block * len(scans)


def observed_start_bank(scans, union, component_count):
    baseline = baseline_joint(scans, union, component_count)
    bank = qmc.Sobol(d=len(baseline), scramble=False).random_base2(m=4)
    starts = [baseline]
    size = free_parameters(component_count)
    layout = block_layout(component_count)
    for row in bank[:15]:
        candidate = baseline.copy()
        for scan_index in range(len(scans)):
            section = slice(scan_index * size, (scan_index + 1) * size)
            local = candidate[section]
            coordinates = row[section]
            local[layout["background"]] += 4.0 * (2.0 * coordinates[layout["background"]] - 1.0)
            if component_count:
                local[layout["areas"]] *= np.exp(4.0 * (2.0 * coordinates[layout["areas"]] - 1.0))
                local[layout["eta"]] = 8.0 * coordinates[layout["eta"]] - 4.0
                local[layout["widths"]] = (union[1] - union[0]) * (
                    0.02 + 0.98 * coordinates[layout["widths"]])
        starts.append(candidate)
    require(len(starts) == 16, "observed start bank")
    return starts


def domains_satisfied(theta, bounds):
    for value, (lower, upper) in zip(theta, bounds):
        if (not math.isfinite(float(value)) or (lower is not None and value < lower)
                or (upper is not None and value > upper)):
            return False
    return True


def fit_one_start(scans, union, component_count, start, start_index, config):
    bounds = physical_bounds(scans, component_count)
    objective = lambda theta: joint_nll(theta, scans, union, component_count)
    try:
        result = minimize(objective, np.asarray(start, dtype=float), method="L-BFGS-B",
                          bounds=bounds, options=config["observed_optimizer"]["options"])
    except (FloatingPointError, ValueError):
        return Candidate(start_index, None, float("-inf"), False, False, False, 0)
    theta = np.asarray(result.x, dtype=float)
    means = [block_expectation(theta[section], scan, union, component_count)
             for scan, section in zip(scans, joint_layout(scans, component_count))]
    valid_means = all(np.isfinite(value).all() and np.all(value > 0.0) for value in means)
    value = objective(theta)
    return Candidate(start_index, theta, -float(value), bool(result.success), valid_means,
                     domains_satisfied(theta, bounds), int(result.nit))


def projected_gradient_max(theta, scans, union, component_count):
    """Final-fit diagnostic only; it never changes or gates fitted parameters."""
    theta = np.asarray(theta, dtype=float)
    bounds = physical_bounds(scans, component_count)
    objective = lambda vector: joint_nll(vector, scans, union, component_count)
    derivatives = []
    baseline = objective(theta)
    for index, value in enumerate(theta):
        step = 1.0e-6 * max(1.0, abs(float(value)))
        lower, upper = bounds[index]
        forward = upper is None or value + step <= upper
        backward = lower is None or value - step >= lower
        if forward and backward:
            plus, minus = theta.copy(), theta.copy()
            plus[index] += step; minus[index] -= step
            derivative = (objective(plus) - objective(minus)) / (2.0 * step)
        elif forward:
            plus = theta.copy(); plus[index] += step
            derivative = (objective(plus) - baseline) / step
        elif backward:
            minus = theta.copy(); minus[index] -= step
            derivative = (baseline - objective(minus)) / step
        else:
            derivative = float("inf")
        if lower is not None and abs(value - lower) <= 1.0e-8 * max(1.0, abs(float(value)), abs(lower)) and derivative >= 0.0:
            derivative = 0.0
        if upper is not None and abs(value - upper) <= 1.0e-8 * max(1.0, abs(float(value)), abs(upper)) and derivative <= 0.0:
            derivative = 0.0
        derivatives.append(float(derivative))
    return float(np.max(np.abs(derivatives)))


def compare_candidates(left, right, config):
    tolerance = config["observed_optimizer"]["deterministic_tie_absolute_likelihood_tolerance"]
    difference = left.log_likelihood - right.log_likelihood
    if abs(difference) > tolerance:
        return -1 if difference > 0.0 else 1
    decimals = config["observed_optimizer"]["deterministic_tie_parameter_round_decimals"]
    left_vector, right_vector = tuple(np.round(left.theta, decimals)), tuple(np.round(right.theta, decimals))
    return -1 if left_vector < right_vector else (1 if left_vector > right_vector else 0)


def best_candidate(candidates, config):
    valid = [candidate for candidate in candidates if candidate.valid]
    return (None if not valid else
            sorted(valid, key=cmp_to_key(lambda a, b: compare_candidates(a, b, config)))[0])


def solution_reproduced(candidates, config):
    best = best_candidate(candidates, config)
    if best is None:
        return False
    tolerance = config["observed_optimizer"]["reproduction_relative_likelihood_tolerance"]
    matching = {candidate.start_index for candidate in candidates if candidate.valid and
                abs(candidate.log_likelihood - best.log_likelihood)
                <= tolerance * max(1.0, abs(best.log_likelihood))}
    return len(matching) >= config["observed_optimizer"]["reproduction_required_distinct_starts"]


def observed_fit(scans, union, component_count, config, fit_function=fit_one_start):
    bank = observed_start_bank(scans, union, component_count)
    candidates = [fit_function(scans, union, component_count, bank[index], index + 1, config)
                  for index in range(8)]
    reproduced = solution_reproduced(candidates, config)
    if not reproduced:
        candidates.extend(fit_function(scans, union, component_count, bank[index], index + 1, config)
                          for index in range(8, 16))
        reproduced = solution_reproduced(candidates, config)
    best = best_candidate(candidates, config)
    return {"fit_status": "valid" if best is not None else "numerical_failure",
            "failure_reason": None if best is not None else "no_valid_optimizer_candidate",
            "theta": None if best is None else best.theta,
            "log_likelihood": None if best is None else best.log_likelihood,
            "start_count": len(candidates),
            "optimizer_stability_status": "stable" if reproduced else "unresolved",
            "projected_gradient_max": (None if best is None else projected_gradient_max(
                best.theta.copy(), scans, union, component_count)),
            "KKT_role": "final_observed_fit_diagnostic_only"}


def bootstrap_start_bank(scans, union, component_count, observed_theta, config):
    baseline = baseline_joint(scans, union, component_count)
    positive, negative = baseline.copy(), baseline.copy()
    size = free_parameters(component_count)
    layout = block_layout(component_count)
    for scan_index in range(len(scans)):
        section = slice(scan_index * size, (scan_index + 1) * size)
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
    require(len(starts) == config["bootstrap"]["model_local_starts"] == 4,
            "bootstrap model-local starts")
    return starts


def bootstrap_fit(scans, union, component_count, observed_theta, config):
    candidates = [fit_one_start(scans, union, component_count, start, index + 1, config)
                  for index, start in enumerate(bootstrap_start_bank(
                      scans, union, component_count, observed_theta, config))]
    best = best_candidate(candidates, config)
    return {"fit_status": "valid" if best is not None else "numerical_failure",
            "failure_reason": None if best is not None else "no_valid_bootstrap_candidate",
            "theta": None if best is None else best.theta,
            "log_likelihood": None if best is None else best.log_likelihood,
            "start_count": 4}


def bootstrap_statistic(parent_fit, child_fit):
    if parent_fit["fit_status"] != "valid" or child_fit["fit_status"] != "valid":
        return float("inf")
    return 2.0 * (child_fit["log_likelihood"] - parent_fit["log_likelihood"])


def seed_payload(hypothesis_id):
    payload = {"job_id": JOB_ID, "c002_execution_spec_version": SPEC_VERSION,
               "c002_execution_spec_freeze_main": DESIGN_FREEZE_MAIN,
               "c001_execution_baseline": C001_EXECUTION_BASELINE,
               "future_C002_spec_sha256": FAMILY_SHA256,
               "hypothesis_id": hypothesis_id, "bootstrap_replicates": 4096,
               "rng": "numpy.random.PCG64"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = sha256_bytes(canonical.encode("utf-8"))
    return canonical, digest, int(digest, 16)


def plus_one_p_value(statistics, observed, replicate_count=4096):
    require(len(statistics) == replicate_count, "bootstrap replicate count")
    return float((1 + np.sum(np.asarray(statistics) >= observed)) / (replicate_count + 1))


def run_hypothesis(hypothesis, scans, config, replicate_count=4096):
    require(replicate_count == config["bootstrap"]["replicates"], "adaptive bootstrap forbidden")
    union = config["complexes"][hypothesis["complex_id"]]["frozen_union_meV"]
    parent = observed_fit(scans, union, 0, config)
    child = observed_fit(scans, union, 1, config)
    canonical, seed_hash, seed_integer = seed_payload(hypothesis["hypothesis_id"])
    observed_numerically_valid = (parent["fit_status"] == "valid"
                                  and child["fit_status"] == "valid"
                                  and parent["optimizer_stability_status"] == "stable"
                                  and child["optimizer_stability_status"] == "stable")
    if not observed_numerically_valid:
        return {"hypothesis_id": hypothesis["hypothesis_id"], "complex_id": hypothesis["complex_id"],
                "exact_eligible_holdout_scan_ids": hypothesis["eligible_holdout_scan_ids"],
                "observed_parent_fit": parent, "observed_child_fit": child, "T_observed": None,
                "bootstrap_replicates": 4096, "bootstrap_completed_replicates": 0,
                "seed_payload_canonical_json": canonical, "seed_sha256": seed_hash,
                "bootstrap_failed_replicates": 0, "bootstrap_statistics": [],
                "raw_p_value": 1.0, "test_status": "numerical_failure"}
    observed = bootstrap_statistic(parent, child)
    rng = np.random.Generator(np.random.PCG64(seed_integer))
    means = [block_expectation(parent["theta"][section], scan, union, 0)
             for scan, section in zip(scans, joint_layout(scans, 0))]
    statistics, failures = [], []
    for replicate in range(1, replicate_count + 1):
        simulated = [ScanData(scan.scan_id, scan.point_indices, scan.energy, scan.exposure,
                              rng.poisson(mean).astype(float)) for scan, mean in zip(scans, means)]
        parent_boot = bootstrap_fit(simulated, union, 0, parent["theta"], config)
        child_boot = bootstrap_fit(simulated, union, 1, child["theta"], config)
        statistic = bootstrap_statistic(parent_boot, child_boot)
        if math.isinf(statistic):
            failures.append({"hypothesis_id": hypothesis["hypothesis_id"],
                             "bootstrap_replicate": replicate,
                             "parent_fit_status": parent_boot["fit_status"],
                             "child_fit_status": child_boot["fit_status"],
                             "failure_reason": "parent_or_child_numerical_failure",
                             "parent_start_count": parent_boot["start_count"],
                             "child_start_count": child_boot["start_count"]})
        statistics.append(statistic)
    return {"hypothesis_id": hypothesis["hypothesis_id"], "complex_id": hypothesis["complex_id"],
            "exact_eligible_holdout_scan_ids": hypothesis["eligible_holdout_scan_ids"],
            "observed_parent_fit": parent, "observed_child_fit": child, "T_observed": observed,
            "bootstrap_replicates": 4096, "bootstrap_completed_replicates": len(statistics),
            "seed_payload_canonical_json": canonical, "seed_sha256": seed_hash,
            "bootstrap_failed_replicates": len(failures), "bootstrap_failures": failures,
            "bootstrap_statistics": statistics,
            "raw_p_value": plus_one_p_value(statistics, observed), "test_status": "numerically_valid"}


def holm_decisions(results, alpha=0.05):
    require(len(results) == 3 and {item["hypothesis_id"] for item in results} == set(EXPECTED_MEMBERSHIP),
            "Holm family mutation")
    ordered = sorted(results, key=lambda item: (item["raw_p_value"], item["hypothesis_id"]))
    stopped = False
    decisions = []
    for rank, item in enumerate(ordered, 1):
        threshold = alpha / (3 - rank + 1)
        rejected = (not stopped and item["raw_p_value"] <= threshold)
        if not rejected:
            stopped = True
        numerical_valid = item["test_status"] != "numerical_failure"
        semantics = ("numerical_failure" if not numerical_valid else
                     "presence_confirmed_internal_holdout" if rejected else
                     "presence_not_confirmed")
        decisions.append({"hypothesis_id": item["hypothesis_id"], "raw_p_value": item["raw_p_value"],
                          "Holm_rank": rank, "Holm_threshold": threshold,
                          "Holm_rejected": rejected, "test_status": item["test_status"],
                          "scientific_result_semantics": semantics})
    return decisions


def projected_csv(path, fields, selected_scan_ids):
    selected = tuple(fields)
    selected_ids = frozenset(selected_scan_ids)
    rows = []
    with Path(path).open("rb") as stream:
        header = stream.readline().rstrip(b"\r\n").decode("utf-8-sig").split(",")
        require(set(selected) <= set(header), "metadata field absent")
        indices = {field: header.index(field) for field in selected}
        sid_index = header.index("scan_record_id")
        for raw_line in stream:
            require(b'"' not in raw_line, "quoted CSV unsupported")
            line = raw_line.rstrip(b"\r\n")
            delimiters = [-1] + [index for index, value in enumerate(line) if value == 44] + [len(line)]
            require(len(delimiters) == len(header) + 1, "CSV row width")
            token = lambda index: line[delimiters[index] + 1:delimiters[index + 1]]
            scan_id = token(sid_index).decode("utf-8-sig")
            if scan_id in selected_ids:
                rows.append({field: token(index).decode("utf-8-sig")
                             for field, index in indices.items()})
    return rows


def metadata_fit_windows(family, config):
    all_ids = sorted({scan_id for values in EXPECTED_MEMBERSHIP.values() for scan_id in values})
    fields = ("scan_record_id", "point_index", "e_raw", "monitor_raw", "time_raw")
    rows = projected_csv(ROOT / config["input_artifacts"]["scan_points"]["path"], fields, all_ids)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["scan_record_id"], []).append(row)
    windows = {}
    for hypothesis in family["hypotheses"]:
        hypothesis_id = hypothesis["hypothesis_id"]
        union = config["complexes"][hypothesis["complex_id"]]["frozen_union_meV"]
        exposure_classes = hypothesis["exposure_class_per_scan"]
        windows[hypothesis_id] = {}
        for scan_id in hypothesis["eligible_holdout_scan_ids"]:
            source = grouped.get(scan_id, [])
            energy = np.asarray([float(row["e_raw"]) for row in source])
            order = np.argsort(energy)
            source = [source[index] for index in order]
            energy = energy[order]
            lower = np.flatnonzero(energy < union[0])
            inside = np.flatnonzero((energy >= union[0]) & (energy <= union[1]))
            upper = np.flatnonzero(energy > union[1])
            require(len(lower) >= 2 and len(inside) >= 3 and len(upper) >= 2,
                    f"frozen metadata window {hypothesis_id} {scan_id}")
            chosen = np.concatenate((lower[-2:], inside, upper[:2]))
            exposure_class = exposure_classes[scan_id]
            exposure_field = config["metadata_window"]["exposure_by_class"].get(exposure_class)
            require(exposure_field is not None, "unknown exposure class")
            exposure = np.asarray([float(source[index][exposure_field]) for index in chosen])
            require(np.isfinite(exposure).all() and np.all(exposure > 0.0), "invalid exposure")
            windows[hypothesis_id][scan_id] = {
                "point_indices": tuple(source[index]["point_index"] for index in chosen),
                "energy": energy[chosen], "exposure": exposure,
            }
    return windows


def detector_counts_for_windows(hypothesis_id, windows, config, guard, data=None, decoder=None):
    for scan_id in windows:
        guard.authorize_detector(hypothesis_id, scan_id, "detector_raw")
    path = ROOT / config["input_artifacts"]["scan_points"]["path"]
    stream = io.BytesIO(data) if data is not None else path.open("rb")
    decode = decoder or (lambda token: float(token.decode("utf-8-sig")))
    required = {(scan_id, point_index) for scan_id, record in windows.items()
                for point_index in record["point_indices"]}
    counts = {scan_id: {} for scan_id in windows}
    with stream:
        header = stream.readline().rstrip(b"\r\n").decode("utf-8-sig").split(",")
        sid_index, point_index, detector_index = (header.index("scan_record_id"),
                                                   header.index("point_index"),
                                                   header.index("detector_raw"))
        for raw_line in stream:
            line = raw_line.rstrip(b"\r\n")
            delimiters = [-1] + [index for index, value in enumerate(line) if value == 44] + [len(line)]
            token = lambda index: line[delimiters[index] + 1:delimiters[index + 1]]
            scan_id = token(sid_index).decode("utf-8-sig")
            index_value = token(point_index).decode("utf-8-sig")
            if (scan_id, index_value) in required:
                value = decode(token(detector_index))
                guard.record_detector_decode(hypothesis_id, scan_id, "detector_raw", index_value)
                counts[scan_id][index_value] = value
    require(sum(len(item) for item in counts.values()) == len(required), "detector window incomplete")
    return counts


def build_scan_data(hypothesis_id, windows, counts):
    scans = []
    for scan_id, record in windows[hypothesis_id].items():
        values = np.asarray([counts[scan_id][index] for index in record["point_indices"]], dtype=float)
        require(np.isfinite(values).all() and np.all(values >= 0.0), "invalid raw counts")
        scans.append(ScanData(scan_id, record["point_indices"], record["energy"],
                              record["exposure"], values))
    return scans


def decode_fit_parameters(fit, scans, union, component_count):
    if fit.get("theta") is None:
        return None
    records = []
    for scan, section in zip(scans, joint_layout(scans, component_count)):
        local = fit["theta"][section]
        entry = {"scan_id": scan.scan_id, "b0": float(local[0]), "b1": float(local[1])}
        if component_count:
            layout = block_layout(component_count)
            entry.update({"integrated_area": float(local[layout["areas"]][0]),
                          "centroid": float(ordered_centroids(local[layout["eta"]], *union)[0]),
                          "observed_fwhm": float(local[layout["widths"]][0])})
        records.append(entry)
    return records


def serializable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def csv_bytes(rows):
    rows = list(rows)
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows or [{"status": "not_applicable"}]:
        writer.writerow({key: json.dumps(row.get(key), default=serializable, sort_keys=True,
                                         separators=(",", ":"))
                         if isinstance(row.get(key), (dict, list, tuple, np.ndarray))
                         else row.get(key) for key in fields})
    return stream.getvalue().encode("utf-8")


def yaml_bytes(document):
    plain = json.loads(json.dumps(document, default=serializable))
    return yaml.safe_dump(plain, sort_keys=False).encode("utf-8")


def output_rows(results, decisions, scans_by_hypothesis, config):
    observed_rows, bootstrap_rows = [], []
    for result in results:
        hypothesis_id = result["hypothesis_id"]
        union = config["complexes"][result["complex_id"]]["frozen_union_meV"]
        scans = scans_by_hypothesis[hypothesis_id]
        for model_id, count, key in (("K0", 0, "observed_parent_fit"),
                                     ("K1", 1, "observed_child_fit")):
            fit = result[key]
            observed_rows.append({"hypothesis_id": hypothesis_id, "model_id": model_id,
                                  "fit_status": fit["fit_status"],
                                  "failure_reason": fit.get("failure_reason"),
                                  "log_likelihood": fit.get("log_likelihood"),
                                  "start_count": fit["start_count"],
                                  "optimizer_stability_status": fit["optimizer_stability_status"],
                                  "KKT_role": fit["KKT_role"],
                                  "scan_specific_parameters": decode_fit_parameters(
                                      fit, scans, union, count)})
        bootstrap_rows.append({key: result.get(key) for key in (
            "hypothesis_id", "T_observed", "bootstrap_replicates",
            "bootstrap_completed_replicates", "seed_payload_canonical_json", "seed_sha256",
            "bootstrap_failed_replicates", "raw_p_value", "test_status",
            "exact_eligible_holdout_scan_ids")})
    membership = {result["hypothesis_id"]: result["exact_eligible_holdout_scan_ids"]
                  for result in results}
    decision_rows = [{**decision,
                      "exact_eligible_holdout_scan_ids": membership[decision["hypothesis_id"]]}
                     for decision in decisions]
    return observed_rows, bootstrap_rows, decision_rows


def build_provenance(config, authorization, family, guard, output_identities=None):
    inputs = {"execution_specification": {"path": SPEC_PATH, "sha256": SPEC_SHA256},
              "future_C002_spec": {"path": FAMILY_PATH, "sha256": FAMILY_SHA256}}
    for key, value in config["input_artifacts"].items():
        digest = (value.get("sha256") or value.get("sha256_from_upstream_manifest"))
        inputs[key] = {"path": value["path"], "sha256": digest}
    return {"canonical_main": authorization["canonical_head"],
            "design_freeze_main": DESIGN_FREEZE_MAIN,
            "c001_execution_baseline": C001_EXECUTION_BASELINE,
            "future_C002_spec_path": FAMILY_PATH, "future_C002_spec_sha256": FAMILY_SHA256,
            "source_sha256": authorization["implementation_source_sha256"],
            "config_sha256": authorization["implementation_config_sha256"],
            "family_size": 3, "family_members": sorted(EXPECTED_MEMBERSHIP),
            "Holm_global_alpha": 0.05,
            "family_membership": {key: list(value) for key, value in EXPECTED_MEMBERSHIP.items()},
            "input_artifact_identities": inputs,
            "output_artifact_identities": output_identities or {},
            "output_identity_policy": {"algorithm": "sha256_of_final_file_bytes",
                                       "provenance_manifest.yaml": "excluded_to_avoid_recursive_self_hash"},
            "field_access_log": {"artifact": "holdout_field_access_log.csv",
                                 "events": len(guard.log),
                                 "detector_materializations": guard.detector_materializations},
            "test_report": {"artifact": "test_report.yaml", "mandatory_tests": "C002-T01..C002-T13"},
            "C002_executed": True, "holdout_detector_access_count": guard.detector_materializations,
            "resolution_status": "resolution_not_established",
            "physical_assignment_performed": False, "spectral_completeness_claim": "forbidden",
            "STOP_CONDITION": STOP_CONDITION}


def test_runner(config, runtime=None):
    tests = []
    family = load_family(config)
    def test(test_id, function):
        try:
            evidence = function()
            tests.append({"test_id": test_id, "status": "PASS", "evidence": evidence, "reason": None})
        except Exception as error:
            tests.append({"test_id": test_id, "status": "FAIL", "evidence": None,
                          "reason": f"{type(error).__name__}: {error}"})

    def t01():
        verify_static_identities(config)
        return {"spec_sha256": SPEC_SHA256, "family_sha256": FAMILY_SHA256,
                "source_sha256": sha256_file(Path(__file__)),
                "config_sha256": sha256_file(ROOT / CONFIG_PATH)}
    def t02():
        verify_family(family, config)
        return {"family_members": sorted(EXPECTED_MEMBERSHIP)}
    def t03():
        verify_family(family, config)
        return {key: len(value) for key, value in EXPECTED_MEMBERSHIP.items()}
    def t04():
        guard = HoldoutAccessGuard(family, authorization_valid=False)
        decoded = []
        data = b"scan_record_id,point_index,detector_raw\nSCAN-02R-26cdfd757f62fb5b,0,999\n"
        denied = False
        try:
            detector_counts_for_windows("C002-CX-01-K0-K1",
                {"SCAN-02R-26cdfd757f62fb5b": {"point_indices": ("0",)}}, config,
                guard, data=data, decoder=lambda token: decoded.append(token) or float(token))
        except ConformanceError:
            denied = True
        require(denied and not decoded and guard.detector_materializations == 0, "preauthorization decode")
        authorized = HoldoutAccessGuard(family, authorization_valid=True)
        for hypothesis_id, scan_id, field in (("C002-CX-01-K0-K1", "NOT-A-MEMBER", "detector_raw"),
                                               ("C002-CX-01-K0-K1", EXPECTED_MEMBERSHIP["C002-CX-01-K0-K1"][0], "det_err_raw")):
            try:
                authorized.authorize_detector(hypothesis_id, scan_id, field)
            except ConformanceError:
                continue
            raise ConformanceError("non-family scan/field allowed")
        allowed_scan = EXPECTED_MEMBERSHIP["C002-CX-01-K0-K1"][0]
        synthetic_counts = detector_counts_for_windows("C002-CX-01-K0-K1",
            {allowed_scan: {"point_indices": ("0",)}}, config, authorized,
            data=(f"scan_record_id,point_index,detector_raw\n{allowed_scan},0,7\n").encode("ascii"))
        require(synthetic_counts[allowed_scan]["0"] == 7.0
                and authorized.detector_materializations == 1, "authorized synthetic decode audit")
        if runtime is not None:
            runtime_guard = runtime["guard"]
            require(runtime_guard.authorization_valid and runtime_guard.detector_materializations > 0
                    and all(item.get("allowed") is True for item in runtime_guard.log),
                    "runtime access audit")
        return {"authorization_denied_before_decode": True, "detector_materializations": 0,
                "synthetic_authorized_materializations": 1,
                "audit_events": len(guard.log) + len(authorized.log),
                "runtime_access_events": None if runtime is None else len(runtime["guard"].log)}
    def t05():
        scan1, scan2 = synthetic_scans()
        theta = baseline_joint([scan1, scan2], [-1.0, 1.0], 1)
        separate = block_nll(theta[:5], scan1, [-1.0, 1.0], 1) + block_nll(
            theta[5:], scan2, [-1.0, 1.0], 1)
        require(abs(joint_nll(theta, [scan1, scan2], [-1.0, 1.0], 1) - separate) < 1e-12,
                "factorized likelihood")
        return {"factorized_joint_likelihood": True, "parent_K": 0, "child_K": 1}
    def t06():
        scan = synthetic_scans()[0]
        fit = observed_fit([scan], [-1.0, 1.0], 0, config)
        require(fit["start_count"] in (8, 16), "8 to 16 policy")
        require(config["observed_optimizer"]["method"] == "L-BFGS-B"
                and config["observed_optimizer"]["post_optimizer_polishing"] == "forbidden"
                and config["observed_optimizer"]["secondary_optimizer"] == "forbidden",
                "optimizer contract")
        return {"start_count": fit["start_count"], "KKT_role": fit["KKT_role"]}
    def t07():
        scan = synthetic_scans()[0]
        starts = bootstrap_start_bank([scan], [-1.0, 1.0], 1,
                                      baseline_joint([scan], [-1.0, 1.0], 1), config)
        require(len(starts) == 4 and math.isinf(bootstrap_statistic(
            {"fit_status": "numerical_failure"},
            {"fit_status": "valid", "log_likelihood": 0.0})), "bootstrap failure policy")
        return {"B": 4096, "model_local_starts": 4, "failure_statistic": "+infinity"}
    def t08():
        actual = {hypothesis_id: seed_payload(hypothesis_id)[1] for hypothesis_id in EXPECTED_MEMBERSHIP}
        require(actual == config["seed_policy"]["frozen_sha256"], "frozen seed hash")
        return actual
    def t09():
        statistics = [2.0] + [0.0] * 4095
        require(plus_one_p_value(statistics, 1.0) == 2.0 / 4097.0, "plus-one p value")
        return {"tail": ">=", "denominator": 4097, "example_p": 2.0 / 4097.0}
    def t10():
        sample = [{"hypothesis_id": key, "raw_p_value": value, "test_status": "numerically_valid"}
                  for key, value in zip(reversed(sorted(EXPECTED_MEMBERSHIP)), (0.06, 0.001, 0.001))]
        decisions = holm_decisions(sample)
        require([item["hypothesis_id"] for item in decisions[:2]] == sorted(EXPECTED_MEMBERSHIP)[:2],
                "Holm lexical tie")
        require(decisions[0]["Holm_rejected"] and decisions[1]["Holm_rejected"]
                and not decisions[2]["Holm_rejected"], "Holm stop")
        stopped = holm_decisions([
            {"hypothesis_id": key, "raw_p_value": value, "test_status": "numerically_valid"}
            for key, value in zip(sorted(EXPECTED_MEMBERSHIP), (0.02, 0.03, 0.04))])
        require(not any(item["Holm_rejected"] for item in stopped), "Holm continued after first failure")
        return decisions
    def t11():
        failed_id = sorted(EXPECTED_MEMBERSHIP)[0]
        sample = [{"hypothesis_id": key, "raw_p_value": 1.0 if key == failed_id else 0.5,
                   "test_status": "numerical_failure" if key == failed_id else "numerically_valid"}
                  for key in EXPECTED_MEMBERSHIP]
        decisions = holm_decisions(sample)
        failed = next(item for item in decisions if item["hypothesis_id"] == failed_id)
        require(failed["raw_p_value"] == 1.0 and
                failed["scientific_result_semantics"] == "numerical_failure", "failure semantics")
        return failed
    def t12():
        allowed = set(config["scientific_boundary"]["allowed_result_semantics"])
        require(allowed == {"presence_confirmed_internal_holdout", "presence_not_confirmed",
                            "numerical_failure"}, "scientific semantics")
        require(config["scientific_boundary"]["resolution_status"] == "resolution_not_established"
                and config["scientific_boundary"]["physical_assignment_performed"] is False
                and config["scientific_boundary"]["spectral_completeness_claim"] == "forbidden",
                "scientific boundary")
        return config["scientific_boundary"]
    def t13():
        expected_outputs = {"c002_observed_fits.csv", "c002_bootstrap_summary.csv",
                            "c002_holm_decisions.csv", "c002_numerical_diagnostics.yaml",
                            "holdout_field_access_log.csv", "provenance_manifest.yaml", "test_report.yaml"}
        require(set(config["output_contract"]["names"]) == expected_outputs, "output contract")
        denied = False
        try:
            validate_authorization_document(None, config, "x", "y", "z")
        except ConformanceError:
            denied = True
        require(denied and config["output_contract"]["stop_condition"] == STOP_CONDITION,
                "authorization/STOP")
        guard = HoldoutAccessGuard(family, authorization_valid=True)
        authorization = {"canonical_head": git_head(),
                         "implementation_source_sha256": sha256_file(Path(__file__)),
                         "implementation_config_sha256": sha256_file(ROOT / CONFIG_PATH)}
        provenance = build_provenance(config, authorization, family, guard, {"test_report.yaml": "0" * 64})
        required_provenance = {"design_freeze_main", "c001_execution_baseline",
                               "future_C002_spec_path", "future_C002_spec_sha256", "source_sha256",
                               "config_sha256", "input_artifact_identities",
                               "output_artifact_identities", "field_access_log", "test_report",
                               "STOP_CONDITION"}
        require(required_provenance <= set(provenance), "provenance contract")
        serialized = json.dumps({"config": config, "provenance": provenance}, sort_keys=True)
        require("http://" not in serialized and "https://" not in serialized
                and provenance["physical_assignment_performed"] is False, "private/physical boundary")
        if runtime is not None:
            require({item["hypothesis_id"] for item in runtime["results"]} == set(EXPECTED_MEMBERSHIP)
                    and {item["hypothesis_id"] for item in runtime["decisions"]} == set(EXPECTED_MEMBERSHIP),
                    "runtime family/result mutation")
        return {"outputs": sorted(expected_outputs), "STOP_CONDITION": STOP_CONDITION,
                "missing_authorization_fails_closed": True,
                "provenance_fields": sorted(required_provenance)}

    for index, function in enumerate((t01, t02, t03, t04, t05, t06, t07, t08,
                                      t09, t10, t11, t12, t13), 1):
        test(f"C002-T{index:02d}", function)
    return {"mode": "static_and_synthetic_only" if runtime is None else "production_runtime",
            "C002_executed": runtime is not None,
            "holdout_detector_access_count": 0 if runtime is None else runtime["guard"].detector_materializations,
            "tests": tests, "passed": sum(item["status"] == "PASS" for item in tests),
            "failed": sum(item["status"] == "FAIL" for item in tests),
            "all_mandatory_tests_pass": all(item["status"] == "PASS" for item in tests)}


def synthetic_scans():
    scans = []
    for scan_id, shift in (("S1", 0.0), ("S2", 0.1)):
        energy = np.linspace(-2.0, 2.0, 9)
        exposure = np.full(9, 20.0)
        rate = np.exp(-2.0 + 0.03 * energy) + 0.2 * np.exp(-0.5 * ((energy - shift) / 0.5) ** 2)
        scans.append(ScanData(scan_id, tuple(str(index) for index in range(9)), energy,
                              exposure, np.rint(exposure * rate)))
    return scans


def write_outputs(results, decisions, scans_by_hypothesis, family, guard, authorization, config):
    output_dir = ROOT / config["output_contract"]["directory"]
    require(not output_dir.exists(), "C002 output directory already exists")
    temporary = output_dir.with_name(output_dir.name + ".partial")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    observed, bootstrap, holm = output_rows(results, decisions, scans_by_hypothesis, config)
    diagnostics = {"numerical_failures": [failure for result in results
                                           for failure in result.get("bootstrap_failures", [])],
                   "observed_numerical_failures": [result["hypothesis_id"] for result in results
                                                    if result["test_status"] == "numerical_failure"],
                   "resolution_status": "resolution_not_established"}
    report = test_runner(config, runtime={"guard": guard, "results": results,
                                          "decisions": decisions,
                                          "authorization": authorization})
    documents = {"c002_observed_fits.csv": csv_bytes(observed),
                 "c002_bootstrap_summary.csv": csv_bytes(bootstrap),
                 "c002_holm_decisions.csv": csv_bytes(holm),
                 "c002_numerical_diagnostics.yaml": yaml_bytes(diagnostics),
                 "holdout_field_access_log.csv": csv_bytes(guard.log),
                 "test_report.yaml": yaml_bytes(report)}
    for name, content in documents.items():
        (temporary / name).write_bytes(content)
    identities = {name: sha256_file(temporary / name) for name in sorted(documents)}
    provenance = build_provenance(config, authorization, family, guard, identities)
    (temporary / "provenance_manifest.yaml").write_bytes(yaml_bytes(provenance))
    require(set(path.name for path in temporary.iterdir()) == set(config["output_contract"]["names"]),
            "output contract materialization")
    require(report["all_mandatory_tests_pass"], "runtime C002-T01..C002-T13 failure")
    os.replace(temporary, output_dir)
    return output_dir


def execute_candidate(config):
    verify_static_identities(config)
    authorization = require_external_authorization(config)
    family = load_family(config)
    verify_family(family, config)
    windows = metadata_fit_windows(family, config)
    guard = HoldoutAccessGuard(family, authorization_valid=True)
    results, scans_by_hypothesis = [], {}
    for hypothesis in family["hypotheses"]:
        hypothesis_id = hypothesis["hypothesis_id"]
        counts = detector_counts_for_windows(hypothesis_id, windows[hypothesis_id], config, guard)
        scans = build_scan_data(hypothesis_id, windows, counts)
        scans_by_hypothesis[hypothesis_id] = scans
        results.append(run_hypothesis(hypothesis, scans, config,
                                      replicate_count=hypothesis["bootstrap_replicates"]))
    decisions = holm_decisions(results, config["holm"]["global_alpha"])
    output_dir = write_outputs(results, decisions, scans_by_hypothesis, family, guard,
                               authorization, config)
    return {"output_dir": str(output_dir), "C002_executed": True,
            "holdout_detector_access_count": guard.detector_materializations,
            "STOP_CONDITION": STOP_CONDITION}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    config = load_config()
    if arguments.self_test:
        report = test_runner(config)
        print(json.dumps(report, indent=2, default=serializable))
        raise SystemExit(0 if report["failed"] == 0 else 1)
    result = execute_candidate(config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
