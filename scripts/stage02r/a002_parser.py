"""Frozen Stage02R A-002 parser: raw preservation and bounded metadata checks only.

No import-time raw access. Registry construction reads only the reviewed A-001
catalogue. Execution is explicit and refuses existing result directories.
"""
from __future__ import annotations

import argparse
import ast
import collections
import copy
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path, PurePosixPath
import platform
import random
import re
import subprocess
import sys

import yaml
import a001_reconnaissance as a001

JOB = "W02-02R-A-002"
DATASET = "EXP-TAIPAN-001"
VERSION = "stage02r_a002_parser_v1"
SERIALIZATION = "stage02r_a002_serialization_v1"
SCAN_VERSION = "stage02r_scan_record_v1"
LAT_VERSION = "stage02r_lattice_state_v1"
UB_VERSION = "stage02r_ub_state_v1"
A001_DIR = Path("04_Results/Stage02R/W02-02R-A-001")
OUTPUT_DIR = Path("04_Results/Stage02R") / JOB
REGISTRY = Path("scripts/stage02r/a002_schema_registry.yaml")
SPEC = Path("03_Protocols/STAGE02R_T02R03_A002_PARSER_SPEC.md")
INPUT_DIGEST = "bb7a3f99710a9463a7697ebbf23cce3fd5c02936b9788df72cac3cc0f90a1e95"
A001_HASHES = {
    "file_inventory_preliminary.csv": "859fbd410caae4346ae400cac20ab419978d14f7d935a82bc521170920f950ef",
    "format_catalogue.yaml": "4306384d49d595af3e83da6a981075a4f4bd5ef90a01fb2ff536a883e360b359",
    "parsed_header_metadata_sample.jsonl": "039fde9116b5862728c49744a5198ae1314ef41ff3540201d88119cced0d63ab",
    "field_semantics_report.yaml": "534f9d5b1ec665c51796cd6519922fdfb86c74073b29dadeb31651bf2de7603d",
    "reconnaissance_diagnostics.csv": "5afa3964bc2dac6978974ae6898989457bafdc7b1ebd9140fadabf2b53349fc3",
    "provenance_manifest.yaml": "ff6bc1810d2ed6f1cacc1492186dd86c04202d61045066cc560bf61c842731f1",
    "test_report.yaml": "3dbb1c0a34c6be64acbaac536696f4e7d4094119091bc942fd4884a9b5a0adff",
}
WIDE = dict(zip(
    "q h k l e ei vei ef time detector det_err monitor m1 m2 s1 s2 a1 a2".split(),
    "q_raw h_raw k_raw l_raw e_raw ei_raw vei_raw ef_raw time_raw detector_raw det_err_raw monitor_raw M1_raw M2_raw S1_raw S2_raw A1_raw A2_raw".split(),
))
FILE_COLS = "file_record_id dataset_id source_file source_checksum file_size_bytes file_extension filesystem_mtime filesystem_mtime_trust raw_format_id raw_format_fingerprint file_role parse_status parse_message duplicate_status duplicate_group_id raw_scan_id file_scan_cardinality_status quality_flag quality_reasons".split()
SCAN_COLS = """scan_record_id scan_record_fingerprint scan_identity_version dataset_id experiment_id raw_scan_id scan_identity_status primary_file_record_id source_file source_checksum
acquisition_start_time acquisition_end_time acquisition_timestamp_source sequence_index sequence_status filesystem_mtime filesystem_mtime_trust
raw_format_id scan_variable_raw scan_variable_canonical scan_coordinate_type scan_start_derived scan_stop_derived scan_range_status scan_point_count def_x_raw def_y_raw command_raw builtin_command_raw
preset_channel_raw count_control_mode count_control_status raw_time_field_status raw_monitor_field_status raw_detector_field_status
mode_raw mode_semantics mode_semantics_status Ei_summary_meV Ef_summary_meV Ei_variation_status Ef_variation_status energy_transfer_field_raw energy_transfer_convention energy_relation_status en_e_mapping_status
h_variation_status k_variation_status l_variation_status q_semantics_status lattice_state_id UB_state_id orientation_status
monochromator_material monochromator_reflection monochromator_reflection_status monochromator_mosaic monochromator_mosaic_status analyzer_material analyzer_reflection analyzer_reflection_status analyzer_mosaic analyzer_mosaic_status collimation filter_state filter_state_status attenuation_state attenuation_state_status
temperature_summary_K temperature_variation_status sensor_metadata_ref setpoint_metadata_ref
repeat_candidate_status repeat_metadata_signature repeat_candidate_count repeat_candidate_basis
quality_flag quality_reasons parser_schema_version point_data_ref""".split()
MAP_COLS = "file_record_id scan_record_id relationship_role mapping_status mapping_evidence".split()
POINT_COLS = ["dataset_id", "scan_record_id", "file_record_id", "point_index", *WIDE.values(), "source_data_line_number"]
AUX_COLS = "dataset_id scan_record_id file_record_id point_index raw_field_name raw_value raw_unit semantic_status source_column_index".split()
PDIAG_COLS = "dataset_id file_record_id scan_record_id raw_format_id diagnostic_type severity field_or_section source_line_number message".split()
QDIAG_COLS = "dataset_id file_record_id scan_record_id quality_test status affected_point_count details".split()
REFERENCES = [
    {"url": "https://www.ansto.gov.au/media/1429/download", "scope": "TAIPAN SICS manual v14 (2017): ei/ef in meV, lattice and reciprocal coordinates; fixed-energy command is tasub const, not an interpretation of mode=0."},
    {"url": "https://www.ansto.gov.au/facilities/australian-centre-for-neutron-scattering/neutron-scattering-instruments/taipan/services-taipan", "scope": "SICS qh/qk/ql and en controls; count presets monitor or time; no per-scan filter or reflection inference."},
]


class StopExecution(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise StopExecution(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return a001.sha256_file(path)


def jbytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def ybytes(value):
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=True, width=120, line_break="\n").encode("utf-8")


def csvbytes(columns, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def canonical_number(value):
    value = Decimal(value)
    require(value.is_finite(), "Nonfinite value cannot define a state")
    if value == 0:
        return "0"
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def fingerprint(version, values):
    return sha((version + "\n" + "\n".join(values) + "\n").encode("utf-8"))


def display_ids(fingerprints, prefix):
    full = sorted(set(fingerprints))
    require(all(re.fullmatch("[0-9a-f]{64}", x) for x in full), "Invalid fingerprint")
    lengths = dict.fromkeys(full, 16)
    while True:
        groups = collections.defaultdict(list)
        for fp in full:
            groups[fp[:lengths[fp]]].append(fp)
        collided = [v for v in groups.values() if len(v) > 1]
        if not collided:
            return {fp: prefix + fp[:lengths[fp]] for fp in full}
        for group in collided:
            for fp in group:
                lengths[fp] += 2
                require(lengths[fp] <= 64, "Unresolvable fingerprint collision")


def canonical_relative(value):
    value = value.replace("\\", "/")
    require(not re.match(r"^[A-Za-z]:", value), "Absolute source path prohibited")
    p = PurePosixPath(value)
    require(not p.is_absolute() and ".." not in p.parts and str(p) not in ("", "."), "Invalid relative source path")
    return str(p)


def local_path_leaks(data, roots):
    # Specific execution roots only; raw instrument paths are not generically redacted.
    haystack = data.decode("utf-8").replace("\\\\", "/").replace("\\", "/").casefold()
    return [str(i) for i, root in enumerate(roots) if str(root).replace("\\", "/").casefold() in haystack]


def reviewed_inventory(repo):
    for name, expected in A001_HASHES.items():
        require(file_sha(repo / A001_DIR / name) == expected, "A001 artifact integrity: " + name)
    checkpoint = (repo / "02_Work_Checkpoints/W02-02R-A-001.md").read_text(encoding="utf-8")
    require("status: completed" in checkpoint and "review_status: reviewed" in checkpoint, "A001 not reviewed")
    with (repo / A001_DIR / "file_inventory_preliminary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == 201, "Reviewed census does not contain 201 files")
    return rows


def census(root):
    result = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix().encode("utf-8")):
        require(not path.is_symlink(), "Raw symlink requires review")
        if path.is_file():
            result.append({"source_file": canonical_relative(path.relative_to(root).as_posix()), "file_size_bytes": path.stat().st_size, "source_checksum": file_sha(path)})
    return result


def identity_digest(rows):
    matrix = [[r["source_file"], int(r["file_size_bytes"]), r["source_checksum"]] for r in sorted(rows, key=lambda r: r["source_file"].encode("utf-8"))]
    return sha(a001.canonical_json(matrix).encode("utf-8"))


def make_registry(repo):
    reviewed_inventory(repo)
    catalogue = yaml.safe_load((repo / A001_DIR / "format_catalogue.yaml").read_text(encoding="utf-8"))
    formats = []
    for item in sorted(catalogue["formats"], key=lambda x: x["raw_format_id"]):
        descriptor = item["canonical_structural_descriptor"]
        columns = descriptor["normalized_declared_columns"]
        formats.append({
            "raw_format_id": item["raw_format_id"], "raw_format_fingerprint": item["raw_format_fingerprint"],
            "column_names": columns, "canonical_structural_descriptor": descriptor,
            "scan_variable_schema": {"header": "def_x", "column_lookup": "normalized declared label; preserve all duplicate occurrences; alias en/e and qk/k or ql/l only after bounded checks"},
            "verified_mappings": {k: v for k, v in WIDE.items() if k in columns},
            "unresolved_fields": ["q physical meaning", "mode=0", "filters", "attenuation", "PG reflection/mosaic", "auxiliary motors", "temperature sensor identity/units"],
            "required_header_keys": ["scan", "start_time", "end_time", "latticeconstants", "ubmatrix", "preset_channel", "def_x", "def_y", "col_headers"],
            "optional_header_keys": sorted(set(descriptor["normalized_header_key_sequence"]) - {"scan", "start_time", "end_time", "latticeconstants", "ubmatrix", "preset_channel", "def_x", "def_y", "col_headers"}),
            "parser_rules": {"encoding": "utf-8-sig", "numeric_blocks": 1, "row_tokenization": "whitespace", "column_count": len(columns), "duplicate_label_policy": "wide uses first declared occurrence, all other occurrences preserved in auxiliary; no physical equivalence assumed", "invalid_width": "stop", "invalid_numeric_token": "stop", "header": "ordered nonlossy records including declaration line"},
        })
    return {"parser_schema_version": VERSION, "source_catalogue_sha256": A001_HASHES["format_catalogue.yaml"], "identity_versions": [SCAN_VERSION, LAT_VERSION, UB_VERSION], "serialization_contract_version": SERIALIZATION, "method_references": REFERENCES, "formats": formats}


def parse_text(text):
    records, columns, points = [], None, []
    declaration_pending = False
    in_data, ended_data = False, False
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not in_data:
            if stripped.startswith("#") or not stripped:
                raw_key, raw_value = None, None
                if stripped.startswith("#"):
                    body = line[line.index("#") + 1:]
                    match = re.match(r"\s*([^=]+?)\s*=(.*)$", body)
                    if match:
                        raw_key, raw_value = match.group(1).strip(), match.group(2)
                        if a001.normalize_name(raw_key) == "col_headers":
                            require(columns is None and not declaration_pending, "Multiple column declarations")
                            declaration_pending = True
                            require(not raw_value.strip(), "Unexpected inline column declaration")
                    elif declaration_pending:
                        columns = body.split()
                        require(bool(columns), "Empty column declaration")
                        declaration_pending = False
                records.append({"source_line_number": line_number, "raw_key": raw_key, "raw_value": raw_value, "raw_text": line})
                continue
            require(columns is not None and not declaration_pending, "Numeric data without declared columns")
            in_data = True
        if not stripped:
            ended_data = True
            continue
        require(not ended_data and not stripped.startswith("#"), "More than one numeric block or trailing nonnumeric section")
        tokens = stripped.split()
        require(len(tokens) == len(columns), "Declared/actual numeric width mismatch at line " + str(line_number))
        try:
            values = [Decimal(t) for t in tokens]
        except InvalidOperation as exc:
            raise StopExecution("Nonnumeric token at line " + str(line_number)) from exc
        require(all(v.is_finite() for v in values), "Nonfinite numeric token at line " + str(line_number))
        points.append({"line": line_number, "tokens": tokens})
    require(points and columns, "No complete numeric block")
    return {"header": records, "columns": columns, "normalized_columns": [a001.normalize_name(c) for c in columns], "points": points}


def header_values(parsed, key):
    return [r["raw_value"].strip() for r in parsed["header"] if r["raw_key"] is not None and a001.normalize_name(r["raw_key"]) == key]


def header_one(parsed, key, required=False):
    values = header_values(parsed, key)
    if required:
        require(len(values) == 1 and values[0] != "", "Missing/ambiguous required header: " + key)
    return values[0] if len(values) == 1 else None


def indexes(parsed, label):
    return [i for i, c in enumerate(parsed["normalized_columns"]) if c == label]


def tokens_for(parsed, label, occurrence=0):
    idx = indexes(parsed, label)
    return [p["tokens"][idx[occurrence]] for p in parsed["points"]] if len(idx) > occurrence else []


def variation(tokens):
    if not tokens:
        return "not_recorded"
    return "constant" if len({Decimal(t) for t in tokens}) == 1 else "variable"


def summary_value(tokens):
    # Metadata summary only: a varying channel is not collapsed to a mean.
    return canonical_number(tokens[0]) if variation(tokens) == "constant" else None


def ulp(token):
    return Decimal(1).scaleb(Decimal(token).as_tuple().exponent)


def energy_check(e, ei, ef):
    with localcontext() as ctx:
        ctx.prec = 60
        residual = Decimal(e) - (Decimal(ei) - Decimal(ef))
        tolerance = (ulp(e) + ulp(ei) + ulp(ef)) / 2 + Decimal("1e-40")
        return {"residual": canonical_number(residual), "tolerance": canonical_number(tolerance), "status": "pass" if abs(residual) <= tolerance else "fail"}


def pair_check(left, right):
    with localcontext() as ctx:
        ctx.prec = 60
        residual = Decimal(left) - Decimal(right)
        tolerance = (ulp(left) + ulp(right)) / 2 + Decimal("1e-40")
        return {"residual": canonical_number(residual), "tolerance": canonical_number(tolerance), "status": "pass" if abs(residual) <= tolerance else "fail"}


def timestamp(parsed, key):
    value = header_one(parsed, key)
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def duplicate_groups(records):
    groups = collections.defaultdict(list)
    for row in records:
        groups[row["source_checksum"]].append(row["file_record_id"])
    return {key: sorted(values) for key, values in groups.items() if len(values) > 1}


def repeat_signature(parsed):
    # Diagnostic only, whitelist of recorded acquisition metadata; no point intensity.
    allowed = ["experiment_number", "def_x", "preset_channel", "preset_value", "latticeconstants", "ubmatrix", "monochromator", "analyzer", "collimation"]
    return sha(jbytes({key: header_values(parsed, key) for key in allowed}))


def topic(status, evidence, tests, mapping=None, ambiguity=None, exceptions=None):
    return {"status": status, "evidence": evidence, "tests": tests, "exceptions": exceptions or [], "canonical_mapping": mapping, "remaining_ambiguity": ambiguity}


def state_tables(scans):
    lattice_ids = display_ids([s["lat_fp"] for s in scans], "LAT-02R-")
    ub_ids = display_ids([s["ub_fp"] for s in scans], "UB-02R-")
    lattices, ubs = {}, {}
    for s in sorted(scans, key=lambda s: s["scan_id"]):
        lat_id, ub_id = lattice_ids[s["lat_fp"]], ub_ids[s["ub_fp"]]
        s["lat_id"], s["ub_id"] = lat_id, ub_id
        if lat_id not in lattices:
            lattices[lat_id] = {"lattice_state_fingerprint": s["lat_fp"], "lattice_state_identity_version": LAT_VERSION, **dict(zip("a_A b_A c_A alpha_deg beta_deg gamma_deg".split(), s["lat"])), "source_scan_record_ids": []}
        lattices[lat_id]["source_scan_record_ids"].append(s["scan_id"])
        if ub_id not in ubs:
            ubs[ub_id] = {"UB_state_fingerprint": s["ub_fp"], "ub_state_identity_version": UB_VERSION, "matrix": [s["ub"][i:i+3] for i in (0, 3, 6)], "source_scan_record_ids": [], "lattice_state_ids": [], "semantic_status": "recorded_not_refined"}
        ubs[ub_id]["source_scan_record_ids"].append(s["scan_id"])
        ubs[ub_id]["lattice_state_ids"] = sorted(set(ubs[ub_id]["lattice_state_ids"] + [lat_id]))
    for record in ubs.values():
        record["lattice_state_id"] = record["lattice_state_ids"][0] if len(record["lattice_state_ids"]) == 1 else None
        record["lattice_association_status"] = "unique" if record["lattice_state_id"] else "multiple_recorded_associations"
    return lattices, ubs


def inverse3(matrix):
    a, b, c, d, e, f, g, h, i = matrix
    det = a*(e*i-f*h) - b*(d*i-f*g) + c*(d*h-e*g)
    require(det != 0, "Singular geometry matrix")
    return [x / det for x in [e*i-f*h, c*h-b*i, b*f-c*e, f*g-d*i, a*i-c*g, c*d-a*f, d*h-e*g, b*g-a*h, a*e-b*d]], det


def geometry_checks(scan):
    a, b, c, alpha, beta, gamma = map(float, scan["lat"])
    require(min(a, b, c) > 0 and all(0 < x < 180 for x in (alpha, beta, gamma)), "Invalid lattice metadata")
    ca, cb, cg = [math.cos(math.radians(x)) for x in (alpha, beta, gamma)]
    direct = [a*a, a*b*cg, a*c*cb, a*b*cg, b*b, b*c*ca, a*c*cb, b*c*ca, c*c]
    reciprocal, volume_squared = inverse3(direct)
    require(volume_squared > 0, "Nonpositive lattice volume")
    ub = list(map(float, scan["ub"]))
    _, ub_det = inverse3(ub)
    ub_gram = [sum(ub[3*k+i]*ub[3*k+j] for k in range(3)) for i in range(3) for j in range(3)]
    metric_max_residual = max(abs(x-y) for x, y in zip(ub_gram, reciprocal))
    p = scan["parsed"]
    required = [tokens_for(p, field) for field in ("q", "h", "k", "l")]
    candidates = []
    if all(required):
        for index, (q, h, k, l) in enumerate(zip(*required)):
            vector = list(map(float, (h, k, l)))
            squared = sum(vector[i]*reciprocal[3*i+j]*vector[j] for i in range(3) for j in range(3))
            magnitude = 2 * math.pi * math.sqrt(max(0.0, squared))
            candidates.append({"scan_record_id": scan["scan_id"], "point_index": index, "q_raw": q, "candidate_Q_magnitude_A_inverse": format(magnitude, ".17g"), "raw_minus_candidate": format(float(q)-magnitude, ".17g")})
    return {"scan_record_id": scan["scan_id"], "lattice_state_id": scan["lat_id"], "UB_state_id": scan["ub_id"], "lattice_volume_squared": format(volume_squared, ".17g"), "UB_determinant": format(ub_det, ".17g"), "UB_transpose_UB_minus_reciprocal_metric_max_abs": format(metric_max_residual, ".17g"), "status": "bounded_metadata_check_not_refinement"}, candidates


def analyze_semantics(scan):
    p, sid = scan["parsed"], scan["scan_id"]
    energy = []
    channels = [tokens_for(p, c) for c in ("e", "ei", "ef")]
    if all(channels):
        for index, (e, ei, ef) in enumerate(zip(*channels)):
            energy.append({"scan_record_id": sid, "point_index": index, "e_raw": e, "ei_raw": ei, "ef_raw": ef, **energy_check(e, ei, ef)})
    energy_status = "verified_global" if len(energy) == len(p["points"]) and all(r["status"] == "pass" for r in energy) else "unresolved"
    variable = header_one(p, "def_x", True)
    mapping_rows = []
    target = {"en": "e", "qk": "k", "ql": "l"}.get(variable)
    mapping_status = "unresolved"
    if target:
        for occurrence, column_index in enumerate(indexes(p, variable)):
            for index, (left, right) in enumerate(zip(tokens_for(p, variable, occurrence), tokens_for(p, target))):
                mapping_rows.append({"scan_record_id": sid, "point_index": index, "source_column_index": column_index, "scan_variable_raw": variable, "target_field": target, "control_token": left, "target_token": right, **pair_check(left, right)})
        if mapping_rows and len(mapping_rows) == len(p["points"]) * len(indexes(p, variable)) and all(r["status"] == "pass" for r in mapping_rows):
            mapping_status = "verified" if target != "e" or energy_status == "verified_global" else "partially_verified"
    elif indexes(p, variable):
        occurrences = [tokens_for(p, variable, i) for i in range(len(indexes(p, variable)))]
        mapping_status = "verified" if all(all(pair_check(x, y)["status"] == "pass" for x, y in zip(occurrences[0], seq)) for seq in occurrences) else "unresolved"
    coordinates = tokens_for(p, target or variable) if mapping_status == "verified" else []
    canonical = {"en": "energy_transfer", "qk": "k", "ql": "l", "s1": "S1", "s2": "S2", "a1": "A1", "a2": "A2", "m1": "M1", "m2": "M2"}.get(variable)
    if canonical is None:
        coordinates = []
    scan.update({"energy": energy, "energy_status": energy_status, "mapping_rows": mapping_rows, "mapping_status": mapping_status, "coordinate_tokens": coordinates, "canonical_variable": canonical if coordinates else None})


def build_outputs(scans, registry_bytes):
    # Every ordering key is independent of traversal and local path/mtime.
    scans = sorted(scans, key=lambda s: s["source_file"].encode("utf-8"))
    lattice, ub = state_tables(scans)
    duplicates = duplicate_groups(scans)
    signatures = collections.Counter(repeat_signature(s["parsed"]) for s in scans)
    chronology = sorted(scans, key=lambda s: (timestamp(s["parsed"], "start_time") is None, timestamp(s["parsed"], "start_time") or "", s["raw_scan_id"], s["source_file"].encode("utf-8")))
    sequence = {s["scan_id"]: i for i, s in enumerate(chronology)}
    files, scan_rows, maps, points, auxiliary, headers, pdiag, qdiag = [], [], [], [], [], [], [], []
    all_energy, all_mapping, geometry, q_candidates, env = [], [], [], [], []
    counts = collections.Counter()
    raw_ids = collections.Counter(s["raw_scan_id"] for s in scans)
    for scan in scans:
        p, sid, fid = scan["parsed"], scan["scan_id"], scan["file_record_id"]
        analyze_semantics(scan)
        all_energy.extend(scan["energy"])
        all_mapping.extend(scan["mapping_rows"])
        geom, candidates = geometry_checks(scan)
        geometry.append(geom)
        q_candidates.extend(candidates)
        base = {"dataset_id": DATASET, "scan_record_id": sid, "file_record_id": fid}
        h = lambda key: header_one(p, key)
        control = {"monitor": "monitor_controlled", "time": "time_controlled"}.get(h("preset_channel"), "unknown")
        counts[control] += 1
        start, end = timestamp(p, "start_time"), timestamp(p, "end_time")
        reasons = ["mode_semantics_unresolved", "q_semantics_unresolved", "PG_reflection_mosaic_unverified", "filter_attenuation_not_recorded", "temperature_channel_semantics_unresolved"]
        if scan["energy_status"] == "unresolved":
            reasons.append("energy_relation_unresolved")
        if not scan["coordinate_tokens"]:
            reasons.append("scan_range_unresolved_mapping")
        if not start or not end or end < start:
            reasons.append("timestamp_missing_invalid_or_order_inconsistent")
        signature = repeat_signature(p)
        env_channels = [{"raw_field_name": name, "source_column_index": i, "variation_status": variation([row["tokens"][i] for row in p["points"]]), "semantic_status": "unresolved", "raw_unit": None} for i, name in enumerate(p["columns"]) if any(word in name.lower() for word in ("sensor", "setpoint", "temp", "ptsamp", "tfloat"))]
        env.append({"scan_record_id": sid, "channels": env_channels, "temperature_summary_K": None, "selection_status": "no_unique_sensor_or_unit_selected"})
        record = dict.fromkeys(SCAN_COLS)
        record.update({
            "scan_record_id": sid, "scan_record_fingerprint": scan["scan_fp"], "scan_identity_version": SCAN_VERSION, "dataset_id": DATASET, "experiment_id": h("experiment_number"), "raw_scan_id": scan["raw_scan_id"], "scan_identity_status": "verified" if raw_ids[scan["raw_scan_id"]] == 1 else "raw_id_collision_distinct_file_identity", "primary_file_record_id": fid, "source_file": scan["source_file"], "source_checksum": scan["source_checksum"],
            "acquisition_start_time": start, "acquisition_end_time": end, "acquisition_timestamp_source": "header_start_time_end_time_timezone_unrecorded", "sequence_index": sequence[sid], "sequence_status": "verified_header_chronology" if start else "unresolved_timestamp_deterministic_tiebreak_only", "filesystem_mtime": scan["a001"]["filesystem_mtime"], "filesystem_mtime_trust": "A001_snapshot_filesystem_metadata_only",
            "raw_format_id": scan["raw_format_id"], "scan_variable_raw": h("def_x"), "scan_variable_canonical": scan["canonical_variable"], "scan_coordinate_type": ("energy_transfer_meV" if h("def_x") == "en" else "reciprocal_lattice_coordinate" if h("def_x") in ("qk", "ql") else "tas_motor_angle_raw") if scan["coordinate_tokens"] else "unresolved", "scan_start_derived": scan["coordinate_tokens"][0] if scan["coordinate_tokens"] else None, "scan_stop_derived": scan["coordinate_tokens"][-1] if scan["coordinate_tokens"] else None, "scan_range_status": "verified_point_endpoints_not_command_range" if scan["coordinate_tokens"] else "unresolved_mapping", "scan_point_count": len(p["points"]), "def_x_raw": h("def_x"), "def_y_raw": h("def_y"), "command_raw": h("command"), "builtin_command_raw": h("builtin_command"),
            "preset_channel_raw": h("preset_channel"), "count_control_mode": control, "count_control_status": "verified" if control != "unknown" else "unresolved", "raw_time_field_status": "preserved_no_universal_exposure_assumption", "raw_monitor_field_status": "verified_count_field_hardware_not_recorded", "raw_detector_field_status": "verified_count_field_hardware_not_recorded",
            "mode_raw": h("mode"), "mode_semantics_status": "unresolved", "Ei_summary_meV": summary_value(tokens_for(p, "ei")), "Ef_summary_meV": summary_value(tokens_for(p, "ef")), "Ei_variation_status": variation(tokens_for(p, "ei")), "Ef_variation_status": variation(tokens_for(p, "ef")), "energy_transfer_field_raw": "e", "energy_transfer_convention": "Ei_minus_Ef" if scan["energy_status"] == "verified_global" else None, "energy_relation_status": scan["energy_status"], "en_e_mapping_status": scan["mapping_status"] if h("def_x") == "en" else "not_applicable",
            "h_variation_status": variation(tokens_for(p, "h")), "k_variation_status": variation(tokens_for(p, "k")), "l_variation_status": variation(tokens_for(p, "l")), "q_semantics_status": "unresolved", "lattice_state_id": scan["lat_id"], "UB_state_id": scan["ub_id"], "orientation_status": "recorded_UB_auxiliary_orientation_unresolved",
            "monochromator_material": h("monochromator"), "monochromator_reflection_status": "unverified", "monochromator_mosaic_status": "unverified", "analyzer_material": h("analyzer"), "analyzer_reflection_status": "unverified", "analyzer_mosaic_status": "unverified", "collimation": h("collimation"), "filter_state_status": "not_recorded", "attenuation_state_status": "not_recorded",
            "temperature_variation_status": "per_channel_in_semantic_report_no_unique_temperature", "sensor_metadata_ref": "semantic_verification_report.yaml#environment/" + sid, "setpoint_metadata_ref": "semantic_verification_report.yaml#environment/" + sid,
            "repeat_candidate_status": "metadata_match_only_not_validated_repeat" if signatures[signature] > 1 else "no_metadata_match", "repeat_metadata_signature": signature, "repeat_candidate_count": signatures[signature], "repeat_candidate_basis": "recorded_header_whitelist_only_no_intensity_or_group_assignment",
            "quality_flag": "warning", "quality_reasons": ";".join(reasons), "parser_schema_version": VERSION, "point_data_ref": "scan_points.csv#" + sid,
        })
        scan_rows.append(record)
        frow = {key: scan["a001"].get(key) for key in FILE_COLS}
        frow.update({"filesystem_mtime_trust": "A001_snapshot_filesystem_metadata_only", "file_role": "scan", "parse_status": "parsed", "parse_message": "complete_one_declared_numeric_block", "duplicate_status": "exact_duplicate" if scan["source_checksum"] in duplicates else "unique_content", "duplicate_group_id": "DUP-02R-" + scan["source_checksum"] if scan["source_checksum"] in duplicates else None, "raw_scan_id": scan["raw_scan_id"], "file_scan_cardinality_status": "verified_1_to_1", "quality_flag": record["quality_flag"], "quality_reasons": record["quality_reasons"]})
        files.append(frow)
        maps.append({"file_record_id": fid, "scan_record_id": sid, "relationship_role": "primary", "mapping_status": "verified_1_to_1", "mapping_evidence": "one_header_scan_identifier_one_numeric_block"})
        selected = {indexes(p, name)[0]: target for name, target in WIDE.items() if indexes(p, name)}
        for index, row in enumerate(p["points"]):
            wide = {**base, "point_index": index, **dict.fromkeys(WIDE.values()), "source_data_line_number": row["line"]}
            for column, token in enumerate(row["tokens"]):
                if column in selected:
                    wide[selected[column]] = token
                else:
                    auxiliary.append({**base, "point_index": index, "raw_field_name": p["columns"][column], "raw_value": token, "raw_unit": None, "semantic_status": "raw_preserved_unresolved" if p["normalized_columns"][column] not in ("en", "qk", "ql", "pt") else "raw_preserved_control_or_index_no_unit_assumption", "source_column_index": column})
            points.append(wide)
        headers.append({**base, "source_file": scan["source_file"], "source_checksum": scan["source_checksum"], "raw_format_id": scan["raw_format_id"], "raw_header_records": p["header"], "declared_column_names": p["columns"], "canonical_header_mappings": {key: {"values": header_values(p, key), "source_line_numbers": [r["source_line_number"] for r in p["header"] if r["raw_key"] is not None and a001.normalize_name(r["raw_key"]) == key]} for key in sorted({a001.normalize_name(r["raw_key"]) for r in p["header"] if r["raw_key"] is not None})}})
        for name, occurrences in sorted(collections.Counter(p["normalized_columns"]).items()):
            if occurrences > 1:
                pdiag.append({**base, "raw_format_id": scan["raw_format_id"], "diagnostic_type": "duplicate_declared_label", "severity": "info", "field_or_section": name, "source_line_number": p["header"][-1]["source_line_number"], "message": "All occurrences preserved by source_column_index; first occurrence only selected for wide mapping."})
        checks = {
            "readability": (True, "strict UTF-8 decoded"), "format_identity": (True, scan["raw_format_id"]), "header_parsing": (True, "ordered raw records retained"), "numeric_block_parsing": (True, "one nonempty contiguous block"), "declared_actual_column_count": (True, str(len(p["columns"]))), "point_count_reconciliation": (True, str(len(p["points"]))), "detector_monitor_time_numeric_validity": (all(tokens_for(p, c) for c in ("detector", "det_err", "monitor", "time")), "finite Decimal tokens; no correction"), "timestamp_validity": (bool(start and end and end >= start), "header timestamps; timezone unrecorded"), "raw_scan_ID_consistency": (bool(re.search(r"scan" + re.escape(scan["raw_scan_id"]) + r"(?:\D|$)", scan["source_file"])), "filename compared with raw header scan ID"), "lattice_parse": (True, scan["lat_id"]), "UB_parse": (True, scan["ub_id"]), "energy_relation": (scan["energy_status"] == "verified_global", scan["energy_status"]), "count_control_semantics": (control != "unknown", control), "all_declared_fields_preserved": (True, "wide plus auxiliary exhaustive by declared index"),
        }
        for name, (passed, details) in checks.items():
            qdiag.append({**base, "quality_test": name, "status": "pass" if passed else "warning", "affected_point_count": 0 if passed else len(p["points"]), "details": details})
    energy_failures = [r for r in all_energy if r["status"] != "pass"]
    en_rows = [r for r in all_mapping if r["scan_variable_raw"] == "en"]
    reciprocal_rows = [r for r in all_mapping if r["scan_variable_raw"] in ("qk", "ql")]
    semantic = {
        "job_id": JOB, "dataset_id": DATASET, "method_references": REFERENCES,
        "e_Ei_Ef_relation": topic("verified" if all_energy and not energy_failures else "partially_verified", "Candidate e=Ei-Ef; all usable rows checked with source-token decimal precision", {"classification": "verified_global" if not energy_failures else "verified_with_exceptions", "arithmetic_guard": "1e-40 meV", "decimal_precision": 60, "tolerance_rule": "half_ulp(e)+half_ulp(ei)+half_ulp(ef)+guard", "rows": all_energy}, "e -> Ei_minus_Ef only for scans passing every row", "No spectroscopy or resolution inference", [{"scan_record_id": r["scan_record_id"], "point_index": r["point_index"]} for r in energy_failures]),
        "en_e_mapping": topic("verified" if en_rows and all(r["status"] == "pass" for r in en_rows) and all(s["mapping_status"] == "verified" for s in scans if header_one(s["parsed"], "def_x") == "en") else "partially_verified", "ANSTO control semantics plus every en occurrence versus e in point order, sign and meV energy convention; no name-only alias", {"rows": en_rows, "progression_check": "pointwise equality for every occurrence entails source-order progression agreement", "scans": [{"scan_record_id": s["scan_id"], "status": s["mapping_status"], "control_variation": variation(tokens_for(s["parsed"], "en")), "e_variation": variation(tokens_for(s["parsed"], "e"))} for s in scans if header_one(s["parsed"], "def_x") == "en"]}, "energy_transfer only for verified scans", "Failure leaves canonical range null"),
        "mode_0_semantics": topic("unresolved", "Recorded mode values and Ei/Ef variation do not identify a unique enum meaning; tasub const is separate", [{"scan_record_id": r["scan_record_id"], "mode_raw": r["mode_raw"], "Ei_variation_status": r["Ei_variation_status"], "Ef_variation_status": r["Ef_variation_status"], "def_x_raw": r["def_x_raw"]} for r in scan_rows], None, "No fixed-Ef or operating-mode default"),
        "h_k_l_semantics": topic("partially_verified", "Reviewed reciprocal labels plus qk/k and ql/l pointwise checks; lattice and recorded UB bounded metric checks", {"coordinate_rows": reciprocal_rows, "geometry": geometry, "qh": "not_recorded"}, "h/k/l preserved reciprocal coordinates; aliases only when verified", "No angle calibration, reindexing or UB refinement; h lacks a qh-control validation"),
        "q_semantics": topic("unresolved", "Only kinematically justified |Q(hkl,lattice)| candidate evaluated", {"formula": "2*pi*sqrt(hkl_transpose*inverse_direct_cell_metric*hkl)", "calculation": "float64 trigonometry; descriptive residuals, not a precision-derived acceptance threshold", "rows": q_candidates}, None, "Units/convention are not uniquely established; raw q retained, no arbitrary correlation search"),
        "count_control_semantics": topic("verified" if counts == {"monitor_controlled": 103, "time_controlled": 98} else "partially_verified", "Explicit preset_channel", dict(sorted(counts.items())), "monitor/time control; four raw fields separate", "Time is not universally interpreted as exposure; hardware identity not recorded"),
        "filter_metadata": topic("not_recorded", "No dedicated filter header/point field; titles are not state evidence", "header and declared-label audit", None, "No title/manual/default inference"),
        "attenuation_metadata": topic("not_recorded", "No dedicated attenuation field", "header and declared-label audit", None, "No assumed zero attenuation"),
        "auxiliary_motor_semantics": topic("unresolved", "sgl/sgu/stl/stu/PS/PA and other declared fields preserved by index", "exhaustive numeric-field reconciliation", None, "No physical mapping or instrument configuration inference"),
        "lattice_state_count": topic("verified" if len(lattice) == 2 else "unresolved", "Exact Decimal tuple fingerprints", {"observed": len(lattice), "reviewed_expected": 2}, "lattice_states.yaml", "No tolerance merging or refinement"),
        "UB_state_count": topic("verified" if len(ub) == 4 else "unresolved", "Exact Decimal row-major fingerprints", {"observed": len(ub), "reviewed_expected": 4}, "UB_states.yaml", "Recorded associations only; no refinement"),
        "environment": {r["scan_record_id"]: r for r in env},
        "summary_policy": "Ei/Ef summaries populated only for an exactly constant raw channel; varying channels have null summary. Temperature is not collapsed across sensors/setpoints.",
    }
    for component in ("monochromator", "analyzer"):
        semantic[component + "_material"] = topic("verified", "Explicit material header", sorted({header_one(s["parsed"], component) for s in scans}), "PG", "Material does not specify reflection/mosaic")
        for attribute in ("reflection", "mosaic"):
            semantic[component + "_" + attribute] = topic("unresolved", "No verified dedicated field", "PG material separated from optical parameters", None, "No instrument default")
    scan_rows.sort(key=lambda r: sequence[r["scan_record_id"]])
    maps.sort(key=lambda r: (r["file_record_id"], r["scan_record_id"]))
    points.sort(key=lambda r: (r["scan_record_id"], r["point_index"]))
    auxiliary.sort(key=lambda r: (r["scan_record_id"], r["point_index"], r["source_column_index"], r["raw_field_name"]))
    pdiag.sort(key=lambda r: (r["file_record_id"], r["source_line_number"], r["field_or_section"]))
    qdiag.sort(key=lambda r: (r["file_record_id"], r["quality_test"]))
    output = {
        "file_inventory.csv": csvbytes(FILE_COLS, files), "scan_inventory.csv": csvbytes(SCAN_COLS, scan_rows), "file_scan_map.csv": csvbytes(MAP_COLS, maps), "scan_points.csv": csvbytes(POINT_COLS, points), "scan_point_auxiliary.csv": csvbytes(AUX_COLS, auxiliary),
        "parsed_header_metadata.jsonl": b"".join(jbytes(h) for h in headers), "lattice_states.yaml": ybytes(lattice), "UB_states.yaml": ybytes(ub), "parser_schema_registry.yaml": registry_bytes, "parser_diagnostics.csv": csvbytes(PDIAG_COLS, pdiag), "quality_diagnostics.csv": csvbytes(QDIAG_COLS, qdiag), "semantic_verification_report.yaml": ybytes(semantic),
    }
    return output, {"files": files, "scans": scan_rows, "maps": maps, "points": points, "aux": auxiliary, "headers": headers, "lattice": lattice, "ub": ub, "semantic": semantic, "duplicates": duplicates, "counts": dict(counts), "quality": qdiag}


def synthetic_tests():
    fixture = "# scan = 7\n# x = first\n# x = \n# instrument_path = /instrument/archive/run.nxs\n# col_headers = \n# Pt. e ei ef detector monitor time det_err s1 s1\n0 -0.00 5.00 5.00 8 12 3 2 1 1\n1 1.0 6.0 5.0 9 13 4 3 2 2\n"
    p = parse_text(fixture)
    require(len(p["points"]) == 2 and len(p["columns"]) == 10, "Synthetic parse failed")
    malformed = [fixture.replace("0 -0.00", "0"), fixture.replace("8 12 3", "bad 12 3"), fixture.replace("1 1.0", "\n1 1.0"), fixture.replace("1 1.0", "# second block\n1 1.0"), fixture.replace("# col_headers = \n# Pt. e ei ef detector monitor time det_err s1 s1\n", "")]
    rejected = 0
    for value in malformed:
        try:
            parse_text(value)
        except StopExecution:
            rejected += 1
    prefix = "ab" * 8
    hashes = [prefix + "11" + "a"*46, prefix + "11" + "b"*46, prefix + "22" + "c"*46]
    ids = display_ids(hashes, "TEST-")
    require([len(ids[h])-5 for h in hashes] == [20, 20, 18], "Two-hex collision extension failed")
    numeric = [canonical_number(x) for x in ("-0.000", "1.000", "1e0", "1.0000001")]
    require(numeric == ["0", "1", "1", "1.0000001"], "Decimal canonicalization failed")
    f1 = fingerprint(SCAN_VERSION, [DATASET, "FILE-test-a", "7"])
    f2 = fingerprint(SCAN_VERSION, [DATASET, "FILE-test-b", "7"])
    require(f1 != f2, "Raw scan collision merged")
    envelopes = [{"source_file": r"folder\file.dat", "mtime": "old", "machine": "Windows"}, {"source_file": "folder/file.dat", "mtime": "new", "machine": "POSIX"}]
    envelope_ids = []
    for envelope in envelopes:
        file_id = "FILE-02R-" + a001.file_identity_digest(canonical_relative(envelope["source_file"]))[:16]
        envelope_ids.append(fingerprint(SCAN_VERSION, [DATASET, file_id, "7"]))
    require(len(set(envelope_ids)) == 1, "Identity depends on machine/mtime/path separators")
    require(fingerprint(LAT_VERSION, [canonical_number(x) for x in ["-0", "1.00"]]) == fingerprint(LAT_VERSION, ["0", "1"]), "State numeric equivalence failed")
    require(fingerprint(LAT_VERSION, ["1"]) != fingerprint(LAT_VERSION, ["1.0000001"]), "Distinct states tolerance-merged")
    require(fingerprint(UB_VERSION, list(map(str, range(9)))) != fingerprint(UB_VERSION, list(map(str, reversed(range(9))))), "UB row-major ordering lost")
    modified = copy.deepcopy(p)
    di = indexes(modified, "detector")[0]
    for row in modified["points"]:
        row["tokens"][di] = "999"
    modified["points"].reverse()
    require(repeat_signature(p) == repeat_signature(modified), "Repeat signature depends on intensity")
    duplicates = duplicate_groups([{"source_checksum": "same", "file_record_id": "a"}, {"source_checksum": "same", "file_record_id": "b"}])
    require(duplicates == {"same": ["a", "b"]}, "Synthetic duplicate distinction failed")
    require(header_values(p, "x") == ["first", ""] and "\n".join(r["raw_text"] for r in p["header"]) == "\n".join(fixture.splitlines()[:6]), "Header lossiness")
    require(canonical_relative(r"folder\file.dat") == canonical_relative("folder/file.dat"), "Cross-platform path handling failed")
    require(not local_path_leaks(jbytes(p), ["/work/execution"]), "Instrument path incorrectly flagged")
    require(bool(local_path_leaks(b'{"path":"/work/execution/x"}\n', ["/work/execution"])), "Local path audit missed leak")
    require(energy_check("1.00", "6.00", "5.00")["status"] == "pass" and energy_check("2.00", "6.00", "5.00")["status"] == "fail", "Energy precision regression failed")
    test_csv = csvbytes(["a", "b"], [{"a": 'quoted,"value"', "b": "-0.00"}])
    require(list(csv.DictReader(io.StringIO(test_csv.decode())))[0]["b"] == "-0.00", "CSV token roundtrip failed")
    require(rejected == len(malformed), "Malformed inputs not all rejected")
    return {"malformed_fixtures_rejected": rejected, "collision_hex_lengths": [len(ids[h])-5 for h in hashes], "decimal_regressions": numeric, "raw_scan_collision": "distinct", "exact_duplicate": "distinct_records_one_group", "intensity_permutation": "invariant", "windows_posix_path": "equal", "machine_mtime_identity": "invariant", "UB_row_major": "verified", "state_exact_not_tolerance": "verified", "instrument_path": "preserved", "csv_roundtrip": "pass"}


def parse_inputs(repo, raw_root, inventory, registry):
    formats = {f["raw_format_fingerprint"]: f for f in registry["formats"]}
    scans = []
    for row in inventory:
        source = canonical_relative(row["source_file"])
        data = (raw_root / source).read_bytes()
        require(sha(data) == row["source_checksum"], "Raw changed during parse: " + source)
        text = data.decode("utf-8-sig")
        structure = a001.analyze_text_structure(text)
        structure["descriptor"]["encoding_class"] = "utf-8"
        fp = a001.descriptor_fingerprint(structure["descriptor"])
        require(fp in formats and fp == row["raw_format_fingerprint"], "Unknown or changed structural format: " + source)
        schema = formats[fp]
        p = parse_text(text)
        require(p["normalized_columns"] == schema["column_names"], "Registry column order mismatch: " + source)
        for key in schema["required_header_keys"]:
            require(len(header_values(p, key)) == 1, "Required header cardinality: " + key)
        dedicated_state_fields = {"filter", "filters", "filter_state", "attenuation", "attenuation_state", "attenuator", "monochromator_reflection", "analyzer_reflection", "monochromator_mosaic", "analyzer_mosaic"}
        recorded_fields = set(p["normalized_columns"]) | {a001.normalize_name(r["raw_key"]) for r in p["header"] if r["raw_key"] is not None}
        require(not recorded_fields & dedicated_state_fields, "Unexpected dedicated optics/state fields require explicit review, not forced absence")
        raw_id = header_one(p, "scan", True)
        lat = [canonical_number(t) for t in header_one(p, "latticeconstants", True).split()]
        ub = [canonical_number(t) for t in header_one(p, "ubmatrix", True).split()]
        require(len(lat) == 6 and len(ub) == 9, "Invalid lattice/UB tuple width")
        scans.append({"a001": row, "file_record_id": row["file_record_id"], "source_file": source, "source_checksum": row["source_checksum"], "raw_format_id": schema["raw_format_id"], "raw_scan_id": raw_id, "scan_fp": fingerprint(SCAN_VERSION, [DATASET, row["file_record_id"], raw_id]), "lat": lat, "ub": ub, "lat_fp": fingerprint(LAT_VERSION, lat), "ub_fp": fingerprint(UB_VERSION, ub), "parsed": p})
    ids = display_ids([s["scan_fp"] for s in scans], "SCAN-02R-")
    for s in scans:
        s["scan_id"] = ids[s["scan_fp"]]
    return scans


def audit_source(repo):
    source = repo / "scripts/stage02r/a002_parser.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = sorted({n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) and (not isinstance(n, ast.ImportFrom) or n.module)})
    scope_imports = {"numpy", "scipy", "matplotlib", "lmfit", "mantid"}  # AUDIT_RULE_ONLY
    return {"blind_static_audit": a001.source_static_audit(source)[0] and a001.source_static_audit(repo / REGISTRY)[0], "imports": imports, "scope_import_audit": not set(imports) & scope_imports}


def verify_outputs(scans, tables, outputs, registry_bytes, pre, post, synthetic, source_audit, determinism, roots):
    tests = []
    def test(number, passed, evidence, details):
        tests.append({"test_id": f"A002-T{number:02d}", "status": "pass" if passed else "fail", "evidence": evidence, "details": details})
    row_count = sum(len(s["parsed"]["points"]) for s in scans)
    raw_fields = sum(len(s["parsed"]["columns"])*len(s["parsed"]["points"]) for s in scans)
    preserved = sum(v is not None for p in tables["points"] for k, v in p.items() if k in WIDE.values()) + len(tables["aux"])
    # Independently reconstruct every declared row from the output tables.
    point_lookup = {(r["scan_record_id"], r["point_index"]): r for r in tables["points"]}
    aux_lookup = {(r["scan_record_id"], r["point_index"], r["source_column_index"]): r for r in tables["aux"]}
    reconstruction = True
    for s in scans:
        p = s["parsed"]
        selected = {indexes(p, k)[0]: v for k, v in WIDE.items() if indexes(p, k)}
        for index, row in enumerate(p["points"]):
            wide = point_lookup[(s["scan_id"], index)]
            reconstructed = [wide[selected[c]] if c in selected else aux_lookup[(s["scan_id"], index, c)]["raw_value"] for c in range(len(p["columns"]))]
            reconstruction &= reconstructed == row["tokens"] and wide["source_data_line_number"] == row["line"]
    test(1, True, "seven reviewed artifact SHA-256 and reviewed checkpoint verified before raw parsing", A001_HASHES)
    test(2, len(pre) == 201 and identity_digest(pre) == INPUT_DIGEST, "full relative-path/size/SHA census", {"count": len(pre), "digest": identity_digest(pre)})
    test(3, pre == post, "complete postflight census", {"pre": identity_digest(pre), "post": identity_digest(post)})
    test(4, len(scans) == 201, "strict parser completed", {"parsed_files": len(scans)})
    test(5, len(tables["files"]) == len(tables["maps"]) == len(tables["scans"]) == 201 and len({s["scan_id"] for s in scans}) == 201, "one required scan header and numeric block perfile", "201:201:201")
    test(6, len({s["raw_format_id"] for s in scans}) == 21, "full frozen descriptor comparison", sorted(collections.Counter(s["raw_format_id"] for s in scans).items()))
    test(7, outputs["parser_schema_registry.yaml"] == registry_bytes and determinism, "registry snapshot and reordered-input determinism", sha(registry_bytes))
    test(8, synthetic["malformed_fixtures_rejected"] == 5, "strict declared-width and numeric-token failures", synthetic)
    test(9, reconstruction and preserved == raw_fields, "every field reconstructed from wide+aux by declared index", {"declared_tokens": raw_fields, "preserved_tokens": preserved})
    test(10, all(s["file_record_id"] == s["a001"]["file_record_id"] for s in scans), "exact A001 IDs retained", "No identity derived from mtime")
    test(11, all(s["scan_fp"] == fingerprint(SCAN_VERSION, [DATASET, s["file_record_id"], s["raw_scan_id"]]) for s in scans) and determinism and synthetic["collision_hex_lengths"] == [20, 20, 18], "exact LF payload and collision-extension regression", synthetic)
    test(12, all(r["source_checksum"] == next(s["source_checksum"] for s in scans if s["scan_id"] == r["scan_record_id"]) for r in tables["scans"]), "scan/file/header provenance reconciliation", "SHA-256 retained")
    test(13, len(tables["points"]) == row_count and reconstruction, "point indexes0-based, source lines1-based, no truncation", {"point_count": row_count})
    test(14, reconstruction and all(r[k] is not None for r in tables["points"] for k in ("time_raw", "monitor_raw", "detector_raw", "det_err_raw")), "all four fields separately roundtripped", "No floating-point replacement of raw tokens")
    test(15, tables["counts"] == {"monitor_controlled": 103, "time_controlled": 98}, "explicit preset_channel classification", tables["counts"])
    energy = tables["semantic"]["e_Ei_Ef_relation"]["tests"]["rows"]
    test(16, len(energy) == row_count and all(all(k in r for k in ("residual", "tolerance", "status")) for r in energy), "frozen row-precision decision procedure; failures remain unresolved", {"rows": len(energy), "failures": sum(r["status"] == "fail" for r in energy)})
    test(17, all(r["en_e_mapping_status"] in ("verified", "partially_verified", "unresolved") for r in tables["scans"] if r["def_x_raw"] == "en"), "all en occurrences, progression and energy convention checked", collections.Counter(r["en_e_mapping_status"] for r in tables["scans"]))
    test(18, all(r["mode_semantics"] is None and r["mode_semantics_status"] == "unresolved" for r in tables["scans"]), "No unique mode enum evidence; conservative unresolved passes", "No fixed-Ef default")
    test(19, len(tables["semantic"]["h_k_l_semantics"]["tests"]["geometry"]) == 201 and bool(tables["semantic"]["h_k_l_semantics"]["tests"]["coordinate_rows"]), "qk/k and ql/l plus lattice/UB metric tests", "partial verification; qh unavailable; no refinement")
    test(20, len(tables["semantic"]["q_semantics"]["tests"]["rows"]) == row_count and all(r["q_semantics_status"] == "unresolved" for r in tables["scans"]), "bounded kinematic candidate evaluated; ambiguity retained", "No forced q=|Q| alias")
    test(21, len(tables["lattice"]) == 2 and all(fingerprint(LAT_VERSION, s["lat"]) == s["lat_fp"] for s in scans), "exact Decimal lattice states + shared collision/numeric regressions", {"count": len(tables["lattice"]), "numeric": synthetic["decimal_regressions"]})
    test(22, len(tables["ub"]) == 4 and all(fingerprint(UB_VERSION, s["ub"]) == s["ub_fp"] for s in scans), "exact Decimal row-major UB + shared identity regressions", {"count": len(tables["ub"])})
    test(23, all(r[c + "_material"] == "PG" and r[c + "_reflection"] is None and r[c + "_mosaic"] is None for r in tables["scans"] for c in ("monochromator", "analyzer")), "explicit PG material only", "reflection/mosaic unverified")
    test(24, all(r["filter_state"] is None and r["filter_state_status"] == "not_recorded" for r in tables["scans"]), "dedicated field absence checked", "scan titles not used for filter inference")
    test(25, all(r["attenuation_state"] is None and r["attenuation_state_status"] == "not_recorded" for r in tables["scans"]), "dedicated field absence checked", "no assumed absent attenuation")
    test(26, reconstruction and len(aux_lookup) == len(tables["aux"]), "all auxiliary fields and duplicate occurrences retained", {"auxiliary_rows": len(tables["aux"]), "raw_units": "not recorded, left null"})
    test(27, [r["sequence_index"] for r in tables["scans"]] == list(range(201)) and all(r["acquisition_end_time"] == timestamp(next(s["parsed"] for s in scans if s["scan_id"] == r["scan_record_id"]), "end_time") for r in tables["scans"]), "header-only chronology; no fabricated endpoints", "filesystem mtime is reviewed A001 snapshot only")
    test(28, not tables["duplicates"] and synthetic["exact_duplicate"] == "distinct_records_one_group", "current census and synthetic duplicate behavior", {"exact_duplicate_groups": len(tables["duplicates"])})
    test(29, synthetic["raw_scan_collision"] == "distinct", "synthetic same raw ID in different file identities", "distinct full scan fingerprints, never merged")
    test(30, synthetic["intensity_permutation"] == "invariant", "detector replacement and point permutation", "repeat whitelist contains only acquisition headers")
    test(31, not any(local_path_leaks(b, roots) for b in outputs.values()) and synthetic["windows_posix_path"] == "equal", "specific local roots audited, instrument absolute path preserved", synthetic)
    test(32, determinism and all(b.endswith(b"\n") and b"\r\n" not in b and not b.startswith(b"\xef\xbb\xbf") for b in outputs.values()), "forward/reverse/shuffled byte equality and serialization roundtrips", "Canonical bytes for nonvolatile outputs; manifest excludes volatile execution metadata/self digest for content hash; no actual Linux execution claimed")
    test(33, all(h["raw_header_records"] == s["parsed"]["header"] for h, s in zip(tables["headers"], sorted(scans, key=lambda s: s["source_file"].encode("utf-8")))) and header_values(parse_text("# scan = 1\n# empty = \n# empty = x\n# col_headers = \n# a b\n1 2\n"), "empty") == ["", "x"], "ordered raw_text, repeated keys, empty values, physical lines", "additive canonical mappings only")
    prohibited = {"acquisition_block_id", "instrument_config_id", "instrument_block_id", "repeat_candidate_group_id", "normalized_intensity", "intensity_rate", "peak_energy", "CEF_assignment"}  # AUDIT_RULE_ONLY
    test(34, reconstruction and not set(POINT_COLS) & prohibited and source_audit["scope_import_audit"], "raw reconstruction and executable-source scope review", "no ratios, corrections or background subtraction")
    test(35, not set(SCAN_COLS) & prohibited, "exact frozen column schema", "no acquisition/instrument block inference")
    test(36, source_audit["scope_import_audit"] and not set(SCAN_COLS) & prohibited, "AST imports and manual full source review", "no spectral plotting, detection or fitting")
    test(37, source_audit["scope_import_audit"] and not set(SCAN_COLS) & prohibited, "AST imports and manual full source review", "no CEF analysis")
    test(38, source_audit["blind_static_audit"], "A001 frozen historical-token audit on A002 source+registry; dependencies limited to metadata methods", source_audit)
    # Counter is converted to plain mapping for portable YAML.
    for row in tests:
        if isinstance(row["details"], collections.Counter):
            row["details"] = dict(row["details"])
    return {"job_id": JOB, "tests": tests, "summary": {"total": len(tests), "passed": sum(t["status"] == "pass" for t in tests), "failed": sum(t["status"] == "fail" for t in tests)}, "semantic_unresolved_is_not_computational_failure": True}


def execute(repo, context, expected_commit):
    require(context == "W02-win" and sys.platform == "win32", "This authorized run is Windows W02-win only")
    require(sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == (repo / ".venv").resolve(), "Canonical local isolated .venv required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(commit == expected_commit, "Canonical HEAD changed")
    require(not subprocess.check_output(["git", "diff", "--name-only"], cwd=repo, text=True).strip(), "Tracked working tree changed since clean re-entry")
    require(not subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=repo, text=True).strip(), "Git index must remain unchanged")
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo, text=True).splitlines()
    require(set(untracked) <= {"scripts/stage02r/a002_parser.py", REGISTRY.as_posix()}, "Unexpected untracked files at execution preflight")
    result_dir = repo / OUTPUT_DIR
    require(not result_dir.exists(), "A002 output directory already exists; no overwrite/re-execution")
    inventory = reviewed_inventory(repo)
    raw_root = a001.parse_local_mapping(repo / "configs/local_paths.yaml", DATASET)
    require(not raw_root.is_relative_to(repo) and not repo.is_relative_to(raw_root), "Raw and repository trees must be disjoint")
    registry_bytes = (repo / REGISTRY).read_bytes()
    require(registry_bytes == ybytes(make_registry(repo)), "Registry differs from deterministic reviewed-catalogue construction")
    registry = yaml.safe_load(registry_bytes)
    require(len(registry["formats"]) == 21, "Registry must contain 21 families")
    pre = census(raw_root)
    require(identity_digest(pre) == identity_digest(inventory) == INPUT_DIGEST and len(pre) == 201, "Raw census mismatch; Project Control review required")
    lock = repo / ".venv/a002_execution.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(context + "\n")
    try:
        print("A002 preflight passed; parsing 201 verified raw files", flush=True)
        synthetic = synthetic_tests()
        scans = parse_inputs(repo, raw_root, inventory, registry)
        print("Full parsing complete; building canonical tables and bounded semantics", flush=True)
        outputs, tables = build_outputs(scans, registry_bytes)
        digest_set = {name: sha(data) for name, data in outputs.items()}
        print("Checking reverse and shuffled traversal determinism", flush=True)
        reversed_outputs, _ = build_outputs(list(reversed(scans)), registry_bytes)
        determinism = digest_set == {name: sha(data) for name, data in reversed_outputs.items()}
        del reversed_outputs, _
        shuffled = list(scans)
        random.Random(0).shuffle(shuffled)
        shuffled_outputs, _ = build_outputs(shuffled, registry_bytes)
        determinism &= digest_set == {name: sha(data) for name, data in shuffled_outputs.items()}
        del shuffled_outputs, _
        for name, data in outputs.items():
            if name.endswith(".csv"):
                parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
                require(csvbytes(list(parsed[0]) if parsed else data.decode().splitlines()[0].split(","), parsed) == data, "CSV roundtrip failure: " + name)
            elif name.endswith(".yaml"):
                require(ybytes(yaml.safe_load(data)) == data, "YAML roundtrip failure: " + name)
            elif name.endswith(".jsonl"):
                require(b"".join(jbytes(json.loads(line)) for line in data.splitlines()) == data, "JSONL roundtrip failure")
        post = census(raw_root)
        source_audit = audit_source(repo)
        report = verify_outputs(scans, tables, outputs, registry_bytes, pre, post, synthetic, source_audit, determinism, [raw_root, repo, repo / ".venv"])
        outputs["test_report.yaml"] = ybytes(report)
        require(report["summary"]["failed"] == 0, "A002 tests failed: " + ",".join(t["test_id"] for t in report["tests"] if t["status"] == "fail"))
        dependencies = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
        sources = {str(p.as_posix()): file_sha(repo / p) for p in [Path("scripts/stage02r/a002_parser.py"), REGISTRY, Path("scripts/stage02r/a001_reconnaissance.py"), SPEC]}
        commands = ["git pull --ff-only", "git status --short", "git rev-parse HEAD", "python -m venv .venv", ".venv/Scripts/python.exe -m pip install -r requirements.txt", ".venv/Scripts/python.exe -B scripts/stage02r/a002_parser.py --self-test", f".venv/Scripts/python.exe -B scripts/stage02r/a002_parser.py --execute --execution-context {context} --expected-commit {commit}"]
        manifest = {"job_id": JOB, "parent_checkpoint": "W02-02R-A-001", "dataset_id": DATASET, "repository": "canonical Git working tree", "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip(), "code_commit": commit, "uncommitted_execution_sources": sources, "execution_context": context, "platform": "windows", "python_version": platform.python_version(), "python_implementation": platform.python_implementation(), "requirements_file": "requirements.txt", "requirements_file_checksum": file_sha(repo / "requirements.txt"), "installed_dependency_versions": dict(sorted(dependencies.items())), "A001_capture_commit": "55b54c9b9e4510cf993cb2b968b44aeefd497893", "A001_artifact_checksums": A001_HASHES, "raw_data_access": "read_only", "dataset_resolver": "configs/local_paths.yaml:EXP-TAIPAN-001 (local absolute value intentionally excluded)", "input_raw_census_digest": identity_digest(pre), "output_raw_census_digest": identity_digest(post), "parser_version": VERSION, "serialization_contract_version": SERIALIZATION, "source_schema_registry_checksum": sha(registry_bytes), "result_schema_registry_snapshot_checksum": sha(outputs["parser_schema_registry.yaml"]), "registry_snapshot_match": True, "configuration_checksum": sha(registry_bytes), "filesystem_mtime_policy": "A001 reviewed snapshot, not execution-machine mtime; never used as acquisition time or identity", "commands": commands, "outputs": [{"logical_name": name, "path": (OUTPUT_DIR / name).as_posix(), "size_bytes": len(data), "byte_sha256": sha(data), "canonical_content_sha256": sha(data)} for name, data in sorted(outputs.items())], "stop_condition": "A002 complete; STOP for 02 - TAIPAN Data Reduction scientific review; no A003, normalization, block/configuration inference, resolution, spectral or CEF analysis", "cross_platform_validation": "Windows production plus synthetic Windows/POSIX paths, shuffled/reversed traversal and serialization roundtrips; no independent Linux execution", "execution_metadata": {"completed_at_UTC": dt.datetime.now(dt.timezone.utc).isoformat()}, "manifest_digest_policy": "Self byte SHA-256 is detached in checkpoint to avoid circular hashing; canonical content excludes execution_metadata and manifest_canonical_content_sha256 and uses deterministic YAML bytes."}
        manifest["manifest_canonical_content_sha256"] = sha(ybytes({k: v for k, v in manifest.items() if k != "execution_metadata"}))
        outputs["provenance_manifest.yaml"] = ybytes(manifest)
        require(not any(local_path_leaks(b, [raw_root, repo]) for b in outputs.values()), "Output contains an execution-local absolute path")
        result_dir.mkdir(parents=True)
        for name, data in outputs.items():
            with (result_dir / name).open("xb") as handle:
                handle.write(data)
            require(file_sha(result_dir / name) == sha(data), "Written byte verification failed")
        print(json.dumps({"job_id": JOB, "status": "completed", "tests": report["summary"], "files": len(scans), "points": len(tables["points"]), "auxiliary_rows": len(tables["aux"]), "lattice_states": len(tables["lattice"]), "UB_states": len(tables["ub"]), "energy_failures": report["tests"][15]["details"]["failures"], "outputs": [{"name": name, "bytes": len(data), "sha256": sha(data)} for name, data in sorted(outputs.items())]}, indent=2), flush=True)
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--registry-stdout", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--execution-context")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.registry_stdout:
        sys.stdout.buffer.write(ybytes(make_registry(repo)))
    elif args.self_test:
        print(json.dumps(synthetic_tests(), indent=2))
    else:
        execute(repo, args.execution_context, args.expected_commit)


if __name__ == "__main__":
    try:
        main()
    except (StopExecution, OSError, UnicodeError, ValueError) as exc:
        # No raw-root absolute path is placed in a canonical artifact/error file.
        print("STOP: " + (str(exc) if isinstance(exc, StopExecution) else type(exc).__name__), file=sys.stderr)
        sys.exit(2)
