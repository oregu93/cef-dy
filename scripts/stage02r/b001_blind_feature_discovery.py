#!/usr/bin/env python3
"""Frozen B001 execution: field-projected preparation, sealed discovery, then STOP.

Byte-only integrity reads are distinct from numeric detector-field access.
The point adapter never decodes detector fields unless the immutable split
explicitly grants discovery access; det_err is never decoded.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse
import ast
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import platform
import re
import subprocess
import sys
import time

import numpy as np
import scipy
import yaml
from scipy.optimize import minimize


ROOT = Path(__file__).resolve().parents[2]
JOB = "W02-02R-B-001"
HEAD = "4fff990b40c673b1a2a679880d2495ec519f835f"
SPEC = "03_Protocols/STAGE02R_T02R04_B001_BLIND_FEATURE_DISCOVERY_SPEC.md"
SPEC_SHA = "010b54125bdd97618353e70915c009f3be0d8cd76a8547f04ca401904e9e4a86"
SOURCE = "scripts/stage02r/b001_blind_feature_discovery.py"
CONFIG = "scripts/stage02r/b001_discovery_config.yaml"
BASE2 = "04_Results/Stage02R/W02-02R-A-002/"
BASE3 = "04_Results/Stage02R/W02-02R-A-003/"
OUT = ROOT / "04_Results/Stage02R" / JOB
SNAPSHOT_ID = "20260904T071945904165Z_950dbe95_start"
SNAPSHOT_REL = f"CEF_Dy_Backup/work_recovery/{JOB}/{SNAPSHOT_ID}"
MODES = ("monitor_controlled", "time_controlled")
# Rejection definitions only; these values never enter analysis or fixtures.
AUDIT_ONLY_HISTORY = ("6.45", "18.2", "18.25", "27.90", "44.4", "F002", "F004")
CACHE = ROOT / "04_Results/cache" / JOB
POINT_META = ("scan_record_id", "file_record_id", "point_index", "e_raw",
              "time_raw", "monitor_raw", "source_data_line_number")
SELECTION_COLUMNS = (
    "scan_record_id", "raw_scan_id", "count_control_mode", "acquisition_state_id",
    "lattice_state_id", "UB_state_id", "scan_variable_raw", "pre_detector_status",
    "split_role", "discovery_runtime_status", "pre_detector_reasons",
    "source_point_count", "usable_geometry_points", "energy_order",
    "admissible_windows", "discovery_qc_reasons",
)
SPLIT_COLUMNS = (
    "scan_record_id", "count_control_mode", "acquisition_state_id",
    "pre_detector_status", "split_role", "assignment_sha256", "stratum_size",
    "stratum_holdout_count", "holdout_status", "holdout_backfill",
)


class StopJob(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise StopJob(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def yload(data):
    return yaml.load(data, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def ybytes(data):
    return yaml.dump(data, Dumper=Dumper, allow_unicode=True, sort_keys=False,
                     width=110, line_break="\n").encode("utf-8")


def csvbytes(rows, columns):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        values = {}
        for key in columns:
            v = row.get(key, "")
            if isinstance(v, (list, tuple)):
                v = ";".join(map(str, v))
            elif isinstance(v, bool):
                v = str(v).lower()
            values[key] = v
        writer.writerow(values)
    return buf.getvalue().encode("utf-8")


def write_new(name, data):
    path = OUT / name
    with path.open("xb") as handle:
        handle.write(data)


def metadata_projection(path, fields):
    """Project metadata CSVs, which contain no point detector-count values."""
    with (ROOT / path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        require(set(fields) <= set(header), "canonical_field_schema_inconsistent:" + path)
        indices = {k: header.index(k) for k in fields}
        return [{k: row[i] for k, i in indices.items()} for row in reader]


class PointAccess:
    """Decode selected fields only; unselected CSV byte spans stay opaque.

    The canonical point CSV has an unquoted numeric/token schema. Delimiter
    scanning sees the container bytes, like hashing, but never decodes unused
    field values. Field-level accesses are logged and guarded independently.
    """
    def __init__(self, discovery_ids=None, data=None):
        self.discovery_ids = None if discovery_ids is None else frozenset(discovery_ids)
        self.data = data
        self.detector_scan_ids = set()
        self.detector_values_decoded = 0

    def rows(self, fields, selected_ids=None):
        require("det_err_raw" not in fields, "holdout_or_scope_violation:det_err_access")
        detector = "detector_raw" in fields
        if detector:
            require(self.discovery_ids is not None and selected_ids is not None,
                    "holdout_or_scope_violation:detector_before_seal")
            require(set(selected_ids) <= self.discovery_ids, "holdout_or_scope_violation:non_discovery")
        else:
            require(set(fields) <= set(POINT_META), "point_projection_outside_preflight_allowlist")
        stream = io.BytesIO(self.data) if self.data is not None else (ROOT / BASE2 / "scan_points.csv").open("rb")
        with stream:
            header = stream.readline().rstrip(b"\r\n").decode("ascii").split(",")
            require(set(fields) <= set(header), "canonical_field_schema_inconsistent:point_columns")
            columns = {k: header.index(k) for k in fields}
            sid_col = header.index("scan_record_id")
            for raw_line in stream:
                require(b'"' not in raw_line, "canonical_field_schema_inconsistent:quoted_point_token")
                line = raw_line.rstrip(b"\r\n")
                delimiters = [-1]
                pos = line.find(b",")
                while pos >= 0:
                    delimiters.append(pos)
                    pos = line.find(b",", pos + 1)
                delimiters.append(len(line))
                require(len(delimiters) == len(header) + 1, "canonical_field_schema_inconsistent:point_width")
                def token(index):
                    return line[delimiters[index] + 1:delimiters[index + 1]].decode("ascii")
                sid = token(sid_col)
                if selected_ids is not None and sid not in selected_ids:
                    continue
                values = {k: token(i) for k, i in columns.items()}
                if detector:
                    self.detector_scan_ids.add(sid)
                    self.detector_values_decoded += 1
                yield values


def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def integrity():
    require(git("rev-parse", "HEAD").decode().strip() == HEAD, "canonical_input_identity_failure:HEAD")
    identities = []
    def verified(path, expected=None):
        data = (ROOT / path).read_bytes()
        require(data == git("show", "HEAD:" + path), "canonical_input_identity_failure:" + path)
        if expected is not None:
            require((len(data), sha(data)) == expected, "reviewed_input_identity_failure:" + path)
        identities.append({"path": path, "size_bytes": len(data), "sha256": sha(data)})
        return data
    spec = verified(SPEC)
    require(sha(spec) == SPEC_SHA, "frozen_specification_identity_failure")
    config = yload((ROOT / CONFIG).read_bytes())
    frozen = re.search(rb"## DETERMINISTIC_CONFIGURATION.*?```yaml\n(.*?)```", spec, re.S)
    require(frozen is not None and config == yload(frozen.group(1)), "frozen_configuration_mismatch")
    for job in ("W02-02R-A-001", "W02-02R-A-002", "W02-02R-A-003"):
        data = verified("02_Work_Checkpoints/" + job + ".md")
        meta = yload(data.decode().split("---", 2)[1])
        require(meta["review_status"] == "reviewed", "required_checkpoint_not_reviewed:" + job)
    for job, names in (
        ("W02-02R-A-002", ("scan_inventory.csv", "scan_points.csv", "quality_diagnostics.csv",
                            "semantic_verification_report.yaml", "provenance_manifest.yaml")),
        ("W02-02R-A-003", ("scan_classification.csv", "acquisition_states.yaml", "acquisition_boundaries.csv",
                            "normalization_compatibility_groups.yaml", "provenance_manifest.yaml")),
    ):
        cp = (ROOT / "02_Work_Checkpoints" / (job + ".md")).read_text()
        expected = {n: (int(size), digest) for n, size, digest in
                    re.findall(r"\| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|", cp)}
        for name in names:
            verified("04_Results/Stage02R/" + job + "/" + name, expected[name])
    p2 = yload((ROOT / BASE2 / "provenance_manifest.yaml").read_bytes())
    for name, digest in sorted(p2["A001_artifact_checksums"].items()):
        data = verified("04_Results/Stage02R/W02-02R-A-001/" + name)
        require(sha(data) == digest, "reviewed_A001_identity_failure:" + name)
    for path in ("00_Project/PROJECT_CONTROL.md", "00_Project/PROJECT_METADATA.yaml", "00_Project/PROJECT_STATE.md",
                 "03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md", "03_Protocols/DATA_CONTRACTS.md",
                 "03_Protocols/SCIENTIFIC_TERMINOLOGY.md", "03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md",
                 "03_Protocols/STAGE02R_T02R03_A003_CLASSIFICATION_SPEC.md", "03_Protocols/CHAT_BOOTSTRAPS.md",
                 "03_Protocols/WORK_RECOVERY_PROTOCOL.md", "scripts/work_recovery.py"):
        verified(path)
    metadata = yload((ROOT / "00_Project/PROJECT_METADATA.yaml").read_bytes())
    require(metadata["control"]["next_work_job"] == JOB, "execution_not_authorized")
    return config, identities


def verify_start():
    path = ROOT / "scripts/work_recovery.py"
    spec = importlib.util.spec_from_file_location("b001_recovery", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ok, saved_metadata, details = module.verify_snapshot(ROOT / SNAPSHOT_REL)
    require(ok, "recovery_infrastructure_failure:START_integrity")
    report = module.audit_snapshot(ROOT, JOB, SNAPSHOT_ID)
    require(report["SNAPSHOT_INTEGRITY"] == "PASS" and report["HEAD_SAVED"] == HEAD
            and report["BRANCH_SAVED"] == "main" and not report["GIT_OPERATION_IN_PROGRESS"],
            "recovery_infrastructure_failure:START_authority")
    return {"snapshot_id": SNAPSHOT_ID, "relative_path": SNAPSHOT_REL,
            "head": HEAD, "branch": "main", "integrity": "PASS"}


def load_metadata():
    fields = ("scan_record_id", "raw_scan_id", "scan_variable_raw", "count_control_mode",
              "preset_channel_raw", "acquisition_start_time", "acquisition_end_time",
              "acquisition_timestamp_source", "scan_point_count", "en_e_mapping_status",
              "energy_relation_status", "count_control_status", "lattice_state_id", "UB_state_id")
    rows = metadata_projection(BASE2 + "scan_inventory.csv", fields)
    scans = {row["scan_record_id"]: row for row in rows}
    classification = metadata_projection(BASE3 + "scan_classification.csv",
                                         ("scan_record_id", "acquisition_state_id", "count_control_mode",
                                          "lattice_state_id", "UB_state_id"))
    require(len(scans) == len(rows) == len(classification) == 201,
            "canonical_field_schema_inconsistent:201_scans")
    require(set(scans) == {r["scan_record_id"] for r in classification}, "canonical_scan_identity_mismatch")
    for row in classification:
        s = scans[row["scan_record_id"]]
        require(all(s[k] == row[k] for k in ("count_control_mode", "lattice_state_id", "UB_state_id")),
                "canonical_field_schema_inconsistent:metadata_join")
        s["acquisition_state_id"] = row["acquisition_state_id"]
    points = defaultdict(list)
    access = PointAccess()
    for row in access.rows(POINT_META):
        require(row["scan_record_id"] in scans, "canonical_point_scan_identity_mismatch")
        row["point_index"] = int(row["point_index"])
        points[row["scan_record_id"]].append(row)
    for sid, s in scans.items():
        points[sid].sort(key=lambda p: p["point_index"])
        require(len(points[sid]) == int(s["scan_point_count"]), "canonical_point_count_mismatch:" + sid)
        require(len({p["point_index"] for p in points[sid]}) == len(points[sid]), "duplicate_point_provenance:" + sid)
    require(access.detector_values_decoded == 0, "detector_access_before_seal")
    return scans, points


def header_duration(scan):
    try:
        start = datetime.fromisoformat(scan["acquisition_start_time"])
        end = datetime.fromisoformat(scan["acquisition_end_time"])
        seconds = (end - start).total_seconds()
        return seconds if seconds >= 0 else None
    except (ValueError, TypeError):
        return None


def exposure_gate(scan, points, config):
    mode = scan["count_control_mode"]
    require(mode in MODES, "global_exposure_semantic_contradiction:unknown_control")
    expected = "time" if mode == "time_controlled" else "monitor"
    require(scan["preset_channel_raw"] == expected, "global_exposure_semantic_contradiction:preset_channel")
    vals = np.array([number(p[expected + "_raw"]) for p in points])
    rules = config["exposure_preflight"]
    reasons = []
    if not np.isfinite(vals).all():
        reasons.append("non_finite_controlling_exposure")
    if np.any(vals <= 0):
        reasons.append("non_positive_controlling_exposure")
    evidence = {"scan_record_id": scan["scan_record_id"], "count_control_mode": mode,
                "point_count": len(vals), "controlling_field": expected + "_raw",
                "control_constancy_evidence": "full_scan" if len(vals) >= 5 else "limited_by_short_scan"}
    if not reasons and len(vals):
        median = float(np.median(vals))
        deviations = np.abs(vals / median - 1)
        within = int(np.sum(deviations <= rules["control_relative_tolerance"]))
        required = math.ceil(rules["control_required_fraction_within_tolerance"] * len(vals))
        passed = float(np.max(deviations)) <= rules["control_max_relative_deviation"]
        if len(vals) >= 5:
            passed = passed and within >= required
        evidence.update(controlling_exposure_median=median, points_within_tolerance=within,
                        required_points_within_tolerance=required, maximum_relative_deviation=float(np.max(deviations)))
        if not passed:
            reasons.append("control_constancy_test_failed")
    times = np.array([number(p["time_raw"]) for p in points])
    duration = header_duration(scan)
    time_positive = bool(np.isfinite(times).all() and np.all(times > 0))
    sum_times = float(times.sum()) if np.isfinite(times).all() else None
    duration_ok = duration is not None and time_positive and sum_times <= duration + rules["timestamp_rounding_slack_seconds"]
    evidence.update(header_duration_seconds=duration, sum_time_raw=sum_times,
                    detector_blind_duration_semantics_pass=bool(duration_ok))
    if mode == "time_controlled" and duration is not None and (sum_times is None or sum_times > duration + rules["timestamp_rounding_slack_seconds"]):
        reasons.append("time_header_duration_test_failed")
    evidence["failure_reasons"] = reasons
    evidence["status"] = "PASS" if not reasons else "SCAN_LOCAL_FAIL"
    return evidence


def windows(energy, config):
    if len(energy) < 2:
        return []
    delta = np.diff(energy)
    median = float(np.median(delta))
    answer = []
    for c in config["geometry"]["central_width_points"]:
        half = (c - 1) // 2
        for j in range(half + 3, len(energy) - half - 3):
            a, b = j - half, j + half
            lo, hi = a - 3, b + 4
            if np.any(delta[lo:hi - 1] > config["geometry"]["maximum_local_gap_ratio"] * median):
                continue
            answer.append({"j": j, "c": c, "lo": lo, "hi": hi,
                           "L": float((energy[a - 1] + energy[a]) / 2),
                           "U": float((energy[b] + energy[b + 1]) / 2)})
    return answer


def geometry(points, config):
    finite = [p for p in points if math.isfinite(number(p["e_raw"]))]
    flags = [] if len(finite) == len(points) else ["nonfinite_energy_excluded_from_geometry"]
    energy = np.array([number(p["e_raw"]) for p in finite])
    if len(energy) < config["geometry"]["minimum_usable_points"]:
        return "diagnostic_only_insufficient_geometry", finite, [], flags, "insufficient"
    if len(set(energy)) != len(energy):
        return "diagnostic_only_duplicate_energy", finite, [], flags, "duplicate"
    step = np.diff(energy)
    if not (np.all(step > 0) or np.all(step < 0)):
        return "diagnostic_only_nonmonotonic_energy", finite, [], flags, "nonmonotonic"
    order = "increasing" if step[0] > 0 else "decreasing_reversed_with_provenance"
    if step[0] < 0:
        finite = list(reversed(finite))
        energy = energy[::-1]
    valid = windows(energy, config)
    adjacent = any(a["c"] + 2 == b["c"] and abs(a["j"] - b["j"]) <= 1
                   and max(a["L"], b["L"]) <= min(a["U"], b["U"])
                   for a in valid for b in valid)
    if not adjacent:
        return "diagnostic_only_insufficient_contiguous_geometry", finite, valid, flags, order
    return "eligible_for_split", finite, valid, flags, order


def assign_split(scans, selection, config):
    strata = defaultdict(list)
    settings = config["holdout"]
    for sid in sorted(scans):
        if selection[sid]["pre_detector_status"] == "eligible_for_split":
            s = scans[sid]
            strata[(s["count_control_mode"], s["acquisition_state_id"])].append(sid)
    assignments = {}
    for (mode, state), sids in sorted(strata.items()):
        hashes = {}
        for sid in sids:
            payload = (settings["identity_version"] + "\n" + "salt=" + settings["salt"] + "\n"
                       + "count_control_mode=" + mode + "\nacquisition_state_id=" + state
                       + "\nscan_record_id=" + sid + "\n")
            hashes[sid] = sha(payload.encode("utf-8"))
        n = len(sids)
        nh = max(1, math.floor(settings["fraction"] * n)) if n >= settings["minimum_stratum_size"] else 0
        holdout = set(sorted(sids, key=lambda sid: (hashes[sid], sid))[:nh])
        for sid in sids:
            assignments[sid] = {"split_role": "holdout" if sid in holdout else "discovery",
                                "assignment_sha256": hashes[sid], "stratum_size": n,
                                "stratum_holdout_count": nh,
                                "holdout_status": "available" if nh else "unavailable_small_stratum"}
    rows = []
    for sid in sorted(scans):
        row = {k: selection[sid][k] for k in ("scan_record_id", "count_control_mode", "acquisition_state_id", "pre_detector_status")}
        row.update(assignments.get(sid, {"split_role": "not_applicable", "assignment_sha256": "",
                                        "stratum_size": 0, "stratum_holdout_count": 0,
                                        "holdout_status": "not_applicable"}))
        row["holdout_backfill"] = False
        selection[sid]["split_role"] = row["split_role"]
        rows.append(row)
    return rows


def prepare():
    require(not OUT.exists(), "existing_B001_result_tree_refuses_restart")
    config, inputs = integrity()
    recovery = verify_start()
    scans, points = load_metadata()
    selection, exposures = {}, []
    usable_geometry = {}
    # Complete the global detector-blind semantic gate for the whole primary
    # population before constructing geometry or assigning any holdout role.
    gates = {}
    for sid, s in sorted(scans.items()):
        if s["scan_variable_raw"] != "en":
            continue
        require(s["en_e_mapping_status"] == "verified" and s["energy_relation_status"] == "verified_global",
                "canonical_field_schema_inconsistent:verified_en_mapping")
        gates[sid] = exposure_gate(s, points[sid], config)
        exposures.append(gates[sid])
    for sid, s in sorted(scans.items()):
        row = {k: s[k] for k in ("scan_record_id", "raw_scan_id", "count_control_mode", "acquisition_state_id",
                                "lattice_state_id", "UB_state_id", "scan_variable_raw")}
        row.update(pre_detector_status="not_primary_energy_discovery", split_role="not_applicable",
                   discovery_runtime_status="not_evaluated", pre_detector_reasons=[],
                   source_point_count=len(points[sid]), usable_geometry_points=0, energy_order="not_evaluated",
                   admissible_windows=0, discovery_qc_reasons=[])
        selection[sid] = row
        if s["scan_variable_raw"] != "en":
            continue
        gate = gates[sid]
        if gate["status"] != "PASS":
            row["pre_detector_status"] = "diagnostic_only_exposure_preflight_failed"
            row["pre_detector_reasons"] = gate["failure_reasons"]
            continue
        status, projected, valid, flags, order = geometry(points[sid], config)
        row.update(pre_detector_status=status, pre_detector_reasons=flags,
                   usable_geometry_points=len(projected), energy_order=order, admissible_windows=len(valid))
        usable_geometry[sid] = projected
    split = assign_split(scans, selection, config)
    split_data = csvbytes(split, SPLIT_COLUMNS)
    mode_status = {}
    for mode in MODES:
        population = [e for e in exposures if e["count_control_mode"] == mode]
        passed = sum(e["status"] == "PASS" for e in population)
        mode_status[mode] = {"semantic_status": "verified" if passed else "no_usable_scans",
                             "primary_energy_scans": len(population), "exposure_passed_scans": passed,
                             "exposure_failed_scans": len(population) - passed}
    preflight = {"job_id": JOB, "status": "PASS", "global_semantic_contradictions": [],
                 "detector_fields_accessed": False, "exposure_mode_status": mode_status,
                 "scan_evidence": exposures}
    population = Counter(r["split_role"] for r in split)
    stop = "no_usable_discovery_population" if population["discovery"] == 0 else None
    diagnostic = {"job_id": JOB, "phase": "stopped_before_detector_access" if stop else "prepared_holdout_sealed",
                  "stop_reason": stop, "pre_detector_status_counts": dict(Counter(r["pre_detector_status"] for r in selection.values())),
                  "split_role_counts": dict(population), "blind_split_sha256": sha(split_data),
                  "detector_values_decoded": 0, "holdout_detector_values_decoded": 0,
                  "holdout_high_rate_status": "not_evaluated_due_to_holdout_seal",
                  "holdout_backfill": False, "recovery_start": recovery}
    provenance = {"job_id": JOB, "dataset_id": "EXP-TAIPAN-001", "repository_commit": HEAD,
                  "execution_context": "W02-Lin", "platform": "linux", "python_version": platform.python_version(),
                  "raw_data_access": "none", "raw_reparse": False, "external_auxiliary_used": False,
                  "review_status": "pending", "scientific_interpretation_status": "pending",
                  "preparation_source_sha256": sha((ROOT / SOURCE).read_bytes()),
                  "configuration_sha256": sha((ROOT / CONFIG).read_bytes()), "inputs": inputs,
                  "recovery_start": recovery, "phase": diagnostic["phase"]}
    OUT.mkdir(parents=True)
    write_new("exposure_semantic_preflight.yaml", ybytes(preflight))
    write_new("scan_selection.csv", csvbytes([selection[s] for s in sorted(selection)], SELECTION_COLUMNS))
    write_new("blind_split.csv", split_data)
    write_new("discovery_diagnostics.yaml", ybytes(diagnostic))
    write_new("provenance_manifest.yaml", ybytes(provenance))
    print(json.dumps({"phase": diagnostic["phase"], "exposure_mode_status": mode_status,
                      "pre_detector_status_counts": diagnostic["pre_detector_status_counts"],
                      "split_role_counts": dict(population), "blind_split_sha256": sha(split_data),
                      "stop_reason": stop}, sort_keys=True), flush=True)
    if stop:
        raise StopJob(stop)


def high_rate_gate(detector, times, mode, duration, config):
    """Frozen discovery-only QC; call only after split-role authorization."""
    rules = config["high_rate_qc"]
    finite_time = bool(np.isfinite(times).all() and np.all(times > 0))
    assessable = finite_time
    if mode == "monitor_controlled":
        assessable = assessable and duration is not None and float(times.sum()) <= (
            duration + config["exposure_preflight"]["timestamp_rounding_slack_seconds"])
    rates = np.full(len(detector), np.nan)
    labels = ["not_assessable"] * len(detector)
    if assessable:
        rates = detector / times
        for i, r in enumerate(rates):
            if not np.isfinite(r):
                labels[i] = "nonfinite_detector_rate"
            elif r >= rules["documented_saturation_warning_cps"]:
                labels[i] = "documented_warning_region"
            elif r >= rules["approaching_warning_cps"]:
                labels[i] = "approaching_documented_warning"
            else:
                labels[i] = "normal_rate_diagnostic"
        if np.any(rates >= rules["documented_saturation_warning_cps"]):
            return "stop_high_rate_warning_region", ["documented_warning_region"], rates, labels
    if not np.isfinite(detector).all():
        return "excluded_nonfinite_detector", ["nonfinite_detector"], rates, labels
    reasons = []
    if np.any(detector < 0):
        reasons.append("negative_detector_counts")
    if np.any(detector != np.floor(detector)):
        reasons.append("noninteger_detector_counts")
    if not assessable:
        reasons.append("diagnostic_only_high_rate_unassessable")
    if reasons:
        return "excluded_other_detector_QC", reasons, rates, labels
    return "discovery_usable", [], rates, labels


def discovery_qc():
    config, inputs = integrity()
    verify_start()
    diagnostic = yload((OUT / "discovery_diagnostics.yaml").read_bytes())
    require(diagnostic["phase"] == "prepared_holdout_sealed", "QC_phase_refuses_restart_or_unsealed_split")
    split_data = (OUT / "blind_split.csv").read_bytes()
    require(sha(split_data) == diagnostic["blind_split_sha256"], "holdout_seal_identity_failure")
    provenance = yload((OUT / "provenance_manifest.yaml").read_bytes())
    require(provenance["configuration_sha256"] == sha((ROOT / CONFIG).read_bytes()), "configuration_changed_after_seal")
    split_rows = list(csv.DictReader(io.StringIO(split_data.decode())))
    discovery_ids = {r["scan_record_id"] for r in split_rows if r["split_role"] == "discovery"}
    holdout_ids = {r["scan_record_id"] for r in split_rows if r["split_role"] == "holdout"}
    scans, points = load_metadata()
    selection = {r["scan_record_id"]: r for r in csv.DictReader((OUT / "scan_selection.csv").open())}
    require(all(selection[r["scan_record_id"]]["split_role"] == r["split_role"] for r in split_rows),
            "selection_split_identity_failure")
    access = PointAccess(discovery_ids)
    detector_rows = defaultdict(list)
    for row in access.rows((*POINT_META, "detector_raw"), selected_ids=discovery_ids):
        detector_rows[row["scan_record_id"]].append(row)
    require(access.detector_scan_ids <= discovery_ids and not (access.detector_scan_ids & holdout_ids),
            "holdout_detector_access_violation")
    qc, representation = [], []
    runtime_counts = Counter()
    stop = None
    for sid in sorted(discovery_ids):
        s = scans[sid]
        rows = sorted(detector_rows[sid], key=lambda r: int(r["point_index"]))
        d = np.array([number(r["detector_raw"]) for r in rows])
        t = np.array([number(r["time_raw"]) for r in rows])
        status, reasons, rates, labels = high_rate_gate(d, t, s["count_control_mode"], header_duration(s), config)
        selection[sid]["discovery_runtime_status"] = status
        selection[sid]["discovery_qc_reasons"] = reasons
        runtime_counts[status] += 1
        for row, rate, label in zip(rows, rates, labels):
            qc.append({"scan_record_id": sid, "point_index": int(row["point_index"]),
                       "discovery_runtime_status": status, "high_rate_status": label,
                       "detector_counts_per_second": float(rate) if math.isfinite(rate) else "",
                       "qc_reasons": reasons})
        if status == "stop_high_rate_warning_region":
            stop = "discovery_detector_documented_warning_region"
            break
        if status != "discovery_usable":
            continue
        by_index = {int(r["point_index"]): r for r in rows}
        _, ordered, _, _, _ = geometry(points[sid], config)
        for analysis_index, meta_point in enumerate(ordered):
            row = by_index[meta_point["point_index"]]
            mode = s["count_control_mode"]
            exposure_field = "monitor_raw" if mode == "monitor_controlled" else "time_raw"
            exposure = number(row[exposure_field])
            counts = number(row["detector_raw"])
            representation.append({"scan_record_id": sid, "point_index": int(row["point_index"]),
                                   "analysis_point_index": analysis_index,
                                   "file_record_id": row["file_record_id"],
                                   "source_data_line_number": int(row["source_data_line_number"]),
                                   "energy_transfer_meV": number(row["e_raw"]), "detector_counts": counts,
                                   "monitor_counts": number(row["monitor_raw"]), "time_exposure": number(row["time_raw"]),
                                   "exposure_value": exposure, "exposure_type": exposure_field,
                                   "count_control_mode": mode, "acquisition_state_id": s["acquisition_state_id"],
                                   "lattice_state_id": s["lattice_state_id"], "UB_state_id": s["UB_state_id"],
                                   "display_rate": counts / exposure, "display_sigma_rate": math.sqrt(counts) / exposure,
                                   "likelihood_model": "Poisson_E_times_lambda", "likelihood_detector_counts": counts,
                                   "likelihood_exposure": exposure, "QC_flags": labels[int(row["point_index"])],
                                   "split_role": "discovery"})
    if not stop and runtime_counts["discovery_usable"] == 0:
        stop = "no_usable_discovery_population"
    require(sha((OUT / "blind_split.csv").read_bytes()) == diagnostic["blind_split_sha256"], "holdout_seal_changed")
    qc_columns = ("scan_record_id", "point_index", "discovery_runtime_status", "high_rate_status",
                  "detector_counts_per_second", "qc_reasons")
    rep_columns = ("scan_record_id", "point_index", "analysis_point_index", "file_record_id", "source_data_line_number",
                   "energy_transfer_meV", "detector_counts", "monitor_counts", "time_exposure", "exposure_value",
                   "exposure_type", "count_control_mode", "acquisition_state_id", "lattice_state_id", "UB_state_id",
                   "display_rate", "display_sigma_rate", "likelihood_model", "likelihood_detector_counts",
                   "likelihood_exposure", "QC_flags", "split_role")
    write_new("discovery_qc.csv", csvbytes(qc, qc_columns))
    # A global high-rate STOP never produces an apparent completed discovery representation.
    if not stop:
        write_new("discovery_point_representation.csv", csvbytes(representation, rep_columns))
    (OUT / "scan_selection.csv").write_bytes(csvbytes([selection[s] for s in sorted(selection)], SELECTION_COLUMNS))
    diagnostic.update(phase="stopped_after_discovery_QC" if stop else "discovery_QC_complete",
                      stop_reason=stop, discovery_runtime_status_counts=dict(runtime_counts),
                      detector_values_decoded=access.detector_values_decoded,
                      detector_access_scan_ids=sorted(access.detector_scan_ids), holdout_detector_values_decoded=0,
                      discovery_representation_points=len(representation) if not stop else 0,
                      high_rate_status_counts=dict(Counter(r["high_rate_status"] for r in qc)))
    (OUT / "discovery_diagnostics.yaml").write_bytes(ybytes(diagnostic))
    provenance.update(phase=diagnostic["phase"], discovery_QC_source_sha256=sha((ROOT / SOURCE).read_bytes()),
                      blind_split_sha256=diagnostic["blind_split_sha256"], inputs=inputs)
    (OUT / "provenance_manifest.yaml").write_bytes(ybytes(provenance))
    print(json.dumps({k: diagnostic[k] for k in ("phase", "stop_reason", "discovery_runtime_status_counts",
                                               "detector_values_decoded", "holdout_detector_values_decoded",
                                               "high_rate_status_counts", "discovery_representation_points")}, sort_keys=True), flush=True)
    if stop:
        raise StopJob(stop)


class LocalModel:
    """The frozen offset likelihood, expressed by exact sufficient statistics.

    Count factorials and D*log(exposure) cancel in the LRT. Removing only these
    parameter-independent constants allows memoization of identical fits; no
    objective scaling, alternate optimizer, approximate statistic, or warm start
    from another window/replicate is used.
    """
    def __init__(self, energy, exposure):
        self.x = np.asarray(energy, dtype=float) - np.median(energy)
        self.exposure = np.asarray(exposure, dtype=float)
        self.z = np.zeros(len(energy))
        self.z[3:-3] = 1

    @lru_cache(maxsize=65536)
    def fit_null(self, s0, s1):
        if s0 == 0:
            return (float("-inf"), 0.0, 0.0)
        def fun(theta):
            with np.errstate(over="ignore", invalid="ignore"):
                mu = self.exposure * np.exp(theta[0] + theta[1] * self.x)
            m0, m1 = float(mu.sum()), float(mu @ self.x)
            return m0 - theta[0] * s0 - theta[1] * s1, np.array([m0 - s0, m1 - s1])
        initial = [math.log(max(s0, 0.5) / float(self.exposure.sum())), 0.0]
        result = minimize(fun, initial, jac=True, method="L-BFGS-B", bounds=[(None, None), (None, None)],
                          options={"maxiter": 500, "ftol": 1.0e-12, "gtol": 1.0e-8})
        if not result.success or not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            return None
        return float(result.x[0]), float(result.x[1]), float(result.fun)

    @lru_cache(maxsize=65536)
    def fit_statistic(self, s0, s1, sc):
        if s0 == 0:
            return 0.0
        null = self.fit_null(s0, s1)
        if null is None:
            return None
        def fun(theta):
            with np.errstate(over="ignore", invalid="ignore"):
                mu = self.exposure * np.exp(theta[0] + theta[1] * self.x + theta[2] * self.z)
            m0, m1, mc = float(mu.sum()), float(mu @ self.x), float(mu @ self.z)
            return m0 - theta[0] * s0 - theta[1] * s1 - theta[2] * sc, np.array([m0 - s0, m1 - s1, mc - sc])
        result = minimize(fun, [null[0], null[1], 0.0], jac=True, method="L-BFGS-B",
                          bounds=[(None, None), (None, None), (0.0, None)],
                          options={"maxiter": 500, "ftol": 1.0e-12, "gtol": 1.0e-8})
        if not result.success or not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            return None
        statistic = 2.0 * (null[2] - float(result.fun))
        if statistic < -1.0e-7:
            return None
        return max(0.0, statistic)

    def statistic(self, detector):
        return self.fit_statistic(float(detector.sum()), float(detector @ self.x), float(detector @ self.z))


@lru_cache(maxsize=2048)
def local_model(centered_energy, exposure):
    return LocalModel(centered_energy, exposure)


def model_for(energy, exposure):
    x = energy - np.median(energy)
    return local_model(tuple(map(float, x)), tuple(map(float, exposure)))


def nuisance_field(energy, exposure, detector):
    result = []
    for i in range(len(energy)):
        lo = min(max(i - 4, 0), len(energy) - 9)
        hi = lo + 9
        model = model_for(energy[lo:hi], exposure[lo:hi])
        local_d = detector[lo:hi]
        fit = model.fit_null(float(local_d.sum()), float(local_d @ model.x))
        if fit is None:
            return None
        value = 0.0 if local_d.sum() == 0 else float(exposure[i] * math.exp(fit[0] + fit[1] * model.x[i - lo]))
        if not math.isfinite(value) or value < 0:
            return None
        result.append(value)
    return np.array(result)


def bootstrap_seed(scan_id, config):
    b = config["bootstrap"]
    payload = (b["seed_version"] + "\nmaster=" + b["master_seed_text"] + "\nscan_record_id=" + scan_id + "\n")
    return int(sha(payload.encode("utf-8"))[:16], 16)


def fwer_p(statistic, maxima):
    return (1 + int(np.sum(np.asarray(maxima) >= statistic))) / (len(maxima) + 1)


def persistent_candidates(primitive):
    significant = [w for w in primitive if w["p_FWER"] <= 0.05]
    persistent = [a for a in significant if any(abs(a["c"] - b["c"]) == 2
                  and abs(a["j"] - b["j"]) <= 1
                  and max(a["L"], b["L"]) <= min(a["U"], b["U"]) for b in significant)]
    remaining = sorted(persistent, key=lambda w: (w["p_FWER"], -w["T"], w["energy"], w["c"], w["j"]))
    answer = []
    while remaining:
        seed = remaining[0]
        absorbed = [w for w in remaining if max(seed["L"], w["L"]) <= min(seed["U"], w["U"])
                    and abs(seed["j"] - w["j"]) <= 1]
        absorbed_keys = {(w["j"], w["c"]) for w in absorbed}
        remaining = [w for w in remaining if (w["j"], w["c"]) not in absorbed_keys]
        answer.append({"L": seed["L"], "U": seed["U"], "representative_energy": (seed["L"] + seed["U"]) / 2,
                       "p_FWER": seed["p_FWER"], "T": seed["T"], "seed_center_index": seed["j"],
                       "seed_central_width": seed["c"], "absorbed_window_count": len(absorbed),
                       "persistent_scales": sorted({w["c"] for w in absorbed}),
                       "support_union_L": min(w["L"] for w in absorbed),
                       "support_union_U": max(w["U"] for w in absorbed)})
    return sorted(answer, key=lambda c: (c["representative_energy"], c["p_FWER"], -c["T"]))


def analyze_scan(scan_id, energy, exposure, detector, config):
    valid = windows(energy, config)
    models = [(w, model_for(energy[w["lo"]:w["hi"]], exposure[w["lo"]:w["hi"]])) for w in valid]
    mu0 = nuisance_field(energy, exposure, detector)
    if mu0 is None:
        return {"scan_record_id": scan_id, "status": "numeric_exclusion", "reason": "nuisance_field_fit_failure"}
    observed, observed_failures = [], []
    for w, model in models:
        value = model.statistic(detector[w["lo"]:w["hi"]])
        if value is None:
            observed_failures.append({"j": w["j"], "c": w["c"], "reason": "local_fit_failure"})
        else:
            observed.append({**w, "T": value, "energy": float(energy[w["j"]])})
    seed = bootstrap_seed(scan_id, config)
    rng = np.random.Generator(np.random.PCG64(seed))
    maxima, failure_count = [], 0
    for replicate in range(config["bootstrap"]["replicates"]):
        simulated = rng.poisson(mu0).astype(float)
        largest = None
        for w, model in models:
            value = model.statistic(simulated[w["lo"]:w["hi"]])
            if value is None:
                failure_count += 1
            else:
                largest = value if largest is None else max(largest, value)
        if largest is None:
            return {"scan_record_id": scan_id, "status": "numeric_exclusion", "reason": "bootstrap_no_valid_window",
                    "failed_replicate": replicate}
        maxima.append(largest)
    for w in observed:
        w["p_FWER"] = fwer_p(w["T"], maxima)
    candidates = persistent_candidates(observed)
    return {"scan_record_id": scan_id, "status": "complete", "seed": seed,
            "admissible_windows": len(valid), "observed_fit_failures": observed_failures,
            "bootstrap_fit_failure_count": failure_count, "bootstrap_replicates": len(maxima),
            "bootstrap_scan_maxima": maxima, "bootstrap_scan_maxima_sha256": sha(np.asarray(maxima, dtype="<f8").tobytes()),
            "nuisance_mean_sha256": sha(np.asarray(mu0, dtype="<f8").tobytes()),
            "significant_primitive_count": sum(w["p_FWER"] <= config["bootstrap"]["familywise_alpha"] for w in observed),
            "candidates": candidates}


def position_compatible(a, b):
    ca, cb = (a["L"] + a["U"]) / 2, (b["L"] + b["U"]) / 2
    return max(a["L"], b["L"]) <= min(a["U"], b["U"]) and b["L"] <= ca <= b["U"] and a["L"] <= cb <= a["U"]


def consolidate(candidates):
    clusters = []
    for mode in MODES:
        remaining = sorted([c for c in candidates if c["count_control_mode"] == mode],
                           key=lambda c: (c["representative_energy"], c["p_FWER"], c["scan_record_id"], c["candidate_id"]))
        while remaining:
            members, rest = [remaining[0]], remaining[1:]
            while True:
                next_rest = []
                changed = False
                for candidate in rest:
                    if candidate["scan_record_id"] not in {c["scan_record_id"] for c in members} and all(
                            position_compatible(candidate, c) for c in members):
                        members.append(candidate)
                        changed = True
                    else:
                        next_rest.append(candidate)
                rest = next_rest
                if not changed:
                    break
            remaining = rest
            states = sorted({m["acquisition_state_id"] for m in members})
            tier = 0 if len(members) == 1 else (2 if len(states) > 1 else 1)
            lo, hi = max(m["L"] for m in members), min(m["U"] for m in members)
            clusters.append({"count_control_mode": mode, "L": lo, "U": hi,
                             "representative_energy": (lo + hi) / 2, "reproducibility_tier": tier,
                             "supporting_scan_record_ids": sorted(m["scan_record_id"] for m in members),
                             "supporting_acquisition_state_ids": states, "members": members})
    clusters.sort(key=lambda c: (c["representative_energy"], c["count_control_mode"], c["supporting_scan_record_ids"]))
    features = []
    for cluster in clusters:
        if cluster["reproducibility_tier"] == 0:
            continue
        features.append({"blind_feature_id": f"BF-{len(features) + 1:03d}", "count_control_mode": cluster["count_control_mode"],
                         "discovery_energy_interval": [cluster["L"], cluster["U"]],
                         "discovery_location_not_confirmatory_centroid": cluster["representative_energy"],
                         "supporting_scan_record_ids": cluster["supporting_scan_record_ids"],
                         "supporting_acquisition_state_ids": cluster["supporting_acquisition_state_ids"],
                         "reproducibility_tier": f"tier_{cluster['reproducibility_tier']}",
                         "scan_level_support_intervals": [{"scan_record_id": m["scan_record_id"],
                                                           "interval": [m["L"], m["U"]],
                                                           "p_FWER": m["p_FWER"], "T": m["T"]} for m in cluster["members"]],
                         "cross_mode_position_recurrence": []})
    for a in features:
        for b in features:
            if a["count_control_mode"] != b["count_control_mode"] and position_compatible(
                    dict(zip(("L", "U"), a["discovery_energy_interval"])),
                    dict(zip(("L", "U"), b["discovery_energy_interval"]))):
                a["cross_mode_position_recurrence"].append(b["blind_feature_id"])
    return clusters, features


def fixture_points(n, energy=None, exposure=None):
    energy = np.arange(n, dtype=float) if energy is None else np.asarray(energy)
    exposure = np.ones(n) if exposure is None else np.asarray(exposure)
    return [{"scan_record_id": "SYNTHETIC", "point_index": i, "e_raw": str(e),
             "time_raw": str(t), "monitor_raw": str(t)} for i, (e, t) in enumerate(zip(energy, exposure))]


def fixture_scan(mode="time_controlled"):
    return {"scan_record_id": "SYNTHETIC", "count_control_mode": mode,
            "preset_channel_raw": "time" if mode == "time_controlled" else "monitor",
            "acquisition_start_time": "2000-01-01T00:00:00", "acquisition_end_time": "2000-01-01T01:00:00"}


def test_static_blindness(config):
    tree = ast.parse((ROOT / SOURCE).read_text())
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "AUDIT_ONLY_HISTORY" for t in n.targets))]
    text = ast.unparse(tree) + ybytes(config).decode()
    for token in AUDIT_ONLY_HISTORY:
        require(re.search(r"(?<![0-9.])" + re.escape(token) + r"(?![0-9.])", text) is None,
                "historical_token_outside_static_audit_definition")
    return {"static_source_config": "PASS", "history_definitions_rejection_only": True,
            "synthetic_origin": "middle_of_dimensionless_native_grid"}


def test_exposure(config):
    for mode in MODES:
        s = fixture_scan(mode)
        require(exposure_gate(s, fixture_points(20), config)["status"] == "PASS", "constant_exposure")
        try:
            exposure_gate(dict(s, preset_channel_raw="invalid"), fixture_points(9), config)
        except StopJob:
            pass
        else:
            raise StopJob("global_semantic_contradiction_not_stopped")
        for value, reason in [(float("nan"), "non_finite_controlling_exposure"),
                              (0, "non_positive_controlling_exposure"), (-1, "non_positive_controlling_exposure")]:
            v = np.ones(20); v[0] = value
            require(reason in exposure_gate(s, fixture_points(20, exposure=v), config)["failure_reasons"], reason)
        v = np.ones(20); v[0] = 1.2
        require(exposure_gate(s, fixture_points(20, exposure=v), config)["status"] == "PASS", "exact_fraction_rule")
        v[1] = 1.2
        require("control_constancy_test_failed" in exposure_gate(s, fixture_points(20, exposure=v), config)["failure_reasons"], "constancy_fraction")
        v = np.ones(4); v[0] = 1.2
        short = exposure_gate(s, fixture_points(4, exposure=v), config)
        require(short["status"] == "PASS" and short["control_constancy_evidence"] == "limited_by_short_scan", "short_scan_rule")
    s = fixture_scan(); s["acquisition_end_time"] = "2000-01-01T00:00:05"
    require("time_header_duration_test_failed" in exposure_gate(s, fixture_points(9), config)["failure_reasons"], "duration_rule")
    return {"global_vs_local": "PASS", "exact_exposure_rules": "PASS", "short_scan_rule": "PASS", "detector_access": False}


def test_holdout(config):
    for n, expected in [(3, 0), (4, 1), (8, 2)]:
        scans = {f"SYN-{i:03d}": {"scan_record_id": f"SYN-{i:03d}", "count_control_mode": "monitor_controlled",
                                 "acquisition_state_id": "SYN-STATE"} for i in range(n)}
        selection = {sid: dict(s, pre_detector_status="eligible_for_split") for sid, s in scans.items()}
        a = assign_split(scans, selection, config)
        b = assign_split(dict(reversed(list(scans.items()))), selection, config)
        require(a == b and sum(r["split_role"] == "holdout" for r in a) == expected, "holdout_rule_or_order")
        for r in a:
            payload = ("stage02r_b001_holdout_v1\nsalt=CEF-Dy:T-02R-04:W02-02R-B-001:algorithmic-holdout-v1\n"
                       "count_control_mode=monitor_controlled\nacquisition_state_id=SYN-STATE\nscan_record_id=" + r["scan_record_id"] + "\n")
            require(r["assignment_sha256"] == sha(payload.encode()), "holdout_payload")
    columns = (*POINT_META, "detector_raw", "det_err_raw")
    def data(poison):
        return csvbytes([{"scan_record_id": sid, "file_record_id": "SYN-FILE", "point_index": i,
                          "e_raw": i - 4, "time_raw": 1, "monitor_raw": 1, "source_data_line_number": i,
                          "detector_raw": poison if sid == "HOLDOUT" else 12,
                          "det_err_raw": poison if sid == "HOLDOUT" else 0}
                         for sid in ("DISCOVERY", "HOLDOUT") for i in range(9)], columns)
    signatures = []
    for poison in ("12", "POISON_ERROR_IF_DECODED", "nan", "1e200"):
        access = PointAccess({"DISCOVERY"}, data(poison))
        projected = list(access.rows((*POINT_META, "detector_raw"), {"DISCOVERY"}))
        require(access.detector_scan_ids == {"DISCOVERY"} and access.detector_values_decoded == 9, "poison_holdout_access")
        signatures.append(csvbytes(projected, (*POINT_META, "detector_raw")))
        pre = PointAccess(data=data(poison))
        require(len(list(pre.rows(POINT_META))) == 18 and pre.detector_values_decoded == 0, "preflight_poison_access")
    require(all(v == signatures[0] for v in signatures), "poison_changed_discovery_input_bytes")
    e, exposure, d = np.arange(-4, 5, dtype=float), np.ones(9), np.full(9, 12.0)
    first = analyze_scan("SYNTHETIC-SEAL-001", e, exposure, d, config)
    second = analyze_scan("SYNTHETIC-SEAL-001", e, exposure, d, config)
    require(first["status"] == "complete" and ybytes(first) == ybytes(second), "full_discovery_determinism")
    return {"exact_hash_rule": "PASS", "order_invariance": "PASS", "poison_variants": 4,
            "discovery_input_bytes_invariant": True, "full_discovery_content_deterministic": True,
            "holdout_detector_access": 0, "holdout_backfill": False}


def test_geometry(config):
    require(geometry(fixture_points(8), config)[0] == "diagnostic_only_insufficient_geometry", "N8_geometry")
    g = geometry(fixture_points(9), config)
    require(g[0] == "eligible_for_split" and {w["c"] for w in g[2]} == {1, 3}, "N9_geometry")
    require({w["c"] for w in windows(np.arange(13.), config)} == {1, 3, 5, 7}, "frozen_widths")
    for w in windows(np.arange(13.), config):
        require(w["hi"] - w["lo"] == w["c"] + 6 and w["lo"] >= 0 and w["hi"] <= 13, "full_flanks")
    e = np.r_[np.arange(10.), np.arange(100., 110.)]
    for w in windows(e, config):
        require(not (w["lo"] <= 9 and w["hi"] > 10), "gap_window_crossing")
    require(geometry(fixture_points(9, np.arange(8, -1, -1)), config)[4] == "decreasing_reversed_with_provenance", "descending_provenance")
    return {"minimum_9": "PASS", "widths": [1, 3, 5, 7], "flanks": [3, 3], "gap_rule": "PASS", "detector_dependency": False}


def test_mode_separation(config):
    with (OUT / "discovery_point_representation.csv").open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        field = "monitor_counts" if row["count_control_mode"] == "monitor_controlled" else "time_exposure"
        require(float(row["likelihood_exposure"]) == float(row[field]) == float(row["exposure_value"]), "wrong_primary_exposure")
        require(float(row["likelihood_detector_counts"]) == float(row["detector_counts"]), "wrong_likelihood_counts")
    require(not config["reproducibility"]["cross_mode_amplitude_comparison"], "cross_mode_amplitude")
    return {"real_discovery_rows_checked": len(rows), "controlling_exposure_only": "PASS", "common_or_A003_scale": "absent"}


def test_statistic(config):
    e, exposure = np.arange(-5, 6, dtype=float), np.ones(11)
    model = model_for(e, exposure)
    require(model.statistic(np.zeros(11)) == 0, "zero_window")
    values = []
    for central in (10, 20, 30):
        d = np.full(11, 10.0); d[3:-3] = central
        value = model.statistic(d)
        require(value is not None, "synthetic_local_fit_failure")
        values.append(value)
    mean = (6 * 10 + 5 * 20) / 11
    exact = 2 * (6 * 10 * math.log(10 / mean) + 5 * 20 * math.log(20 / mean))
    require(abs(values[1] - exact) < 1e-6 and values[0] < values[1] < values[2], "exact_LRT_or_monotonicity")
    d = np.full(11, 20.0); d[3:-3] = 5
    deficit = model.statistic(d)
    require(deficit is not None and deficit < 1e-6, "one_sided_delta_bound")
    require(config["optimizer"] == {"implementation": "scipy.optimize.minimize", "method": "L-BFGS-B", "maxiter": 500,
                                     "ftol": 1e-12, "gtol": 1e-8}, "optimizer_config")
    return {"exact_LRT_error": abs(values[1] - exact), "monotonic_statistics": values,
            "deficit_statistic": deficit, "optimizer": config["optimizer"], "zero_window": "PASS"}


def test_bootstrap(config):
    sid = "SYNTHETIC-SEED-001"
    payload = ("stage02r_b001_bootstrap_seed_v1\nmaster=CEF-Dy:T-02R-04:W02-02R-B-001:bootstrap-v1\nscan_record_id=" + sid + "\n")
    seed = int(sha(payload.encode())[:16], 16)
    require(bootstrap_seed(sid, config) == seed and config["bootstrap"]["replicates"] == 2048, "seed_or_replicates")
    a = np.random.Generator(np.random.PCG64(seed)).poisson(25, (2048, 9))
    b = np.random.Generator(np.random.PCG64(seed)).poisson(25, (2048, 9))
    require(a.tobytes() == b.tobytes(), "PCG64_determinism")
    simulated = np.column_stack((np.zeros(2048), np.full(2048, 20.0)))
    require(fwer_p(10.0, simulated.max(axis=1)) == 1.0, "scan_maximum_not_same_window")
    require(fwer_p(30.0, simulated.max(axis=1)) == 1 / 2049, "authoritative_FWER_denominator")
    return {"replicates": 2048, "seed": seed, "seed_payload_sha256": sha(payload.encode()),
            "rng": "PCG64", "scan_maximum_rule": "PASS", "denominator": 2049, "familywise_alpha": 0.05}


def test_high_rate(config):
    for count, expected in [(27999, "normal_rate_diagnostic"), (28000, "approaching_documented_warning"),
                             (34999, "approaching_documented_warning"), (35000, "documented_warning_region")]:
        status, _, _, labels = high_rate_gate(np.array([float(count)]), np.ones(1), "time_controlled", 1, config)
        require(labels == [expected], "high_rate_boundary")
        require((status == "stop_high_rate_warning_region") == (count >= 35000), "high_rate_global_stop")
    d = yload((OUT / "discovery_diagnostics.yaml").read_bytes())
    require(d["holdout_detector_values_decoded"] == 0 and d["holdout_high_rate_status"] == "not_evaluated_due_to_holdout_seal", "holdout_high_rate_opened")
    return {"approaching_cps": 28000, "stop_cps": 35000, "boundary_tests": "PASS",
            "holdout_high_rate_status": "not_evaluated_due_to_holdout_seal", "dead_time_correction": False}


def test_qc(config):
    cases = [(np.array([0, 1, 2, 3, 3, 5, 6, 7, 8]), "diagnostic_only_duplicate_energy"),
             (np.array([0, 1, 2, 3, 2.5, 5, 6, 7, 8]), "diagnostic_only_nonmonotonic_energy"),
             (np.array([0, 1, 2, 3, 100, 101, 102, 103, 104]), "diagnostic_only_insufficient_contiguous_geometry")]
    for e, expected in cases:
        require(geometry(fixture_points(9, e), config)[0] == expected, expected)
    e = np.arange(9.); e[4] = np.nan
    require(geometry(fixture_points(9, e), config)[0] == "diagnostic_only_insufficient_geometry", "nonfinite_energy")
    for d, t, expected, reason in [([np.nan], [1], "excluded_nonfinite_detector", "nonfinite_detector"),
                                 ([-1], [1], "excluded_other_detector_QC", "negative_detector_counts"),
                                 ([1.5], [1], "excluded_other_detector_QC", "noninteger_detector_counts"),
                                 ([10], [0], "excluded_other_detector_QC", "diagnostic_only_high_rate_unassessable")]:
        status, reasons, _, _ = high_rate_gate(np.array(d), np.array(t), "monitor_controlled", 1, config)
        require(status == expected and reason in reasons, "detector_QC_fixture")
    for w in windows(np.arange(31.), config):
        require(w["j"] - (w["c"] - 1) // 2 >= 3 and w["j"] + (w["c"] - 1) // 2 < 28, "endpoint_only_support")
    for row in csv.DictReader((OUT / "scan_selection.csv").open()):
        if row["split_role"] != "discovery":
            require(row["discovery_runtime_status"] == "not_evaluated", "mixed_status_axes")
    return {"nonfinite_energy_detector": "PASS", "negative_noninteger_counts": "PASS", "geometry_failures": "PASS",
            "endpoint_full_flanks": "PASS", "unassessable_high_rate": "PASS", "separated_status_axes": "PASS"}


def test_persistence(config):
    def w(j, c, lo, hi, p=0.01, t=10):
        return {"j": j, "c": c, "L": lo, "U": hi, "p_FWER": p, "T": t, "energy": float(j)}
    require(not persistent_candidates([w(0, 1, -1, 1)]), "one_scale_candidate")
    require(len(persistent_candidates([w(0, 1, -1, 1), w(1, 3, 0, 2)])) == 1, "adjacent_scales")
    require(not persistent_candidates([w(0, 1, -1, 1), w(2, 3, 1, 3)]), "center_shift_greater_than_one")
    result = persistent_candidates([w(0, 1, -1, 1, 0.001, 20), w(1, 3, 0, 2), w(2, 5, 1, 3), w(3, 7, 2, 4)])
    require(len(result) == 2 and result[0]["support_union_U"] == 2, "transitive_merge_forbidden")
    return {"adjacent_scale_requirement": "PASS", "one_point_shift": "PASS", "non_transitive_merge": "PASS"}


def test_reproducibility(config):
    def c(sid, state="A", mode="monitor_controlled", lo=-1., hi=1.):
        return {"candidate_id": sid, "scan_record_id": sid, "acquisition_state_id": state,
                "count_control_mode": mode, "L": lo, "U": hi, "representative_energy": (lo + hi) / 2,
                "p_FWER": 0.01, "T": 10.}
    require(not consolidate([c("S1")])[1], "single_scan_catalogue")
    require(consolidate([c("S1"), c("S2")])[1][0]["reproducibility_tier"] == "tier_1", "tier_1")
    require(consolidate([c("S1"), c("S2", "B")])[1][0]["reproducibility_tier"] == "tier_2", "tier_2")
    require(not consolidate([c("S1"), c("S2", mode="time_controlled")])[1], "cross_mode_rescued_tier0")
    candidates = [c("S1"), c("S2"), c("S3", mode="time_controlled"), c("S4", mode="time_controlled")]
    a = consolidate(candidates)[1]; b = consolidate(list(reversed(candidates)))[1]
    require(ybytes(a) == ybytes(b) and len(a) == 2 and all(len(f["cross_mode_position_recurrence"]) == 1 for f in a), "cross_mode_annotation_or_order")
    clusters, _ = consolidate([c("S1", lo=-2, hi=0), c("S2", lo=-1, hi=1), c("S3", lo=0, hi=2)])
    require(max(len(g["members"]) for g in clusters) == 2, "complete_link_not_single_link")
    return {"tiers_0_1_2": "PASS", "complete_link": "PASS", "cross_mode_position_only": "PASS", "input_order_invariance": "PASS"}


def test_scope(config):
    tree = ast.parse((ROOT / SOURCE).read_text())
    banned = {"curve_fit", "least_squares", "gaussian_filter", "find_peaks"}
    calls = {n.func.id if isinstance(n.func, ast.Name) else n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))}
    require(not (calls & banned), "scope_forbidden_statistical_operation")
    protected = ["00_Project/PROJECT_CONTROL.md", "00_Project/PROJECT_METADATA.yaml", "00_Project/PROJECT_STATE.md", "README.md",
                 "00_Project/RESULT_REGISTER.yaml", "00_Project/EVIDENCE_REGISTER.yaml", "00_Project/HYPOTHESIS_REGISTER.yaml",
                 "00_Project/MODEL_REGISTER.yaml", "00_Project/DECISION_REGISTER.yaml", SPEC,
                 "03_Protocols/WORK_RECOVERY_PROTOCOL.md", "scripts/work_recovery.py", "scripts/project_transition.py"]
    for p in protected:
        require((ROOT / p).read_bytes() == git("show", "HEAD:" + p), "protected_file_changed:" + p)
    return {"protected_files_identical": len(protected), "raw_reparse": False, "corrections_or_physical_subtraction": False,
            "line_shape_fitting": False, "historical_comparison": False, "local_nuisance_terms_only": True}


def synthetic_worker(task):
    kind, index, source_hash = task
    config = yload((ROOT / CONFIG).read_bytes())
    seed = int(sha(("stage02r_b001_synthetic_" + kind + "_fixture_v1").encode())[:16], 16)
    rng = np.random.Generator(np.random.PCG64(seed))
    e = np.arange(31, dtype=float) - 15
    mean = config["synthetic_null_test"]["mean_counts_at_center"] * np.exp(config["synthetic_null_test"]["log_rate_slope_per_grid_unit"] * e)
    if kind == "injection":
        mean[14:17] *= config["synthetic_injection_test"]["rate_multiplier"]
    generated = rng.poisson(mean, (100, 31)).astype(float)
    result = analyze_scan(f"SYNTHETIC-{kind.upper()}-{index:03d}", e, np.ones(31), generated[index], config)
    result.pop("bootstrap_scan_maxima", None)
    result.update(fixture_data_seed=seed, source_sha256=source_hash)
    return index, result


def calibration(kind, config, workers):
    directory = CACHE / ("synthetic_" + kind)
    directory.mkdir(parents=True, exist_ok=True)
    source_hash = sha((ROOT / SOURCE).read_bytes())
    results, missing = {}, []
    for i in range(100):
        path = directory / f"{i:03d}.json"
        if path.exists():
            saved = json.loads(path.read_bytes())
            require(saved["source_sha256"] == source_hash, "synthetic_cache_source_identity_mismatch")
            results[i] = saved
        else:
            missing.append(i)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(synthetic_worker, (kind, i, source_hash)) for i in missing]
        for future in as_completed(futures):
            i, result = future.result()
            with (directory / f"{i:03d}.json").open("xb") as handle:
                handle.write((json.dumps(result, sort_keys=True, allow_nan=False) + "\n").encode())
            results[i] = result
            print(f"SYNTHETIC_{kind.upper()} {len(results)}/100 completed", flush=True)
    ordered = [results[i] for i in range(100)]
    numeric = sum(r["status"] != "complete" for r in ordered)
    positives = sum(bool(r.get("candidates", [])) for r in ordered)
    recovered = sum(any(c["L"] <= 0 <= c["U"] for c in r.get("candidates", [])) for r in ordered)
    if kind == "null":
        require(positives <= config["synthetic_null_test"]["max_false_positive_scans"], f"synthetic_null_false_positives:{positives}")
    else:
        require(recovered >= config["synthetic_injection_test"]["minimum_recovered_scans"], f"synthetic_injection_recovered:{recovered}")
    require(all(r["bootstrap_replicates"] == 2048 for r in ordered if r["status"] == "complete"), "synthetic_replicate_count")
    return {"scans": 100, "points": 31, "replicates_per_scan": 2048,
            "false_positive_scans": positives if kind == "null" else None,
            "recovered_at_middle_grid_point": recovered if kind == "injection" else None,
            "numeric_excluded_scans": numeric, "fixture_seed": ordered[0]["fixture_data_seed"], "scan_results": ordered}


def mandatory_tests(workers):
    config, inputs = integrity()
    require(yload((OUT / "discovery_diagnostics.yaml").read_bytes())["phase"] == "discovery_QC_complete", "tests_before_QC_gate")
    report_path = OUT / "test_report.yaml"
    source_hash = sha((ROOT / SOURCE).read_bytes())
    if report_path.exists():
        report = yload(report_path.read_bytes())
        require(report["source_sha256"] == source_hash and report["failed"] == 0, "tests_refuse_changed_source_or_failed_restart")
    else:
        report = {"job_id": JOB, "required_tests": 16, "passed": 0, "failed": 0, "not_run": 16,
                  "source_sha256": source_hash, "tests": [{"test_id": f"B001-T{i:02d}", "status": "not_run"} for i in range(1, 17)],
                  "scientific_review_status": "pending"}
    functions = {
        1: lambda: {"canonical_head": HEAD, "input_identities_verified": len(inputs), "canonical_scans": len(load_metadata()[0]), "raw_reparse": False},
        2: lambda: test_static_blindness(config), 3: lambda: test_exposure(config), 4: lambda: test_holdout(config),
        5: lambda: test_geometry(config), 6: lambda: test_mode_separation(config), 7: lambda: test_statistic(config),
        8: lambda: test_bootstrap(config), 9: lambda: calibration("null", config, workers),
        10: lambda: calibration("injection", config, workers), 11: lambda: test_high_rate(config),
        12: lambda: test_qc(config), 13: lambda: test_persistence(config), 14: lambda: test_reproducibility(config),
        15: lambda: test_scope(config),
    }
    for i in range(1, 16):
        row = report["tests"][i - 1]
        if row["status"] == "PASS":
            continue
        print(f"B001-T{i:02d}: RUNNING", flush=True)
        try:
            row.update(status="PASS", evidence=functions[i]())
        except Exception as exc:
            row.update(status="FAIL", failure=str(exc))
            report.update(passed=sum(t["status"] == "PASS" for t in report["tests"]), failed=1,
                          not_run=sum(t["status"] == "not_run" for t in report["tests"]))
            report_path.write_bytes(ybytes(report))
            raise StopJob(f"mandatory_test_failure:B001-T{i:02d}:{exc}") from exc
        report.update(passed=sum(t["status"] == "PASS" for t in report["tests"]), failed=0,
                      not_run=sum(t["status"] == "not_run" for t in report["tests"]))
        report_path.write_bytes(ybytes(report))
        print(f"B001-T{i:02d}: PASS", flush=True)
    print("PRE_DISCOVERY_TESTS: 15 PASS; B001-T16 awaits actual catalogue freeze", flush=True)


def actual_scan_worker(task):
    sid, rows = task
    config = yload((ROOT / CONFIG).read_bytes())
    rows = sorted(rows, key=lambda r: int(r["analysis_point_index"]))
    return analyze_scan(sid, np.array([float(r["energy_transfer_meV"]) for r in rows]),
                        np.array([float(r["likelihood_exposure"]) for r in rows]),
                        np.array([float(r["likelihood_detector_counts"]) for r in rows]), config)


def execute_statistics(workers):
    config, inputs = integrity()
    verify_start()
    report_path = OUT / "test_report.yaml"
    report = yload(report_path.read_bytes())
    source_hash = sha((ROOT / SOURCE).read_bytes())
    require(report["source_sha256"] == source_hash and report["passed"] == 15 and report["failed"] == 0,
            "mandatory_tests_not_passed_or_source_changed")
    diagnostic = yload((OUT / "discovery_diagnostics.yaml").read_bytes())
    require(diagnostic["phase"] == "discovery_QC_complete", "discovery_phase_refuses_restart")
    require(sha((OUT / "blind_split.csv").read_bytes()) == diagnostic["blind_split_sha256"], "holdout_seal_identity_failure")
    split = list(csv.DictReader((OUT / "blind_split.csv").open()))
    allowed = {r["scan_record_id"] for r in split if r["split_role"] == "discovery"}
    rows_by_scan = defaultdict(list)
    with (OUT / "discovery_point_representation.csv").open() as handle:
        for row in csv.DictReader(handle):
            require(row["scan_record_id"] in allowed and row["split_role"] == "discovery", "holdout_in_representation")
            rows_by_scan[row["scan_record_id"]].append(row)
    require(bool(rows_by_scan), "no_usable_discovery_population")
    directory = CACHE / "discovery"
    directory.mkdir(parents=True, exist_ok=True)
    results, tasks = {}, []
    for sid, rows in sorted(rows_by_scan.items()):
        path = directory / (sid + ".json")
        if path.exists():
            wrapper = json.loads(path.read_bytes())
            require(wrapper["source_sha256"] == source_hash and wrapper["split_sha256"] == diagnostic["blind_split_sha256"], "discovery_cache_identity_mismatch")
            results[sid] = wrapper["result"]
        else:
            tasks.append((sid, rows))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(actual_scan_worker, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result(); sid = result["scan_record_id"]
            wrapper = {"source_sha256": source_hash, "split_sha256": diagnostic["blind_split_sha256"], "result": result}
            with (directory / (sid + ".json")).open("xb") as handle:
                handle.write((json.dumps(wrapper, sort_keys=True, allow_nan=False) + "\n").encode())
            results[sid] = result
            print(f"DISCOVERY_SCANS {len(results)}/{len(rows_by_scan)} completed", flush=True)
    selection = {r["scan_record_id"]: r for r in csv.DictReader((OUT / "scan_selection.csv").open())}
    candidates = []
    for sid, result in sorted(results.items()):
        if result["status"] != "complete":
            selection[sid].update(discovery_runtime_status="excluded_other_detector_QC", discovery_qc_reasons=[result["reason"]])
            continue
        for i, candidate in enumerate(result["candidates"], 1):
            candidates.append({**candidate, "candidate_id": sid + f"-C{i:03d}", "scan_record_id": sid,
                               "count_control_mode": selection[sid]["count_control_mode"],
                               "acquisition_state_id": selection[sid]["acquisition_state_id"]})
    usable = sum(r["status"] == "complete" for r in results.values())
    require(usable > 0, "no_usable_discovery_population")
    clusters, features = consolidate(candidates)
    catalogue = {"job_id": JOB, "catalogue_status": "frozen_for_scientific_review", "feature_namespace": "BF",
                 "scientific_interpretation_status": "pending", "feature_count": len(features),
                 "zero_features_allowed": True, "usable_discovery_scans": usable,
                 "holdout_detector_access": False, "blind_split_sha256": diagnostic["blind_split_sha256"],
                 "cross_mode_amplitude_combination": False, "features": features}
    catalogue_data = ybytes(catalogue)
    catalogue_sha = sha(catalogue_data)
    columns = ("candidate_id", "scan_record_id", "count_control_mode", "acquisition_state_id", "L", "U",
               "representative_energy", "p_FWER", "T", "seed_center_index", "seed_central_width",
               "absorbed_window_count", "persistent_scales", "support_union_L", "support_union_U")
    rep_rows = [{"cluster_id": f"CL-{i:03d}", "count_control_mode": c["count_control_mode"], "L": c["L"], "U": c["U"],
                 "representative_energy": c["representative_energy"], "reproducibility_tier": f"tier_{c['reproducibility_tier']}",
                 "supporting_scan_record_ids": c["supporting_scan_record_ids"],
                 "supporting_acquisition_state_ids": c["supporting_acquisition_state_ids"],
                 "catalogue_eligible": c["reproducibility_tier"] > 0} for i, c in enumerate(clusters, 1)]
    write_new("scan_feature_candidates.csv", csvbytes(candidates, columns))
    write_new("feature_reproducibility.csv", csvbytes(rep_rows, ("cluster_id", "count_control_mode", "L", "U",
              "representative_energy", "reproducibility_tier", "supporting_scan_record_ids", "supporting_acquisition_state_ids", "catalogue_eligible")))
    write_new("blind_feature_catalogue.yaml", catalogue_data)
    (OUT / "scan_selection.csv").write_bytes(csvbytes([selection[s] for s in sorted(selection)], SELECTION_COLUMNS))
    try:
        require(consolidate(list(reversed(candidates)))[1] == features, "catalogue_input_order_invariance")
        require(consolidate([])[1] == [], "deterministic_empty_catalogue")
        require(all(f["blind_feature_id"] == f"BF-{i:03d}" for i, f in enumerate(features, 1)), "neutral_catalogue_IDs")
        require(sha((OUT / "blind_feature_catalogue.yaml").read_bytes()) == catalogue_sha, "catalogue_checksum")
        require(sha((OUT / "blind_split.csv").read_bytes()) == diagnostic["blind_split_sha256"], "holdout_seal_changed")
        require(diagnostic["holdout_detector_values_decoded"] == 0, "holdout_access")
        report["tests"][15].update(status="PASS", evidence={"neutral_IDs": "PASS", "ordering_membership_determinism": "PASS",
                                   "empty_catalogue_allowed": "PASS", "catalogue_sha256": catalogue_sha,
                                   "holdout_detector_access": 0, "stop_after_catalogue": True})
    except Exception as exc:
        report["tests"][15].update(status="FAIL", failure=str(exc))
        report.update(passed=15, failed=1, not_run=0)
        report_path.write_bytes(ybytes(report))
        raise StopJob("mandatory_test_failure:B001-T16:" + str(exc)) from exc
    report.update(passed=16, failed=0, not_run=0)
    report_path.write_bytes(ybytes(report))
    diagnostic.update(phase="completed_stop_condition", stop_reason="B001_STOP_CONDITION_satisfied",
                      usable_discovery_scans=usable, scan_candidate_count=len(candidates), catalogue_feature_count=len(features),
                      catalogue_sha256=catalogue_sha, per_scan_discovery=[results[s] for s in sorted(results)])
    (OUT / "discovery_diagnostics.yaml").write_bytes(ybytes(diagnostic))
    provenance = yload((OUT / "provenance_manifest.yaml").read_bytes())
    provenance.update(phase="completed_stop_condition", source_sha256=source_hash, inputs=inputs,
                      package_versions={"numpy": np.__version__, "scipy": scipy.__version__, "PyYAML": yaml.__version__},
                      catalogue_sha256=catalogue_sha, stop_condition="satisfied",
                      outputs=[{"logical_name": p.name, "size_bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                               for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "provenance_manifest.yaml"])
    (OUT / "provenance_manifest.yaml").write_bytes(ybytes(provenance))
    print(json.dumps({"B001_STOP_CONDITION": "satisfied", "tests_passed": 16, "usable_discovery_scans": usable,
                      "scan_candidates": len(candidates), "blind_features": len(features), "catalogue_sha256": catalogue_sha}, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--discovery-qc", action="store_true")
    mode.add_argument("--tests", action="store_true")
    mode.add_argument("--discover", action="store_true")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    try:
        if args.prepare:
            prepare()
        elif args.discovery_qc:
            discovery_qc()
        elif args.tests:
            mandatory_tests(args.workers)
        elif args.discover:
            execute_statistics(args.workers)
        return 0
    except StopJob as exc:
        if OUT.exists():
            diagnostic_path = OUT / "discovery_diagnostics.yaml"
            if diagnostic_path.exists():
                diagnostic = yload(diagnostic_path.read_bytes())
                diagnostic.update(phase="stopped", stop_reason=str(exc), production_feature_discovery_completed=False)
                diagnostic_path.write_bytes(ybytes(diagnostic))
            provenance_path = OUT / "provenance_manifest.yaml"
            if provenance_path.exists():
                provenance = yload(provenance_path.read_bytes())
                provenance.update(phase="stopped", execution_status="stopped", stop_reason=str(exc),
                                  source_sha256=sha((ROOT / SOURCE).read_bytes()),
                                  package_versions={"numpy": np.__version__, "scipy": scipy.__version__, "PyYAML": yaml.__version__},
                                  outputs=[{"logical_name": p.name, "size_bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                                           for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "provenance_manifest.yaml"])
                provenance_path.write_bytes(ybytes(provenance))
        print("B001_STOP: " + str(exc), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
