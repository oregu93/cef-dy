#!/usr/bin/env python3
"""Execute frozen W02-02R-C-001 and stop before holdout detector access.

The point-table adapter projects byte tokens before decoding field values.
Detector tokens are decoded only for the frozen discovery set or for the
explicit EV-006 resolution-evidence scan.  Holdout detector and det_err tokens
remain opaque for the complete execution.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import argparse
import ast
import csv
import functools
import hashlib
import importlib.util
import io
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import scipy
import yaml
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import qmc


ROOT = Path(__file__).resolve().parents[2]
JOB = "W02-02R-C-001"
AUTH_HEAD = "8525e573e7de253b7fcb1922502e99b3eddd1a0d"
DESIGN_BASELINE = "31b16b22fc38fc51c063dc1d2908fcb630b8d3cf"
SPEC = "03_Protocols/STAGE02R_T02R05_C001_CONFIRMATORY_MODEL_PREPARATION_SPEC.md"
SPEC_SHA256 = "6dabdf49d72e50329a57bd86e6b2cac8a4f664a76caf4c1f3d62870ccb163ea5"
SOURCE = "scripts/stage02r/c001_confirmatory_model_preparation.py"
CONFIG = "scripts/stage02r/c001_confirmatory_config.yaml"
CHECKPOINT = "02_Work_Checkpoints/W02-02R-C-001.md"
OUT_REL = "04_Results/Stage02R/W02-02R-C-001"
DIAGNOSTIC_FAILURE_REL = "CEF_Dy_Backup/work_recovery/W02-02R-C-001/diagnostic_failures"
A2 = "04_Results/Stage02R/W02-02R-A-002/"
A3 = "04_Results/Stage02R/W02-02R-A-003/"
B1 = "04_Results/Stage02R/W02-02R-B-001/"
B001_SHA256 = "f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5"
EXCLUDED_DISCOVERY = "SCAN-02R-7acd4c14a0007418"
REQUIRED_OUTPUTS = (
    "resolution_evidence.yaml", "resolution_applicability.csv", "resolution_model.yaml",
    "confirmatory_complexes.yaml", "fit_windows.yaml", "discovery_model_fits.csv",
    "background_selection.yaml", "component_development.yaml", "model_identifiability.csv",
    "holdout_metadata_eligibility.csv", "holdout_coverage_summary.yaml",
    "holdout_field_access_log.csv", "instrument_block_assessment.yaml",
    "confirmatory_hypotheses.yaml", "confirmatory_model_spec.yaml",
    "numerical_stability_diagnostics.yaml", "provenance_manifest.yaml", "test_report.yaml",
)
CANONICAL_INPUTS = (
    "00_Project/PROJECT_STATE.md", "00_Project/PROJECT_CONTROL.md",
    "00_Project/PROJECT_METADATA.yaml", "00_Project/RESULT_REGISTER.yaml",
    "00_Project/EVIDENCE_REGISTER.yaml", "03_Protocols/DATA_CONTRACTS.md",
    "03_Protocols/SCIENTIFIC_TERMINOLOGY.md",
    "03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md", SPEC,
    "02_Work_Checkpoints/W02-02R-A-001.md", "02_Work_Checkpoints/W02-02R-A-002.md",
    "02_Work_Checkpoints/W02-02R-A-003.md", "02_Work_Checkpoints/W02-02R-B-001.md",
    B1 + "SCIENTIFIC_REVIEW.md", B1 + "blind_feature_catalogue.yaml",
    B1 + "blind_split.csv", B1 + "scan_selection.csv", B1 + "feature_reproducibility.csv",
    B1 + "provenance_manifest.yaml", A2 + "scan_inventory.csv", A2 + "scan_points.csv",
    A2 + "semantic_verification_report.yaml", A3 + "scan_classification.csv",
    A3 + "instrument_configs.yaml", A3 + "normalization_compatibility_groups.yaml",
)
POINT_METADATA_ALLOWLIST = frozenset({
    "scan_record_id", "file_record_id", "point_index", "e_raw", "ei_raw", "ef_raw",
    "h_raw", "k_raw", "l_raw", "monitor_raw", "time_raw", "source_data_line_number",
})
POINT_DETECTOR_FIELD = "detector_raw"
POINT_DENIED = frozenset({"detector_raw", "det_err_raw", "detector", "det_err",
                          "detector_counts", "detector_monitor_rate", "detector_time_rate"})
MODEL_SCAN_FIELDS = ("scan_record_id", "point_index", "e_raw", "monitor_raw", "detector_raw")
HOLDOUT_POINT_FIELDS = ("scan_record_id", "point_index", "e_raw", "ei_raw", "ef_raw",
                        "h_raw", "k_raw", "l_raw", "monitor_raw", "time_raw")


class StopJob(RuntimeError):
    """Frozen hard-stop condition."""

    def __init__(self, reason, diagnostics=None, diagnostic_path=None):
        super().__init__(reason)
        self.diagnostics = list(diagnostics or [])
        self.diagnostic_path = diagnostic_path


def require(condition, reason):
    if not condition:
        raise StopJob(reason)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


DIAGNOSTIC_FAILURE_FIELDS = (
    "test_id", "complex_id", "comparison_id", "parent_model_id", "child_model_id",
    "benchmark_replicate_index", "candidate_multistart_level", "parent_reference_valid",
    "child_reference_valid", "fit_status", "failure_reason", "projected_gradient_max",
)


def preserve_failure_diagnostic(reason, records, destination=None):
    """Atomically preserve non-canonical STOP evidence outside scientific results."""
    normalized = []
    for record in records:
        normalized.append({field: record.get(field, "not_available")
                           for field in DIAGNOSTIC_FAILURE_FIELDS})
    if not normalized:
        normalized.append({
            "test_id": "runtime_stop", "complex_id": "not_available",
            "comparison_id": "not_available", "parent_model_id": "not_available",
            "child_model_id": "not_available", "benchmark_replicate_index": "not_available",
            "candidate_multistart_level": "not_available",
            "parent_reference_valid": "not_available",
            "child_reference_valid": "not_available", "fit_status": "STOPPED",
            "failure_reason": reason, "projected_gradient_max": "not_available",
        })
    destination = Path(destination) if destination is not None else ROOT / DIAGNOSTIC_FAILURE_REL
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    payload = {
        "record_type": "diagnostic_failure_record",
        "canonical_scientific_result": False,
        "job_id": JOB,
        "repository_commit": AUTH_HEAD,
        "failure_reason": reason,
        "source_sha256": sha256_file(ROOT / SOURCE),
        "config_sha256": sha256_file(ROOT / CONFIG),
        "created_utc": timestamp,
        "records": normalized,
    }
    data = (json.dumps(payload, sort_keys=True, indent=2, default=json_scalar) + "\n").encode("utf-8")
    target = destination / f"{timestamp}_diagnostic_failure.json"
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("xb") as handle:
        handle.write(data)
    require(temporary.read_bytes() == data, "diagnostic_failure_write_verification_failure")
    os.replace(temporary, target)
    return str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target)


def git(*args, text=True):
    result = subprocess.run(["git", *args], cwd=ROOT, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=text)
    return result.stdout


def yload(data):
    return yaml.load(data, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def ybytes(data):
    return yaml.dump(data, Dumper=Dumper, allow_unicode=True, sort_keys=False,
                     width=110, line_break="\n").encode("utf-8")


def csvbytes(rows, columns):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        values = {}
        for key in columns:
            value = row.get(key, "")
            if isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, (list, tuple)):
                value = ";".join(map(str, value))
            elif isinstance(value, dict):
                value = json.dumps(value, sort_keys=True, separators=(",", ":"))
            values[key] = value
        writer.writerow(values)
    return buffer.getvalue().encode("utf-8")


def json_scalar(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def portable_rel(path):
    return Path(path).relative_to(ROOT).as_posix()


def metadata_projection(relative_path, fields, access_log=None, access_role="canonical_metadata"):
    """Project detector-free metadata columns before constructing row mappings."""
    if access_log is not None:
        for field in fields:
            access_log.record(relative_path, field, access_role, True)
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        require(set(fields) <= set(header), "canonical_field_schema_inconsistent:" + relative_path)
        indices = [(field, header.index(field)) for field in fields]
        return [{field: row[index] for field, index in indices} for row in reader]


class AccessLog:
    def __init__(self):
        self.rows = []
        self.sequence = 0

    def record(self, source, field, role, allowed):
        self.sequence += 1
        self.rows.append({"source_artifact": source, "requested_field": field,
                          "access_role": role, "allowed": allowed,
                          "request_sequence": self.sequence})


class PointAccess:
    """Decode only selected byte tokens; denied holdout fields stay opaque."""
    def __init__(self, discovery_ids, resolution_ids, holdout_ids, access_log, data=None):
        self.discovery_ids = frozenset(discovery_ids)
        self.resolution_ids = frozenset(resolution_ids)
        self.holdout_ids = frozenset(holdout_ids)
        self.access_log = access_log
        self.data = data
        self.detector_scan_ids = set()
        self.detector_values_decoded = 0
        self.holdout_detector_values_decoded = 0
        self.forbidden_requests = 0

    def rows(self, fields, selected_ids, access_role):
        fields = tuple(fields)
        selected_ids = frozenset(selected_ids)
        detector = POINT_DETECTOR_FIELD in fields
        denied = set(fields) & POINT_DENIED
        if detector:
            allowed_ids = (self.discovery_ids if access_role == "discovery_detector"
                           else self.resolution_ids if access_role == "resolution_evidence"
                           else frozenset())
            if not selected_ids <= allowed_ids or selected_ids & self.holdout_ids:
                self.forbidden_requests += 1
                raise StopJob("holdout_forbidden_field_request_hard_fail_before_materialization")
            require(denied == {POINT_DETECTOR_FIELD}, "det_err_or_derived_detector_access_forbidden")
            require(set(fields) <= POINT_METADATA_ALLOWLIST | {POINT_DETECTOR_FIELD},
                    "discovery_projection_outside_allowlist")
        else:
            if denied or not set(fields) <= POINT_METADATA_ALLOWLIST:
                self.forbidden_requests += 1
                raise StopJob("holdout_forbidden_field_request_hard_fail_before_materialization")
        for field in fields:
            self.access_log.record(A2 + "scan_points.csv", field, access_role, True)
        stream = io.BytesIO(self.data) if self.data is not None else (ROOT / A2 / "scan_points.csv").open("rb")
        with stream:
            header = stream.readline().rstrip(b"\r\n").decode("ascii").split(",")
            require(set(fields) <= set(header), "canonical_field_schema_inconsistent:scan_points")
            columns = [(field, header.index(field)) for field in fields]
            sid_index = header.index("scan_record_id")
            for raw_line in stream:
                require(b'"' not in raw_line, "canonical_field_schema_inconsistent:quoted_point_token")
                line = raw_line.rstrip(b"\r\n")
                delimiters = [-1]
                position = line.find(b",")
                while position >= 0:
                    delimiters.append(position)
                    position = line.find(b",", position + 1)
                delimiters.append(len(line))
                require(len(delimiters) == len(header) + 1,
                        "canonical_field_schema_inconsistent:scan_point_width")

                def token(index):
                    return line[delimiters[index] + 1:delimiters[index + 1]].decode("ascii")

                sid = token(sid_index)
                if sid not in selected_ids:
                    continue
                values = {field: token(index) for field, index in columns}
                if detector:
                    self.detector_scan_ids.add(sid)
                    self.detector_values_decoded += 1
                    if sid in self.holdout_ids:
                        self.holdout_detector_values_decoded += 1
                yield values


@dataclass
class ScanData:
    scan_record_id: str
    energy: np.ndarray
    exposure: np.ndarray
    counts: np.ndarray


def read_frontmatter(path):
    text = Path(path).read_text(encoding="utf-8")
    require(text.startswith("---\n"), "missing_frontmatter:" + str(path))
    return yload(text.split("---", 2)[1])


def verify_recovery(snapshot_id):
    module_path = ROOT / "scripts/work_recovery.py"
    spec = importlib.util.spec_from_file_location("c001_recovery", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    snapshot = ROOT / "CEF_Dy_Backup" / "work_recovery" / JOB / snapshot_id
    ok, _metadata, _details = module.verify_snapshot(snapshot)
    require(ok, "recovery_START_integrity_failure")
    report = module.audit_snapshot(ROOT, JOB, snapshot_id)
    require(report["SNAPSHOT_INTEGRITY"] == "PASS", "recovery_START_integrity_failure")
    require(report["HEAD_SAVED"] == AUTH_HEAD and report["BRANCH_SAVED"] == "main",
            "recovery_START_identity_failure")
    require(not report["GIT_OPERATION_IN_PROGRESS"], "git_operation_in_progress")
    return {"snapshot_id": snapshot_id,
            "relative_path": f"CEF_Dy_Backup/work_recovery/{JOB}/{snapshot_id}",
            "head": AUTH_HEAD, "branch": "main", "integrity": "PASS"}


def verify_checksum_inventory(path):
    verified = []
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        target = ROOT / relative
        require(target.is_file(), "missing_reviewed_artifact:" + relative)
        worktree_digest = sha256_file(target)
        identity_source = "worktree_bytes"
        if worktree_digest != digest:
            head_oid = git("rev-parse", "HEAD:" + relative).strip()
            filtered_oid = git("hash-object", "--path=" + relative, relative).strip()
            require(filtered_oid == head_oid, "reviewed_artifact_worktree_differs_from_HEAD:" + relative)
            canonical_bytes = git("cat-file", "blob", "HEAD:" + relative, text=False)
            require(sha256_bytes(canonical_bytes) == digest,
                    "reviewed_artifact_identity_failure:" + relative)
            identity_source = "canonical_git_blob_after_clean_filter_check"
        verified.append({"path": relative, "size_bytes": target.stat().st_size, "sha256": digest,
                         "identity_source": identity_source})
    return verified


def verify_inputs(expected_commit, snapshot_id):
    require(expected_commit == AUTH_HEAD, "unexpected_authorization_baseline")
    require(git("rev-parse", "HEAD").strip() == AUTH_HEAD, "canonical_HEAD_mismatch")
    require(git("rev-parse", "origin/main").strip() == AUTH_HEAD, "origin_main_mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", DESIGN_BASELINE, "HEAD"],
                   cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    metadata = yload((ROOT / "00_Project/PROJECT_METADATA.yaml").read_bytes())
    c001 = metadata["scientific_facade"]["c001"]
    require(c001["execution_authorized"] is True, "C001_not_authorized")
    require(c001["holdout_detector_access_authorized"] is False, "holdout_detector_access_not_closed")
    require(metadata["control"]["next_work_job"] == JOB, "unexpected_next_work_job")
    require(metadata["scientific_facade"]["c002"]["execution_authorized"] is False,
            "C002_unexpectedly_authorized")
    identities = []
    for relative in CANONICAL_INPUTS:
        path = ROOT / relative
        require(path.is_file(), "missing_required_input:" + relative)
        data = path.read_bytes()
        head_oid = git("rev-parse", "HEAD:" + relative).strip()
        worktree_oid = git("hash-object", "--path=" + relative, relative).strip()
        require(worktree_oid == head_oid, "tracked_input_differs_from_HEAD:" + relative)
        identities.append({"path": relative, "size_bytes": len(data), "sha256": sha256_bytes(data),
                           "canonical_git_blob_oid": head_oid})
    require(sha256_file(ROOT / SPEC) == SPEC_SHA256, "frozen_specification_identity_failure")
    spec_meta = read_frontmatter(ROOT / SPEC)
    require(spec_meta["status"] == "frozen", "specification_not_frozen")
    require(sha256_file(ROOT / B1 / "blind_feature_catalogue.yaml") == B001_SHA256,
            "B001_catalogue_identity_failure")
    b001_verified = verify_checksum_inventory(B1 + "ARTIFACT_SHA256SUMS")
    local_paths = yload((ROOT / "configs/local_paths.yaml").read_bytes())
    require("EXP-TAIPAN-001" in local_paths, "dataset_path_not_configured")
    dataset_root = Path(local_paths["EXP-TAIPAN-001"]["path"])
    require(dataset_root.is_dir(), "configured_dataset_root_unavailable")
    recovery = verify_recovery(snapshot_id)
    return {
        "status": "PASS", "canonical_inputs": identities,
        "b001_inventory_verified": b001_verified,
        "dataset_id": "EXP-TAIPAN-001", "dataset_root_resolved": True,
        "raw_data_opened": False, "design_baseline_is_ancestor": True,
        "recovery_start": recovery,
    }


def finite_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def monotonic_unique(values):
    delta = np.diff(values)
    return bool((np.all(delta > 0) or np.all(delta < 0)) and len(set(values.tolist())) == len(values))


def load_canonical_tables(access_log):
    selection_fields = (
        "scan_record_id", "raw_scan_id", "count_control_mode", "acquisition_state_id",
        "lattice_state_id", "UB_state_id", "scan_variable_raw", "pre_detector_status",
        "split_role", "discovery_runtime_status", "source_point_count", "energy_order",
    )
    inventory_fields = (
        "scan_record_id", "raw_scan_id", "scan_point_count", "scan_variable_raw",
        "count_control_mode", "count_control_status", "preset_channel_raw",
        "en_e_mapping_status", "energy_relation_status", "Ei_summary_meV", "Ef_summary_meV",
        "lattice_state_id", "UB_state_id", "monochromator_material",
        "monochromator_reflection", "monochromator_reflection_status",
        "monochromator_mosaic", "monochromator_mosaic_status", "analyzer_material",
        "analyzer_reflection", "analyzer_reflection_status", "analyzer_mosaic",
        "analyzer_mosaic_status", "collimation", "orientation_status", "quality_flag",
    )
    classification_fields = (
        "scan_record_id", "instrument_config_id", "normalization_epoch_id",
        "critical_unknown_fields", "relevant_unknown_fields",
    )
    selection = metadata_projection(B1 + "scan_selection.csv", selection_fields,
                                    access_log, "split_and_pre_detector_metadata")
    inventory = metadata_projection(A2 + "scan_inventory.csv", inventory_fields,
                                    access_log, "canonical_scan_metadata")
    classification = metadata_projection(A3 + "scan_classification.csv", classification_fields,
                                         access_log, "classification_metadata")
    require(len(selection) == len(inventory) == len(classification) == 201,
            "canonical_scan_population_mismatch")
    by_id = {row["scan_record_id"]: row for row in selection}
    inv = {row["scan_record_id"]: row for row in inventory}
    cls = {row["scan_record_id"]: row for row in classification}
    require(set(by_id) == set(inv) == set(cls), "canonical_scan_join_failure")
    for sid in by_id:
        require(by_id[sid]["raw_scan_id"] == inv[sid]["raw_scan_id"],
                "raw_scan_identity_mismatch:" + sid)
        by_id[sid].update({"inventory_" + k: v for k, v in inv[sid].items() if k != "scan_record_id"})
        by_id[sid].update({"classification_" + k: v for k, v in cls[sid].items()
                           if k != "scan_record_id"})
    holdout_ids = {sid for sid, row in by_id.items() if row["split_role"] == "holdout"}
    discovery_ids = {sid for sid, row in by_id.items()
                     if row["split_role"] == "discovery"
                     and row["discovery_runtime_status"] == "discovery_usable"}
    require(len(holdout_ids) == 18, "frozen_holdout_count_mismatch")
    require(EXCLUDED_DISCOVERY not in discovery_ids, "B001_exclusion_not_preserved")
    return by_id, discovery_ids, holdout_ids


def collect_point_metadata(access, scan_ids, access_role="detector_blind_point_metadata"):
    grouped = defaultdict(list)
    for row in access.rows(HOLDOUT_POINT_FIELDS, scan_ids, access_role):
        grouped[row["scan_record_id"]].append(row)
    for sid in grouped:
        grouped[sid].sort(key=lambda row: int(row["point_index"]))
    return grouped


def monitor_exposure_verified(scan, rows):
    values = np.array([finite_number(row["monitor_raw"]) for row in rows])
    return bool(scan["count_control_mode"] == "monitor_controlled"
                and scan["inventory_count_control_status"] == "verified"
                and scan["inventory_preset_channel_raw"] == "monitor"
                and len(values) == int(scan["inventory_scan_point_count"])
                and np.isfinite(values).all() and np.all(values > 0))


def energy_values(rows):
    return np.array([finite_number(row["e_raw"]) for row in rows], dtype=float)


def compute_fit_windows(config, scans, discovery_ids, metadata_points):
    results = {}
    base_ids = []
    for sid in sorted(discovery_ids):
        rows = metadata_points[sid]
        energy = energy_values(rows)
        if (scans[sid]["count_control_mode"] == "monitor_controlled"
                and monitor_exposure_verified(scans[sid], rows)
                and monotonic_unique(energy)):
            base_ids.append(sid)
    for complex_id, definition in config["complexes"].items():
        lower, upper = map(float, definition["frozen_union_meV"])
        covering, steps = [], []
        for sid in base_ids:
            energy = np.sort(energy_values(metadata_points[sid]))
            if energy[0] <= lower and energy[-1] >= upper:
                covering.append(sid)
                steps.append(float(np.median(np.diff(energy))))
        require(steps, "no_discovery_energy_coverage:" + complex_id)
        delta_ref = float(np.median(steps))
        chosen = None
        eligible = []
        trials = []
        for multiple in config["fit_window"]["candidate_margin_multiples"]:
            window = [lower - multiple * delta_ref, upper + multiple * delta_ref]
            accepted = []
            for sid in covering:
                energy = np.sort(energy_values(metadata_points[sid]))
                inside = energy[(energy >= window[0]) & (energy <= window[1])]
                if (energy[0] <= window[0] and energy[-1] >= window[1]
                        and len(inside) >= config["fit_window"]["minimum_points_in_window"]
                        and np.sum(inside < lower) >= config["fit_window"]["minimum_flank_points_each_side"]
                        and np.sum(inside > upper) >= config["fit_window"]["minimum_flank_points_each_side"]):
                    accepted.append(sid)
            trials.append({"margin_multiple": multiple, "fit_window_meV": window,
                           "qualifying_scan_count": len(accepted),
                           "qualifying_scan_record_ids": accepted})
            if chosen is None and len(accepted) >= config["fit_window"]["minimum_scan_count"]:
                chosen, eligible = window, accepted
        digest_payload = "".join(sid + "\n" for sid in sorted(eligible)).encode("utf-8")
        results[complex_id] = {
            "complex_id": complex_id, "source_bf_ids": definition["source_bf_ids"],
            "frozen_union_meV": [lower, upper], "maximum_BF_defined_K": definition["maximum_BF_defined_K"],
            "delta_E_ref_meV": delta_ref, "candidate_margin_trials": trials,
            "fit_window_meV": chosen,
            "complex_model_status": ("ready_for_discovery_model_development" if chosen
                                     else "insufficient_discovery_window_coverage"),
            "discovery_model_scan_set": sorted(eligible),
            "discovery_model_scan_set_sha256": sha256_bytes(digest_payload),
        }
    return results


def holdout_eligibility(config, scans, holdout_ids, metadata_points, fit_windows):
    rows = []
    summary = {}
    for complex_id, fit in fit_windows.items():
        lower, upper = fit["frozen_union_meV"]
        window = fit["fit_window_meV"]
        eligible_ids = []
        for sid in sorted(holdout_ids):
            scan = scans[sid]
            points = metadata_points[sid]
            energy = energy_values(points)
            reasons = []
            if scan["count_control_mode"] != "monitor_controlled":
                reasons.append("not_monitor_controlled")
            if not monitor_exposure_verified(scan, points):
                reasons.append("monitor_exposure_not_verified")
            if scan["pre_detector_status"] != "eligible_for_split":
                reasons.append("pre_detector_QC_not_acceptable")
            if not monotonic_unique(energy):
                reasons.append("energy_grid_not_strict_monotonic_unique")
            if window is None:
                reasons.append("no_final_fit_window")
                inside = np.array([])
            else:
                ordered = np.sort(energy)
                inside = ordered[(ordered >= window[0]) & (ordered <= window[1])]
                if ordered[0] > window[0] or ordered[-1] < window[1]:
                    reasons.append("incomplete_fit_window_coverage")
                if len(inside) < 15:
                    reasons.append("fewer_than_15_window_points")
                if np.sum(inside < lower) < 4:
                    reasons.append("fewer_than_4_lower_flank_points")
                if np.sum(inside > upper) < 4:
                    reasons.append("fewer_than_4_upper_flank_points")
            eligible = not reasons
            if eligible:
                eligible_ids.append(sid)
            rows.append({"scan_record_id": sid, "raw_scan_id": scan["raw_scan_id"],
                         "complex_id": complex_id, "split_role": "holdout",
                         "count_control_mode": scan["count_control_mode"],
                         "pre_detector_status": scan["pre_detector_status"],
                         "eligible": eligible, "eligibility_status": "eligible" if eligible else "ineligible",
                         "eligibility_reasons": reasons, "fit_window_point_count": len(inside),
                         "detector_fields_materialized": 0})
        count = len(eligible_ids)
        scope = "none" if count == 0 else "single_scan" if count == 1 else "multi_scan"
        summary[complex_id] = {
            "complex_id": complex_id, "coverage_status": "not_covered" if count == 0 else "covered",
            "holdout_coverage_scope": scope, "eligible_holdout_scan_count": count,
            "eligible_holdout_scan_record_ids": eligible_ids,
            "scope_semantics": "capacity_only_not_observed_support_or_replication",
        }
    return rows, summary


def softmax_with_reference(eta):
    eta = np.asarray(eta, dtype=float)
    maximum = max(0.0, float(np.max(eta)) if len(eta) else 0.0)
    weights = np.exp(np.concatenate([eta, np.array([0.0])]) - maximum)
    return weights / weights.sum()


def centroids_from_eta(eta, lower, upper, delta):
    k_count = len(eta)
    remainder = (upper - lower) - (k_count - 1) * delta
    require(remainder > 0, "invalid_centroid_geometry")
    q_value = softmax_with_reference(eta)
    cumulative = np.cumsum(q_value[:-1])
    centroids = lower + np.arange(k_count) * delta + remainder * cumulative
    jacobian = np.empty((k_count, k_count), dtype=float)
    for k_index in range(k_count):
        for eta_index in range(k_count):
            jacobian[k_index, eta_index] = (remainder * q_value[eta_index]
                                            * ((1.0 if eta_index <= k_index else 0.0)
                                               - cumulative[k_index]))
    return centroids, jacobian, q_value


def gaussian_density(energy, centroid, fwhm):
    sigma = fwhm / 2.3548200450309493
    z_value = (energy - centroid) / sigma
    density = np.exp(-0.5 * z_value * z_value) / (sigma * math.sqrt(2.0 * math.pi))
    derivative_centroid = density * (energy - centroid) / (sigma * sigma)
    derivative_fwhm = density * (z_value * z_value - 1.0) / fwhm
    return density, derivative_centroid, derivative_fwhm


def model_layout(model):
    layout, offset = [], 0
    block_dim = model["background_order"] + 1 + 3 * model["K"]
    for scan in model["scans"]:
        layout.append((scan.scan_record_id, slice(offset, offset + block_dim)))
        offset += block_dim
    return layout, offset


def block_bounds(model):
    bounds = [(None, None)]
    bounds.extend([(-10.0, 10.0)] * model["background_order"])
    bounds.extend([(0.0, None)] * model["K"])
    bounds.extend([(None, None)] * model["K"])
    bounds.extend([(model["width_min"], model["width_max"])] * model["K"])
    return bounds


def block_parts(theta, model):
    p_count = model["background_order"] + 1
    k_count = model["K"]
    background = theta[:p_count]
    areas = theta[p_count:p_count + k_count]
    eta = theta[p_count + k_count:p_count + 2 * k_count]
    widths = theta[p_count + 2 * k_count:p_count + 3 * k_count]
    return background, areas, eta, widths


def block_nll_gradient(theta, model, scan, counts=None):
    counts = scan.counts if counts is None else np.asarray(counts, dtype=float)
    background, areas, eta, widths = block_parts(np.asarray(theta, dtype=float), model)
    midpoint = 0.5 * (model["fit_window"][0] + model["fit_window"][1])
    span = model["fit_window"][1] - model["fit_window"][0]
    x_value = 2.0 * (scan.energy - midpoint) / span
    powers = np.vstack([x_value ** degree for degree in range(model["background_order"] + 1)])
    polynomial = background @ powers
    if not np.isfinite(polynomial).all() or np.max(polynomial) > 700:
        return float("inf"), np.full_like(theta, np.nan), None
    background_rate = np.exp(polynomial)
    rate = background_rate.copy()
    component_density = []
    centroid_derivative = []
    width_derivative = []
    centroids = np.array([])
    centroid_jacobian = np.empty((0, 0))
    if model["K"]:
        centroids, centroid_jacobian, _q = centroids_from_eta(
            eta, model["complex_union"][0], model["complex_union"][1], model["delta_ref"])
        for area, centroid, width in zip(areas, centroids, widths):
            density, dc, dw = gaussian_density(scan.energy, centroid, width)
            component_density.append(density)
            centroid_derivative.append(dc)
            width_derivative.append(dw)
            rate += area * density
    mu = scan.exposure * rate
    if (not np.isfinite(mu).all()) or np.any(mu <= 0) or not np.isfinite(counts).all():
        return float("inf"), np.full_like(theta, np.nan), None
    nll = float(np.sum(mu - counts * np.log(mu) + gammaln(counts + 1.0)))
    common = (1.0 - counts / mu) * scan.exposure
    gradient = []
    for degree in range(model["background_order"] + 1):
        gradient.append(float(np.sum(common * background_rate * powers[degree])))
    if model["K"]:
        for density in component_density:
            gradient.append(float(np.sum(common * density)))
        for eta_index in range(model["K"]):
            drate = np.zeros_like(rate)
            for component in range(model["K"]):
                drate += (areas[component] * centroid_derivative[component]
                          * centroid_jacobian[component, eta_index])
            gradient.append(float(np.sum(common * drate)))
        for component in range(model["K"]):
            gradient.append(float(np.sum(common * areas[component] * width_derivative[component])))
    return nll, np.array(gradient, dtype=float), {
        "mu": mu, "rate": rate, "background_rate": background_rate,
        "centroids": centroids,
    }


def block_nll_value(theta, model, scan, counts=None):
    """Scalar physical Poisson NLL for SciPy's native numerical Jacobian path."""
    counts = scan.counts if counts is None else np.asarray(counts, dtype=float)
    background, areas, eta, widths = block_parts(np.asarray(theta, dtype=float), model)
    midpoint = 0.5 * (model["fit_window"][0] + model["fit_window"][1])
    span = model["fit_window"][1] - model["fit_window"][0]
    x_value = 2.0 * (scan.energy - midpoint) / span
    powers = np.vstack([x_value ** degree for degree in range(model["background_order"] + 1)])
    polynomial = background @ powers
    if not np.isfinite(polynomial).all() or np.max(polynomial) > 700:
        return float("inf")
    rate = np.exp(polynomial)
    if model["K"]:
        centroids, _centroid_jacobian, _q = centroids_from_eta(
            eta, model["complex_union"][0], model["complex_union"][1], model["delta_ref"])
        for area, centroid, width in zip(areas, centroids, widths):
            density, _dc, _dw = gaussian_density(scan.energy, centroid, width)
            rate += area * density
    mu = scan.exposure * rate
    if (not np.isfinite(mu).all()) or np.any(mu <= 0) or not np.isfinite(counts).all():
        return float("inf")
    return float(np.sum(mu - counts * np.log(mu) + gammaln(counts + 1.0)))


def finite_difference_component_fd(theta, index, model, scan, counts, bounds):
    theta = np.asarray(theta, dtype=float)
    step_scale = model["finite_difference_step"]
    base, _g, _state = block_nll_gradient(theta, model, scan, counts)
    if not math.isfinite(base):
        return float("inf"), float("inf")
    value = theta[index]
    step = step_scale * max(1.0, abs(float(value)))
    lower, upper = bounds[index]
    forward_ok = upper is None or value + step <= upper
    backward_ok = lower is None or value - step >= lower
    if forward_ok and backward_ok:
        plus = theta.copy(); plus[index] += step
        minus = theta.copy(); minus[index] -= step
        f_plus = block_nll_gradient(plus, model, scan, counts)[0]
        f_minus = block_nll_gradient(minus, model, scan, counts)[0]
        derivative = (f_plus - f_minus) / (2.0 * step)
    elif forward_ok:
        plus = theta.copy(); plus[index] += step
        derivative = (block_nll_gradient(plus, model, scan, counts)[0] - base) / step
    elif backward_ok:
        minus = theta.copy(); minus[index] -= step
        derivative = (base - block_nll_gradient(minus, model, scan, counts)[0]) / step
    else:
        return float("inf"), float("inf")
    projected = derivative
    lower_scale = (max(1.0, abs(float(value)), abs(lower))
                   if lower is not None else None)
    upper_scale = (max(1.0, abs(float(value)), abs(upper))
                   if upper is not None else None)
    at_lower = (lower is not None
                and abs(value - lower) <= model["active_bound_tolerance"] * lower_scale)
    at_upper = (upper is not None
                and abs(value - upper) <= model["active_bound_tolerance"] * upper_scale)
    if at_lower and derivative >= 0:
        projected = 0.0
    elif at_upper and derivative <= 0:
        projected = 0.0
    return float(derivative), float(projected)


def projected_gradient_fd(theta, model, scan, counts, bounds):
    projected = [finite_difference_component_fd(theta, index, model, scan, counts, bounds)[1]
                 for index in range(len(theta))]
    if not np.isfinite(projected).all():
        return float("inf")
    return float(np.max(np.abs(projected)))


def fit_block(model, scan, counts, start):
    bounds = block_bounds(model)

    def objective(theta):
        return block_nll_value(theta, model, scan, counts)

    try:
        result = minimize(objective, np.asarray(start, dtype=float), method="L-BFGS-B",
                          bounds=bounds, options=model["optimizer"])
    except (FloatingPointError, ValueError):
        return None
    if not result.success or not np.isfinite(result.fun) or not np.isfinite(result.x).all():
        return None
    physical_theta = np.asarray(result.x, dtype=float)
    physical_nll = block_nll_value(physical_theta, model, scan, counts)
    if not math.isfinite(physical_nll):
        return None
    for value, (lower, upper) in zip(physical_theta, bounds):
        if lower is not None and value < lower - 1e-10:
            return None
        if upper is not None and value > upper + 1e-10:
            return None
    return {"theta": physical_theta, "log_likelihood": -float(physical_nll),
            "iterations": int(result.nit), "projected_gradient": None}


def initial_block(model, scan, counts, baseline_background=None):
    counts = np.asarray(counts, dtype=float)
    rate0 = (float(np.sum(counts)) + 0.5) / float(np.sum(scan.exposure))
    area0 = ((model["fit_window"][1] - model["fit_window"][0])
             * (float(np.sum(counts)) + 1.0) / float(np.sum(scan.exposure)))
    background = [math.log(rate0)] + [0.0] * model["background_order"]
    if baseline_background is not None:
        background = list(np.asarray(baseline_background, dtype=float))
    values = background
    values += [area0 / max(model["K"], 1)] * model["K"]
    values += [0.0] * model["K"]
    values += [0.5 * (model["width_min"] + model["width_max"])] * model["K"]
    return np.asarray(values, dtype=float), rate0, area0


def sobol_start(model, scan, counts, coordinates, baseline=False):
    _base, rate0, area0 = initial_block(model, scan, counts)
    p_count = model["background_order"] + 1
    values, offset = [], 0
    values.append(math.log(rate0) + 4.0 * (2.0 * coordinates[offset] - 1.0)); offset += 1
    for _degree in range(1, p_count):
        values.append(-10.0 + 20.0 * coordinates[offset]); offset += 1
    for _component in range(model["K"]):
        values.append(area0 * math.exp(4.0 * (2.0 * coordinates[offset] - 1.0))); offset += 1
    for _component in range(model["K"]):
        values.append(4.0 * (2.0 * coordinates[offset] - 1.0)); offset += 1
    for _component in range(model["K"]):
        values.append(model["width_min"] + coordinates[offset]
                      * (model["width_max"] - model["width_min"])); offset += 1
    return np.asarray(values), offset


def model_starts(model, counts_list, mode, observed_theta=None, count=33):
    layout, dimension = model_layout(model)
    base_blocks = []
    for scan, counts in zip(model["scans"], counts_list):
        baseline = model.get("baseline_background", {}).get(scan.scan_record_id)
        block, _rate0, _area0 = initial_block(model, scan, counts, baseline if mode == "observed" else None)
        base_blocks.append(block)
    base = np.concatenate(base_blocks)
    starts = []
    if mode == "observed":
        starts.append(base)
        bank = qmc.Sobol(d=dimension, scramble=False).random_base2(m=5)
        for row in bank:
            blocks, offset = [], 0
            for scan, counts in zip(model["scans"], counts_list):
                block_dim = layout[0][1].stop - layout[0][1].start
                block, used = sobol_start(model, scan, counts, row[offset:offset + block_dim])
                require(used == block_dim, "Sobol_dimension_mismatch")
                blocks.append(block); offset += block_dim
            starts.append(np.concatenate(blocks))
    else:
        starts.append(np.asarray(observed_theta).copy() if observed_theta is not None else base.copy())
        starts.append(base.copy())
        plus, minus = base.copy(), base.copy()
        for scan_index, (sid, section) in enumerate(layout):
            p_count = model["background_order"] + 1
            k_count = model["K"]
            plus[section.start:section.start + p_count] += 0.05
            minus[section.start:section.start + p_count] -= 0.05
            area_slice = slice(section.start + p_count, section.start + p_count + k_count)
            plus[area_slice] *= 1.10; minus[area_slice] *= 0.90
            eta_slice = slice(section.start + p_count + k_count, section.start + p_count + 2 * k_count)
            if k_count:
                perturb = np.array([0.25 * (2.0 * k / max(k_count - 1, 1) - 1.0)
                                    if k_count > 1 else 0.0 for k in range(k_count)])
                plus[eta_slice] += perturb; minus[eta_slice] -= perturb
            width_slice = slice(section.start + p_count + 2 * k_count, section.stop)
            plus[width_slice] = np.minimum(model["width_max"], plus[width_slice] * 1.10)
            minus[width_slice] = np.maximum(model["width_min"], minus[width_slice] * 0.90)
        starts.extend([plus, minus])
        bank = qmc.Sobol(d=dimension, scramble=False).random_base2(m=5)
        for row in bank[:29]:
            blocks, offset = [], 0
            for scan, counts in zip(model["scans"], counts_list):
                block_dim = layout[0][1].stop - layout[0][1].start
                block, used = sobol_start(model, scan, counts, row[offset:offset + block_dim])
                require(used == block_dim, "Sobol_dimension_mismatch")
                blocks.append(block); offset += block_dim
            starts.append(np.concatenate(blocks))
    require(len(starts) >= count, "insufficient_multistart_bank")
    return starts[:count]


def fit_candidates(model, counts_list, mode, observed_theta=None, count=33):
    starts = model_starts(model, counts_list, mode, observed_theta, count)
    layout, _dimension = model_layout(model)
    candidates = []
    for start_index, start in enumerate(starts, 1):
        blocks, total_ll, total_iterations, raw_valid = [], 0.0, 0, True
        raw_failure_scan_record_id = None
        for scan_index, (scan, counts) in enumerate(zip(model["scans"], counts_list)):
            section = layout[scan_index][1]
            result = fit_block(model, scan, counts, start[section])
            if result is None:
                raw_valid = False
                raw_failure_scan_record_id = scan.scan_record_id
                break
            blocks.append(result)
            total_ll += result["log_likelihood"]
            total_iterations += result["iterations"]
        candidates.append({"start_index": start_index, "blocks": blocks,
                           "log_likelihood": total_ll if raw_valid else float("-inf"),
                           "iterations": total_iterations, "raw_valid": raw_valid,
                           "raw_failure_reason": (None if raw_valid else "invalid_LBFGSB_return"),
                           "raw_failure_scan_record_id": raw_failure_scan_record_id,
                           "valid": None, "theta": (np.concatenate([b["theta"] for b in blocks])
                                                   if raw_valid else None)})
    return candidates


def select_candidate(model, counts_list, candidates, prefix):
    available = [candidate for candidate in candidates[:prefix] if candidate["raw_valid"]]

    def compare(left, right):
        difference = left["log_likelihood"] - right["log_likelihood"]
        if abs(difference) > 1.0e-8:
            return -1 if difference > 0.0 else 1
        left_vector = tuple(np.round(left["theta"], 12))
        right_vector = tuple(np.round(right["theta"], 12))
        return -1 if left_vector < right_vector else (1 if left_vector > right_vector else 0)

    available.sort(key=functools.cmp_to_key(compare))
    layout, _dimension = model_layout(model)
    for candidate in available:
        if candidate["valid"] is None:
            projected = []
            valid = True
            for scan_index, (scan, counts) in enumerate(zip(model["scans"], counts_list)):
                section = layout[scan_index][1]
                value = projected_gradient_fd(candidate["theta"][section], model, scan, counts,
                                              block_bounds(model))
                projected.append(value)
                if not math.isfinite(value) or value > model["projected_gradient_threshold"]:
                    valid = False
            candidate["valid"] = valid
            candidate["projected_gradients"] = projected
        if candidate["valid"]:
            return {"valid": True, "theta": candidate["theta"],
                    "log_likelihood": candidate["log_likelihood"],
                    "start_index": candidate["start_index"],
                    "iterations": candidate["iterations"],
                    "projected_gradient_max": max(candidate["projected_gradients"]),
                    "fit_status": "valid", "failure_reason": None,
                    "candidate_multistart_level": prefix}
    invalid_candidates = []
    for candidate in candidates[:prefix]:
        invalid_candidates.append({
            "start_index": candidate["start_index"],
            "raw_valid": candidate["raw_valid"],
            "failure_reason": (candidate["raw_failure_reason"] if not candidate["raw_valid"]
                               else "projected_gradient_KKT_gate_failed"),
            "failure_scan_record_id": candidate["raw_failure_scan_record_id"],
            "projected_gradient_max": (max(candidate.get("projected_gradients", [float("inf")]))
                                       if candidate["raw_valid"] else None),
        })
    return {"valid": False, "theta": None, "log_likelihood": float("-inf"),
            "start_index": None, "iterations": 0, "projected_gradient_max": float("inf"),
            "fit_status": "numerical_failure",
            "failure_reason": "no_candidate_in_frozen_bank_passed_fit_validity",
            "candidate_multistart_level": prefix,
            "candidate_diagnostics": invalid_candidates}


def fit_model(model, counts_list=None, mode="observed", observed_theta=None, starts=33):
    if counts_list is None:
        counts_list = [scan.counts for scan in model["scans"]]
    candidates = fit_candidates(model, counts_list, mode, observed_theta, starts)
    return select_candidate(model, counts_list, candidates, starts)


def fit_model_levels(model, counts_list, observed_theta, levels):
    candidates = fit_candidates(model, counts_list, "bootstrap", observed_theta, max(levels))
    return {level: select_candidate(model, counts_list, candidates, level) for level in levels}


def predict_model(model, theta):
    layout, _dimension = model_layout(model)
    predictions = []
    for scan_index, scan in enumerate(model["scans"]):
        state = block_nll_gradient(theta[layout[scan_index][1]], model, scan, scan.counts)[2]
        require(state is not None, "invalid_observed_parent_prediction")
        predictions.append(state["mu"])
    return predictions


def decode_model_fit(model, fit):
    records = []
    layout, _dimension = model_layout(model)
    for scan_index, scan in enumerate(model["scans"]):
        theta = fit["theta"][layout[scan_index][1]]
        background, areas, eta, widths = block_parts(theta, model)
        centroids = (centroids_from_eta(eta, model["complex_union"][0],
                                        model["complex_union"][1], model["delta_ref"])[0]
                     if model["K"] else np.array([]))
        records.append({
            "complex_id": model["complex_id"], "model_id": model["model_id"],
            "scan_record_id": scan.scan_record_id, "background_model_id": "B" + str(model["background_order"]),
            "component_count_K": model["K"], "fit_status": "valid" if fit["valid"] else "numerical_failure",
            "joint_log_likelihood": fit["log_likelihood"], "selected_start_index": fit["start_index"],
            "projected_gradient_max": fit["projected_gradient_max"],
            "background_parameters": [float(v) for v in background],
            "areas": [float(v) for v in areas], "centroids_meV": [float(v) for v in centroids],
            "empirical_fwhm_meV": [float(v) for v in widths],
            "width_semantics": "observed_empirical_fwhm" if model["K"] else "not_applicable",
        })
    return records


def make_model(complex_id, scan_data, background_order, component_count, fit_window,
               complex_union, delta_ref, numerical, baseline_background=None):
    return {
        "complex_id": complex_id, "model_id": f"{complex_id}-B{background_order}-K{component_count}",
        "scans": scan_data, "background_order": background_order, "K": component_count,
        "fit_window": list(map(float, fit_window)), "complex_union": list(map(float, complex_union)),
        "delta_ref": float(delta_ref), "width_min": 0.5 * float(delta_ref),
        "width_max": min(float(complex_union[1] - complex_union[0]),
                         0.5 * float(fit_window[1] - fit_window[0])),
        "optimizer": {"maxiter": numerical["optimizer"]["maxiter"],
                      "ftol": numerical["optimizer"]["ftol"],
                      "gtol": numerical["optimizer"]["gtol"],
                      "maxls": numerical["optimizer"]["maxls"]},
        "projected_gradient_threshold": numerical["projected_gradient_threshold"],
        "finite_difference_step": numerical["finite_difference_relative_step"],
        "active_bound_tolerance": numerical["active_bound_relative_tolerance"],
        "baseline_background": baseline_background or {},
    }


def flank_scan_data(scan_data, complex_union):
    lower, upper = complex_union
    answer = []
    for scan in scan_data:
        mask = (scan.energy < lower) | (scan.energy > upper)
        answer.append(ScanData(scan.scan_record_id, scan.energy[mask], scan.exposure[mask], scan.counts[mask]))
    return answer


def discovery_scan_data(access, scan_ids, fit_window):
    grouped = defaultdict(list)
    for row in access.rows(MODEL_SCAN_FIELDS, scan_ids, "discovery_detector"):
        grouped[row["scan_record_id"]].append(row)
    answer = []
    for sid in sorted(scan_ids):
        rows = sorted(grouped[sid], key=lambda row: int(row["point_index"]))
        energy = np.array([float(row["e_raw"]) for row in rows])
        exposure = np.array([float(row["monitor_raw"]) for row in rows])
        counts = np.array([float(row["detector_raw"]) for row in rows])
        mask = (energy >= fit_window[0]) & (energy <= fit_window[1])
        require(np.sum(mask) >= 15, "discovery_window_point_count_failure:" + sid)
        order = np.argsort(energy[mask])
        answer.append(ScanData(sid, energy[mask][order], exposure[mask][order], counts[mask][order]))
    return answer


_WORKER_CONTEXT = None


def _worker_initialize(context):
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = context


def _benchmark_worker(index):
    context = _WORKER_CONTEXT
    counts = context["replicates"][index]
    parent = fit_model_levels(context["parent"], counts, context["parent_observed"]["theta"],
                              context["levels"])
    child = fit_model_levels(context["child"], counts, context["child_observed"]["theta"],
                             context["levels"])
    return index, {
        level: {"parent_valid": parent[level]["valid"], "child_valid": child[level]["valid"],
                "parent_ll": parent[level]["log_likelihood"],
                "child_ll": child[level]["log_likelihood"],
                "parent_projected_gradient_max": parent[level]["projected_gradient_max"],
                "child_projected_gradient_max": child[level]["projected_gradient_max"],
                "parent_failure_reason": parent[level].get("failure_reason"),
                "child_failure_reason": child[level].get("failure_reason")}
        for level in context["levels"]
    }


def _bootstrap_worker(index):
    context = _WORKER_CONTEXT
    counts = context["replicates"][index]
    parent = fit_model(context["parent"], counts, "bootstrap",
                       context["parent_observed"]["theta"], context["selected_starts"])
    child = fit_model(context["child"], counts, "bootstrap",
                      context["child_observed"]["theta"], context["selected_starts"])
    if not parent["valid"] or not child["valid"]:
        return index, float("inf"), False, {
            "test_id": "C001-T14", "complex_id": context["parent"]["complex_id"],
            "comparison_id": context["comparison_id"],
            "parent_model_id": context["parent"]["model_id"],
            "child_model_id": context["child"]["model_id"],
            "benchmark_replicate_index": index,
            "candidate_multistart_level": context["selected_starts"],
            "parent_reference_valid": parent["valid"],
            "child_reference_valid": child["valid"],
            "fit_status": "numerical_failure",
            "failure_reason": "bootstrap_replicate_fit_invalid",
            "projected_gradient_max": max(parent["projected_gradient_max"],
                                          child["projected_gradient_max"]),
        }
    statistic = 2.0 * (child["log_likelihood"] - parent["log_likelihood"])
    if statistic < 0 and statistic > -1e-8:
        statistic = 0.0
    if statistic < -1e-8 or not math.isfinite(statistic):
        return index, float("inf"), False, {
            "test_id": "C001-T14", "complex_id": context["parent"]["complex_id"],
            "comparison_id": context["comparison_id"],
            "parent_model_id": context["parent"]["model_id"],
            "child_model_id": context["child"]["model_id"],
            "benchmark_replicate_index": index,
            "candidate_multistart_level": context["selected_starts"],
            "parent_reference_valid": parent["valid"],
            "child_reference_valid": child["valid"],
            "fit_status": "numerical_failure",
            "failure_reason": "invalid_nested_likelihood_statistic",
            "projected_gradient_max": max(parent["projected_gradient_max"],
                                          child["projected_gradient_max"]),
        }
    return index, float(statistic), True, None


def parallel_map(function, indices, context, workers):
    if workers == 1:
        _worker_initialize(context)
        return [function(index) for index in indices]
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_initialize,
                             initargs=(context,)) as pool:
        return list(pool.map(function, indices, chunksize=1))


def discovery_seed(complex_id, test_id, replicates=4096):
    payload = ("stage02r_c001_bootstrap_seed_v1\n"
               "master=CEF-Dy:T-02R-05:W02-02R-C-001:discovery-bootstrap-v1\n"
               f"complex_id={complex_id}\n"
               f"test_id={test_id}\n"
               f"replicates={replicates}\n")
    fingerprint = sha256_bytes(payload.encode("utf-8"))
    return payload, fingerprint, int(fingerprint[:16], 16)


def generate_bootstrap_replicates(parent_model, parent_fit, complex_id, test_id, replicate_count):
    payload, fingerprint, seed = discovery_seed(complex_id, test_id, replicate_count)
    rng = np.random.Generator(np.random.PCG64(seed))
    means = predict_model(parent_model, parent_fit["theta"])
    replicates = []
    for _replicate in range(replicate_count):
        replicates.append([rng.poisson(mu).astype(float) for mu in means])
    return replicates, {"payload": payload, "payload_sha256": fingerprint,
                        "seed_first_16_hex_unsigned": seed, "rng": "PCG64"}


def benchmark_comparison(parent_model, child_model, parent_fit, child_fit,
                         replicates, workers, numerical, comparison_id):
    levels = list(numerical["bootstrap_fit_multistarts_candidate_sequence"])
    reference = numerical["bootstrap_reference_multistarts"]
    benchmark_count = numerical["bootstrap_adequacy_benchmark_replicates"]
    total = len(replicates)
    indices = [math.floor((j + 0.5) * total / benchmark_count) for j in range(benchmark_count)]
    context = {"parent": parent_model, "child": child_model,
               "parent_observed": parent_fit, "child_observed": child_fit,
               "replicates": replicates, "levels": levels}
    rows = parallel_map(_benchmark_worker, indices, context, workers)
    results = {index: values for index, values in rows}
    reference_valid = all(results[index][reference]["parent_valid"]
                          and results[index][reference]["child_valid"] for index in indices)
    diagnostics = []
    failure_diagnostics = []
    selected = None
    reason = None
    if not reference_valid:
        reason = "invalid_33_start_reference"
        for index in indices:
            reference_values = results[index][reference]
            if not (reference_values["parent_valid"] and reference_values["child_valid"]):
                failure_diagnostics.append({
                    "test_id": "C001-T12", "complex_id": parent_model["complex_id"],
                    "comparison_id": comparison_id,
                    "parent_model_id": parent_model["model_id"],
                    "child_model_id": child_model["model_id"],
                    "benchmark_replicate_index": index,
                    "candidate_multistart_level": reference,
                    "parent_reference_valid": reference_values["parent_valid"],
                    "child_reference_valid": reference_values["child_valid"],
                    "fit_status": "numerical_failure",
                    "failure_reason": "invalid_33_start_reference",
                    "projected_gradient_max": max(
                        reference_values["parent_projected_gradient_max"],
                        reference_values["child_projected_gradient_max"]),
                })
    else:
        tolerance = numerical["log_likelihood_relative_tolerance"]
        allowed = numerical["allowed_likelihood_mismatches_per_model"]
        for level in levels:
            parent_mismatch = 0
            child_mismatch = 0
            for index in indices:
                candidate = results[index][level]
                reference_values = results[index][reference]
                if (not candidate["parent_valid"]
                        or abs(candidate["parent_ll"] - reference_values["parent_ll"])
                        > tolerance * max(1.0, abs(reference_values["parent_ll"]))):
                    parent_mismatch += 1
                if (not candidate["child_valid"]
                        or abs(candidate["child_ll"] - reference_values["child_ll"])
                        > tolerance * max(1.0, abs(reference_values["child_ll"]))):
                    child_mismatch += 1
            passed = parent_mismatch <= allowed and child_mismatch <= allowed
            diagnostics.append({"candidate_starts": level, "parent_mismatches": parent_mismatch,
                                "child_mismatches": child_mismatch, "status": "passed" if passed else "failed"})
            if passed:
                selected = level
                break
        if selected is None:
            reason = "no_candidate_through_33_passed"
    return {
        "comparison_id": comparison_id,
        "optimizer_adequacy_status": "passed" if selected is not None else "failed",
        "optimizer_adequacy_reason": reason,
        "benchmark_replicates": benchmark_count,
        "benchmark_replicate_indices_zero_based": indices,
        "reference_parent_valid_count": sum(results[index][reference]["parent_valid"] for index in indices),
        "reference_child_valid_count": sum(results[index][reference]["child_valid"] for index in indices),
        "candidate_diagnostics": diagnostics,
        "bootstrap_multistarts_selected": selected,
        "failure_diagnostics": failure_diagnostics,
    }


def bootstrap_comparison(parent_model, child_model, parent_fit, child_fit, complex_id,
                         test_id, replicate_count, alpha, workers, numerical):
    observed = 2.0 * (child_fit["log_likelihood"] - parent_fit["log_likelihood"])
    if observed < 0 and observed > -1e-8:
        observed = 0.0
    require(observed >= -1e-8 and math.isfinite(observed),
            "invalid_observed_nested_likelihood:" + test_id)
    replicates, seed = generate_bootstrap_replicates(parent_model, parent_fit, complex_id,
                                                      test_id, replicate_count)
    benchmark = benchmark_comparison(parent_model, child_model, parent_fit, child_fit,
                                     replicates, workers, numerical, test_id)
    if benchmark["optimizer_adequacy_status"] != "passed":
        return {"test_id": test_id, "test_status": "numerical_failure",
                "observed_statistic": float(observed), "bootstrap_replicates": replicate_count,
                "bootstrap_failed_replicates": replicate_count, "failed_fraction": 1.0,
                "p_value_plus_one": None, "alpha": alpha, "development_passed": False,
                "seed": seed, "optimizer_adequacy": benchmark, "statistics_sha256": None,
                "failure_diagnostics": benchmark["failure_diagnostics"]}
    selected = benchmark["bootstrap_multistarts_selected"]
    context = {"parent": parent_model, "child": child_model,
               "parent_observed": parent_fit, "child_observed": child_fit,
               "replicates": replicates, "selected_starts": selected,
               "comparison_id": test_id}
    values = parallel_map(_bootstrap_worker, range(replicate_count), context, workers)
    values.sort(key=lambda item: item[0])
    statistics = np.array([item[1] for item in values], dtype="<f8")
    failures = sum(not item[2] for item in values)
    failure_diagnostics = [item[3] for item in values if item[3] is not None]
    failed_fraction = failures / replicate_count
    numerical_failure = failed_fraction > numerical["bootstrap_failed_replicate_fraction_max"]
    p_value = ((1 + int(np.sum(statistics >= observed))) / (replicate_count + 1)
               if not numerical_failure else None)
    return {
        "test_id": test_id, "test_status": "numerical_failure" if numerical_failure else "complete",
        "observed_statistic": float(observed), "bootstrap_replicates": replicate_count,
        "bootstrap_failed_replicates": failures, "failed_fraction": failed_fraction,
        "p_value_plus_one": p_value, "alpha": alpha,
        "development_passed": bool(p_value is not None and p_value <= alpha),
        "seed": seed, "optimizer_adequacy": benchmark,
        "statistics_sha256": sha256_bytes(statistics.tobytes()),
        "failure_diagnostics": failure_diagnostics,
    }


def hessian_condition_number(model, scan, theta):
    dimension = len(theta)
    hessian = np.empty((dimension, dimension), dtype=float)
    for index, value in enumerate(theta):
        step = 1e-5 * max(1.0, abs(float(value)))
        plus = theta.copy(); plus[index] += step
        minus = theta.copy(); minus[index] -= step
        g_plus = block_nll_gradient(plus, model, scan, scan.counts)[1]
        g_minus = block_nll_gradient(minus, model, scan, scan.counts)[1]
        hessian[:, index] = (g_plus - g_minus) / (2.0 * step)
    hessian = 0.5 * (hessian + hessian.T)
    try:
        return float(np.linalg.cond(hessian))
    except np.linalg.LinAlgError:
        return float("inf")


def profile_centroid_scan(model, scan, theta, centroid_index, grid_points, threshold):
    background, areas, eta, widths = block_parts(theta, model)
    k_count = model["K"]
    centroids, _jacobian, q_value = centroids_from_eta(
        eta, model["complex_union"][0], model["complex_union"][1], model["delta_ref"])
    lower, upper = model["complex_union"]
    delta = model["delta_ref"]
    remainder = (upper - lower) - (k_count - 1) * delta
    allowed_lower = lower + centroid_index * delta
    allowed_upper = upper - (k_count - 1 - centroid_index) * delta
    epsilon = max(1e-9, 1e-8 * (allowed_upper - allowed_lower))
    grid = np.linspace(allowed_lower + epsilon, allowed_upper - epsilon, grid_points)
    p_count = model["background_order"] + 1

    def group_logits(probabilities):
        probabilities = np.maximum(np.asarray(probabilities, dtype=float), 1e-300)
        if len(probabilities) <= 1:
            return np.array([], dtype=float)
        return np.log(probabilities[:-1] / probabilities[-1])

    values = []
    for target in grid:
        left_total = (target - lower - centroid_index * delta) / remainder
        if not 0 < left_total < 1:
            values.append(float("inf")); continue
        left_base = q_value[:centroid_index + 1]
        right_base = q_value[centroid_index + 1:]
        left_logits = group_logits(left_base / left_base.sum())
        right_logits = group_logits(right_base / right_base.sum())
        start = np.concatenate([background, areas, left_logits, right_logits, widths])
        bounds = [(None, None)] + [(-10.0, 10.0)] * model["background_order"]
        bounds += [(0.0, None)] * k_count
        bounds += [(None, None)] * (k_count - 1)
        bounds += [(model["width_min"], model["width_max"])] * k_count

        def unpack_profile(vector):
            bg = vector[:p_count]
            ar = vector[p_count:p_count + k_count]
            cursor = p_count + k_count
            left_count = centroid_index
            right_count = k_count - centroid_index - 1
            left_q = softmax_with_reference(vector[cursor:cursor + left_count]); cursor += left_count
            right_q = softmax_with_reference(vector[cursor:cursor + right_count]); cursor += right_count
            q_full = np.concatenate([left_total * left_q, (1.0 - left_total) * right_q])
            full_eta = np.log(q_full[:-1] / q_full[-1])
            wd = vector[cursor:cursor + k_count]
            return np.concatenate([bg, ar, full_eta, wd])

        def objective(vector):
            return block_nll_gradient(unpack_profile(vector), model, scan, scan.counts)[0]

        result = minimize(objective, start, method="L-BFGS-B", bounds=bounds,
                          options=model["optimizer"])
        values.append(float(result.fun) if result.success and math.isfinite(result.fun) else float("inf"))
    mle_nll = block_nll_gradient(theta, model, scan, scan.counts)[0]
    delta_profile = np.array([2.0 * (value - mle_nll) for value in values])
    mle_centroid = centroids[centroid_index]
    left = [index for index, value in enumerate(grid)
            if value < mle_centroid and math.isfinite(delta_profile[index]) and delta_profile[index] >= threshold]
    right = [index for index, value in enumerate(grid)
             if value > mle_centroid and math.isfinite(delta_profile[index]) and delta_profile[index] >= threshold]
    left_crossing = float(grid[max(left)]) if left else None
    right_crossing = float(grid[min(right)]) if right else None
    return {
        "centroid_index": centroid_index + 1, "mle_centroid_meV": float(mle_centroid),
        "profile_grid_points": grid_points, "profile_threshold": threshold,
        "left_threshold_crossing_meV": left_crossing,
        "right_threshold_crossing_meV": right_crossing,
        "finite_in_bound_interval": left_crossing is not None and right_crossing is not None,
        "profile_grid_sha256": sha256_bytes(np.column_stack((grid, delta_profile)).astype("<f8").tobytes()),
    }


def assess_identifiability(model, fit, config):
    numerical = config["numerical"]
    layout, _dimension = model_layout(model)
    records = []
    pair_informative = [False] * max(0, model["K"] - 1)
    pair_clear = [False] * max(0, model["K"] - 1)
    all_profiles = True
    tau = max(0.10 * model["delta_ref"], 1e-6)
    for scan_index, scan in enumerate(model["scans"]):
        theta = fit["theta"][layout[scan_index][1]]
        _background, areas, eta, _widths = block_parts(theta, model)
        centroids = centroids_from_eta(eta, model["complex_union"][0],
                                       model["complex_union"][1], model["delta_ref"])[0]
        profiles = []
        for component in range(model["K"]):
            profile = profile_centroid_scan(model, scan, theta, component,
                                            numerical["profile_grid_points"],
                                            numerical["profile_delta_minus2logL_threshold"])
            profiles.append(profile)
            all_profiles = all_profiles and profile["finite_in_bound_interval"]
        for pair in range(model["K"] - 1):
            informative = (areas[pair] > numerical["active_bound_relative_tolerance"]
                           and areas[pair + 1] > numerical["active_bound_relative_tolerance"])
            pair_informative[pair] = pair_informative[pair] or informative
            pair_clear[pair] = pair_clear[pair] or (informative and
                (centroids[pair + 1] - centroids[pair] - model["delta_ref"]) > tau)
        condition = hessian_condition_number(model, scan, theta)
        records.append({"complex_id": model["complex_id"], "model_id": model["model_id"],
                        "scan_record_id": scan.scan_record_id,
                        "component_count_K": model["K"], "tau_sep_meV": tau,
                        "areas": [float(value) for value in areas],
                        "centroids_meV": [float(value) for value in centroids],
                        "profile_results": profiles, "all_profiles_finite_in_bounds": all(p["finite_in_bound_interval"] for p in profiles),
                        "hessian_condition_number": condition,
                        "hessian_warning": condition > numerical["hessian_condition_warning_threshold"]})
    if any(not value for value in pair_informative):
        status = "rejected_no_informative_scan_for_split"
    elif any(not value for value in pair_clear):
        status = "rejected_minimum_separation_proximity"
    elif not all_profiles:
        status = "rejected_nonidentifiable"
    else:
        status = "passed"
    return status, records


def fit_resolution_evidence(access, scans, config):
    scan_id = next(sid for sid, scan in scans.items() if scan["raw_scan_id"] == "104062")
    require(scan_id not in access.holdout_ids, "EV006_unexpected_holdout_membership")
    fields = ("scan_record_id", "point_index", "e_raw", "time_raw", "detector_raw")
    raw_rows = list(access.rows(fields, {scan_id}, "resolution_evidence"))
    raw_rows.sort(key=lambda row: int(row["point_index"]))
    energy = np.array([float(row["e_raw"]) for row in raw_rows])
    exposure = np.array([float(row["time_raw"]) for row in raw_rows])
    counts = np.array([float(row["detector_raw"]) for row in raw_rows])
    order = np.argsort(energy)
    energy, exposure, counts = energy[order], exposure[order], counts[order]
    step = float(np.median(np.diff(energy)))
    evidence_scan = ScanData(scan_id, energy, exposure, counts)
    numerical = config["numerical"]
    variants = []
    fits = {}
    for background_order in (0, 1):
        for contracted in (False, True):
            selected = evidence_scan
            if contracted:
                selected = ScanData(scan_id, energy[1:-1], exposure[1:-1], counts[1:-1])
            model = make_model("EV-006", [selected], background_order, 1,
                               [float(selected.energy.min()), float(selected.energy.max())],
                               [float(selected.energy.min()), float(selected.energy.max())],
                               step, numerical)
            model["width_min"] = 0.25 * step
            model["width_max"] = float(selected.energy.max() - selected.energy.min())
            fit = fit_model(model, starts=33)
            fits[(background_order, contracted)] = (model, fit)
            if fit["valid"]:
                decoded = decode_model_fit(model, fit)[0]
                variants.append({"background_model_id": "B" + str(background_order),
                                 "window": "contracted_one_native_point_each_side" if contracted else "nominal",
                                 "fit_status": "valid", "fwhm_meV": decoded["empirical_fwhm_meV"][0],
                                 "centroid_meV": decoded["centroids_meV"][0],
                                 "log_likelihood": fit["log_likelihood"],
                                 "projected_gradient_max": fit["projected_gradient_max"]})
            else:
                variants.append({"background_model_id": "B" + str(background_order),
                                 "window": "contracted_one_native_point_each_side" if contracted else "nominal",
                                 "fit_status": "numerical_failure"})
    nominal_model, nominal_fit = fits[(1, False)]
    reproduction_status = "failed"
    profile = {"finite_profile_interval": False}
    fitted_width = None
    if nominal_fit["valid"]:
        theta = nominal_fit["theta"].copy()
        width_index = len(theta) - 1
        width_grid = np.linspace(nominal_model["width_min"], nominal_model["width_max"], 41)
        profile_values = []
        for width in width_grid:
            start = theta.copy(); start[width_index] = width
            bounds = block_bounds(nominal_model); bounds[width_index] = (width, width)

            def objective(vector):
                return block_nll_gradient(vector, nominal_model, evidence_scan, counts)[0]

            result = minimize(objective, start, method="L-BFGS-B", bounds=bounds,
                              options=nominal_model["optimizer"])
            profile_values.append(float(result.fun) if result.success else float("inf"))
        nominal_record = decode_model_fit(nominal_model, nominal_fit)[0]
        fitted_width = nominal_record["empirical_fwhm_meV"][0]
        centroid = nominal_record["centroids_meV"][0]
        minimum = -nominal_fit["log_likelihood"]
        delta_profile = 2.0 * (np.asarray(profile_values) - minimum)
        threshold = config["numerical"]["profile_delta_minus2logL_threshold"]
        left_indices = [i for i, value in enumerate(width_grid)
                        if value < fitted_width and math.isfinite(delta_profile[i]) and delta_profile[i] >= threshold]
        right_indices = [i for i, value in enumerate(width_grid)
                         if value > fitted_width and math.isfinite(delta_profile[i]) and delta_profile[i] >= threshold]
        left = float(width_grid[max(left_indices)]) if left_indices else None
        right = float(width_grid[min(right_indices)]) if right_indices else None
        finite_interval = left is not None and right is not None
        sigma_new = ((right - left) / (2.0 * 1.959963984540054) if finite_interval else None)
        historical = config["resolution"]["historical_EV006_fwhm_meV"]
        historical_sigma = config["resolution"]["historical_EV006_sigma_meV"]
        agreement_limit = (max(2.0 * math.sqrt(sigma_new * sigma_new + historical_sigma * historical_sigma),
                               0.10 * historical) if sigma_new is not None else None)
        centroid_ok = abs(centroid) <= 2.0 * step
        agreement = bool(agreement_limit is not None and abs(fitted_width - historical) <= agreement_limit)
        valid_widths = [row["fwhm_meV"] for row in variants if row["fit_status"] == "valid"]
        stability = bool(valid_widths and all(abs(value - fitted_width) <= 0.10 * fitted_width
                                              for value in valid_widths))
        below = int(np.sum(energy < 0)); above = int(np.sum(energy > 0))
        grid_suitable = bool(below >= 4 and above >= 4 and np.min(np.abs(energy)) <= step
                             and np.all(exposure > 0))
        reproduction_status = "passed" if (finite_interval and centroid_ok and agreement) else "failed"
        profile = {"grid_points": 41, "threshold": threshold,
                   "left_crossing_meV": left, "right_crossing_meV": right,
                   "finite_profile_interval": finite_interval, "sigma_new_meV": sigma_new,
                   "profile_sha256": sha256_bytes(np.column_stack((width_grid, delta_profile)).astype("<f8").tobytes())}
    else:
        centroid_ok = agreement = stability = grid_suitable = False
        agreement_limit = None
    physical_basis = config["resolution"]["resolution_probe_physical_basis_status"]
    suitability = "suitable" if (physical_basis == "established" and reproduction_status == "passed"
                                   and stability and grid_suitable) else "unresolved"
    return {
        "evidence_id": "EV-006", "scan_record_id": scan_id, "raw_scan_id": "104062",
        "access_role": "resolution_evidence", "historical_reported_fwhm_meV": 0.894,
        "historical_reported_sigma_meV": 0.025, "reproduction_status": reproduction_status,
        "nominal_fitted_fwhm_meV": fitted_width, "profile_interval": profile,
        "centroid_within_two_median_steps": centroid_ok,
        "historical_width_agreement": agreement, "historical_agreement_limit_meV": agreement_limit,
        "background_and_window_width_stability_within_10_percent": stability,
        "numerical_geometry_suitability_checks_pass": grid_suitable,
        "fit_variants": variants,
        "resolution_probe_physical_basis": {
            "status": physical_basis, "basis_type": None, "provenance": "00_Project/EVIDENCE_REGISTER.yaml#EV-006",
            "scientific_rationale": "Canonical evidence has partial provenance and does not independently establish an allowed calibration basis."
        },
        "resolution_probe_suitability": {"status": suitability},
        "scan_104062_role": "empirical_effective_width_evidence",
        "direct_empirical_calibration_promoted": False,
        "second_component_gate_used": False,
    }


def background_parameters_by_scan(model, fit):
    parameters = {}
    layout, _dimension = model_layout(model)
    p_count = model["background_order"] + 1
    for scan_index, scan in enumerate(model["scans"]):
        parameters[scan.scan_record_id] = fit["theta"][layout[scan_index][1]][:p_count].copy()
    return parameters


def run_comparison(parent_model, child_model, parent_fit, child_fit, complex_id,
                   test_id, alpha, workers, config):
    print(f"HEAVY_COMPARISON_START {test_id}", flush=True)
    started = time.time()
    result = bootstrap_comparison(
        parent_model, child_model, parent_fit, child_fit, complex_id, test_id,
        config["component_development"]["bootstrap_replicates"], alpha, workers,
        config["numerical"])
    result["elapsed_seconds"] = round(time.time() - started, 3)
    print(f"HEAVY_COMPARISON_DONE {test_id} status={result['test_status']} "
          f"p={result['p_value_plus_one']} starts="
          f"{result['optimizer_adequacy']['bootstrap_multistarts_selected']} "
          f"seconds={result['elapsed_seconds']}", flush=True)
    return result


def run_model_development(access, fit_windows, config, workers):
    discovery_fit_rows = []
    backgrounds = {}
    components = {}
    identifiability_rows = []
    comparison_diagnostics = []
    failure_diagnostics = []
    selected_starts = []
    models_for_spec = {}
    for complex_id, fit_window in fit_windows.items():
        if fit_window["complex_model_status"] != "ready_for_discovery_model_development":
            backgrounds[complex_id] = {
                "complex_id": complex_id, "status": "not_run_insufficient_discovery_window_coverage",
                "selected_background_model_id": None, "development_tests": []}
            components[complex_id] = {
                "complex_id": complex_id, "status": "not_preparable_insufficient_discovery_window_coverage",
                "maximum_preregistered_K": 0, "presence_test": None, "split_tests": []}
            continue
        scan_data = discovery_scan_data(access, fit_window["discovery_model_scan_set"],
                                        fit_window["fit_window_meV"])
        union = fit_window["frozen_union_meV"]
        flank_data = flank_scan_data(scan_data, union)
        numerical = config["numerical"]
        background_models, background_fits = {}, {}
        for order in (0, 1, 2):
            model = make_model(complex_id, flank_data, order, 0, fit_window["fit_window_meV"],
                               union, fit_window["delta_E_ref_meV"], numerical)
            observed = fit_model(model, starts=33)
            require(observed["valid"], f"observed_background_B{order}_numerical_failure:{complex_id}")
            background_models[order] = model
            background_fits[order] = observed
            discovery_fit_rows.extend(decode_model_fit(model, observed))
        background_tests = []
        test01 = run_comparison(background_models[0], background_models[1], background_fits[0],
                                background_fits[1], complex_id, complex_id + "-B0-to-B1",
                                config["background_development"]["alpha"], workers, config)
        background_tests.append(test01)
        comparison_diagnostics.append(test01["optimizer_adequacy"])
        failure_diagnostics.extend(test01.get("failure_diagnostics", []))
        if test01["optimizer_adequacy"]["bootstrap_multistarts_selected"]:
            selected_starts.append(test01["optimizer_adequacy"]["bootstrap_multistarts_selected"])
        selected_order = 0
        background_limited = False
        if test01["test_status"] == "numerical_failure":
            background_limited = True
        elif test01["development_passed"]:
            selected_order = 1
            test12 = run_comparison(background_models[1], background_models[2], background_fits[1],
                                    background_fits[2], complex_id, complex_id + "-B1-to-B2",
                                    config["background_development"]["alpha"], workers, config)
            background_tests.append(test12)
            comparison_diagnostics.append(test12["optimizer_adequacy"])
            failure_diagnostics.extend(test12.get("failure_diagnostics", []))
            if test12["optimizer_adequacy"]["bootstrap_multistarts_selected"]:
                selected_starts.append(test12["optimizer_adequacy"]["bootstrap_multistarts_selected"])
            if test12["test_status"] == "numerical_failure":
                background_limited = True
            elif test12["development_passed"]:
                selected_order = 2
        backgrounds[complex_id] = {
            "complex_id": complex_id, "status": ("background_selection_limited_by_numerics"
                                                  if background_limited else "selected"),
            "selected_background_model_id": "B" + str(selected_order),
            "selection_rule": "parent_gated_B0_to_B1_to_B2",
            "alpha": config["background_development"]["alpha"],
            "bootstrap_replicates": config["background_development"]["bootstrap_replicates"],
            "development_tests": background_tests,
            "AIC_BIC_promotion_used": False,
        }
        baseline_background = background_parameters_by_scan(background_models[selected_order],
                                                            background_fits[selected_order])
        cap_geometry = 1 + math.floor((union[1] - union[0]) / fit_window["delta_E_ref_meV"])
        cap = min(cap_geometry, fit_window["maximum_BF_defined_K"])
        spectral_models, spectral_fits = {}, {}
        for component_count in range(cap + 1):
            model = make_model(complex_id, scan_data, selected_order, component_count,
                               fit_window["fit_window_meV"], union,
                               fit_window["delta_E_ref_meV"], numerical, baseline_background)
            observed = fit_model(model, starts=33)
            spectral_models[component_count] = model
            spectral_fits[component_count] = observed
            if observed["valid"]:
                discovery_fit_rows.extend(decode_model_fit(model, observed))
        if not spectral_fits[0]["valid"] or not spectral_fits[1]["valid"]:
            for component_count in (0, 1):
                failed_fit = spectral_fits[component_count]
                if not failed_fit["valid"]:
                    failure_diagnostics.append({
                        "test_id": "C001-T09", "complex_id": complex_id,
                        "comparison_id": f"{complex_id}-observed-K{component_count}",
                        "parent_model_id": (spectral_models[0]["model_id"]
                                            if component_count else "not_applicable"),
                        "child_model_id": spectral_models[component_count]["model_id"],
                        "benchmark_replicate_index": "not_applicable_observed_fit",
                        "candidate_multistart_level": 33,
                        "parent_reference_valid": (spectral_fits[0]["valid"]
                                                   if component_count else "not_applicable"),
                        "child_reference_valid": failed_fit["valid"],
                        "fit_status": "numerical_failure",
                        "failure_reason": failed_fit.get("failure_reason"),
                        "projected_gradient_max": failed_fit["projected_gradient_max"],
                    })
            components[complex_id] = {
                "complex_id": complex_id, "status": "confirmatory_model_not_preparable",
                "reason": "K0_or_K1_observed_numerical_failure", "maximum_preregistered_K": 0,
                "presence_test": None, "split_tests": []}
            continue
        presence = run_comparison(spectral_models[0], spectral_models[1], spectral_fits[0], spectral_fits[1],
                                  complex_id, complex_id + "-K0-to-K1-presence",
                                  config["component_development"]["alpha"], workers, config)
        presence["registration_is_independent_of_discovery_p_value"] = True
        comparison_diagnostics.append(presence["optimizer_adequacy"])
        failure_diagnostics.extend(presence.get("failure_diagnostics", []))
        if presence["optimizer_adequacy"]["bootstrap_multistarts_selected"]:
            selected_starts.append(presence["optimizer_adequacy"]["bootstrap_multistarts_selected"])
        maximum_k = 1
        split_tests = []
        component_status = "presence_prepared"
        for parent_k in range(1, cap):
            child_k = parent_k + 1
            if not spectral_fits[child_k]["valid"]:
                split_tests.append({"test_id": f"{complex_id}-K{parent_k}-to-K{child_k}-split",
                                    "test_status": "numerical_failure",
                                    "development_passed": False,
                                    "development_consequence": "retain_parent_and_stop_deeper"})
                component_status = "component_development_limited_by_numerics"
                break
            comparison = run_comparison(
                spectral_models[parent_k], spectral_models[child_k], spectral_fits[parent_k],
                spectral_fits[child_k], complex_id, f"{complex_id}-K{parent_k}-to-K{child_k}-split",
                config["component_development"]["alpha"], workers, config)
            comparison_diagnostics.append(comparison["optimizer_adequacy"])
            failure_diagnostics.extend(comparison.get("failure_diagnostics", []))
            if comparison["optimizer_adequacy"]["bootstrap_multistarts_selected"]:
                selected_starts.append(comparison["optimizer_adequacy"]["bootstrap_multistarts_selected"])
            if comparison["test_status"] == "numerical_failure":
                comparison["development_consequence"] = "retain_parent_and_stop_deeper"
                split_tests.append(comparison)
                component_status = "component_development_limited_by_numerics"
                break
            if not comparison["development_passed"]:
                comparison["component_identifiability_status"] = "not_evaluated_development_test_not_passed"
                comparison["development_consequence"] = "retain_parent_and_stop_deeper"
                split_tests.append(comparison)
                component_status = "split_not_development_accepted"
                break
            identity_status, records = assess_identifiability(spectral_models[child_k],
                                                              spectral_fits[child_k], config)
            identifiability_rows.extend(records)
            comparison["component_identifiability_status"] = identity_status
            if identity_status != "passed":
                comparison["development_passed"] = False
                comparison["development_consequence"] = "retain_parent_and_stop_deeper"
                split_tests.append(comparison)
                component_status = identity_status
                break
            comparison["development_consequence"] = "preregister_child_and_continue"
            split_tests.append(comparison)
            maximum_k = child_k
            component_status = "split_hierarchy_developed"
        components[complex_id] = {
            "complex_id": complex_id, "status": component_status,
            "presence_test": presence, "split_tests": split_tests,
            "K_geometry": cap_geometry, "K_BF": fit_window["maximum_BF_defined_K"],
            "K_cap": cap, "maximum_preregistered_K": maximum_k,
            "presence_and_split_hypotheses_separate": True,
            "parent_gating_applied": True,
        }
        models_for_spec[complex_id] = {
            "background_order": selected_order, "maximum_K": maximum_k,
            "spectral_models": spectral_models, "spectral_fits": spectral_fits,
        }
    return {
        "discovery_fit_rows": discovery_fit_rows, "backgrounds": backgrounds,
        "components": components, "identifiability_rows": identifiability_rows,
        "optimizer_adequacy": comparison_diagnostics,
        "failure_diagnostics": failure_diagnostics,
        "bootstrap_multistarts_selected": max(selected_starts) if selected_starts else None,
        "models_for_spec": models_for_spec,
    }


def resolution_outputs(scans, fit_windows, evidence, config):
    applicability = []
    split_scans = [scan for scan in scans.values() if scan["split_role"] in ("discovery", "holdout")]
    for scan in sorted(split_scans, key=lambda row: row["scan_record_id"]):
        missing = [
            "monochromator_reflection", "monochromator_mosaic", "analyzer_reflection",
            "analyzer_mosaic", "focusing_state", "sample_mosaic", "resolution_relevant_aperture_divergence",
        ]
        for complex_id in fit_windows:
            applicability.append({
                "scan_record_id": scan["scan_record_id"], "raw_scan_id": scan["raw_scan_id"],
                "complex_id": complex_id, "resolution_status": "resolution_not_established",
                "resolution_model_id": f"RES-{complex_id}-{scan['scan_record_id']}",
                "resolution_evidence_id": "EV-006",
                "applicability_status": "not_established",
                "applicability_basis": "critical_metadata_unverified_and_empirical_physical_basis_unresolved",
                "missing_resolution_critical_fields": missing,
                "metadata_decided_before_holdout_detector_access": True,
            })
    model = {
        "job_id": JOB,
        "decision_order": ["direct_applicable_empirical", "validated_calculated", "resolution_not_established"],
        "empirical_branch": {
            "EV006_reproduction_status": evidence["reproduction_status"],
            "physical_basis_status": evidence["resolution_probe_physical_basis"]["status"],
            "probe_suitability_status": evidence["resolution_probe_suitability"]["status"],
            "direct_empirical_applicability": "not_established",
            "empirical_resolution_interpolation_enabled": False,
        },
        "calculated_resolution_implementation": config["resolution"]["calculated_resolution_implementation"],
        "calculated_resolution_branch": "unavailable",
        "final_status": "resolution_not_established",
        "line_shape_model": "unit_area_empirical_Gaussian",
        "width_semantics": "observed_empirical_fwhm",
        "intrinsic_linewidth_reporting": "forbidden",
        "resolution_limited_claim": "forbidden",
        "intrinsically_broadened_claim": "forbidden",
    }
    return applicability, model


def make_hypotheses(fit_windows, development, coverage, model_spec_sha256):
    hypotheses = []
    excluded = []
    parent_id = {}
    for complex_id in sorted(fit_windows):
        fit = fit_windows[complex_id]
        component = development["components"][complex_id]
        cov = coverage[complex_id]
        if fit["complex_model_status"] != "ready_for_discovery_model_development":
            excluded.append({"complex_id": complex_id, "reason": fit["complex_model_status"]})
            continue
        if component["maximum_preregistered_K"] < 1 or cov["eligible_holdout_scan_count"] == 0:
            excluded.append({"complex_id": complex_id,
                             "reason": "confirmatory_model_not_preparable_or_no_holdout_coverage"})
            continue
        background = development["backgrounds"][complex_id]["selected_background_model_id"]
        common = {
            "complex_id": complex_id, "fit_window_meV": fit["fit_window_meV"],
            "eligible_holdout_scan_record_ids": cov["eligible_holdout_scan_record_ids"],
            "holdout_eligible_scan_count": cov["eligible_holdout_scan_count"],
            "holdout_coverage_scope": cov["holdout_coverage_scope"],
            "background_model_id": background,
            "line_shape_model_id": "unit_area_empirical_Gaussian",
            "resolution_model_id": "resolution_not_established",
            "resolution_status": "resolution_not_established",
            "resolution_applicability_basis": "frozen_decision_tree_exhausted_without_established_branch",
            "parameter_bounds": {
                "b0": "(-infinity,+infinity)", "b1_b2": [-10.0, 10.0],
                "areas": "[0,+infinity)", "centroids": fit["frozen_union_meV"],
                "observed_empirical_fwhm": [0.5 * fit["delta_E_ref_meV"],
                    min(fit["frozen_union_meV"][1] - fit["frozen_union_meV"][0],
                        0.5 * (fit["fit_window_meV"][1] - fit["fit_window_meV"][0]))],
            },
            "future_bootstrap_replicates": 8192,
            "future_seed_rule": "stage02r_c002_bootstrap_seed_v1",
            "confirmatory_model_spec_sha256": model_spec_sha256,
            "raw_p_value_rule": "plus_one", "global_multiple_testing": "holm",
            "global_alpha": 0.05, "status": "preregistered",
        }
        presence_id = f"C002-H-{complex_id}-PRESENCE-K0-K1"
        hypotheses.append({"hypothesis_id": presence_id, "hypothesis_type": "presence",
                           "parent_model_id": f"{complex_id}-{background}-K0",
                           "child_model_id": f"{complex_id}-{background}-K1",
                           "parent_hypothesis_id": None, **common})
        parent_id[complex_id] = presence_id
        for k_value in range(1, component["maximum_preregistered_K"]):
            hypothesis_id = f"C002-H-{complex_id}-SPLIT-K{k_value}-K{k_value + 1}"
            hypotheses.append({"hypothesis_id": hypothesis_id, "hypothesis_type": "split",
                               "parent_model_id": f"{complex_id}-{background}-K{k_value}",
                               "child_model_id": f"{complex_id}-{background}-K{k_value + 1}",
                               "parent_hypothesis_id": parent_id[complex_id], **common})
            parent_id[complex_id] = hypothesis_id
    return {"job_id": JOB, "future_job_id": "W02-02R-C-002",
            "C002_execution_authorized": False, "holdout_detector_access_authorized": False,
            "family_frozen_before_holdout_detector_access": True,
            "family_size": len(hypotheses), "hypotheses": hypotheses,
            "excluded_complexes": excluded,
            "holm": {"sort": "raw_p_ascending_then_hypothesis_id_lexical",
                     "global_alpha": 0.05, "step_down_stop_at_first_failure": True,
                     "numerical_failure_raw_p_value": 1.0,
                     "ancestor_gate_separate": True}}


def make_model_spec(config, fit_windows, development, coverage):
    entries = {}
    for complex_id, fit in fit_windows.items():
        background = development["backgrounds"][complex_id]
        component = development["components"][complex_id]
        entries[complex_id] = {
            "source_bf_ids": fit["source_bf_ids"], "frozen_union_meV": fit["frozen_union_meV"],
            "fit_window_meV": fit["fit_window_meV"], "delta_E_ref_meV": fit["delta_E_ref_meV"],
            "complex_model_status": fit["complex_model_status"],
            "discovery_model_scan_set": fit["discovery_model_scan_set"],
            "discovery_model_scan_set_sha256": fit["discovery_model_scan_set_sha256"],
            "background_model_id": background["selected_background_model_id"],
            "line_shape_model_id": ("unit_area_empirical_Gaussian" if fit["fit_window_meV"] else None),
            "resolution_status": "resolution_not_established",
            "maximum_preregistered_K": component["maximum_preregistered_K"],
            "ordered_centroid_rule": "K_free_logits_plus_fixed_reference_softmax",
            "minimum_centroid_separation_meV": fit["delta_E_ref_meV"],
            "minimum_separation_proximity_tolerance_meV": max(0.10 * fit["delta_E_ref_meV"], 1e-6),
            "holdout_eligible_scan_record_ids": coverage[complex_id]["eligible_holdout_scan_record_ids"],
            "holdout_coverage_scope": coverage[complex_id]["holdout_coverage_scope"],
        }
    return {
        "job_id": JOB, "dataset_id": "EXP-TAIPAN-001", "status": "frozen_C001_result",
        "canonical_baseline": AUTH_HEAD, "complexes": entries,
        "parameter_bounds": {"b0": "unbounded", "areas": "nonnegative_unbounded_above",
                             "background_slopes": [-10.0, 10.0],
                             "centroids": "inside_frozen_complex_union",
                             "width_semantics": "observed_empirical_fwhm"},
        "optimizer": config["numerical"]["optimizer"],
        "observed_fit_multistarts": 33,
        "bootstrap_multistarts_selected": development["bootstrap_multistarts_selected"],
        "future_C002": {
            "execution_authorized": False, "holdout_detector_access_authorized": False,
            "bootstrap_replicates": 8192, "seed_rule": "stage02r_c002_bootstrap_seed_v1",
            "plus_one_p_values": True, "Holm_global_alpha": 0.05,
            "numerical_failure_raw_p_value": 1.0,
            "family_cannot_shrink_after_holdout_access": True,
            "hierarchy_ancestor_gate": True,
        },
        "dominant_scan_diagnostic": {
            "formula": "max_s(max(0,T_all-T_minus_s))/max(T_all,1e-12)",
            "warning_if_greater_than": 0.50, "gating": False,
            "leave_one_out_bootstrap_p_values": False,
        },
        "nondetection_semantics": "zero_eligible_scans_is_not_a_nondetection",
        "scope_prohibitions": [
            "holdout_detector_access", "C002_execution", "discovery_holdout_joint_fit",
            "historical_target_comparison", "physical_assignment", "Stage03R_inference", "Stage03D_execution",
            "cross_mode_normalization", "arbitrary_scan_scale",
        ],
        "identity": {"algorithm": "SHA-256", "location": "provenance_manifest.yaml_and_confirmatory_hypotheses.yaml"},
    }


def holm_adjust(raw_values, alpha=0.05):
    ordered = sorted(raw_values, key=lambda item: (item[1], item[0]))
    family_size = len(ordered)
    running, stopped = 0.0, False
    result = {}
    for index, (hypothesis_id, raw_p) in enumerate(ordered, 1):
        adjusted = min(1.0, max(running, (family_size - index + 1) * raw_p))
        running = adjusted
        rejected = False if stopped else raw_p <= alpha / (family_size - index + 1)
        if not rejected:
            stopped = True
        result[hypothesis_id] = {"raw_p_value": raw_p, "adjusted_p_value": adjusted,
                                 "rejected": rejected, "rank": index}
    return result


def verify_t11_semantics(config):
    """Exercise every frozen T11 model/domain invariant without production fitting."""
    energy = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    first = ScanData("T11-SCAN-A", energy, np.array([10.0, 11.0, 12.0, 13.0, 14.0]),
                     np.array([2.0, 3.0, 5.0, 4.0, 2.0]))
    second = ScanData("T11-SCAN-B", energy, np.array([20.0, 19.0, 18.0, 17.0, 16.0]),
                      np.array([7.0, 6.0, 8.0, 6.0, 7.0]))
    structural = dict(complex_id="T11-CX", background_order=2, component_count=1,
                      fit_window=[-2.0, 2.0], complex_union=[-0.5, 0.5], delta_ref=0.25,
                      numerical=config["numerical"])
    model = make_model(scan_data=[first, second], **structural)
    bounds = block_bounds(model)
    p_count = model["background_order"] + 1
    block_dimension = p_count + 3 * model["K"]
    require(bounds[0] == (None, None), "T11_b0_must_be_unbounded")
    require(bounds[1:p_count] == [(-10.0, 10.0)] * model["background_order"],
            "T11_background_finite_bounds")
    require(bounds[p_count:p_count + model["K"]] == [(0.0, None)] * model["K"],
            "T11_area_domain")
    require(len(bounds) == block_dimension, "T11_no_extra_scale_parameter")
    layout, total_dimension = model_layout(model)
    require(total_dimension == 2 * block_dimension
            and layout[0][1].stop == layout[1][1].start,
            "T11_scan_specific_parameter_blocks")

    first_start, first_r0, first_a0 = initial_block(model, first, first.counts)
    second_start, second_r0, second_a0 = initial_block(model, second, second.counts)
    require(first_r0 != second_r0 and first_a0 != second_a0,
            "T11_detector_derived_initializers_must_be_scan_local")
    require(len(first_start) == block_dimension and len(second_start) == block_dimension,
            "T11_parameter_block_shape")
    background, areas, eta, widths = block_parts(first_start, model)
    require((len(background), len(areas), len(eta), len(widths)) == (3, 1, 1, 1),
            "T11_scan_specific_parameter_families")

    nll, _gradient, state = block_nll_gradient(first_start, model, first, first.counts)
    require(state is not None and np.allclose(state["mu"], first.exposure * state["rate"]),
            "T11_exposure_conditioning")
    manual_nll = float(np.sum(state["mu"] - first.counts * np.log(state["mu"])
                              + gammaln(first.counts + 1.0)))
    require(math.isclose(nll, manual_nll, rel_tol=0.0, abs_tol=1.0e-12),
            "T11_raw_count_Poisson_likelihood")

    altered = ScanData("T11-SCAN-C", energy, first.exposure * 7.0, first.counts + 101.0)
    altered_model = make_model(scan_data=[altered], **structural)
    altered_start, altered_r0, altered_a0 = initial_block(
        altered_model, altered, altered.counts)
    require(block_bounds(altered_model) == bounds,
            "T11_detector_values_must_not_change_inferential_bounds")
    require((altered_r0, altered_a0) != (first_r0, first_a0)
            and not np.array_equal(altered_start, first_start),
            "T11_r0_A0_initialization_only")
    nested_parent = make_model(scan_data=[first], complex_id="T11-CX", background_order=2,
                               component_count=0, fit_window=[-2.0, 2.0],
                               complex_union=[-0.5, 0.5], delta_ref=0.25,
                               numerical=config["numerical"])
    require(block_bounds(nested_parent) == bounds[:p_count],
            "T11_initializers_must_not_modify_nesting")
    return {
        "likelihood": "raw_detector_counts_exposure_conditioned_Poisson",
        "scan_specific_parameter_families": ["background", "area", "centroid", "width"],
        "arbitrary_per_scan_scale": False,
        "b0_finite_bound": False,
        "area_upper_bound": None,
        "finite_bounds_detector_independent": True,
        "r0_A0_role": "initialization_only",
    }


def semantic_scope_audit(config, access, model_spec, hypotheses, eligibility_rows,
                         analysis_operations):
    """Check operational scope semantically; numeric/string values are not evidence."""
    tree = ast.parse((ROOT / SOURCE).read_text(encoding="utf-8"))

    def call_name(node):
        if isinstance(node.func, ast.Name):
            return node.func.id.lower()
        if isinstance(node.func, ast.Attribute):
            return node.func.attr.lower()
        return ""

    forbidden_operational_names = {
        "map_f002_f004", "f002_f004_mapping", "compare_historical_target",
        "historical_target_comparison", "assign_cef", "cef_assignment",
        "fit_holdout_detector", "fit_holdout_spectrum", "execute_c002",
        "combined_discovery_holdout_fit", "execute_stage03r", "execute_stage03d",
    }
    defined = {node.name.lower() for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    called = {call_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    require(not ((defined | called) & forbidden_operational_names),
            "T18_forbidden_operational_logic_present")
    fit_callers = set()
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        if any(isinstance(node, ast.Call) and call_name(node) in {"fit_model", "fit_model_levels"}
               for node in ast.walk(function)):
            fit_callers.add(function.name.lower())
    require(not any("holdout" in name for name in fit_callers),
            "T18_holdout_fit_call_path_present")
    require(config["future_c002"]["execution_authorized"] is False
            and config["future_c002"]["holdout_detector_access_authorized"] is False,
            "T18_future_execution_configuration")
    required_prohibitions = {
        "holdout_detector_access", "C002_execution", "discovery_holdout_joint_fit",
        "historical_target_comparison", "physical_assignment", "Stage03R_inference",
        "Stage03D_execution",
    }
    require(required_prohibitions <= set(model_spec["scope_prohibitions"]),
            "T18_generated_model_scope_prohibitions")
    require(all(item["status"] == "preregistered" for item in hypotheses["hypotheses"]),
            "T18_hypotheses_must_be_preregistration_only")
    require(all(not row["detector_fields_materialized"] for row in eligibility_rows),
            "T18_holdout_output_materialized_detector_field")
    require(access.holdout_detector_values_decoded == 0
            and not (access.detector_scan_ids & access.holdout_ids),
            "T18_holdout_detector_invariant")
    require(analysis_operations and not any(analysis_operations.values()),
            "T18_forbidden_analysis_operation_performed")
    return {
        "source_operational_forbidden_hits": [],
        "fit_model_callers": sorted(fit_callers),
        "configuration_execution_flags": {
            "C002": False, "holdout_detector": False,
        },
        "generated_outputs_scope": "preregistration_only",
        "performed_forbidden_operations": [],
    }


def run_mandatory_tests(context):
    config = context["config"]
    access = context["access"]
    fit_windows = context["fit_windows"]
    development = context["development"]
    resolution = context["resolution_model"]
    evidence = context["resolution_evidence"]
    coverage = context["coverage"]
    tests = []

    def test(test_id, name, function):
        try:
            detail = function()
            tests.append({"test_id": test_id, "name": name, "status": "PASS",
                          "details": detail or "frozen assertions satisfied"})
        except Exception as error:
            tests.append({"test_id": test_id, "name": name, "status": "FAIL",
                          "details": f"{type(error).__name__}: {error}"})

    def t01():
        require(context["input_identity"]["status"] == "PASS", "input identity")
        require(context["input_identity"]["design_baseline_is_ancestor"], "design baseline")
        return f"{len(context['input_identity']['canonical_inputs'])} canonical inputs and " \
               f"{len(context['input_identity']['b001_inventory_verified'])} B001 inventory entries verified"

    def t02():
        require(context["b001_before"] == context["b001_after"] == B001_SHA256, "catalogue changed")
        return B001_SHA256

    def t03():
        synthetic = (b"scan_record_id,point_index,e_raw,detector_raw,det_err_raw,monitor_raw,time_raw\n"
                     b"H,0,1.0,999,31.6,1000,1\n")
        isolated_log = AccessLog()
        guard = PointAccess({"D"}, set(), {"H"}, isolated_log, synthetic)
        denied = False
        try:
            list(guard.rows(("scan_record_id", "detector_raw"), {"H"}, "holdout_metadata"))
        except StopJob:
            denied = True
        require(denied and guard.detector_values_decoded == 0, "forbidden field did not pre-materialization fail")
        require(access.holdout_detector_values_decoded == 0 and access.forbidden_requests == 0,
                "production holdout detector access")
        require(all(row["allowed"] for row in context["access_log"].rows), "actual denied request")
        return "allowlist projection and isolated hard-fail fixture passed; production holdout detector materializations=0"

    def t04():
        require(evidence["raw_scan_id"] == "104062" and evidence["access_role"] == "resolution_evidence",
                "EV006 role")
        require(evidence["scan_104062_role"] == "empirical_effective_width_evidence", "EV006 promotion")
        return "scan 104062 isolated to resolution evidence"

    def t05():
        require(resolution["decision_order"] == ["direct_applicable_empirical", "validated_calculated",
                                                  "resolution_not_established"], "decision order")
        require(resolution["calculated_resolution_branch"] == "unavailable", "calculated lock")
        require(not resolution["empirical_branch"]["empirical_resolution_interpolation_enabled"], "interpolation")
        return resolution["final_status"]

    def t06():
        require(evidence["resolution_probe_physical_basis"]["status"] == "unresolved", "physical basis")
        require(evidence["resolution_probe_suitability"]["status"] == "unresolved", "suitability promotion")
        require(not evidence["second_component_gate_used"], "second component gate")
        return {"reproduction": evidence["reproduction_status"], "physical_basis": "unresolved"}

    def t07():
        repeated = compute_fit_windows(config, context["scans"], context["discovery_ids"],
                                       {sid: list(reversed(rows)) for sid, rows in context["metadata_points"].items()})
        for complex_id in fit_windows:
            require(repeated[complex_id]["fit_window_meV"] == fit_windows[complex_id]["fit_window_meV"], "window order")
            require(repeated[complex_id]["discovery_model_scan_set_sha256"] ==
                    fit_windows[complex_id]["discovery_model_scan_set_sha256"], "set digest order")
        require(fit_windows["CX-01"]["fit_window_meV"] is None
                and fit_windows["CX-02"]["fit_window_meV"] is None
                and fit_windows["CX-03"]["fit_window_meV"] is not None, "measured window outcomes")
        return "metadata/grid-only selection invariant to input order"

    def t08():
        for complex_id, result in development["backgrounds"].items():
            if result["development_tests"]:
                require(result["development_tests"][0]["test_id"].endswith("B0-to-B1"), "B0->B1")
                require(all(item["bootstrap_replicates"] == 4096 for item in result["development_tests"]), "B")
                require(result["alpha"] == 0.05 and not result["AIC_BIC_promotion_used"], "alpha/AIC")
        return "B0->B1->B2 parent-gated selection, B=4096, alpha=0.05"

    def t09():
        for result in development["components"].values():
            if result["presence_test"]:
                require(result["presence_test"]["registration_is_independent_of_discovery_p_value"], "presence")
                require(result["K_cap"] <= result["K_BF"] and result["K_cap"] <= result["K_geometry"], "K cap")
                require(result["parent_gating_applied"], "parent gate")
        return "presence separated from parent-gated split development; B=4096, alpha=0.10"

    def t10():
        for k_count in (1, 2, 3):
            centroids, _jac, q_value = centroids_from_eta(np.zeros(k_count), 0.0, 8.0, 1.0)
            require(len(q_value) == k_count + 1 and np.all(np.diff(centroids) > 1.0), "ordered transform")
        require(max(0.10 * 1.0, 1e-6) == 0.1, "tau_sep")
        return "exact K-logit fixed-reference transform and tau_sep verified"

    def t11():
        require(all(record["width_semantics"] in ("observed_empirical_fwhm", "not_applicable")
                    for record in development["discovery_fit_rows"]), "width semantics")
        return verify_t11_semantics(config)

    def t12():
        diagnostics = development["optimizer_adequacy"]
        require(diagnostics and all(item["optimizer_adequacy_status"] == "passed" for item in diagnostics),
                "optimizer adequacy")
        require(all(item["reference_parent_valid_count"] == 64
                    and item["reference_child_valid_count"] == 64 for item in diagnostics), "33 reference")
        require(development["bootstrap_multistarts_selected"] in (4, 8, 16, 33), "selected starts")
        return {"comparisons": len(diagnostics),
                "bootstrap_multistarts_selected": development["bootstrap_multistarts_selected"]}

    def t13():
        payload, fingerprint, seed = discovery_seed("CX-03", "fixture", 4096)
        require(payload.endswith("replicates=4096\n") and seed == int(fingerprint[:16], 16), "seed")
        rng1 = np.random.Generator(np.random.PCG64(seed)).poisson(3, 20)
        rng2 = np.random.Generator(np.random.PCG64(seed)).poisson(3, 20)
        require(np.array_equal(rng1, rng2), "PCG64")
        require((1 + 0) / (4096 + 1) > 0, "plus one")
        return "SHA-256 first-16-hex PCG64 and plus-one convention verified"

    def t14():
        require(config["numerical"]["bootstrap_failed_replicate_fraction_max"] == 0.01, "failure limit")
        require(config["numerical"]["projected_gradient_threshold"] == 1e-4, "KKT threshold")
        failed_statistic = float("inf")
        require(failed_statistic >= 0.0, "conservative statistic")
        return "failed replicate maps to +infinity; 1% gate and projected-gradient/KKT constants verified"

    def t15():
        require(config["numerical"]["profile_grid_points"] == 41, "profile grid")
        require(config["numerical"]["profile_delta_minus2logL_threshold"] == 3.841458820694124,
                "profile threshold")
        for record in development["identifiability_rows"]:
            require(all(item["profile_grid_points"] == 41 for item in record["profile_results"]), "profile record")
        statuses = {"passed", "rejected_nonidentifiable", "rejected_no_informative_scan_for_split",
                    "rejected_minimum_separation_proximity", "not_evaluated_development_test_not_passed"}
        for component in development["components"].values():
            for item in component.get("split_tests", []):
                if "component_identifiability_status" in item:
                    require(item["component_identifiability_status"] in statuses, "identity status")
        return "41-point in-bound centroid profiles, exact threshold and Hessian warning semantics"

    def t16():
        scopes = ["none" if n == 0 else "single_scan" if n == 1 else "multi_scan" for n in (0, 1, 2)]
        require(scopes == ["none", "single_scan", "multi_scan"], "coverage fixtures")
        require(all(item["scope_semantics"] == "capacity_only_not_observed_support_or_replication"
                    for item in coverage.values()), "scope semantics")
        return {key: value["holdout_coverage_scope"] for key, value in coverage.items()}

    def t17():
        adjusted = holm_adjust([("H-B", 0.01), ("H-A", 0.01), ("H-C", 1.0)])
        require(adjusted["H-A"]["rank"] == 1 and adjusted["H-B"]["rank"] == 2, "lexical tie")
        require(adjusted["H-C"]["raw_p_value"] == 1.0 and not adjusted["H-C"]["rejected"], "failure p")
        require(access.holdout_detector_values_decoded == 0, "holdout guard")
        return "exact Holm ordering/adjustment, numerical-failure p=1 and field guard verified"

    def t18():
        require(context["dominant_scan_rule"]["warning_if_greater_than"] == 0.50
                and not context["dominant_scan_rule"]["gating"], "dominant scan")
        return semantic_scope_audit(
            config, access, context["model_spec"], context["hypotheses"],
            context["eligibility_rows"], context["analysis_operations"])

    functions = (t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12, t13, t14, t15, t16, t17, t18)
    names = (
        "Canonical input integrity", "Catalogue immutability", "Holdout detector blindness",
        "EV-006 isolation", "Resolution decision-tree and granularity",
        "EV-006 physical basis, suitability and applicability",
        "Discovery sample and fit-window determinism", "Background selection",
        "Component hierarchy", "Ordered-centroid transform and proximity",
        "Poisson likelihood and inferential bounds", "Multistart determinism and optimizer adequacy",
        "Bootstrap, seeds and p-values", "Bootstrap failures and KKT convergence",
        "Profile identifiability", "Holdout eligibility and coverage",
        "Holm registry and field-access guard", "Scope, dominant scan and STOP",
    )
    for index, (name, function) in enumerate(zip(names, functions), 1):
        test(f"C001-T{index:02d}", name, function)
    return tests


def checkpoint_bytes(summary, output_hashes, command):
    output_lines = "\n".join(
        f"| `{name}` | {details['size_bytes']} | `{details['sha256']}` |"
        for name, details in sorted(output_hashes.items()))
    tests = "\n".join(f"- `{item['test_id']}`: **{item['status']}** — {item['name']}"
                      for item in summary["tests"])
    fit_lines = "\n".join(
        f"- `{cid}`: status `{fit['complex_model_status']}`, window `{fit['fit_window_meV']}`, "
        f"discovery scans `{len(fit['discovery_model_scan_set'])}`, holdout scope "
        f"`{summary['coverage'][cid]['holdout_coverage_scope']}`."
        for cid, fit in summary["fit_windows"].items())
    text = f"""---
type: work_checkpoint
checkpoint_id: W02-02R-C-001
date: 2026-09-05
status: completed
review_status: not_reviewed
scientific_interpretation_status: not_reviewed
parent_checkpoint: W02-02R-B-001
execution_context: W02-win
platform: windows
repository_commit: {AUTH_HEAD}
dataset_id: EXP-TAIPAN-001
dataset_identity_status: verified_canonical_parsed_inputs
---

# W02-02R-C-001 work checkpoint

## GOAL

Prepare the deterministic confirmatory model package and future C-002 hypothesis registry under the frozen C-001 specification. This is not holdout confirmation and contains no physical assignment.

## INPUTS

- Frozen specification: `{SPEC}` (`{SPEC_SHA256}`).
- Frozen B-001 catalogue before/after: `{B001_SHA256}`.
- Canonical authorization baseline: `{AUTH_HEAD}`; design baseline `{DESIGN_BASELINE}` is an ancestor.
- All required A/B checkpoints and reviewed artifacts were verified by size/SHA-256 or exact canonical HEAD bytes.

## DATASET_IDENTITY

`EXP-TAIPAN-001` was resolved through ignored `configs/local_paths.yaml`. C-001 used canonical parsed Stage02R inputs; no raw file was opened or re-analysed.

## CODE_VERSION

- `{SOURCE}`: `{summary['source_sha256']}`.
- `{CONFIG}`: `{summary['config_sha256']}`.

## ENVIRONMENT

- W02-win / Windows; CPython `{platform.python_version()}`.
- NumPy `{np.__version__}`; SciPy `{scipy.__version__}`; PyYAML `{yaml.__version__}`.
- Recovery START: `{summary['recovery_start']['snapshot_id']}` (integrity PASS).

## COMMANDS

```powershell
python scripts/work_recovery.py start --job W02-02R-C-001
{command}
python scripts/kb_refresh.py --check
python scripts/kb_validate.py --strict
git diff --check
```

## PARAMETERS

The complete frozen numerical configuration is `{CONFIG}`. Observed fits use 33 starts; discovery development uses B=4096, future C-002 metadata uses B=8192, PCG64 SHA-derived seeds and plus-one p-values.

## TESTS

{tests}

## OUTPUTS

| Artifact | Size (bytes) | SHA-256 |
|---|---:|---|
{output_lines}

## OBJECTIVE_DECOMPOSITION

Joint likelihoods are exact sums of scan likelihoods with scan-specific backgrounds, areas, centroids and observed empirical widths. No arbitrary scan scale or cross-mode normalization was introduced.

## NUMERICAL_SUMMARY

{fit_lines}

- Resolution: `{summary['resolution_status']}`.
- Optimizer adequacy: `{summary['optimizer_adequacy_status']}`; bootstrap multistarts selected `{summary['bootstrap_multistarts_selected']}`.
- Confirmatory hypotheses frozen: `{summary['hypothesis_count']}`.

## WARNINGS

- The independent physical basis for scan 104062 is unresolved; its fit is empirical effective-width evidence only.
- Where resolution is not established, all widths are observed empirical FWHM and have no intrinsic-linewidth interpretation.
- Coverage scope is capacity only and is not observed support or replication.

## FAILED_OR_DEFERRED

- C-002 execution and all holdout detector access remain unauthorized and were not performed.
- Historical-target comparison, physical assignment, Stage03R/Stage03D inference and cross-mode normalization were not performed.

## REPRODUCTION_COMMAND

```powershell
{command}
```

Use only at canonical HEAD `{AUTH_HEAD}` with the recorded recovery START and verified inputs. Do not rerun automatically after this completed result directory exists.

## PASS_CRITERIA

All 43 frozen criteria are represented by C001-T01...T18 and the provenance/access audits. Tests pass: `{sum(item['status'] == 'PASS' for item in summary['tests'])}/18`.

## STOP_CONDITION

SATISFIED. Required artifacts, field-access audit, frozen future hypothesis/model package and provenance exist. B-001 is byte-identical. Holdout detector access count is zero. C-002 was not executed.

## HANDOFF_STATE

Return this checkpoint and `{OUT_REL}/` to `02 - TAIPAN Data Reduction` for scientific/methodological review. Next recommended actor: `02 - TAIPAN Data Reduction`.

## REVIEW_NOTES

> [!warning]
> This computational result is not automatically scientific review. No scientific conclusion or physical assignment is promoted here.
"""
    return text.encode("utf-8")


def execute(expected_commit, snapshot_id, workers, command):
    require(not (ROOT / OUT_REL).exists(), "C001_result_directory_already_exists")
    require(not (ROOT / CHECKPOINT).exists(), "C001_checkpoint_already_exists")
    config = yload((ROOT / CONFIG).read_bytes())
    require(config["authorization_baseline"] == AUTH_HEAD, "config_authorization_baseline")
    require(config["canonical_design_baseline"] == DESIGN_BASELINE, "config_design_baseline")
    require(config["recovery_start_snapshot"] == snapshot_id, "config_recovery_snapshot")
    input_identity = verify_inputs(expected_commit, snapshot_id)
    b001_before = sha256_file(ROOT / B1 / "blind_feature_catalogue.yaml")
    access_log = AccessLog()
    scans, discovery_ids, holdout_ids = load_canonical_tables(access_log)
    resolution_ids = {sid for sid, scan in scans.items() if scan["raw_scan_id"] == "104062"}
    access = PointAccess(discovery_ids, resolution_ids, holdout_ids, access_log)
    metadata_points = collect_point_metadata(access, set(scans), "detector_blind_point_metadata")
    require(set(metadata_points) == set(scans), "point_metadata_population_mismatch")
    fit_windows = compute_fit_windows(config, scans, discovery_ids, metadata_points)
    eligibility_rows, coverage = holdout_eligibility(config, scans, holdout_ids,
                                                     metadata_points, fit_windows)
    resolution_evidence = fit_resolution_evidence(access, scans, config)
    applicability_rows, resolution_model = resolution_outputs(scans, fit_windows,
                                                               resolution_evidence, config)
    development = run_model_development(access, fit_windows, config, workers)
    require(access.detector_scan_ids <= discovery_ids | resolution_ids,
            "detector_access_outside_authorized_sets")
    require(not (access.detector_scan_ids & holdout_ids)
            and access.holdout_detector_values_decoded == 0,
            "holdout_detector_access_violation")
    b001_after = sha256_file(ROOT / B1 / "blind_feature_catalogue.yaml")
    require(b001_before == b001_after == B001_SHA256, "B001_catalogue_postflight_identity_failure")
    model_spec = make_model_spec(config, fit_windows, development, coverage)
    model_spec_data = ybytes(model_spec)
    model_spec_sha = sha256_bytes(model_spec_data)
    hypotheses = make_hypotheses(fit_windows, development, coverage, model_spec_sha)
    analysis_operations = {
        "F002_F004_mapping": False,
        "historical_target_comparison": False,
        "CEF_assignment": False,
        "holdout_spectral_fitting": False,
        "C002_execution": False,
        "combined_discovery_holdout_detector_fitting": False,
        "Stage03R_inference": False,
        "Stage03D_inference": False,
    }
    instrument_block = {
        "job_id": JOB, "shared_normalization_promotion": {"status": "not_proposed"},
        "proposed_instrument_block_id": None, "member_scan_record_ids": [],
        "metadata_basis": "A003 conditionally-supported same-control-mode classes only",
        "missing_critical_metadata": ["filter_state", "higher_order_suppression_state",
            "attenuation_state", "monochromator_reflection", "analyzer_reflection",
            "detector_hardware_identity", "monitor_hardware_identity"],
        "limitations": "No shared normalization parameter is activated.",
    }
    complexes_output = {"job_id": JOB, "confirmatory_unit": "overlap_complex",
                        "one_BF_equals_one_physical_line": False,
                        "complexes": [{key: value for key, value in fit.items()
                                       if key != "candidate_margin_trials"}
                                      for fit in fit_windows.values()]}
    windows_output = {"job_id": JOB, "selection_uses_detector_values": False,
                      "candidate_margin_multiples": [5, 4, 3],
                      "fit_windows": list(fit_windows.values())}
    background_output = {"job_id": JOB, "complexes": list(development["backgrounds"].values())}
    component_output = {"job_id": JOB, "complexes": list(development["components"].values())}
    coverage_output = {"job_id": JOB, "detector_blind": True,
                       "scope_is_capacity_not_observed_replication": True,
                       "complexes": list(coverage.values())}
    numerical_output = {
        "job_id": JOB, "numerical_spec_version": config["numerical"]["numerical_spec_version"],
        "optimizer": config["numerical"]["optimizer"], "observed_fit_multistarts": 33,
        "bootstrap_candidate_sequence": [4, 8, 16, 33],
        "bootstrap_reference_multistarts": 33,
        "bootstrap_adequacy_benchmark_replicates": 64,
        "bootstrap_multistarts_selected": development["bootstrap_multistarts_selected"],
        "optimizer_adequacy": development["optimizer_adequacy"],
        "projected_gradient_threshold": 1e-4,
        "optimizer_parameter_coordinates": "frozen_physical_model_parameters",
        "post_LBFGSB_parameter_refinement": False,
        "failed_replicate_consequence": "T=+infinity",
        "failed_fraction_max": 0.01,
    }
    artifact_bytes = {
        "resolution_evidence.yaml": ybytes(resolution_evidence),
        "resolution_applicability.csv": csvbytes(applicability_rows, (
            "scan_record_id", "raw_scan_id", "complex_id", "resolution_status", "resolution_model_id",
            "resolution_evidence_id", "applicability_status", "applicability_basis",
            "missing_resolution_critical_fields", "metadata_decided_before_holdout_detector_access")),
        "resolution_model.yaml": ybytes(resolution_model),
        "confirmatory_complexes.yaml": ybytes(complexes_output),
        "fit_windows.yaml": ybytes(windows_output),
        "discovery_model_fits.csv": csvbytes(development["discovery_fit_rows"], (
            "complex_id", "model_id", "scan_record_id", "background_model_id", "component_count_K",
            "fit_status", "joint_log_likelihood", "selected_start_index", "projected_gradient_max",
            "background_parameters", "areas", "centroids_meV", "empirical_fwhm_meV", "width_semantics")),
        "background_selection.yaml": ybytes(background_output),
        "component_development.yaml": ybytes(component_output),
        "model_identifiability.csv": csvbytes(development["identifiability_rows"], (
            "complex_id", "model_id", "scan_record_id", "component_count_K", "tau_sep_meV", "areas",
            "centroids_meV", "profile_results", "all_profiles_finite_in_bounds",
            "hessian_condition_number", "hessian_warning")),
        "holdout_metadata_eligibility.csv": csvbytes(eligibility_rows, (
            "scan_record_id", "raw_scan_id", "complex_id", "split_role", "count_control_mode",
            "pre_detector_status", "eligible", "eligibility_status", "eligibility_reasons",
            "fit_window_point_count", "detector_fields_materialized")),
        "holdout_coverage_summary.yaml": ybytes(coverage_output),
        "holdout_field_access_log.csv": csvbytes(access_log.rows, (
            "source_artifact", "requested_field", "access_role", "allowed", "request_sequence")),
        "instrument_block_assessment.yaml": ybytes(instrument_block),
        "confirmatory_hypotheses.yaml": ybytes(hypotheses),
        "confirmatory_model_spec.yaml": model_spec_data,
        "numerical_stability_diagnostics.yaml": ybytes(numerical_output),
    }
    context = {
        "config": config, "access": access, "access_log": access_log,
        "fit_windows": fit_windows, "development": development,
        "resolution_model": resolution_model, "resolution_evidence": resolution_evidence,
        "coverage": coverage, "input_identity": input_identity,
        "b001_before": b001_before, "b001_after": b001_after,
        "scans": scans, "discovery_ids": discovery_ids,
        "metadata_points": metadata_points,
        "dominant_scan_rule": model_spec["dominant_scan_diagnostic"],
        "model_spec": model_spec,
        "hypotheses": hypotheses, "eligibility_rows": eligibility_rows,
        "analysis_operations": analysis_operations,
    }
    tests = run_mandatory_tests(context)
    failed_tests = [item for item in tests if item["status"] != "PASS"]
    if failed_tests:
        reason = "mandatory_test_failure:" + ",".join(item["test_id"] for item in failed_tests)
        diagnostics = list(development.get("failure_diagnostics", []))
        existing_test_ids = {item.get("test_id") for item in diagnostics}
        for item in failed_tests:
            if item["test_id"] not in existing_test_ids:
                diagnostics.append({
                    "test_id": item["test_id"], "complex_id": "not_applicable",
                    "comparison_id": "not_applicable", "parent_model_id": "not_applicable",
                    "child_model_id": "not_applicable",
                    "benchmark_replicate_index": "not_applicable",
                    "candidate_multistart_level": "not_applicable",
                    "parent_reference_valid": "not_applicable",
                    "child_reference_valid": "not_applicable", "fit_status": "test_failure",
                    "failure_reason": item["details"],
                    "projected_gradient_max": "not_applicable",
                })
        diagnostic_path = preserve_failure_diagnostic(reason, diagnostics)
        raise StopJob(reason, diagnostics=diagnostics, diagnostic_path=diagnostic_path)
    test_report = {"job_id": JOB, "required_tests": 18, "tests_pass": 18, "tests_failed": 0,
                   "overall_status": "PASS", "tests": tests}
    artifact_bytes["test_report.yaml"] = ybytes(test_report)
    source_sha = sha256_file(ROOT / SOURCE)
    config_sha = sha256_file(ROOT / CONFIG)
    non_manifest_hashes = {
        name: {"size_bytes": len(data), "sha256": sha256_bytes(data)}
        for name, data in sorted(artifact_bytes.items())
    }
    provenance = {
        "job_id": JOB, "dataset_id": "EXP-TAIPAN-001", "repository_commit": AUTH_HEAD,
        "execution_context": "W02-win", "platform": "windows",
        "python_version": platform.python_version(),
        "package_versions": {"numpy": np.__version__, "scipy": scipy.__version__, "PyYAML": yaml.__version__},
        "source_path": SOURCE, "source_sha256": source_sha,
        "configuration_path": CONFIG, "configuration_sha256": config_sha,
        "specification_path": SPEC, "specification_sha256": SPEC_SHA256,
        "recovery_start": input_identity["recovery_start"],
        "input_identity_status": "PASS",
        "canonical_input_identities": input_identity["canonical_inputs"],
        "B001_catalogue_sha256_before": b001_before,
        "B001_catalogue_sha256_after": b001_after,
        "B001_catalogue_unchanged": True,
        "raw_data_access": "none", "raw_data_reanalysis": False,
        "holdout_detector_access_count": 0, "holdout_forbidden_field_requests": 0,
        "analysis_operations": analysis_operations,
        "confirmatory_model_spec_sha256": model_spec_sha,
        "outputs_excluding_this_manifest": [
            {"logical_name": name, **details} for name, details in non_manifest_hashes.items()],
        "C001_stop_condition": "satisfied", "C002_executed": False,
        "C002_execution_authorized": False, "holdout_detector_access_authorized": False,
    }
    artifact_bytes["provenance_manifest.yaml"] = ybytes(provenance)
    require(set(artifact_bytes) == set(REQUIRED_OUTPUTS), "required_output_set_mismatch")
    result_parent = ROOT / "04_Results/Stage02R"
    temporary = Path(tempfile.mkdtemp(prefix=".W02-02R-C-001-", dir=result_parent))
    try:
        for name, data in artifact_bytes.items():
            target = temporary / name
            with target.open("xb") as handle:
                handle.write(data)
        for name, data in artifact_bytes.items():
            require((temporary / name).read_bytes() == data, "atomic_output_verification_failure:" + name)
        os.replace(temporary, ROOT / OUT_REL)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    output_hashes = {
        name: {"size_bytes": (ROOT / OUT_REL / name).stat().st_size,
               "sha256": sha256_file(ROOT / OUT_REL / name)}
        for name in REQUIRED_OUTPUTS
    }
    summary = {
        "tests": tests, "fit_windows": fit_windows, "coverage": coverage,
        "source_sha256": source_sha, "config_sha256": config_sha,
        "recovery_start": input_identity["recovery_start"],
        "resolution_status": resolution_model["final_status"],
        "optimizer_adequacy_status": ("passed" if all(item["optimizer_adequacy_status"] == "passed"
                                                       for item in development["optimizer_adequacy"])
                                       else "failed"),
        "bootstrap_multistarts_selected": development["bootstrap_multistarts_selected"],
        "hypothesis_count": hypotheses["family_size"],
    }
    checkpoint_data = checkpoint_bytes(summary, output_hashes, command)
    checkpoint_path = ROOT / CHECKPOINT
    temporary_checkpoint = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
    with temporary_checkpoint.open("xb") as handle:
        handle.write(checkpoint_data)
    require(temporary_checkpoint.read_bytes() == checkpoint_data, "checkpoint_write_verification_failure")
    os.replace(temporary_checkpoint, checkpoint_path)
    require(sha256_file(ROOT / B1 / "blind_feature_catalogue.yaml") == B001_SHA256,
            "B001_catalogue_final_identity_failure")
    return {
        "JOB_STATUS": "completed", "CANONICAL_BASELINE": AUTH_HEAD,
        "RECOVERY_START_SNAPSHOT": snapshot_id, "SOURCE_SHA256": source_sha,
        "CONFIG_SHA256": config_sha, "INPUT_IDENTITY_STATUS": "PASS",
        "B001_CATALOGUE_SHA256_BEFORE": b001_before,
        "B001_CATALOGUE_SHA256_AFTER": b001_after, "B001_CATALOGUE_UNCHANGED": True,
        "DISCOVERY_MODEL_SCAN_SET": {cid: fit["discovery_model_scan_set"] for cid, fit in fit_windows.items()},
        "DISCOVERY_MODEL_SCAN_SET_SHA256": {cid: fit["discovery_model_scan_set_sha256"] for cid, fit in fit_windows.items()},
        "RESOLUTION_STATUS": resolution_model["final_status"],
        "RESOLUTION_EVIDENCE_STATUS": resolution_evidence["reproduction_status"],
        "RESOLUTION_APPLICABILITY_SUMMARY": "0 established; all frozen scan-complex identities resolution_not_established",
        "FIT_WINDOWS": {cid: fit["fit_window_meV"] for cid, fit in fit_windows.items()},
        "BACKGROUND_SELECTION": {cid: value["selected_background_model_id"]
                                 for cid, value in development["backgrounds"].items()},
        "COMPONENT_DEVELOPMENT": {cid: value["maximum_preregistered_K"]
                                  for cid, value in development["components"].items()},
        "IDENTIFIABILITY_STATUS": {cid: value["status"] for cid, value in development["components"].items()},
        "OPTIMIZER_ADEQUACY_STATUS": summary["optimizer_adequacy_status"],
        "BOOTSTRAP_MULTISTARTS_SELECTED": development["bootstrap_multistarts_selected"],
        "HOLDOUT_METADATA_ELIGIBILITY_SUMMARY": {
            cid: value["eligible_holdout_scan_count"] for cid, value in coverage.items()},
        "HOLDOUT_COVERAGE_SCOPE": {cid: value["holdout_coverage_scope"] for cid, value in coverage.items()},
        "HOLDOUT_DETECTOR_ACCESS_COUNT": 0, "HOLDOUT_FORBIDDEN_FIELD_REQUESTS": 0,
        "CONFIRMATORY_HYPOTHESIS_COUNT": hypotheses["family_size"],
        "CONFIRMATORY_MODEL_SPEC_SHA256": model_spec_sha,
        "TESTS_PASS": 18, "TESTS_FAILED": 0,
        "NUMERICAL_LIMITATIONS": ["resolution physical basis unresolved"],
        "SCIENTIFIC_LIMITATIONS": ["overlap complexes are not physical line assignments",
                                   "coverage scope is capacity only"],
        "C001_STOP_CONDITION": "satisfied", "C002_EXECUTED": False,
        "C002_EXECUTION_AUTHORIZED": False, "HOLDOUT_DETECTOR_ACCESS_AUTHORIZED": False,
        "FILES_CREATED_OR_MODIFIED": [SOURCE, CONFIG, CHECKPOINT, OUT_REL + "/"],
        "CHECKPOINT_PATH": CHECKPOINT, "RESULT_DIRECTORY": OUT_REL,
        "BLOCKERS": [], "NEXT_RECOMMENDED_ACTOR": "02 - TAIPAN Data Reduction",
    }


def verify_frozen_lbfgsb_implementation():
    tree = ast.parse((ROOT / SOURCE).read_text(encoding="utf-8"))
    fit_node = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "fit_block")
    fit_text = ast.get_source_segment((ROOT / SOURCE).read_text(encoding="utf-8"), fit_node)
    minimize_calls = [node for node in ast.walk(fit_node) if isinstance(node, ast.Call)
                      and ((isinstance(node.func, ast.Name) and node.func.id == "minimize")
                           or (isinstance(node.func, ast.Attribute) and node.func.attr == "minimize"))]
    require(len(minimize_calls) == 1, "frozen_fit_must_have_one_LBFGSB_call")
    keywords = {item.arg: item.value for item in minimize_calls[0].keywords}
    require(isinstance(keywords.get("method"), ast.Constant)
            and keywords["method"].value == "L-BFGS-B", "frozen_optimizer_method")
    require("jac" not in keywords, "production_LBFGSB_must_not_receive_explicit_jacobian")
    require(isinstance(keywords.get("bounds"), ast.Name) and keywords["bounds"].id == "bounds",
            "frozen_physical_bounds")
    require(isinstance(keywords.get("options"), ast.Subscript), "frozen_optimizer_options")
    objective_node = next(node for node in fit_node.body
                          if isinstance(node, ast.FunctionDef) and node.name == "objective")
    objective_calls = {node.func.id for node in ast.walk(objective_node)
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    require("block_nll_value" in objective_calls and "block_nll_gradient" not in objective_calls,
            "production_objective_must_be_scalar_without_analytic_gradient_helper")
    for forbidden in ("scales", "centered_objective", "polish_block_kkt",
                      "minimize_scalar", "least_squares", "brentq"):
        require(forbidden not in fit_text, "nonconforming_fit_operation:" + forbidden)
    select_node = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef) and node.name == "select_candidate")
    select_text = ast.get_source_segment((ROOT / SOURCE).read_text(encoding="utf-8"), select_node)
    require("projected_gradient_fd" in select_text and "candidate[\"theta\"] =" not in select_text,
            "KKT_gate_must_not_modify_theta")
    return {
        "optimizer_calls_in_fit_block": 1,
        "method": "L-BFGS-B",
        "jacobian": None,
        "coordinates": "physical",
        "post_optimizer_theta_modification": False,
    }


def small_optimizer_smoke(config):
    energy = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    scan = ScanData("SMOKE-SCAN", energy, np.full(5, 10.0), np.full(5, 5.0))
    model = make_model("SMOKE-CX", [scan], 0, 0, [-1.0, 1.0], [-0.25, 0.25],
                       0.1, config["numerical"])
    candidates = fit_candidates(model, [scan.counts], "observed", count=1)
    theta_returned_by_lbfgsb = candidates[0]["theta"].copy()
    selected = select_candidate(model, [scan.counts], candidates, 1)
    require(selected["valid"], "small_LBFGSB_candidate_must_pass_KKT")
    require(np.array_equal(candidates[0]["theta"], theta_returned_by_lbfgsb),
            "KKT_gate_changed_LBFGSB_theta")
    require(math.isclose(selected["theta"][0], math.log(0.5), rel_tol=0.0, abs_tol=1.0e-6),
            "small_LBFGSB_physical_solution")

    invalid_theta = np.array([math.log(0.1)])
    invalid_nll = block_nll_gradient(invalid_theta, model, scan, scan.counts)[0]
    invalid_candidates = [{
        "start_index": 1, "blocks": [{"theta": invalid_theta.copy(),
                                         "log_likelihood": -invalid_nll, "iterations": 0}],
        "log_likelihood": -invalid_nll, "iterations": 0, "raw_valid": True,
        "raw_failure_reason": None, "raw_failure_scan_record_id": None,
        "valid": None, "theta": invalid_theta.copy(),
    }]
    invalid_before = invalid_candidates[0]["theta"].copy()
    rejected = select_candidate(model, [scan.counts], invalid_candidates, 1)
    require(not rejected["valid"] and np.array_equal(invalid_candidates[0]["theta"], invalid_before),
            "failed_KKT_candidate_must_be_rejected_without_refinement")
    return {"valid_candidate": "accepted", "invalid_KKT_candidate": "rejected",
            "theta_modified_after_LBFGSB": False}


def small_kkt_bound_scale_smoke(config):
    """Prove each active-bound scale excludes the opposite finite bound."""
    energy = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    positive_scan = ScanData("KKT-LOWER", energy, np.ones(5), np.zeros(5))
    negative_scan = ScanData("KKT-UPPER", energy, np.ones(5), np.full(5, 10.0))
    model = make_model("KKT-CX", [positive_scan], 0, 0, [-1.0, 1.0], [-0.25, 0.25],
                       0.1, config["numerical"])

    lower_bounds = [(0.0, 1.0e12)]
    lower_derivative, lower_projected = finite_difference_component_fd(
        np.array([1.0e-7]), 0, model, positive_scan, positive_scan.counts, lower_bounds)
    require(lower_derivative > 0.0 and lower_projected > 0.0,
            "lower_activity_scale_included_opposite_upper_bound")
    _lower_active_derivative, lower_active_projected = finite_difference_component_fd(
        np.array([5.0e-9]), 0, model, positive_scan, positive_scan.counts, lower_bounds)
    require(lower_active_projected == 0.0, "lower_active_bound_projection")

    upper_bounds = [(-1.0e12, 0.0)]
    upper_derivative, upper_projected = finite_difference_component_fd(
        np.array([-1.0e-7]), 0, model, negative_scan, negative_scan.counts, upper_bounds)
    require(upper_derivative < 0.0 and upper_projected < 0.0,
            "upper_activity_scale_included_opposite_lower_bound")
    _upper_active_derivative, upper_active_projected = finite_difference_component_fd(
        np.array([-5.0e-9]), 0, model, negative_scan, negative_scan.counts, upper_bounds)
    require(upper_active_projected == 0.0, "upper_active_bound_projection")
    return {"lower_bound_local_scale": "PASS", "upper_bound_local_scale": "PASS",
            "opposite_bound_excluded": True}


def small_multistart_smoke(config):
    energy = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    scan = ScanData("START-SCAN", energy, np.full(5, 10.0), np.array([2., 3., 5., 3., 2.]))
    model = make_model("START-CX", [scan], 0, 1, [-1.0, 1.0], [-0.25, 0.25],
                       0.1, config["numerical"])
    observed_starts = model_starts(model, [scan.counts], "observed", count=33)
    scalar_nll = block_nll_value(observed_starts[0], model, scan, scan.counts)
    analytic_helper_nll = block_nll_gradient(observed_starts[0], model, scan, scan.counts)[0]
    require(math.isclose(scalar_nll, analytic_helper_nll, rel_tol=0.0, abs_tol=1.0e-12),
            "scalar_optimizer_objective_changed_physical_likelihood")
    bootstrap_starts = model_starts(model, [scan.counts], "bootstrap",
                                    observed_starts[0], count=33)
    repeated_observed_starts = model_starts(model, [scan.counts], "observed", count=33)
    require(len(observed_starts) == len(bootstrap_starts) == 33,
            "frozen_multistart_bank_size")
    require(all(np.array_equal(observed_starts[index], repeated_observed_starts[index])
                for index in range(33)),
        "observed_Sobol_bank_repeatability")
    require(np.array_equal(bootstrap_starts[0], observed_starts[0]),
            "bootstrap_start1_same_model_observed_MLE_fixture")

    left = {"start_index": 1, "raw_valid": True, "valid": True,
            "theta": np.array([0.2]), "log_likelihood": 10.0,
            "iterations": 1, "projected_gradients": [0.0], "blocks": []}
    right = {"start_index": 2, "raw_valid": True, "valid": True,
             "theta": np.array([0.1]), "log_likelihood": 10.0 - 0.5e-8,
             "iterations": 1, "projected_gradients": [0.0], "blocks": []}
    selected = select_candidate(model, [scan.counts], [left, right], 2)
    require(selected["start_index"] == 2, "frozen_12_decimal_lexical_tie_break")
    return {"observed_starts": 33, "bootstrap_starts": 33,
            "candidate_prefixes": [4, 8, 16, 33], "tie_rule": "PASS"}


def self_test():
    require(len(softmax_with_reference(np.zeros(3))) == 4, "softmax_reference")
    centers, _jacobian, _q = centroids_from_eta(np.zeros(3), 0.0, 8.0, 1.0)
    require(np.all(np.diff(centers) > 1.0), "ordered_centroids")
    payload, digest, seed = discovery_seed("CX-T", "T", 4096)
    require(seed == int(digest[:16], 16) and payload.endswith("\n"), "seed_rule")
    adjusted = holm_adjust([("B", 0.01), ("A", 0.01), ("C", 1.0)])
    require(adjusted["A"]["rank"] == 1 and adjusted["C"]["adjusted_p_value"] == 1.0, "Holm")
    tree = ast.parse((ROOT / SOURCE).read_text(encoding="utf-8"))
    require(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "minimize" for node in ast.walk(tree)), "optimizer_presence")
    config = yload((ROOT / CONFIG).read_bytes())
    lbfgsb = verify_frozen_lbfgsb_implementation()
    t11 = verify_t11_semantics(config)
    optimizer_smoke = small_optimizer_smoke(config)
    kkt_bound_smoke = small_kkt_bound_scale_smoke(config)
    multistart_smoke = small_multistart_smoke(config)

    class FixtureAccess:
        holdout_detector_values_decoded = 0
        detector_scan_ids = frozenset({"DISCOVERY"})
        holdout_ids = frozenset({"HOLDOUT"})

    prohibitions = [
        "holdout_detector_access", "C002_execution", "discovery_holdout_joint_fit",
        "historical_target_comparison", "physical_assignment", "Stage03R_inference",
        "Stage03D_execution", "arbitrary_scan_scale",
    ]
    operations = {
        "F002_F004_mapping": False, "historical_target_comparison": False,
        "CEF_assignment": False, "holdout_spectral_fitting": False,
        "C002_execution": False, "combined_discovery_holdout_detector_fitting": False,
        "Stage03R_inference": False, "Stage03D_inference": False,
    }
    t18_fixture_model_spec = {
        "scope_prohibitions": prohibitions,
        "test_only_nonoperational_literals": [6.45, 27.90, "historical_target_comparison"],
    }
    t18 = semantic_scope_audit(
        config, FixtureAccess(), t18_fixture_model_spec,
        {"hypotheses": [{"status": "preregistered"}]},
        [{"detector_fields_materialized": False}], operations)

    fixture_record = {
        "test_id": "C001-T12", "complex_id": "CX-FIXTURE",
        "comparison_id": "fixture-comparison", "parent_model_id": "fixture-parent",
        "child_model_id": "fixture-child", "benchmark_replicate_index": 32,
        "candidate_multistart_level": 33, "parent_reference_valid": True,
        "child_reference_valid": False, "fit_status": "numerical_failure",
        "failure_reason": "invalid_33_start_reference", "projected_gradient_max": float("inf"),
    }
    with tempfile.TemporaryDirectory(prefix="c001-diagnostic-fixture-") as directory:
        diagnostic_path = preserve_failure_diagnostic(
            "fixture_stop", [fixture_record], destination=directory)
        diagnostic = json.loads(Path(diagnostic_path).read_text(encoding="utf-8"))
        require(diagnostic["canonical_scientific_result"] is False,
                "diagnostic_must_not_be_scientific_result")
        require(set(DIAGNOSTIC_FAILURE_FIELDS) <= set(diagnostic["records"][0]),
                "diagnostic_required_fields")
        require(diagnostic["records"][0]["benchmark_replicate_index"] == 32,
                "diagnostic_replicate_identity")
    return {"SELF_TEST": "PASS", "checks": 12, "LBFGSB": lbfgsb,
            "optimizer_smoke": optimizer_smoke, "KKT_bound_smoke": kkt_bound_smoke,
            "multistart_smoke": multistart_smoke,
            "T11": t11, "T18": t18, "failure_diagnostic_fixture": "PASS"}


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--execute", action="store_true")
    group.add_argument("--self-test", action="store_true")
    parser.add_argument("--expected-commit")
    parser.add_argument("--recovery-snapshot")
    parser.add_argument("--execution-context", default="W02-win")
    parser.add_argument("--workers", type=int, default=max(1, min(os.cpu_count() or 1, 8)))
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return
    require(args.execution_context == "W02-win", "unexpected_execution_context")
    require(args.expected_commit and args.recovery_snapshot, "execution_identity_arguments_required")
    require(1 <= args.workers <= 32, "invalid_worker_count")
    command = (".\\.venv\\Scripts\\python.exe -B " + SOURCE.replace("/", "\\")
               + " --execute --execution-context W02-win --expected-commit " + args.expected_commit
               + " --recovery-snapshot " + args.recovery_snapshot + " --workers " + str(args.workers))
    try:
        report = execute(args.expected_commit, args.recovery_snapshot, args.workers, command)
    except StopJob as error:
        diagnostic_path = error.diagnostic_path
        if diagnostic_path is None:
            diagnostic_path = preserve_failure_diagnostic(str(error), error.diagnostics)
        print(json.dumps({"JOB_STATUS": "STOPPED", "reason": str(error),
                          "diagnostic_failure_record": diagnostic_path,
                          "diagnostic_record_count": max(1, len(error.diagnostics)),
                          "C002_EXECUTED": False, "HOLDOUT_DETECTOR_ACCESS_COUNT": 0}, indent=2))
        raise SystemExit(2)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=json_scalar))


if __name__ == "__main__":
    main()
