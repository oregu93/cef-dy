#!/usr/bin/env python3
"""Execute only the frozen A003 metadata classification; never open raw/point data."""

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from itertools import combinations
from pathlib import Path
import argparse
import ast
import csv
import hashlib
import io
import json
import platform
import random
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
HEAD = "302f6323cda03aeb17cdbf621e85edc1599bda9a"
SPEC = "03_Protocols/STAGE02R_T02R03_A003_CLASSIFICATION_SPEC.md"
SPEC_SHA = "3055739f853bd65344025bd64253afb513fd9b9ea6db480fb132332f9466479f"
SOURCE = "scripts/stage02r/a003_classify.py"
BASE = "04_Results/Stage02R/W02-02R-A-002/"
OUT = "04_Results/Stage02R/W02-02R-A-003/"
CHECKPOINT = "02_Work_Checkpoints/W02-02R-A-003.md"
INPUT_NAMES = (
    "scan_inventory.csv", "file_scan_map.csv", "lattice_states.yaml", "UB_states.yaml",
    "parsed_header_metadata.jsonl", "semantic_verification_report.yaml",
    "parser_diagnostics.csv", "quality_diagnostics.csv", "provenance_manifest.yaml",
)
CONTEXT_PATHS = (
    SPEC, "00_Project/PROJECT_STATE.md", "00_Project/PROJECT_CONTROL.md",
    "00_Project/PROJECT_METADATA.yaml", "00_Project/RESULT_REGISTER.yaml",
    "02_Work_Checkpoints/W02-02R-A-001.md", "02_Work_Checkpoints/W02-02R-A-002.md",
    "03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md", "03_Protocols/DATA_CONTRACTS.md",
    "03_Protocols/SCIENTIFIC_TERMINOLOGY.md", "03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md",
    "03_Protocols/CHAT_BOOTSTRAPS.md",
)
ACQ_FIELDS = ("count_control_mode", "scan_variable_raw", "lattice_state_id", "UB_state_id")
CONFIG_FIELDS = ("monochromator_material", "analyzer_material", "collimation")
GROUP_FIELDS = ("count_control_mode", "instrument_config_id", "normalization_epoch_id")
ACQ_VERSION = "stage02r_acquisition_state_v1"
CONFIG_VERSION = "stage02r_instrument_config_v1"
GROUP_VERSION = "stage02r_normalization_compatibility_group_v1"
CRITICAL = (
    "filter_state", "higher_order_suppression_state", "attenuation_state",
    "monochromator_reflection", "analyzer_reflection",
    "detector_hardware_identity", "monitor_hardware_identity",
)
RELEVANT = (
    "monochromator_mosaic", "analyzer_mosaic",
    "unresolved_focusing_aperture_configuration_fields",
    "other_unresolved_beam_path_configuration_fields",
)
STATUSES = ("supported", "conditionally_supported", "not_supported", "unresolved")
POSITIVE = set(STATUSES[:2])
PAIR_COLUMNS = (
    "scan_a_record_id", "scan_b_record_id", "compatibility_status", "decision_code",
    "count_control_compatibility", "instrument_config_compatibility",
    "normalization_epoch_compatibility", "verified_equal_fields", "verified_conflicting_fields",
    "critical_unknown_fields", "relevant_unknown_fields", "boundary_evidence", "decision_reason",
)
BOUNDARY_COLUMNS = (
    "boundary_index", "previous_scan_record_id", "next_scan_record_id", "boundary_type",
    "changed_fields", "normalization_relevant", "supporting_evidence", "confidence",
)
SCAN_COLUMNS = (
    "scan_record_id", "raw_scan_id", "sequence_index", "acquisition_state_id",
    "acquisition_state_status", "instrument_config_id", "instrument_config_status",
    "count_control_mode", "lattice_state_id", "UB_state_id", "normalization_epoch_id",
    "critical_unknown_fields", "relevant_unknown_fields", "normalization_compatibility_status",
    "normalization_compatibility_group_id", "classification_notes",
)
DIAG_COLUMNS = ("diagnostic_id", "diagnostic_type", "severity", "scan_record_id", "field", "evidence", "limitation")
LIMITATION = "Recorded verified vector only; unrecorded physical instrument state is not established."


class JobError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise JobError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def yaml_load(data):
    return yaml.load(data, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


class StableDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def yaml_bytes(value):
    return yaml.dump(value, Dumper=StableDumper, sort_keys=False, allow_unicode=True,
                     default_flow_style=False, width=110, line_break="\n").encode("utf-8")


def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def csv_bytes(rows, columns):
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        selected = {}
        for key in columns:
            value = row[key]
            if isinstance(value, (list, tuple)):
                value = ";".join(str(item) for item in value)
            elif isinstance(value, dict):
                value = compact(value)
            elif isinstance(value, bool):
                value = "true" if value else "false"
            selected[key] = value
        writer.writerow(selected)
    return handle.getvalue().encode("utf-8")


def identity_payload(version, fields, record):
    values = [record[key] for key in fields]
    require(all(isinstance(v, str) and v and "\n" not in v and "\r" not in v for v in values),
            "Unusable frozen identity metadata; STOP rather than serialize missing equality")
    return (version + "\n" + "".join(f"{k}={v}\n" for k, v in zip(fields, values))).encode("utf-8")


def display_ids(fingerprints, prefix):
    unique = sorted(set(fingerprints))
    require(all(re.fullmatch("[0-9a-f]{64}", fp) for fp in unique), "Invalid full fingerprint")
    result = {}
    for fp in unique:
        length = 16
        while any(other != fp and other[:length] == fp[:length] for other in unique):
            length += 2
        result[fp] = prefix + fp[:length]
    return result


def assign_identities(scans, version, fields, prefix, id_key):
    fingerprints = {s["scan_record_id"]: sha(identity_payload(version, fields, s)) for s in scans}
    ids = display_ids(fingerprints.values(), prefix)
    members = defaultdict(list)
    vectors = {}
    for scan in scans:
        fp = fingerprints[scan["scan_record_id"]]
        key = ids[fp]
        scan[id_key] = key
        members[key].append(scan["scan_record_id"])
        vectors[key] = {f: scan[f] for f in fields}
    return {ids[fp]: {
        "identity_version": version, "fingerprint": fp,
        "state_vector": vectors[ids[fp]], "member_scan_record_ids": sorted(members[ids[fp]]),
    } for fp in sorted(ids, key=ids.get)}


def normalization_fields(scan):
    # Only verified, recorded physical configuration. Extra fields are for explicit
    # verified synthetic fixtures; the reviewed production adapter supplies none.
    return {**{key: scan[key] for key in CONFIG_FIELDS}, **scan.get("_verified_additional_fields", {})}


def verified_comparison(a, b):
    left, right = normalization_fields(a), normalization_fields(b)
    both = [key for key in sorted(set(left) & set(right))
            if left[key] not in (None, "") and right[key] not in (None, "")]
    return ([k for k in both if left[k] == right[k]], [k for k in both if left[k] != right[k]])


def make_epochs(scans):
    chronology = sorted(scans, key=lambda s: (int(s["sequence_index"]), s["scan_record_id"]))
    boundaries = []
    epoch = 1
    for index, current in enumerate(chronology):
        if index:
            previous = chronology[index - 1]
            acq_changes = [k for k in ACQ_FIELDS if previous[k] != current[k]]
            _, config_changes = verified_comparison(previous, current)
            explicit = current.get("_verified_event_before", "")
            uncertain = current.get("_uncertain_event_before", "")
            relevant = bool(config_changes or explicit)
            if relevant:
                epoch += 1
            if acq_changes or config_changes or explicit or uncertain:
                types = []
                if acq_changes:
                    types.append("acquisition_state_change")
                if config_changes:
                    types.append("verified_configuration_change")
                if explicit:
                    types.append("explicit_verified_reconfiguration")
                if uncertain:
                    types.append("uncertain_possible_reconfiguration")
                fields = list(dict.fromkeys([*acq_changes, *config_changes]))
                left, right = {**previous, **normalization_fields(previous)}, {**current, **normalization_fields(current)}
                evidence = {"source": BASE + "scan_inventory.csv",
                            "previous_acquisition_start_time": previous["acquisition_start_time"],
                            "next_acquisition_start_time": current["acquisition_start_time"],
                            "changes": {k: {"previous": left[k], "next": right[k]} for k in fields}}
                if explicit:
                    evidence["explicit_verified_event"] = explicit
                if uncertain:
                    evidence["uncertain_event"] = uncertain
                boundaries.append({
                    "boundary_index": len(boundaries) + 1,
                    "previous_scan_record_id": previous["scan_record_id"],
                    "next_scan_record_id": current["scan_record_id"],
                    "boundary_type": ";".join(types), "changed_fields": fields,
                    "normalization_relevant": relevant, "supporting_evidence": evidence,
                    "confidence": "verified_boundary" if relevant else
                    ("uncertain_boundary" if uncertain else "verified_recorded_acquisition_change"),
                    "_next_sequence_index": int(current["sequence_index"]),
                })
        current["normalization_epoch_id"] = f"NORMEPOCH-02R-{epoch:04d}"
    return boundaries


def pair_decision(a, b, boundaries):
    require(a["scan_record_id"] < b["scan_record_id"], "Pair must be lexically canonical")
    lo, hi = sorted([int(a["sequence_index"]), int(b["sequence_index"])])
    separating = [r for r in boundaries if lo < r["_next_sequence_index"] <= hi]
    verified_boundaries = [r["boundary_index"] for r in separating if r["normalization_relevant"]]
    uncertain_boundaries = [r["boundary_index"] for r in separating if r["confidence"] == "uncertain_boundary"]
    critical = [k for k in CRITICAL if k in a["_critical"] or k in b["_critical"]]
    relevant = [k for k in RELEVANT if k in a["_relevant"] or k in b["_relevant"]]
    row = dict(zip(PAIR_COLUMNS, [None] * len(PAIR_COLUMNS)))
    row.update(scan_a_record_id=a["scan_record_id"], scan_b_record_id=b["scan_record_id"],
               count_control_compatibility="not_evaluated", instrument_config_compatibility="not_evaluated",
               normalization_epoch_compatibility="not_evaluated", verified_equal_fields=[],
               verified_conflicting_fields=[], critical_unknown_fields=critical,
               relevant_unknown_fields=relevant, boundary_evidence=[])

    def finish(status, code, reason):
        row.update(compatibility_status=status, decision_code=code, decision_reason=reason)
        if uncertain_boundaries:
            row["decision_reason"] += "; uncertain_boundary=" + ";".join(map(str, uncertain_boundaries))
            row["boundary_evidence"] = list(dict.fromkeys(row["boundary_evidence"] + uncertain_boundaries))
        return row

    # Six steps, in the exact frozen precedence order. Return terminates evaluation.
    if a["count_control_mode"] != b["count_control_mode"]:
        row["count_control_compatibility"] = "conflict"
        row["verified_conflicting_fields"] = ["count_control_mode"]
        return finish("not_supported", "count_control_mode_conflict", "Distinct recorded count-control modes.")
    row["count_control_compatibility"] = "equal"
    equal, conflict = verified_comparison(a, b)
    row["verified_equal_fields"] = ["count_control_mode", *equal]
    row["verified_conflicting_fields"] = conflict
    row["instrument_config_compatibility"] = "equal" if a["instrument_config_id"] == b["instrument_config_id"] else "different"
    if conflict:
        row["instrument_config_compatibility"] = "verified_conflict"
        return finish("not_supported", "verified_configuration_conflict", "Recorded verified configuration fields conflict.")
    row["normalization_epoch_compatibility"] = "same" if a["normalization_epoch_id"] == b["normalization_epoch_id"] else "different"
    if verified_boundaries:
        row["boundary_evidence"] = verified_boundaries
        return finish("not_supported", "explicit_reconfiguration_boundary", "Verified chronological reconfiguration separates scans.")
    if (not a["_metadata_usable"] or not b["_metadata_usable"]
            or a["instrument_config_id"] != b["instrument_config_id"]
            or any(k not in equal for k in CONFIG_FIELDS)):
        return finish("unresolved", "insufficient_or_contradictory_metadata", "Recorded configuration equivalence cannot be assessed.")
    if critical:
        return finish("conditionally_supported", "recorded_equivalence_with_critical_unknowns",
                      "Frozen-vector equality only; critical unknowns remain.")
    return finish("supported", "recorded_metadata_supports_shared_treatment",
                  "Supported by available recorded metadata, not proven complete physical identity.")


def build_groups(scans, pairs, boundaries):
    groups = assign_identities(scans, GROUP_VERSION, GROUP_FIELDS, "NORMCOMP-02R-", "normalization_compatibility_group_id")
    by_scan = {s["scan_record_id"]: s for s in scans}
    lookup = {(r["scan_a_record_id"], r["scan_b_record_id"]): r for r in pairs}
    diagnostics = []
    for group_id, group in groups.items():
        members = group["member_scan_record_ids"]
        counts = Counter(lookup[p]["compatibility_status"] for p in combinations(members, 2))
        critical = [k for k in CRITICAL if any(k in by_scan[m]["_critical"] for m in members)]
        relevant = [k for k in RELEVANT if any(k in by_scan[m]["_relevant"] for m in members)]
        failed = bool(counts["not_supported"] or counts["unresolved"])
        if len(members) == 1:
            failed = not by_scan[members[0]]["_metadata_usable"]
            status = "conditionally_supported" if critical else "supported"
        else:
            status = "conditionally_supported" if counts["conditionally_supported"] else "supported"
        if failed:
            status = "unresolved"
            diagnostics.append((group_id, "Exact-key partition has a forbidden internal pair; no heuristic split."))
        vector = group.pop("state_vector")
        group.update(status=status, **vector,
                     acquisition_state_ids=sorted({by_scan[m]["acquisition_state_id"] for m in members}),
                     critical_unknown_fields=critical, relevant_unknown_fields=relevant,
                     pair_count=sum(counts.values()),
                     internal_pair_status_counts={k: counts[k] for k in STATUSES},
                     clique_audit_status="FAIL" if failed else "PASS",
                     compatibility_basis="Exact frozen key partition plus complete internal pair audit.",
                     limitations=[LIMITATION], normalization_performed=False)
        if critical:
            group["limitations"].append("Critical unknowns preclude supported status.")
        ranks = [int(by_scan[m]["sequence_index"]) for m in members]
        uncertain = [r["boundary_index"] for r in boundaries if r["confidence"] == "uncertain_boundary"
                     and min(ranks) < r["_next_sequence_index"] <= max(ranks)]
        if uncertain:
            group["limitations"].append("Uncertain boundaries: " + ";".join(map(str, uncertain)))
    return groups, diagnostics


def classify(input_scans):
    # All numerical detector payloads, if supplied by a test, remain unused.
    scans = deepcopy(sorted(input_scans, key=lambda s: s["scan_record_id"]))
    states = assign_identities(scans, ACQ_VERSION, ACQ_FIELDS, "ACQSTATE-02R-", "acquisition_state_id")
    configs = assign_identities(scans, CONFIG_VERSION, CONFIG_FIELDS, "INSTCFG-02R-", "instrument_config_id")
    for value in states.values():
        value["evidence"] = [BASE + "scan_inventory.csv; exact frozen four-field recorded vector."]
    by_scan = {s["scan_record_id"]: s for s in scans}
    for value in configs.values():
        members = value["member_scan_record_ids"]
        value.update(semantic_meaning="recorded_verified_configuration_equivalence_only",
                     critical_unknown_fields=[k for k in CRITICAL if any(k in by_scan[m]["_critical"] for m in members)],
                     relevant_unknown_fields=[k for k in RELEVANT if any(k in by_scan[m]["_relevant"] for m in members)],
                     limitation=LIMITATION)
    boundaries = make_epochs(scans)
    pairs = [pair_decision(a, b, boundaries) for a, b in combinations(scans, 2)]
    groups, failures = build_groups(scans, pairs, boundaries)
    rows = []
    for scan in scans:
        row = {key: scan[key] for key in SCAN_COLUMNS if key in scan}
        row.update(acquisition_state_status="recorded_v1_equivalence",
                   instrument_config_status="recorded_verified_configuration_equivalence_only",
                   critical_unknown_fields=list(scan["_critical"]), relevant_unknown_fields=list(scan["_relevant"]),
                   normalization_compatibility_status=groups[scan["normalization_compatibility_group_id"]]["status"],
                   classification_notes="Metadata-only; no normalization; acquisition state is not hardware identity.")
        rows.append(row)
    return {"scans": scans, "states": states, "configs": configs, "boundaries": boundaries,
            "pairs": pairs, "groups": groups, "scan_rows": rows, "clique_failures": failures}


def read_inputs():
    require(git("rev-parse", "HEAD").decode().strip() == HEAD, "Canonical HEAD differs")
    require(not git("diff", "HEAD", "--name-only"), "Existing tracked files are modified")
    require(not git("diff", "--cached", "--name-only"), "Index must remain clean")
    untracked = set(git("ls-files", "--others", "--exclude-standard", "-z").decode().strip("\0").split("\0")) - {""}
    require(untracked <= {SOURCE}, "Unexpected pre-existing untracked files")
    require(not (ROOT / OUT).exists() and not (ROOT / CHECKPOINT).exists(), "A003 outputs already exist; refusing overwrite")
    identities = []
    content = {}
    for path in [*CONTEXT_PATHS, *(BASE + name for name in INPUT_NAMES)]:
        data = (ROOT / path).read_bytes()
        require(data == git("show", "HEAD:" + path), "Input differs from canonical Git bytes: " + path)
        content[path] = data
        identities.append({"path": path, "size_bytes": len(data), "sha256": sha(data)})
    require(sha(content[SPEC]) == SPEC_SHA, "Frozen specification identity differs")
    for field, value in [("status", "frozen"), ("design_status", "approved"),
                         ("specification_status", "frozen"), ("execution_status", "not_started"),
                         ("execution_authorized", "false")]:
        require(re.findall(r"^" + field + r": ([^\n]+)$", content[SPEC].decode(), re.M) == [value],
                "Unexpected frozen specification field: " + field)
    metadata = yaml_load(content["00_Project/PROJECT_METADATA.yaml"])
    require(metadata["control"]["next_work_job"] == "W02-02R-A-003", "Project Control authorization missing")
    control = content["00_Project/PROJECT_CONTROL.md"].decode("utf-8")
    require(len(re.findall(r"^\| `W02-02R-A-003` \| ready \|", control, re.M)) == 1,
            "Exactly one ready A003 queue row required")
    cp = content["02_Work_Checkpoints/W02-02R-A-002.md"].decode("utf-8")
    frontmatter = yaml_load(cp.split("---", 2)[1])
    require(frontmatter["review_status"] == "reviewed" and frontmatter["scientific_review_outcome"] == "accepted",
            "A002 reviewed checkpoint required")
    expected = {name: (int(size), digest) for name, size, digest in re.findall(
        r"^\| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|$", cp, re.M)}
    manifest = yaml_load(content[BASE + "provenance_manifest.yaml"])
    manifest_entries = {row["logical_name"]: row for row in manifest["outputs"]}
    for name in INPUT_NAMES:
        data = content[BASE + name]
        require((len(data), sha(data)) == expected[name], "Reviewed A002 identity failed: " + name)
        if name != "provenance_manifest.yaml":
            entry = manifest_entries[name]
            require(entry["path"] == BASE + name and (entry["size_bytes"], entry["byte_sha256"]) == expected[name],
                    "Checkpoint/manifest identity disagreement: " + name)
    scans = csv_rows(content[BASE + "scan_inventory.csv"])
    require(len(scans) == 201, "Expected 201 canonical scans")
    ids = [s["scan_record_id"] for s in scans]
    require(len(set(ids)) == len(ids), "Duplicate canonical scan ID")
    headers = [json.loads(line) for line in content[BASE + "parsed_header_metadata.jsonl"].decode().splitlines()]
    by_header = {h["scan_record_id"]: h for h in headers}
    require(len(by_header) == len(headers) == len(scans) and set(by_header) == set(ids), "Header coverage mismatch")
    file_map = csv_rows(content[BASE + "file_scan_map.csv"])
    require(len(file_map) == len(scans) and {r["scan_record_id"] for r in file_map} == set(ids), "File-map coverage mismatch")
    by_mapping = {r["scan_record_id"]: r for r in file_map}
    require(all(by_mapping[s["scan_record_id"]]["file_record_id"] == s["primary_file_record_id"] for s in scans),
            "File/scan provenance association mismatch")
    semantic = yaml_load(content[BASE + "semantic_verification_report.yaml"])
    for key in ("monochromator_material", "analyzer_material", "count_control_semantics"):
        require(semantic[key]["status"] == "verified" and not semantic[key]["exceptions"], "Unusable A002 semantic mapping: " + key)
    for key in ("monochromator_reflection", "analyzer_reflection", "monochromator_mosaic", "analyzer_mosaic",
                "filter_metadata", "attenuation_metadata", "auxiliary_motor_semantics"):
        require(semantic[key]["status"] in ("unresolved", "not_recorded")
                and semantic[key]["canonical_mapping"] is None and not semantic[key]["exceptions"],
                "Unknown-field evidence needs review: " + key)
    lattice = yaml_load(content[BASE + "lattice_states.yaml"])
    ub = yaml_load(content[BASE + "UB_states.yaml"])
    for key, catalogue in [("lattice_state_id", lattice), ("UB_state_id", ub)]:
        require({s[key] for s in scans} == set(catalogue), "A002 state coverage mismatch: " + key)
        for state_id, record in catalogue.items():
            require({s["scan_record_id"] for s in scans if s[key] == state_id} == set(record["source_scan_record_ids"]),
                    "A002 state membership mismatch: " + state_id)
    chronology = sorted(scans, key=lambda s: int(s["sequence_index"]))
    require([int(s["sequence_index"]) for s in chronology] == list(range(len(scans))), "Chronology sequence invalid")
    times = [datetime.fromisoformat(s["acquisition_start_time"]) for s in chronology]
    require(times == sorted(times), "Canonical chronology contradicts acquisition timestamps")
    # No recorded dedicated event field exists in the reviewed header vocabulary.
    # Neither titles nor unverified motor names are interpreted as event evidence.
    reviewed_header_keys = {
        "analyzer", "builtin_command", "col_headers", "collimation", "command", "def_x", "def_y", "end_time",
        "experiment", "experiment_number", "latticeconstants", "local_contact", "mode", "monochromator",
        "plane_normal", "preset_channel", "preset_type", "preset_value", "proposal", "raw_file", "samplemosaic",
        "samplename", "sampletype", "scan", "scan_title", "sense", "start_time", "ubconf", "ubmatrix", "users",
    }
    for scan in scans:
        sid = scan["scan_record_id"]
        require(scan["dataset_id"] == "EXP-TAIPAN-001" and scan["scan_identity_status"] == "verified", "Invalid scan identity")
        require(scan["sequence_status"] == "verified_header_chronology", "Unusable chronology")
        require(scan["count_control_status"] == "verified" and scan["count_control_mode"] in ("monitor_controlled", "time_controlled"),
                "Unusable count-control metadata")
        require(all(scan[f] for f in (*ACQ_FIELDS, *CONFIG_FIELDS)), "Missing frozen vector field")
        require(all(not scan[f] for f in ("filter_state", "attenuation_state", "monochromator_reflection",
                                        "analyzer_reflection", "monochromator_mosaic", "analyzer_mosaic")),
                "Contradictory unknown metadata")
        header = by_header[sid]
        require(header["file_record_id"] == scan["primary_file_record_id"]
                and header["source_checksum"] == scan["source_checksum"], "Header provenance mismatch")
        mappings = header["canonical_header_mappings"]
        raw_keys = {r["raw_key"] for r in header["raw_header_records"] if r["raw_key"] is not None}
        require(raw_keys <= reviewed_header_keys and set(mappings) <= reviewed_header_keys,
                "Additional header semantics require review; no inferred event handling")
        for field, key in [("monochromator_material", "monochromator"), ("analyzer_material", "analyzer"),
                           ("collimation", "collimation"), ("scan_variable_raw", "def_x")]:
            require(mappings[key]["values"] == [scan[field]], "Header/inventory contradiction: " + field)
        expected_channel = "monitor" if scan["count_control_mode"] == "monitor_controlled" else "time"
        require(mappings["preset_channel"]["values"] == [expected_channel], "Contradictory control channel")
        require(all(mappings[k]["values"] == [""] for k in ("command", "builtin_command")),
                "Recorded command requires explicit event-semantic review")
        require(ub[scan["UB_state_id"]]["lattice_state_id"] == scan["lattice_state_id"], "UB/lattice association contradiction")
        scan.update(_critical=list(CRITICAL), _relevant=list(RELEVANT), _metadata_usable=True)
    for row in csv_rows(content[BASE + "parser_diagnostics.csv"]):
        require(row["severity"] == "info", "A002 parser diagnostic requires review")
    for row in csv_rows(content[BASE + "quality_diagnostics.csv"]):
        require(row["status"] == "pass", "A002 quality diagnostic requires review")
    return scans, {"identities": identities, "headers": headers, "lattice": lattice, "ub": ub,
                   "input_artifacts_verified": len(INPUT_NAMES), "external_auxiliary_used": False,
                   "raw_data_opened": False, "point_tables_opened": False}


def make_diagnostics(inputs, result):
    rows = []

    def add(kind, field, evidence, limitation, sid=""):
        rows.append({"diagnostic_id": "", "diagnostic_type": kind, "severity": "info", "scan_record_id": sid,
                     "field": field, "evidence": evidence, "limitation": limitation})

    for key in CRITICAL:
        add("critical_unknown_propagated", key, "A002 canonical metadata: unresolved or not recorded for every scan.",
            "Missingness is not equality evidence; blocks supported status.")
    for key in RELEVANT:
        add("relevant_unknown_propagated", key, "A002 canonical metadata: unverified or unresolved for every scan.",
            "Not included in frozen identity or verified equality evidence.")
    add("explicit_reconfiguration_event_census", "canonical_header_mappings",
        "All reviewed header keys checked; command/builtin_command empty; no dedicated verified reconfiguration event recorded.",
        "No event inferred from titles, chronology gaps, state/coordinate changes or unverified motor labels.")
    # Presence diagnostics only: the values live in the external auxiliary artifact,
    # which no frozen classification field requires. No name-only physical mapping.
    candidates = ("ahfocus", "avfocus", "pghf", "pgvf", "cuhf", "cuvf", "atilt", "atrans", "mtilt", "mtrans",
                  "pa_bottom", "pa_left", "pa_right", "pa_top", "ps_bottom", "ps_left", "ps_right", "ps_top",
                  "vs_left", "vs_right")
    for key in candidates:
        count = sum(key in h["declared_column_names"] for h in inputs["headers"])
        if count:
            add("unresolved_configuration_field_presence", key, f"Declared in {count} canonical header column lists.",
                "Candidate for future semantic verification only; no value analysis, boundary inference or v1 inclusion.")
    for key in ("sense", "samplemosaic", "plane_normal", "ubconf"):
        counts = Counter(compact(h["canonical_header_mappings"].get(key, {}).get("values", [])) for h in inputs["headers"])
        add("excluded_header_value_diagnostic", key, compact(dict(sorted(counts.items()))),
            "Recorded variation is not verified normalization-hardware reconfiguration; no v1 identity extension.")
    for group_id, evidence in result["clique_failures"]:
        add("group_clique_failure", group_id, evidence, "Exact-key partition unresolved; mandatory STOP.")
        rows[-1]["severity"] = "error"
    for index, row in enumerate(rows, 1):
        row["diagnostic_id"] = f"A003-D{index:03d}"
    return rows


def scientific_artifact_bytes(result, diagnostics):
    return {
        "acquisition_states.yaml": yaml_bytes(result["states"]),
        "instrument_configs.yaml": yaml_bytes(result["configs"]),
        "acquisition_boundaries.csv": csv_bytes(result["boundaries"], BOUNDARY_COLUMNS),
        "normalization_compatibility.csv": csv_bytes(result["pairs"], PAIR_COLUMNS),
        "normalization_compatibility_groups.yaml": yaml_bytes(result["groups"]),
        "scan_classification.csv": csv_bytes(result["scan_rows"], SCAN_COLUMNS),
        "classification_diagnostics.csv": csv_bytes(diagnostics, DIAG_COLUMNS),
    }


def run_tests(scans, inputs, result, source_bytes):
    reports = []
    shuffled_scans = deepcopy(scans)
    random.Random(3).shuffle(shuffled_scans)
    reordered = classify(shuffled_scans)

    def fixture(count=3):
        rows = []
        for i in range(count):
            row = deepcopy(scans[0])
            row.update(scan_record_id=f"SYN-{i:04d}", sequence_index=str(i),
                       acquisition_start_time=f"2000-01-01T00:{i:02d}:00")
            rows.append(row)
        return rows

    def signatures(value):
        return {key: value[key] for key in ("states", "configs", "boundaries", "pairs", "groups", "scan_rows")}

    def collision_check(prefix):
        first, second, other = "ab" * 8 + "00" + "a" * 46, "ab" * 8 + "00" + "b" * 46, "cd" * 32
        expected = {first: prefix + first[:20], second: prefix + second[:20], other: prefix + other[:16]}
        require(display_ids([first, second, other, first], prefix) == expected, "Collision extension incorrect")
        require(display_ids([other, second, first], prefix) == expected, "Collision extension depends on order")

    def t01():
        require(inputs["input_artifacts_verified"] == len(INPUT_NAMES), "Incomplete A002 verification")
        require(not inputs["external_auxiliary_used"] and not inputs["raw_data_opened"] and not inputs["point_tables_opened"],
                "Unexpected raw/point/auxiliary access")
        return {"reviewed_primary_artifacts": len(INPUT_NAMES), "canonical_inputs": len(inputs["identities"]),
                "byte_size_and_sha256": "PASS", "external_auxiliary_used": False}

    def t02():
        ids = {s["scan_record_id"] for s in scans}
        require(len(result["scan_rows"]) == 201 and {r["scan_record_id"] for r in result["scan_rows"]} == ids,
                "Incomplete scan coverage")
        raw_ids = {s["scan_record_id"]: s["raw_scan_id"] for s in scans}
        require(all(r["raw_scan_id"] == raw_ids[r["scan_record_id"]] for r in result["scan_rows"]), "Raw scan ID changed")
        return {"canonical_scans": len(scans), "classification_rows": len(result["scan_rows"]), "silent_exclusions": 0}

    def t03():
        require(ACQ_FIELDS == ("count_control_mode", "scan_variable_raw", "lattice_state_id", "UB_state_id"), "Wrong acquisition vector")
        example = dict(zip(ACQ_FIELDS, ("time_controlled", "s1", "LAT-example", "UB-example")))
        golden = (b"stage02r_acquisition_state_v1\ncount_control_mode=time_controlled\n"
                  b"scan_variable_raw=s1\nlattice_state_id=LAT-example\nUB_state_id=UB-example\n")
        require(identity_payload(ACQ_VERSION, ACQ_FIELDS, example) == golden, "Acquisition serialization incorrect")
        source_records = {s["scan_record_id"]: s for s in scans}
        expected_ids = display_ids([v["fingerprint"] for v in result["states"].values()], "ACQSTATE-02R-")
        for state_id, value in result["states"].items():
            require(tuple(value["state_vector"]) == ACQ_FIELDS, "Acquisition vector/order changed")
            require(value["fingerprint"] == sha(identity_payload(ACQ_VERSION, ACQ_FIELDS, value["state_vector"])), "Acquisition fingerprint mismatch")
            require(state_id == expected_ids[value["fingerprint"]], "Acquisition display ID mismatch")
            require(all({k: source_records[m][k] for k in ACQ_FIELDS} == value["state_vector"] for m in value["member_scan_record_ids"]),
                    "Acquisition membership/vector mismatch")
        require(result["states"] == reordered["states"], "Acquisition identity changes under shuffle")
        collision_check("ACQSTATE-02R-")
        return {"states": len(result["states"]), "golden_payload": "PASS", "shuffle_and_collision_extension": "PASS"}

    def t04():
        require(CONFIG_FIELDS == ("monochromator_material", "analyzer_material", "collimation"), "Wrong instrument vector")
        example = dict(zip(CONFIG_FIELDS, ("PG", "PG", "o-40-40-o")))
        golden = (b"stage02r_instrument_config_v1\nmonochromator_material=PG\n"
                  b"analyzer_material=PG\ncollimation=o-40-40-o\n")
        require(identity_payload(CONFIG_VERSION, CONFIG_FIELDS, example) == golden, "Instrument serialization incorrect")
        source_records = {s["scan_record_id"]: s for s in scans}
        expected_ids = display_ids([v["fingerprint"] for v in result["configs"].values()], "INSTCFG-02R-")
        for config_id, value in result["configs"].items():
            require(tuple(value["state_vector"]) == CONFIG_FIELDS, "Instrument vector/order changed")
            require(value["fingerprint"] == sha(identity_payload(CONFIG_VERSION, CONFIG_FIELDS, value["state_vector"])), "Instrument fingerprint mismatch")
            require(config_id == expected_ids[value["fingerprint"]], "Instrument display ID mismatch")
            require(all({k: source_records[m][k] for k in CONFIG_FIELDS} == value["state_vector"] for m in value["member_scan_record_ids"]),
                    "Instrument membership/vector mismatch")
        require(result["configs"] == reordered["configs"], "Instrument identity changes under shuffle")
        collision_check("INSTCFG-02R-")
        return {"configs": len(result["configs"]), "golden_payload": "PASS", "shuffle_and_collision_extension": "PASS"}

    def t05():
        unknown = set(CRITICAL + RELEVANT)
        require(not unknown.intersection(ACQ_FIELDS + CONFIG_FIELDS), "Unknown field in frozen identity")
        for pair in result["pairs"]:
            require(not unknown.intersection(pair["verified_equal_fields"]), "Missing value used as equality evidence")
            require(pair["critical_unknown_fields"] == list(CRITICAL) and pair["relevant_unknown_fields"] == list(RELEVANT),
                    "Frozen unknown sets not propagated")
        original = fixture(2)
        mutated = deepcopy(original)
        for row in mutated:
            row.update({key: None for key in CRITICAL + RELEVANT})
        require(signatures(classify(original)) == signatures(classify(mutated)), "Shared missingness alters classification")
        return {"both_unknown_sets_propagated": "PASS", "shared_missing_null_fixture": "PASS"}

    def t06():
        ids = sorted(s["scan_record_id"] for s in scans)
        expected_pairs = list(combinations(ids, 2))
        actual_pairs = [(r["scan_a_record_id"], r["scan_b_record_id"]) for r in result["pairs"]]
        require(actual_pairs == expected_pairs and len(actual_pairs) == 20100, "Pair enumeration/order mismatch")
        lookup = {s["scan_record_id"]: s["count_control_mode"] for s in scans}
        cross = [r for r in result["pairs"] if lookup[r["scan_a_record_id"]] != lookup[r["scan_b_record_id"]]]
        require(all(r["compatibility_status"] == "not_supported" and r["decision_code"] == "count_control_mode_conflict" for r in cross),
                "Count-control separation failed")
        counts = Counter(lookup.values())
        expected_cross = sum(a * b for a, b in combinations(counts.values(), 2))
        require(len(cross) == expected_cross, "Cross-control pair reconciliation failed")
        return {"unordered_pairs": len(actual_pairs), "duplicates": len(actual_pairs) - len(set(actual_pairs)),
                "cross_control_mode_pairs": len(cross), "count_control_memberships": dict(sorted(counts.items()))}

    def t07():
        for field, catalogue in [("lattice_state_id", inputs["lattice"]), ("UB_state_id", inputs["ub"])]:
            require({s[field] for s in result["scan_rows"]} == set(catalogue), "Reviewed state lost")
            source_values = {s["scan_record_id"]: s[field] for s in scans}
            require(all(s[field] == source_values[s["scan_record_id"]] for s in result["scan_rows"]), "State remapped")
        synthetic = fixture()
        synthetic[1]["lattice_state_id"] = "LAT-synthetic-change"
        synthetic[2]["UB_state_id"] = "UB-synthetic-change"
        classified = classify(synthetic)
        require(len({s["normalization_epoch_id"] for s in classified["scans"]}) == 1, "Orientation-only epoch split")
        return {"lattice_states": len(inputs["lattice"]), "UB_states": len(inputs["ub"]), "orientation_only_epoch_test": "PASS"}

    def t08():
        chronological = sorted(result["scans"], key=lambda s: int(s["sequence_index"]))
        changes = []
        for a, b in zip(chronological, chronological[1:]):
            _, conflict = verified_comparison(a, b)
            if conflict:
                changes.append((a["scan_record_id"], b["scan_record_id"]))
                require(any(r["previous_scan_record_id"] == a["scan_record_id"] and r["next_scan_record_id"] == b["scan_record_id"]
                            and r["normalization_relevant"] for r in result["boundaries"]), "Verified change not marked")
        synthetic = fixture()
        synthetic[1]["collimation"] = "synthetic_changed_collimation"
        synthetic[2]["collimation"] = "synthetic_changed_collimation"
        synthetic[2]["_verified_event_before"] = "synthetic documented hardware reconfiguration"
        classified = classify(synthetic)
        require(len({s["normalization_epoch_id"] for s in classified["scans"]}) == 3, "Verified configuration/event epoch missing")
        require(all(r["normalization_relevant"] for r in classified["boundaries"]), "Verified boundary not relevant")
        return {"recorded_configuration_changes": len(changes), "synthetic_verified_change_and_explicit_event": "PASS"}

    def t09():
        synthetic = fixture()
        excluded = ("scan_variable_raw", "h", "k", "l", "e", "Ei_summary_meV", "Ef_summary_meV",
                    "scan_start_derived", "scan_stop_derived", "temperature_summary_K", "raw_format_id")
        for i, row in enumerate(synthetic):
            row.update({key: f"synthetic-{i}-{key}" for key in excluded})
        classified = classify(synthetic)
        require(len(classified["configs"]) == 1, "Coordinate/configuration over-splitting")
        return {"excluded_fields_varied": list(excluded), "instrument_configs_in_fixture": len(classified["configs"])}

    def t10():
        base = classify(fixture(2))["scans"]
        boundary = [{"boundary_index": 1, "_next_sequence_index": 1, "normalization_relevant": True, "confidence": "verified_boundary"}]
        observed = []
        expected_codes = ("count_control_mode_conflict", "verified_configuration_conflict", "explicit_reconfiguration_boundary",
                          "insufficient_or_contradictory_metadata", "recorded_equivalence_with_critical_unknowns",
                          "recorded_metadata_supports_shared_treatment")
        expected_status = ("not_supported", "not_supported", "not_supported", "unresolved", "conditionally_supported", "supported")
        for step in range(1, 7):
            a, b = deepcopy(base)
            if step <= 1:
                b["count_control_mode"] = "synthetic_other_mode"
            if step <= 2:
                b["collimation"] = "synthetic_conflict"
            if step <= 4:
                b["_metadata_usable"] = False
            if step == 6:
                a["_critical"], b["_critical"] = [], []
            pair = pair_decision(a, b, boundary if step <= 3 else [])
            require((pair["compatibility_status"], pair["decision_code"]) == (expected_status[step - 1], expected_codes[step - 1]),
                    "Six-step precedence failed at step " + str(step))
            observed.append(pair["decision_code"])
        a, b = deepcopy(base)
        a["_verified_additional_fields"] = {"synthetic_verified_aperture": "a"}
        b["_verified_additional_fields"] = {"synthetic_verified_aperture": "b"}
        require(pair_decision(a, b, [])["decision_code"] == "verified_configuration_conflict", "Additional verified conflict missed")
        return {"six_step_precedence": observed, "additional_verified_conflict": "PASS"}

    def t11():
        pair = classify(fixture(2))["pairs"][0]
        require(pair["compatibility_status"] == "conditionally_supported" and pair["critical_unknown_fields"],
                "Critical unknowns failed to prevent supported")
        require(all(not p["critical_unknown_fields"] for p in result["pairs"] if p["compatibility_status"] == "supported"),
                "Supported output with critical unknowns")
        return {"synthetic_critical_unknowns": "PASS", "supported_output_audit": "PASS"}

    def t12():
        injected = deepcopy(scans)
        for row in injected:
            row["detector"] = [0, 1, 9, 2]
        mutated = deepcopy(injected)
        for row in mutated:
            row["detector"] = [-7, 1000000, 2, 0]
        permuted = deepcopy(injected)
        for row in permuted:
            row["detector"] = [2, 9, 1, 0]
        reference = signatures(result)
        require(signatures(classify(injected)) == reference, "Synthetic detector injection changed output")
        require(signatures(classify(mutated)) == reference, "Detector mutation changed output")
        require(signatures(classify(permuted)) == reference, "Detector permutation changed output")
        return {"fixture": "synthetic detector payload on every canonical metadata record; no measurement table opened",
                "invariant": ["acquisition_state_id", "instrument_config_id", "normalization_epoch_id", "all_pair_decisions", "groups"],
                "mutation_and_permutation": "PASS"}

    def t13():
        require(result["boundaries"] == reordered["boundaries"], "Boundaries depend on input order")
        require({s["scan_record_id"]: s["normalization_epoch_id"] for s in result["scans"]}
                == {s["scan_record_id"]: s["normalization_epoch_id"] for s in reordered["scans"]}, "Epoch IDs depend on order")
        synthetic = fixture()
        synthetic[1].update(acquisition_start_time="2001-12-31T00:00:00", lattice_state_id="LAT-other",
                            UB_state_id="UB-other", scan_variable_raw="synthetic_variable", temperature_summary_K="synthetic_temp",
                            raw_format_id="synthetic_format", repeat_metadata_signature="synthetic_repeat")
        synthetic[2].update(acquisition_start_time="2002-01-01T00:00:00", _uncertain_event_before="synthetic uncertain possibility")
        classified = classify(synthetic)
        require(len({s["normalization_epoch_id"] for s in classified["scans"]}) == 1, "Forbidden epoch split")
        require(any(b["confidence"] == "uncertain_boundary" for b in classified["boundaries"]), "Uncertain boundary not recorded")
        require(any("uncertain_boundary" in p["decision_reason"] for p in classified["pairs"]), "Pair uncertainty not propagated")
        require(any(any("Uncertain boundaries" in v for v in g["limitations"]) for g in classified["groups"].values()),
                "Group uncertainty not propagated")
        diagnostics = make_diagnostics(inputs, result)
        require(scientific_artifact_bytes(result, diagnostics) == scientific_artifact_bytes(reordered, diagnostics),
                "Serialized scientific outputs depend on input order")
        return {"shuffled_serialized_artifacts": "byte_identical", "gap_day_coordinates_and_uncertain_epoch_tests": "PASS"}

    def t14():
        tree = ast.parse(source_bytes.decode("utf-8"))
        classification_functions = {"classify", "pair_decision", "verified_comparison", "normalization_fields", "make_epochs", "build_groups"}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in classification_functions:
                require(not any(isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv)) for n in ast.walk(node)),
                        "Unexpected division in classification code")
                require(not any(isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                                and n.slice.value in {"detector", "monitor", "time", "ki", "kf"} for n in ast.walk(node)),
                        "Intensity/counting values accessed by classification")
        require(all(g["normalization_performed"] is False for g in result["groups"].values()), "Normalization flag incorrect")
        require(not set(SCAN_COLUMNS + PAIR_COLUMNS) & {"detector", "monitor", "time", "intensity", "scale", "ki", "kf"},
                "Prohibited output quantity")
        return {"classification_numeric_division": "absent", "count_values_accessed": False, "normalization_performed": False}

    def t15():
        tree = ast.parse(source_bytes.decode("utf-8"))
        allowed_imports = {"collections", "copy", "datetime", "itertools", "pathlib", "argparse", "ast", "csv", "hashlib",
                           "io", "json", "platform", "random", "re", "subprocess", "sys", "yaml"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                require(all(n.name.split(".")[0] in allowed_imports for n in node.names), "Out-of-scope import")
            if isinstance(node, ast.ImportFrom):
                require(node.module.split(".")[0] in allowed_imports, "Out-of-scope import")
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                require(name not in {"find_peaks", "curve_fit", "least_squares", "plot", "imshow", "eval", "exec"}, "Out-of-scope call")
        require("scan_points.csv" not in INPUT_NAMES and "scan_point_auxiliary.csv" not in INPUT_NAMES, "Unexpected point input")
        return {"source_scope_audit": "PASS", "raw_or_point_files_read": False, "spectral_and_model_operations": "absent"}

    def t16():
        require(GROUP_FIELDS == ("count_control_mode", "instrument_config_id", "normalization_epoch_id"), "Wrong group key")
        require(not result["clique_failures"], "Exact-key partition failed clique audit")
        expected = defaultdict(list)
        for row in result["scans"]:
            expected[tuple(row[k] for k in GROUP_FIELDS)].append(row["scan_record_id"])
        lookup = {(p["scan_a_record_id"], p["scan_b_record_id"]): p for p in result["pairs"]}
        for group in result["groups"].values():
            key = tuple(group[k] for k in GROUP_FIELDS)
            require(group["member_scan_record_ids"] == sorted(expected.pop(key)), "Group is not exact-key partition")
            require(group["fingerprint"] == sha(identity_payload(GROUP_VERSION, GROUP_FIELDS, group)), "Group fingerprint mismatch")
            counts = Counter(lookup[p]["compatibility_status"] for p in combinations(group["member_scan_record_ids"], 2))
            require(set(counts) <= POSITIVE and group["clique_audit_status"] == "PASS", "Forbidden group pair")
            require(group["pair_count"] == sum(counts.values()) and group["internal_pair_status_counts"] == {k: counts[k] for k in STATUSES},
                    "Internal-pair reconciliation failed")
            expected_status = "conditionally_supported" if counts["conditionally_supported"] or (
                len(group["member_scan_record_ids"]) == 1 and group["critical_unknown_fields"]) else "supported"
            require(group["status"] == expected_status, "Group status differs from frozen rule")
        require(not expected, "Missing exact-key group")
        require(result["groups"] == reordered["groups"], "Group partition changes under shuffle")
        collision_check("NORMCOMP-02R-")
        golden = (b"stage02r_normalization_compatibility_group_v1\ncount_control_mode=time_controlled\n"
                  b"instrument_config_id=INST-example\nnormalization_epoch_id=NORMEPOCH-02R-0001\n")
        require(identity_payload(GROUP_VERSION, GROUP_FIELDS, dict(zip(GROUP_FIELDS, ("time_controlled", "INST-example", "NORMEPOCH-02R-0001")))) == golden,
                "Group serialization differs")
        synthetic = classify(fixture())
        for status in ("not_supported", "unresolved"):
            broken = deepcopy(synthetic["pairs"])
            broken[0]["compatibility_status"] = status
            groups, failures = build_groups(deepcopy(synthetic["scans"]), broken, synthetic["boundaries"])
            require(failures and len(groups) == 1 and next(iter(groups.values()))["status"] == "unresolved",
                    "Forbidden internal pair not rejected without heuristic split")
        for unknowns, status in [(list(CRITICAL), "conditionally_supported"), ([], "supported")]:
            single = fixture(1)
            single[0]["_critical"] = unknowns
            require(next(iter(classify(single)["groups"].values()))["status"] == status, "Singleton status incorrect")
        return {"groups": len(result["groups"]), "all_internal_pairs_checked": sum(g["pair_count"] for g in result["groups"].values()),
                "clique_audit": "PASS", "forbidden_pair_rejection_and_singleton_rules": "PASS", "connected_components_used": False}

    functions = [t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12, t13, t14, t15, t16]
    for index, function in enumerate(functions, 1):
        test_id = f"A003-T{index:02d}"
        try:
            evidence = function()
        except Exception as exc:
            reports.append({"test_id": test_id, "status": "FAIL", "evidence": str(exc)})
            print(test_id + ": FAIL: " + str(exc), flush=True)
            break
        reports.append({"test_id": test_id, "status": "PASS", "evidence": evidence})
        print(test_id + ": PASS", flush=True)
    return {"job_id": "W02-02R-A-003", "required_tests": 16,
            "passed": sum(r["status"] == "PASS" for r in reports),
            "failed": sum(r["status"] == "FAIL" for r in reports),
            "not_run": 16 - len(reports), "tests": reports,
            "scientific_review_status": "pending", "normalization_performed": False}


def summarize(result, diagnostics):
    by_scan = {s["scan_record_id"]: s for s in result["scans"]}
    pair_counts = Counter(p["compatibility_status"] for p in result["pairs"])
    epoch_members = defaultdict(list)
    for row in sorted(result["scans"], key=lambda s: int(s["sequence_index"])):
        epoch_members[row["normalization_epoch_id"]].append(row["scan_record_id"])
    return {
        "canonical_scan_count": len(result["scans"]),
        "acquisition_state_count": len(result["states"]),
        "acquisition_state_membership_counts": {key: len(v["member_scan_record_ids"]) for key, v in result["states"].items()},
        "instrument_config_count": len(result["configs"]),
        "recorded_instrument_config_vectors": {key: v["state_vector"] for key, v in result["configs"].items()},
        "acquisition_boundary_count": len(result["boundaries"]),
        "boundary_locations": [{"boundary_index": row["boundary_index"],
                                "previous_sequence_index": int(by_scan[row["previous_scan_record_id"]]["sequence_index"]),
                                "next_sequence_index": int(by_scan[row["next_scan_record_id"]]["sequence_index"]),
                                "previous_raw_scan_id": by_scan[row["previous_scan_record_id"]]["raw_scan_id"],
                                "next_raw_scan_id": by_scan[row["next_scan_record_id"]]["raw_scan_id"],
                                "changed_fields": row["changed_fields"]} for row in result["boundaries"]],
        "boundary_type_distribution": dict(sorted(Counter(b["boundary_type"] for b in result["boundaries"]).items())),
        "boundary_confidence_distribution": dict(sorted(Counter(b["confidence"] for b in result["boundaries"]).items())),
        "normalization_relevant_boundary_count": sum(b["normalization_relevant"] for b in result["boundaries"]),
        "normalization_epoch_count": len(epoch_members),
        "normalization_epochs": {key: {"scan_count": len(members), "first_scan_record_id": members[0],
                                       "last_scan_record_id": members[-1]} for key, members in sorted(epoch_members.items())},
        "pairwise_count": len(result["pairs"]), "pairwise_status_counts": {key: pair_counts[key] for key in STATUSES},
        "cross_control_mode_pairs": sum(by_scan[p["scan_a_record_id"]]["count_control_mode"] != by_scan[p["scan_b_record_id"]]["count_control_mode"]
                                        for p in result["pairs"]),
        "normalization_compatibility_group_count": len(result["groups"]),
        "groups": {key: {"scan_count": len(group["member_scan_record_ids"]), "status": group["status"],
                         "count_control_mode": group["count_control_mode"], "internal_pair_count": group["pair_count"],
                         "clique_audit_status": group["clique_audit_status"]} for key, group in result["groups"].items()},
        "clique_audit_status": "FAIL" if result["clique_failures"] else "PASS",
        "critical_unknown_fields": list(CRITICAL), "relevant_unknown_fields": list(RELEVANT),
        "diagnostic_candidate_fields_unverified": [r["field"] for r in diagnostics if r["diagnostic_type"] == "unresolved_configuration_field_presence"],
        "new_verified_candidate_identity_fields": [],
        "external_auxiliary_used": False, "normalization_performed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--execution-context", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        require(args.expected_commit == HEAD, "Expected authorization commit differs")
        require(args.execution_context == "W02-Lin" and platform.system().lower() == "linux",
                "This invocation is authorized for W02-Lin / Linux only")
        scans, inputs = read_inputs()
        source_bytes = (ROOT / SOURCE).read_bytes()
        print("INPUT_INTEGRITY: PASS; raw and point tables not opened; external_auxiliary_used=false", flush=True)
        result = classify(scans)
        diagnostics = make_diagnostics(inputs, result)
        test_report = run_tests(scans, inputs, result, source_bytes)
        if test_report["failed"] or test_report["not_run"]:
            (ROOT / OUT).mkdir()
            (ROOT / OUT / "test_report.yaml").write_bytes(yaml_bytes(test_report))
            (ROOT / OUT / "classification_diagnostics.csv").write_bytes(csv_bytes(diagnostics, DIAG_COLUMNS))
            if result["clique_failures"]:
                (ROOT / OUT / "normalization_compatibility_groups.yaml").write_bytes(yaml_bytes(result["groups"]))
            print("STOP: mandatory test failed; no rule repair or continuation.", flush=True)
            return 2
        for identity in inputs["identities"]:
            data = (ROOT / identity["path"]).read_bytes()
            require((len(data), sha(data)) == (identity["size_bytes"], identity["sha256"]), "Input changed during execution")
        require(not git("diff", "HEAD", "--name-only"), "Tracked input/source-of-truth changed during execution")
        artifacts = scientific_artifact_bytes(result, diagnostics)
        artifacts["test_report.yaml"] = yaml_bytes(test_report)
        summary = summarize(result, diagnostics)
        command = f"python3 -B {SOURCE} --execute --execution-context {args.execution_context} --expected-commit {HEAD}"
        manifest = {
            "job_id": "W02-02R-A-003", "dataset_id": "EXP-TAIPAN-001", "parent_checkpoint": "W02-02R-A-002",
            "execution_status": "completed", "review_status": "pending", "scientific_interpretation_status": "pending",
            "repository_commit": HEAD, "repository": "oregu93/cef-dy", "branch": "main",
            "execution_context": args.execution_context, "platform": platform.system().lower(),
            "python_executable": Path(sys.executable).name, "python_invocation": "python3",
            "python_environment": "system interpreter; no machine-local absolute path recorded",
            "python_version": platform.python_version(), "python_implementation": platform.python_implementation(),
            "PyYAML_version": yaml.__version__, "command": command,
            "frozen_specification": {"path": SPEC, "sha256": SPEC_SHA},
            "source": {"path": SOURCE, "sha256": sha(source_bytes), "status": "uncommitted_execution_candidate"},
            "inputs": inputs["identities"], "input_identity_basis": "Canonical HEAD bytes plus reviewed A002 checkpoint and manifest sizes/SHA256.",
            "input_postflight_identity_status": "unchanged", "external_auxiliary_used": False,
            "external_auxiliary_reason": "Frozen fields and verified chronology are in primary tracked metadata; unresolved auxiliary semantics do not justify reading values.",
            "raw_data_access": "none", "point_table_access": "none", "raw_dataset_rehashed": False,
            "identity_rules": {"acquisition": {"version": ACQ_VERSION, "fields": list(ACQ_FIELDS)},
                               "instrument": {"version": CONFIG_VERSION, "fields": list(CONFIG_FIELDS)},
                               "group": {"version": GROUP_VERSION, "fields": list(GROUP_FIELDS)},
                               "serialization": "UTF-8/no BOM/LF/final LF; full SHA256; shortest unique even prefix >=16"},
            "boundary_recording_policy": "One row per adjacent verified-chronology transition with a frozen acquisition-vector change, verified configuration change, or explicit/uncertain recorded event; no initial pseudo-boundary.",
            "normalization_epoch_evidence": "Verified physical configuration changes and explicit verified events only. No dedicated event metadata recorded; no event inferred from titles or unverified auxiliary fields.",
            "unknown_evidence": {"critical_fields": list(CRITICAL), "relevant_fields": list(RELEVANT),
                                 "source": BASE + "semantic_verification_report.yaml",
                                 "interpretation": "Frozen sets propagated on every pair, scan, configuration and group; missing values never enter equality evidence."},
            "serialization": {"text": "UTF-8/no BOM/LF/final LF", "CSV_lists": "semicolon-separated field names or IDs; empty means none",
                              "CSV_objects": "compact sorted-key JSON", "row_order": "lexical scan IDs and lexical unordered pairs; chronological boundaries",
                              "YAML": "stable insertion order, identity vector order frozen, sorted ID maps and member lists, no aliases"},
            "classification_summary": summary,
            "scope_audit": {"normalization_performed": False, "spectral_analysis_performed": False,
                            "resolution_calculation_performed": False, "cef_analysis_performed": False,
                            "scientific_registers_or_project_control_modified": False},
            "outputs": [{"path": OUT + name, "size_bytes": len(data), "sha256": sha(data)} for name, data in sorted(artifacts.items())],
            "self_hash_policy": "Manifest byte SHA256 is detached in the execution checkpoint; not self-referential.",
            "project_validation": "Separate required post-execution KB checks; no validator or storage-policy override by this source.",
            "stop_condition": "A003 metadata classification complete; STOP for 02 - TAIPAN Data Reduction scientific review; no downstream execution.",
        }
        artifacts["provenance_manifest.yaml"] = yaml_bytes(manifest)
        for name, data in artifacts.items():
            require(data.endswith(b"\n") and b"\r" not in data and not data.startswith(b"\xef\xbb\xbf"), "Text serialization violation")
            data.decode("utf-8")
            if name.endswith(".yaml"):
                require(yaml_bytes(yaml_load(data)) == data, "YAML byte roundtrip failure")
        (ROOT / OUT).mkdir()
        for name, data in artifacts.items():
            (ROOT / OUT / name).write_bytes(data)
            require((ROOT / OUT / name).read_bytes() == data, "Output byte verification failed")
        print("A003_TESTS: 16/16 PASS", flush=True)
        print("CLASSIFICATION_SUMMARY " + compact(summary), flush=True)
        print("OUTPUT_IDENTITIES " + compact([{ "path": OUT + name, "size_bytes": len(data), "sha256": sha(data)}
                                             for name, data in sorted(artifacts.items())]), flush=True)
        print("SOURCE_SHA256 " + sha(source_bytes), flush=True)
        print("STOP_CONDITION: reached; scientific review pending.", flush=True)
        return 0
    except (JobError, OSError, ValueError, KeyError) as exc:
        print("STOP: " + str(exc), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
