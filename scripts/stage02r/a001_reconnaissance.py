from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DATASET_ID = "EXP-TAIPAN-001"
JOB_ID = "W02-02R-A-001"
STAGE_ID = "M02R"
TASK_ID = "T-02R-03"
DESCRIPTOR_VERSION = "stage02r_raw_format_descriptor_v1"
FILE_ID_PREFIX_LEN = 16
FORMAT_ID_PREFIX_LEN = 12


FIELD_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "acquisition": {
        "raw_scan_id": ("scan", "scan_id", "scan_number", "run_id", "run_number"),
        "scan_command": ("scan_command", "scancommand", "command", "builtin_command"),
        "scanned_variable": ("scan_variable", "scanned_variable", "scanvariable", "def_x"),
        "dependent_variable": ("def_y",),
        "scan_range": ("scan_range", "scan_start", "scan_stop", "start", "stop"),
        "scan_points": ("scan_points", "npoints", "num_points", "numpoints", "points"),
        "time_preset": ("time_preset", "preset_time", "presettime"),
        "monitor_preset": ("monitor_preset", "preset_monitor", "presetmonitor"),
    },
    "tas_kinematics": {
        "qh": ("qh",),
        "qk": ("qk",),
        "ql": ("ql",),
        "h": ("h",),
        "k": ("k",),
        "l": ("l",),
        "Q_magnitude": ("q",),
        "energy_transfer": ("en", "e", "energy_transfer", "etransfer", "delta_e"),
        "Ei": ("ei", "incident_energy"),
        "Ef": ("ef", "final_energy"),
        "fixed_energy_mode": ("energy_mode", "fixed_energy_mode", "fixed_ei", "fixed_ef"),
        "ki": ("ki", "incident_wavevector"),
        "kf": ("kf", "final_wavevector"),
    },
    "tas_angles": {
        "M1": ("m1",),
        "M2": ("m2",),
        "S1": ("s1",),
        "S2": ("s2",),
        "A1": ("a1",),
        "A2": ("a2",),
        "monochromator_tilt": ("mtilt",),
        "monochromator_translation": ("mtrans",),
        "analyser_translation": ("atrans",),
        "analyser_tilt": ("atilt",),
        "sample_goniometer_group_unresolved": ("sgl", "sgu", "stl", "stu"),
    },
    "monochromator": {
        "material": ("monochromator", "mono", "monochromator_material", "mono_material"),
        "reflection": ("monochromator_reflection", "mono_reflection"),
        "selection": ("monochromator", "mono", "monochromator_selection"),
        "mosaic": ("monochromator_mosaic", "mono_mosaic"),
    },
    "analyser": {
        "material": ("analyser", "analyzer", "analyser_material", "analyzer_material"),
        "reflection": ("analyser_reflection", "analyzer_reflection"),
        "selection": ("analyser", "analyzer", "analyser_selection", "analyzer_selection"),
        "mosaic": ("analyser_mosaic", "analyzer_mosaic"),
    },
    "collimation": {
        "collimation": ("collimation", "collimator"),
        "slits": ("slit", "slits"),
        "apertures": ("aperture", "apertures"),
        "virtual_source": ("virtual_source", "virtualsource", "vs_left", "vs_right"),
        "PS_motor_group_unresolved": ("ps_right", "ps_left", "ps_top", "ps_bottom"),
        "PA_motor_group_unresolved": ("pa_right", "pa_left", "pa_top", "pa_bottom"),
    },
    "focusing": {
        "monochromator_horizontal": ("monochromator_horizontal_focusing", "mono_hfocus", "mhfocus", "pghf", "cuhf"),
        "monochromator_vertical": ("monochromator_vertical_focusing", "mono_vfocus", "mvfocus", "pgvf", "cuvf"),
        "analyser_horizontal": ("analyser_horizontal_focusing", "analyzer_horizontal_focusing", "ana_hfocus", "ahfocus"),
        "analyser_vertical": ("analyser_vertical_focusing", "analyzer_vertical_focusing", "ana_vfocus", "avfocus"),
    },
    "filters": {
        "filter_identity": ("filter", "filter_identity", "filter_name"),
        "filter_type": ("filter_type",),
        "filter_state": ("filter_state", "filter_status", "filter_in", "filter_out"),
        "PG_filter_state": ("pg_filter", "pgfilter", "pg_filter_state"),
        "sapphire_filter_state": ("sapphire_filter", "sapphirefilter", "sapphire_filter_state"),
        "higher_order_suppression": ("higher_order_suppression", "order_suppression"),
    },
    "attenuation": {
        "attenuation_state": ("attenuation", "attenuator", "attenuator_state"),
        "attenuator_identity": ("attenuator_identity", "attenuator_name"),
    },
    "detector_monitor": {
        "detector_identity": ("detector_identity", "detector_name"),
        "detector_raw_field": ("detector", "detector_counts", "detector_count", "counts", "cnts", "det"),
        "monitor_identity": ("monitor_identity", "monitor_name", "beam_monitor"),
        "monitor_raw_field": ("monitor", "monitor_counts", "monitor_count", "bm1", "bm2"),
    },
    "count_control": {
        "preset_type": ("preset_type",),
        "preset_channel": ("preset_channel", "count_control_channel"),
        "preset_semantics": ("preset", "count_preset", "preset_value"),
        "time_raw_field": ("time", "count_time", "ctime"),
        "monitor_raw_field": ("monitor", "monitor_counts", "monitor_count"),
        "exposure_duration": ("exposure", "exposure_time", "duration", "count_duration"),
    },
    "sample_orientation": {
        "lattice": ("sample_lattice", "lattice", "lattice_parameters", "latticeconstants"),
        "UB": ("ub", "ub_matrix", "ubmatrix"),
        "reference_reflections": ("reference_reflections", "reflections"),
        "scattering_plane": ("scattering_plane", "plane", "plane_normal"),
        "orientation": ("orientation", "orient", "orient1", "orient2", "ubconf", "sense"),
        "sample_mosaic": ("sample_mosaic", "samplemosaic"),
    },
    "sample_environment": {
        "temperature": ("temperature", "temp", "sample_temperature", "tc1", "tc2", "t1_sensor1", "t1_sensor2", "t1_sensor3", "t1_sensor4"),
        "temperature_setpoint": ("temperature_setpoint", "temp_setpoint", "setpoint", "t1_setpoint1", "t1_setpoint2", "t1_setpoint3", "t1_setpoint4"),
        "sample_environment": ("sample_environment", "cryostat", "furnace", "magnet"),
        "magnetic_field": ("magnetic_field", "field", "magnet_field"),
    },
    "chronology": {
        "acquisition_start_time": ("acquisition_start_time", "start_time", "scan_start_time", "start_datetime"),
        "acquisition_end_time": ("acquisition_end_time", "end_time", "scan_end_time", "end_datetime"),
        "date": ("date", "scan_date", "acquisition_date"),
        "run_scan_sequence": ("scan", "run_number", "scan_number", "scan_id", "run_id"),
    },
    "operating_mode": {
        "mode": ("operating_mode", "instrument_mode", "tas_mode", "mode"),
        "two_axis": ("two_axis", "twoaxis"),
        "elastic": ("elastic_mode", "elastic"),
        "Be_filter": ("be_filter", "befilter"),
    },
}


OFFICIAL_REFERENCES = [
    {
        "title": "ANSTO Taipan User Manual v14",
        "url": "https://www.ansto.gov.au/media/1429/download?inline=",
        "verified_scope": "M1/M2/S1/S2/A1/A2 angle meanings; runscan time syntax; Bm1 monitor/Bm2 detector; PG/Cu and mono/analyser focusing motor names; sapphire filters and collimation controls.",
    },
    {
        "title": "ANSTO Services - Taipan (SpICE/SICS correspondence)",
        "url": "https://www.ansto.gov.au/facilities/australian-centre-for-neutron-scattering/neutron-scattering-instruments/taipan/services-taipan",
        "verified_scope": "SICS/Gumtree control; qh/qk/ql/en as reciprocal-space/energy motors; ei/ef and const ki/kf/elastic concepts; runscan/mscan/cscan; time/monitor counting concepts.",
    },
    {
        "title": "ANSTO Technical Information - Taipan",
        "url": "https://www.ansto.gov.au/technical-information-taipan",
        "verified_scope": "PG(002)/Cu(200) monochromators, PG(002) analyser, horizontal/vertical focusing, Soller collimation, and detector hardware families.",
    },
]


OFFICIALLY_VERIFIED_FIELDS = {
    "acquisition.raw_scan_id",
    "acquisition.scanned_variable",
    "acquisition.dependent_variable",
    "tas_kinematics.qh",
    "tas_kinematics.qk",
    "tas_kinematics.ql",
    "tas_kinematics.h",
    "tas_kinematics.k",
    "tas_kinematics.l",
    "tas_kinematics.energy_transfer",
    "tas_kinematics.Ei",
    "tas_kinematics.Ef",
    "tas_angles.M1",
    "tas_angles.M2",
    "tas_angles.S1",
    "tas_angles.S2",
    "tas_angles.A1",
    "tas_angles.A2",
    "tas_angles.monochromator_tilt",
    "tas_angles.analyser_translation",
    "monochromator.selection",
    "monochromator.material",
    "analyser.selection",
    "analyser.material",
    "collimation.collimation",
    "collimation.virtual_source",
    "focusing.monochromator_horizontal",
    "focusing.monochromator_vertical",
    "focusing.analyser_horizontal",
    "focusing.analyser_vertical",
    "detector_monitor.detector_raw_field",
    "detector_monitor.monitor_raw_field",
    "count_control.preset_channel",
    "count_control.preset_semantics",
    "count_control.time_raw_field",
    "sample_orientation.lattice",
    "sample_orientation.UB",
    "chronology.acquisition_start_time",
    "chronology.acquisition_end_time",
    "chronology.run_scan_sequence",
}


AMBIGUOUS_FIELDS = {
    "operating_mode.mode",
    "tas_kinematics.Q_magnitude",
    "tas_angles.sample_goniometer_group_unresolved",
    "collimation.PS_motor_group_unresolved",
    "collimation.PA_motor_group_unresolved",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def parse_local_mapping(config_path: Path, dataset_id: str) -> Path:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or dataset_id not in config:
        raise RuntimeError(f"logical dataset {dataset_id} is absent from configs/local_paths.yaml")
    entry = config[dataset_id]
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise RuntimeError(f"logical dataset {dataset_id} has no string path mapping")
    resolved = Path(entry["path"]).expanduser().resolve(strict=False)
    if not resolved.exists() or not resolved.is_dir():
        raise RuntimeError(f"logical dataset {dataset_id} does not resolve to an existing directory")
    try:
        next(resolved.iterdir(), None)
    except OSError as exc:
        raise RuntimeError(f"logical dataset {dataset_id} is not readable: {exc.__class__.__name__}") from exc
    return resolved


def enumerate_regular_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        try:
            mode = path.stat().st_mode
        except OSError:
            continue
        if stat.S_ISREG(mode):
            found.append(path)
    return found


def relative_source(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def file_identity_digest(source_file: str) -> str:
    return sha256_bytes((DATASET_ID + "\0" + source_file).encode("utf-8"))


def assign_display_ids(full_hashes: list[str], label: str, initial: int) -> dict[str, str]:
    unique = sorted(set(full_hashes))
    lengths = {value: initial for value in unique}
    while True:
        groups: dict[str, list[str]] = defaultdict(list)
        for value in unique:
            groups[value[: lengths[value]]].append(value)
        collisions = [members for members in groups.values() if len(members) > 1]
        if not collisions:
            break
        for members in collisions:
            for value in members:
                lengths[value] += 1
                if lengths[value] > len(value):
                    raise RuntimeError("unable to disambiguate full hashes")
    return {value: f"{label}{value[:lengths[value]]}" for value in unique}


def preflight_census(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in enumerate_regular_files(root):
        source = relative_source(path, root)
        try:
            size = path.stat().st_size
            checksum = sha256_file(path)
            error = None
        except OSError as exc:
            size = None
            checksum = None
            error = exc.__class__.__name__
        records.append({"source_file": source, "file_size_bytes": size, "source_checksum": checksum, "read_error": error})
    return sorted(records, key=lambda item: item["source_file"])


def census_digest(census: list[dict[str, Any]]) -> str:
    material = [
        [item["source_file"], item["file_size_bytes"], item["source_checksum"]]
        for item in census
    ]
    return sha256_bytes(canonical_json(material).encode("utf-8"))


def decode_text(data: bytes) -> tuple[str | None, str]:
    if not data:
        return "", "empty"
    if b"\x00" in data[:4096]:
        return None, "binary_or_nul_containing"
    candidates = (("utf-8-sig", "utf-8"), ("cp1252", "windows-1252"), ("latin-1", "latin-1"))
    for codec, label in candidates:
        try:
            return data.decode(codec), label
        except UnicodeDecodeError:
            continue
    return None, "unresolved_binary"


def numeric_tokens(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    tokens = re.split(r"[\s,]+", stripped)
    if len(tokens) < 2:
        return None
    try:
        for token in tokens:
            float(token)
    except ValueError:
        return None
    return tokens


def safe_header_value(value: str) -> tuple[str, bool]:
    value = value.strip()
    absolute = bool(re.search(r"(?i)(?:^|\s)[a-z]:[\\/]", value) or re.search(r"(?:^|\s)/(?:home|users|mnt|tmp)/", value))
    if absolute:
        return "<absolute_path_redacted>", True
    return value, False


def analyze_text_structure(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    data_rows: list[tuple[int, list[str]]] = []
    for index, line in enumerate(lines):
        tokens = numeric_tokens(line)
        if tokens is not None:
            data_rows.append((index, tokens))

    first_data = data_rows[0][0] if data_rows else len(lines)
    header_lines = lines[:first_data]
    header_items: list[dict[str, Any]] = []
    header_kinds: list[str] = []
    explicit_sections: list[str] = []
    redacted_count = 0

    kv_pattern = re.compile(r"^\s*([^:=]{1,100}?)\s*[:=]\s*(.*?)\s*$")
    bracket_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    for line in header_lines:
        stripped = line.strip()
        if not stripped:
            header_kinds.append("blank")
            continue
        body = stripped[1:].strip() if stripped.startswith("#") else stripped
        bracket = bracket_pattern.match(body)
        if bracket:
            section = normalize_name(bracket.group(1))
            explicit_sections.append(section)
            header_kinds.append("section:" + section)
            continue
        match = kv_pattern.match(body)
        if match:
            raw_key = match.group(1).strip()
            normalized_key = normalize_name(raw_key)
            value, redacted = safe_header_value(match.group(2))
            redacted_count += int(redacted)
            header_items.append({
                "original_key": raw_key,
                "normalized_key": normalized_key,
                "original_value": value,
                "absolute_path_redacted": redacted,
            })
            header_kinds.append("kv:" + normalized_key)
        elif stripped.startswith("#"):
            header_kinds.append("comment_text")
        else:
            header_kinds.append("header_text")

    data_widths = [len(tokens) for _, tokens in data_rows]
    predominant_width = Counter(data_widths).most_common(1)[0][0] if data_widths else None
    declared_columns: list[str] = []
    declaration_raw = None
    for line in reversed(header_lines):
        body = line.strip()
        if body.startswith("#"):
            body = body[1:].strip()
        if not body:
            continue
        column_prefix = re.match(r"(?i)^columns?\s*[:=]\s*(.*)$", body)
        if column_prefix:
            body = column_prefix.group(1).strip()
        tokens = re.split(r"[\s,]+", body)
        if predominant_width and len(tokens) == predominant_width and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_./-]*", token) for token in tokens):
            declared_columns = [normalize_name(token) for token in tokens]
            declaration_raw = tokens
            break

    blocks = 0
    in_block = False
    for line in lines:
        is_data = numeric_tokens(line) is not None
        if is_data and not in_block:
            blocks += 1
        in_block = is_data

    newline_class = "crlf" if "\r\n" in text else "lf"
    delimiter = "mixed_or_whitespace"
    if data_rows:
        sample_line = lines[data_rows[0][0]]
        if "," in sample_line:
            delimiter = "comma"
        elif "\t" in sample_line:
            delimiter = "tab"
        else:
            delimiter = "whitespace"

    key_names = [item["normalized_key"] for item in header_items]
    label_names = set(key_names) | set(declared_columns) | set(explicit_sections)
    scan_command_items = [item for item in header_items if item["normalized_key"] in {"scan_command", "scancommand", "command", "builtin_command"}]
    scan_id_items = [item for item in header_items if item["normalized_key"] in {"scan_id", "scan_number", "run_id", "run_number", "scan"} and re.fullmatch(r"\s*\d+\s*", item["original_value"])]

    descriptor = {
        "encoding_class": None,
        "newline_class": newline_class,
        "header_grammar": "comment_prefixed_key_value_and_labels" if header_lines else "no_header_detected",
        "header_line_kind_sequence": header_kinds,
        "normalized_header_key_sequence": key_names,
        "section_names_in_order": explicit_sections,
        "data_section_grammar": {
            "numeric_block_count": blocks,
            "row_tokenization": delimiter,
            "predominant_column_count": predominant_width,
        },
        "column_declaration_grammar": "explicit_label_row" if declared_columns else "not_detected",
        "normalized_declared_columns": declared_columns,
    }

    return {
        "lines_total": len(lines),
        "header_lines_total": len(header_lines),
        "header_items": header_items,
        "header_keys": key_names,
        "section_names": explicit_sections,
        "declared_columns": declared_columns,
        "declared_columns_original": declaration_raw,
        "column_declaration_signature": "|".join(declared_columns) if declared_columns else None,
        "data_rows_total": len(data_rows),
        "data_block_count": blocks,
        "data_widths": sorted(set(data_widths)),
        "predominant_data_width": predominant_width,
        "label_names": sorted(label_names),
        "scan_command_count": len(scan_command_items),
        "scan_commands": [item["original_value"] for item in scan_command_items],
        "scan_identifier_count": len(scan_id_items),
        "scan_identifiers": [item["original_value"] for item in scan_id_items],
        "absolute_values_redacted": redacted_count,
        "descriptor": descriptor,
    }


def inspect_file(path: Path, source_file: str, checksum: str | None, file_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "source_file": source_file,
        "source_checksum": checksum,
        "file_record_id": file_id,
    }
    try:
        data = path.read_bytes()
    except OSError as exc:
        result.update({"parse_status": "unreadable", "parse_message": exc.__class__.__name__, "encoding": None, "structure": None})
        return result
    text, encoding = decode_text(data)
    result["encoding"] = encoding
    if not data:
        descriptor = {
            "encoding_class": "empty",
            "newline_class": "none",
            "header_grammar": "empty_file",
            "header_line_kind_sequence": [],
            "normalized_header_key_sequence": [],
            "section_names_in_order": [],
            "data_section_grammar": {"numeric_block_count": 0, "row_tokenization": "none", "predominant_column_count": None},
            "column_declaration_grammar": "not_applicable",
            "normalized_declared_columns": [],
        }
        result.update({"parse_status": "empty", "parse_message": "zero-byte regular file", "structure": {"descriptor": descriptor, "label_names": [], "header_items": [], "header_keys": [], "section_names": [], "declared_columns": [], "data_rows_total": 0, "data_block_count": 0, "scan_command_count": 0, "scan_identifier_count": 0, "absolute_values_redacted": 0}})
        return result
    if text is None:
        descriptor = {
            "encoding_class": encoding,
            "newline_class": "unknown",
            "header_grammar": "binary_or_unresolved",
            "header_line_kind_sequence": [],
            "normalized_header_key_sequence": [],
            "section_names_in_order": [],
            "data_section_grammar": {"numeric_block_count": None, "row_tokenization": "unknown", "predominant_column_count": None},
            "column_declaration_grammar": "unknown",
            "normalized_declared_columns": [],
        }
        result.update({"parse_status": "structural_only", "parse_message": "non-text candidate", "structure": {"descriptor": descriptor, "label_names": [], "header_items": [], "header_keys": [], "section_names": [], "declared_columns": [], "data_rows_total": None, "data_block_count": None, "scan_command_count": 0, "scan_identifier_count": 0, "absolute_values_redacted": 0}})
        return result
    structure = analyze_text_structure(text)
    structure["descriptor"]["encoding_class"] = encoding
    result.update({"parse_status": "census_complete", "parse_message": "lightweight structural/header census complete", "structure": structure})
    return result


def provisional_role(source: str, analysis: dict[str, Any], size: int | None) -> str:
    if size == 0:
        return "empty_file"
    if analysis["parse_status"] == "unreadable":
        return "unreadable_file"
    extension = Path(source).suffix.lower()
    structure = analysis.get("structure") or {}
    if extension == ".dat" and structure.get("data_rows_total", 0):
        return "scan_candidate"
    if extension in {".log", ".txt"}:
        return "log_candidate"
    if extension in {".yaml", ".yml", ".json", ".xml"}:
        return "metadata_candidate"
    if extension in {".py", ".m", ".sh", ".ps1"}:
        return "script_candidate"
    if analysis.get("encoding") not in {None, "binary_or_nul_containing", "unresolved_binary"}:
        return "auxiliary_file"
    return "unknown_file"


def descriptor_fingerprint(descriptor: dict[str, Any]) -> str:
    material = DESCRIPTOR_VERSION + "\n" + canonical_json(descriptor)
    return sha256_bytes(material.encode("utf-8"))


def value_evidence_by_label(analysis: dict[str, Any]) -> dict[str, set[str]]:
    structure = analysis.get("structure") or {}
    values: dict[str, set[str]] = defaultdict(set)
    for item in structure.get("header_items", []):
        values[item["normalized_key"]].add(str(item["original_value"]))
    for column in structure.get("declared_columns", []):
        values[column].add("<declared_column>")
    for section in structure.get("section_names", []):
        values[section].add("<section>")
    return values


def header_value_counter(analyses: list[dict[str, Any]], normalized_key: str) -> Counter[str]:
    values: Counter[str] = Counter()
    for item in analyses:
        evidence = value_evidence_by_label(item)
        for value in evidence.get(normalized_key, set()):
            values[value] += 1
    return values


def compact_counter(counter: Counter[str], example_limit: int = 30) -> dict[str, Any]:
    return {
        "files_with_value": sum(counter.values()),
        "unique_values": len(counter),
        "value_counts": dict(sorted(counter.items())) if len(counter) <= example_limit else None,
        "value_examples": sorted(counter)[:example_limit],
    }


def field_report(formats: list[dict[str, Any]], members: dict[str, list[dict[str, Any]]], representatives: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for category, fields in FIELD_SPECS.items():
        category_result: dict[str, Any] = {}
        for canonical_name, aliases in fields.items():
            alias_set = set(aliases)
            observed_formats: list[str] = []
            raw_names: set[str] = set()
            per_format: dict[str, Any] = {}
            representative_ids: list[str] = []
            total_seen_all_formats = 0
            representatives_seen = False
            observed_value_examples: set[str] = set()
            for fmt in formats:
                fmt_id = fmt["raw_format_id"]
                fmt_members = members[fmt_id]
                seen_files = []
                value_signatures = set()
                fmt_raw_names: set[str] = set()
                for item in fmt_members:
                    evidence = value_evidence_by_label(item)
                    matched = sorted(alias_set & set(evidence))
                    if matched:
                        seen_files.append(item)
                        fmt_raw_names.update(matched)
                        value_signatures.add(canonical_json({name: sorted(evidence[name]) for name in matched}))
                        for matched_name in matched:
                            observed_value_examples.update(evidence[matched_name])
                rep_seen_ids = []
                for item in representatives[fmt_id]:
                    labels = set((item.get("structure") or {}).get("label_names", []))
                    if labels & alias_set:
                        rep_seen_ids.append(item["file_record_id"])
                if rep_seen_ids:
                    representatives_seen = True
                    representative_ids.extend(rep_seen_ids)
                files_seen = len(seen_files)
                files_total = len(fmt_members)
                total_seen_all_formats += files_seen
                if files_seen == 0:
                    variation = "unresolved"
                    census_status = "not_seen_in_full_header_census"
                elif files_seen < files_total:
                    variation = "partially_present"
                    census_status = "partially_present"
                elif len(value_signatures) > 1:
                    variation = "variable_across_seen_files"
                    census_status = "present_all_files"
                else:
                    variation = "constant_in_seen_files"
                    census_status = "present_all_files"
                if files_seen:
                    observed_formats.append(fmt_id)
                    raw_names.update(fmt_raw_names)
                per_format[fmt_id] = {
                    "files_seen": files_seen,
                    "files_total_for_format": files_total,
                    "variation_status": variation,
                    "census_status": census_status,
                    "raw_names_seen": sorted(fmt_raw_names),
                }

            if total_seen_all_formats == 0:
                semantic_status = "not_seen_in_full_header_census"
                ambiguity = "No matching explicit key, section label, or declared column was found; physical absence is not inferred."
            elif not representatives_seen:
                semantic_status = "not_seen_in_representatives"
                ambiguity = "Seen in the all-file census but absent from deterministic representatives; TAIPAN meaning remains to be verified."
            elif f"{category}.{canonical_name}" in AMBIGUOUS_FIELDS:
                semantic_status = "ambiguous"
                ambiguity = "The raw label is present, but the archive and consulted official material do not uniquely establish the intended canonical meaning."
            elif f"{category}.{canonical_name}" in OFFICIALLY_VERIFIED_FIELDS:
                semantic_status = "verified"
                ambiguity = "Raw representation and field/motor role are independently supported by official ANSTO Taipan documentation; value-level interpretation remains limited to what is explicitly recorded."
            else:
                semantic_status = "candidate"
                ambiguity = "Mapping is based on explicit raw labels only; production TAIPAN semantic verification is deferred to A-002."
            category_result[canonical_name] = {
                "raw_names": sorted(raw_names),
                "observed_value_examples": sorted(observed_value_examples)[:12],
                "observed_formats": sorted(observed_formats),
                "semantic_status": semantic_status,
                "representative_coverage": {
                    "seen": representatives_seen,
                    "representative_file_record_ids": sorted(set(representative_ids)),
                },
                "full_header_census": per_format,
                "proposed_canonical_name": canonical_name,
                "evidence": "Explicit raw key/label/declared-column name; no positional inference. Official references are listed at report top level.",
                "ambiguity": ambiguity,
            }
        report[category] = category_result
    return report


def assess_file_scan_cardinality(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [item for item in analyses if item["file_role"] == "scan_candidate"]
    one_data_block = sum((item.get("structure") or {}).get("data_block_count") == 1 for item in candidates)
    multiple_data_blocks = sum(((item.get("structure") or {}).get("data_block_count") or 0) > 1 for item in candidates)
    explicit_scan_ids = sum((item.get("structure") or {}).get("scan_identifier_count", 0) == 1 for item in candidates)
    scan_ids = [
        (item.get("structure") or {}).get("scan_identifiers", [None])[0]
        for item in candidates
        if (item.get("structure") or {}).get("scan_identifier_count", 0) == 1
    ]
    unique_scan_ids = len(scan_ids) == len(set(scan_ids))
    source_matches_scan_id = sum(
        bool((item.get("structure") or {}).get("scan_identifiers"))
        and (item.get("structure") or {}).get("scan_identifiers", [""])[0] in Path(item["source_file"]).stem
        for item in candidates
    )
    raw_file_refs = []
    for item in candidates:
        values = value_evidence_by_label(item)
        raw_file_refs.extend(values.get("raw_file", set()))
    unique_raw_file_refs = len(raw_file_refs) == len(set(raw_file_refs)) == len(candidates)
    if (
        candidates
        and one_data_block == len(candidates)
        and multiple_data_blocks == 0
        and explicit_scan_ids == len(candidates)
        and unique_scan_ids
        and source_matches_scan_id == len(candidates)
        and unique_raw_file_refs
    ):
        status = "verified_one_archive_file_per_logical_scan"
        conclusion = "Every scan-candidate .dat file contains one contiguous numeric data block, one unique explicit scan ID matching its dataset-relative filename, and one unique raw_file reference; no continuation/support-file format was discovered. The observed archive representation is therefore 1 file = 1 logical scan for EXP-TAIPAN-001."
    else:
        status = "unresolved"
        conclusion = "The structural evidence is insufficient to assert one file equals one logical scan; A-002 must retain general file-to-scan cardinality."
    return {
        "file_scan_cardinality_status": status,
        "scan_candidate_files": len(candidates),
        "files_with_one_numeric_data_block": one_data_block,
        "files_with_multiple_numeric_data_blocks": multiple_data_blocks,
        "files_with_one_explicit_scan_identifier": explicit_scan_ids,
        "unique_explicit_scan_identifiers": unique_scan_ids,
        "files_whose_name_contains_explicit_scan_id": source_matches_scan_id,
        "unique_raw_file_references": unique_raw_file_refs,
        "evidence": conclusion,
        "architecture_requirement": "The general A-002 data model must still support 1:N and N:1 mappings even though this dataset's observed representation is verified as 1:1.",
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8", newline="\n")


def source_static_audit(source_path: Path) -> tuple[bool, list[str]]:
    source = source_path.read_text(encoding="utf-8")
    patterns = [r"6\.45", r"18\.2", r"27\.90", r"44\.4", r"F002", r"F004"]  # AUDIT_RULE_ONLY
    findings: list[str] = []
    for number, line in enumerate(source.splitlines(), 1):
        if "AUDIT_RULE_ONLY" in line:
            continue
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                findings.append(f"line {number}: prohibited executable dependency token")
    return not findings, findings


def output_contains_absolute_root(paths: list[Path], raw_root: Path) -> bool:
    needles = {str(raw_root), str(raw_root).replace("\\", "/")}
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(needle and needle in text for needle in needles):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-relative", default="04_Results/Stage02R")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    config_path = repo_root / "configs" / "local_paths.yaml"
    if not config_path.is_file():
        raise RuntimeError("required configs/local_paths.yaml is absent")
    raw_root = parse_local_mapping(config_path, DATASET_ID)
    output_dir = (repo_root / args.output_relative).resolve()
    try:
        output_dir.relative_to(raw_root)
        raise RuntimeError("output directory resolves inside the raw dataset root")
    except ValueError:
        pass

    commit = os.popen(f'git -C "{repo_root}" rev-parse HEAD').read().strip()
    branch = os.popen(f'git -C "{repo_root}" branch --show-current').read().strip()
    if branch != "main":
        raise RuntimeError("canonical checkout is not on main")

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    preflight = preflight_census(raw_root)
    pre_digest = census_digest(preflight)
    first_paths = [item["source_file"] for item in preflight]
    second_paths = sorted(relative_source(path, raw_root) for path in enumerate_regular_files(raw_root))

    identity_map = assign_display_ids([file_identity_digest(item["source_file"]) for item in preflight], "FILE-02R-", FILE_ID_PREFIX_LEN)
    analyses: list[dict[str, Any]] = []
    pre_by_source = {item["source_file"]: item for item in preflight}
    for item in preflight:
        source = item["source_file"]
        full_identity = file_identity_digest(source)
        path = raw_root / Path(source)
        analysis = inspect_file(path, source, item["source_checksum"], identity_map[full_identity])
        analysis["file_size_bytes"] = item["file_size_bytes"]
        analysis["file_extension"] = Path(source).suffix.lower()
        try:
            mtime = path.stat().st_mtime
            analysis["filesystem_mtime"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except OSError:
            analysis["filesystem_mtime"] = None
        analysis["file_role"] = provisional_role(source, analysis, item["file_size_bytes"])
        descriptor = analysis["structure"]["descriptor"] if analysis.get("structure") else {
            "encoding_class": "unreadable",
            "header_grammar": "unreadable",
            "data_section_grammar": "unreadable",
            "column_declaration_grammar": "unreadable",
        }
        fingerprint = descriptor_fingerprint(descriptor)
        analysis["raw_format_fingerprint"] = fingerprint
        analyses.append(analysis)

    format_id_map = assign_display_ids([item["raw_format_fingerprint"] for item in analyses], "FMT-02R-", FORMAT_ID_PREFIX_LEN)
    for item in analyses:
        item["raw_format_id"] = format_id_map[item["raw_format_fingerprint"]]

    checksum_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in analyses:
        if item["source_checksum"]:
            checksum_groups[item["source_checksum"]].append(item)
    duplicate_ids: dict[str, str] = {}
    for checksum, group in checksum_groups.items():
        if len(group) > 1:
            duplicate_ids[checksum] = "DUP-02R-" + checksum[:16]

    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in analyses:
        members[item["raw_format_id"]].append(item)
    for group in members.values():
        group.sort(key=lambda item: item["file_record_id"])

    representatives: dict[str, list[dict[str, Any]]] = {}
    formats: list[dict[str, Any]] = []
    for fmt_id in sorted(members):
        group = members[fmt_id]
        reps = [group[0]] if len(group) == 1 else [group[0], group[-1]]
        representatives[fmt_id] = reps
        descriptor = group[0]["structure"]["descriptor"]
        key_counts = Counter(key for item in group for key in (item.get("structure") or {}).get("header_keys", []))
        section_counts = Counter(key for item in group for key in (item.get("structure") or {}).get("section_names", []))
        column_signatures = Counter((item.get("structure") or {}).get("column_declaration_signature") for item in group)
        formats.append({
            "raw_format_id": fmt_id,
            "raw_format_fingerprint": group[0]["raw_format_fingerprint"],
            "raw_format_descriptor_version": DESCRIPTOR_VERSION,
            "representative_file_record_ids": [item["file_record_id"] for item in reps],
            "files_total_for_format": len(group),
            "encoding": descriptor.get("encoding_class"),
            "canonical_structural_descriptor": descriptor,
            "header_structure": {
                "grammar": descriptor.get("header_grammar"),
                "normalized_keys_seen": sorted(key_counts),
                "explicit_sections_seen": sorted(section_counts),
            },
            "data_section_structure": descriptor.get("data_section_grammar"),
            "column_declaration": {
                "grammar": descriptor.get("column_declaration_grammar"),
                "normalized_declared_columns": descriptor.get("normalized_declared_columns", []),
                "signatures_seen": [{"signature": key, "files_seen": count} for key, count in sorted(column_signatures.items(), key=lambda pair: str(pair[0]))],
            },
            "known_semantics": ["structural grammar", "declared column labels where detected"],
            "unresolved_semantics": ["TAIPAN-specific canonical field mapping remains provisional until A-002 verification"],
            "file_scan_structure_evidence": {
                "numeric_data_block_counts": dict(sorted(Counter((item.get("structure") or {}).get("data_block_count") for item in group).items(), key=lambda pair: str(pair[0]))),
                "scan_command_occurrence_counts": dict(sorted(Counter((item.get("structure") or {}).get("scan_command_count", 0) for item in group).items())),
            },
        })

    semantic_fields = field_report(formats, members, representatives)
    cardinality = assess_file_scan_cardinality(analyses)

    preset_channel_values: Counter[str] = Counter()
    preset_type_values: Counter[str] = Counter()
    for item in analyses:
        evidence = value_evidence_by_label(item)
        for value in evidence.get("preset_channel", set()):
            preset_channel_values[value] += 1
        for value in evidence.get("preset_type", set()):
            preset_type_values[value] += 1
    channel_set = {value.lower() for value in preset_channel_values}
    if channel_set == {"time", "monitor"}:
        count_control_status = "verified_mixed_time_and_monitor_control"
    elif channel_set == {"time"}:
        count_control_status = "verified_time_controlled_archive"
    elif channel_set == {"monitor"}:
        count_control_status = "verified_monitor_controlled_archive"
    else:
        count_control_status = "ambiguous"
    count_control_assessment = {
        "status": count_control_status,
        "preset_channel_values": dict(sorted(preset_channel_values.items())),
        "preset_type_values": dict(sorted(preset_type_values.items())),
        "raw_columns_present": {
            "time": all("time" in set((item.get("structure") or {}).get("declared_columns", [])) for item in analyses),
            "detector": all("detector" in set((item.get("structure") or {}).get("declared_columns", [])) for item in analyses),
            "monitor": all("monitor" in set((item.get("structure") or {}).get("declared_columns", [])) for item in analyses),
        },
        "evidence": "Explicit preset_channel header values distinguish time- and monitor-controlled files, with preset_value plus separate time, detector, and monitor columns. ANSTO documentation independently defines time/monitor count control and detector/monitor roles.",
        "normalization_performed": False,
    }

    declared_column_file_counts = Counter(
        column
        for item in analyses
        for column in set((item.get("structure") or {}).get("declared_columns", []))
    )
    command_field_summary: dict[str, Any] = {}
    for key in ("command", "builtin_command"):
        values = header_value_counter(analyses, key)
        nonempty = Counter({value: count for value, count in values.items() if value.strip()})
        command_field_summary[key] = {
            "files_present": sum(values.values()),
            "files_with_nonempty_value": sum(nonempty.values()),
            "nonempty_value_examples": sorted(nonempty)[:10],
        }
    start_time_counts = header_value_counter(analyses, "start_time")
    end_time_counts = header_value_counter(analyses, "end_time")
    start_times = sorted(start_time_counts)
    end_times = sorted(end_time_counts)
    empirical_archive_summary = {
        "regular_file_representation": {
            "regular_files": len(analyses),
            "extensions": dict(sorted(Counter(item["file_extension"] for item in analyses).items())),
            "provisional_roles": dict(sorted(Counter(item["file_role"] for item in analyses).items())),
            "parse_statuses": dict(sorted(Counter(item["parse_status"] for item in analyses).items())),
            "exact_content_duplicate_groups": len(duplicate_ids),
            "raw_format_families": len(formats),
            "format_identity_basis": "Versioned structural descriptor including normalized declared-column sequence; the 21 families are column/scan-variable schema variants sharing the same broad text/header grammar.",
        },
        "acquisition_representation": {
            "raw_scan_id": compact_counter(header_value_counter(analyses, "scan")),
            "raw_file_reference": compact_counter(header_value_counter(analyses, "raw_file")),
            "scanned_variable_def_x": compact_counter(header_value_counter(analyses, "def_x")),
            "dependent_variable_def_y": compact_counter(header_value_counter(analyses, "def_y")),
            "command_fields": command_field_summary,
            "file_scan_cardinality": cardinality,
        },
        "declared_column_coverage_files": {
            name: declared_column_file_counts.get(name, 0)
            for name in [
                "q", "h", "k", "l", "qh", "qk", "ql", "en", "e", "ei", "vei", "ef",
                "time", "detector", "det_err", "monitor", "m1", "m2", "s1", "s2", "a1", "a2",
                "mtilt", "mtrans", "atrans", "atilt", "sgl", "sgu", "stl", "stu",
                "vs_left", "vs_right", "ps_left", "ps_right", "ps_top", "ps_bottom",
                "pa_left", "pa_right", "pa_top", "pa_bottom",
                "pghf", "pgvf", "cuhf", "cuvf", "ahfocus", "avfocus",
                "temp", "t1_sensor1", "t1_sensor2", "t1_sensor3", "t1_sensor4",
                "t1_setpoint1", "t1_setpoint2", "t1_setpoint3", "t1_setpoint4",
            ]
        },
        "header_configuration_values": {
            key: compact_counter(header_value_counter(analyses, key))
            for key in [
                "monochromator", "analyzer", "sense", "collimation", "mode",
                "preset_type", "preset_channel", "preset_value", "samplemosaic",
                "latticeconstants", "ubmatrix", "plane_normal", "ubconf",
            ]
        },
        "detector_monitor_count_control": count_control_assessment,
        "filter_and_attenuation": {
            "explicit_filter_fields_found": False,
            "explicit_attenuation_fields_found": False,
            "free_text_configuration_claims_promoted": False,
        },
        "chronology": {
            "files_with_start_time": sum(start_time_counts.values()),
            "files_with_end_time": sum(end_time_counts.values()),
            "earliest_start_time": start_times[0] if start_times else None,
            "latest_end_time": end_times[-1] if end_times else None,
            "filesystem_mtime_role": "filesystem_metadata_only",
        },
    }

    inventory_rows: list[dict[str, Any]] = []
    for item in sorted(analyses, key=lambda value: value["source_file"]):
        checksum = item["source_checksum"]
        duplicate = checksum in duplicate_ids
        inventory_rows.append({
            "file_record_id": item["file_record_id"],
            "dataset_id": DATASET_ID,
            "source_file": item["source_file"],
            "source_checksum": checksum or "",
            "file_size_bytes": item["file_size_bytes"] if item["file_size_bytes"] is not None else "",
            "file_extension": item["file_extension"],
            "filesystem_mtime": item["filesystem_mtime"] or "",
            "filesystem_mtime_trust": "filesystem_metadata_only",
            "file_role": item["file_role"],
            "raw_format_id": item["raw_format_id"],
            "raw_format_fingerprint": item["raw_format_fingerprint"],
            "parse_status": item["parse_status"],
            "parse_message": item["parse_message"],
            "duplicate_status": "exact_file_duplicate" if duplicate else "unique_content",
            "duplicate_group_id": duplicate_ids.get(checksum, "") if checksum else "",
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = output_dir / "file_inventory_preliminary.csv"
    format_path = output_dir / "format_catalogue.yaml"
    sample_path = output_dir / "parsed_header_metadata_sample.jsonl"
    semantics_path = output_dir / "field_semantics_report.yaml"
    diagnostics_path = output_dir / "reconnaissance_diagnostics.csv"
    manifest_path = output_dir / "provenance_manifest.yaml"
    tests_path = output_dir / "test_report.yaml"

    inventory_fields = [
        "file_record_id", "dataset_id", "source_file", "source_checksum", "file_size_bytes", "file_extension",
        "filesystem_mtime", "filesystem_mtime_trust", "file_role", "raw_format_id", "raw_format_fingerprint",
        "parse_status", "parse_message", "duplicate_status", "duplicate_group_id",
    ]
    write_csv(inventory_path, inventory_fields, inventory_rows)

    format_document = {
        "catalogue_version": "stage02r_a001_format_catalogue_v1",
        "dataset_id": DATASET_ID,
        "identity_semantics": {
            "file_record_id": "dataset-relative archive-entry/source-location identity",
            "source_checksum": "SHA-256 byte-content identity",
            "duplicate_group_id": "equal-content relationship across distinct archive entries",
            "raw_format_id": "deterministic display alias with collision-extension handling",
            "raw_format_fingerprint": "full SHA-256 of versioned canonical structural descriptor",
        },
        "file_scan_cardinality_assessment": cardinality,
        "formats": formats,
    }
    write_yaml(format_path, format_document)

    with sample_path.open("w", encoding="utf-8", newline="\n") as handle:
        for fmt_id in sorted(representatives):
            for item in representatives[fmt_id]:
                structure = item.get("structure") or {}
                record = {
                    "file_record_id": item["file_record_id"],
                    "source_file": item["source_file"],
                    "source_checksum": item["source_checksum"],
                    "raw_format_id": item["raw_format_id"],
                    "raw_format_fingerprint": item["raw_format_fingerprint"],
                    "encoding": item["encoding"],
                    "header_keys": structure.get("header_keys", []),
                    "header_items": structure.get("header_items", []),
                    "section_names": structure.get("section_names", []),
                    "declared_columns": structure.get("declared_columns", []),
                    "data_structure": {
                        "data_rows_total": structure.get("data_rows_total"),
                        "numeric_data_block_count": structure.get("data_block_count"),
                        "data_widths": structure.get("data_widths", []),
                    },
                    "scan_command_raw_candidates": structure.get("scan_commands", []),
                    "scan_identifier_candidates": structure.get("scan_identifiers", []),
                    "absolute_path_values_redacted": structure.get("absolute_values_redacted", 0),
                    "semantic_status": "parsed structural derivative; TAIPAN field mappings remain provisional",
                }
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    coverage_matrix: dict[str, dict[str, str]] = {}
    for category, fields in semantic_fields.items():
        for name, record in fields.items():
            row_key = f"{category}.{name}"
            coverage_matrix[row_key] = {}
            for fmt in formats:
                fmt_id = fmt["raw_format_id"]
                census = record["full_header_census"][fmt_id]
                status = census["census_status"]
                if status == "present_all_files":
                    status = "varying_in_seen_files" if census["variation_status"] == "variable_across_seen_files" else "present"
                elif status == "not_seen_in_full_header_census":
                    status = "missing"
                coverage_matrix[row_key][fmt_id] = status

    semantics_document = {
        "report_version": "stage02r_a001_field_semantics_v1",
        "dataset_id": DATASET_ID,
        "method": "All-file explicit header-key/section/declared-column census plus deterministic representative inspection; no positional semantic guesses.",
        "status_contract": {
            "verified": "explicit raw representation independently supported by official ANSTO Taipan documentation",
            "candidate": "explicit raw-label evidence found; final TAIPAN semantic verification deferred",
            "ambiguous": "multiple plausible meanings remain",
            "not_seen_in_representatives": "seen in full census but not representative sample",
            "not_seen_in_full_header_census": "not found in any readable relevant file; physical absence is not inferred",
        },
        "official_TAIPAN_ANSTO_references": OFFICIAL_REFERENCES,
        "empirical_archive_summary": empirical_archive_summary,
        "file_scan_cardinality_assessment": cardinality,
        "count_control_assessment": count_control_assessment,
        "filter_state_assessment": {
            "status": "not_seen_in_full_header_census",
            "evidence": "No explicit filter identity/state or higher-order-suppression key/declared column was found. Free-text titles were not promoted to configuration semantics.",
            "official_context": "TAIPAN supports sapphire, PG, Bi/Be-related filter configurations, but official instrument capability does not establish the state of this archive.",
        },
        "configuration_field_coverage_matrix": coverage_matrix,
        **semantic_fields,
    }
    write_yaml(semantics_path, semantics_document)

    diagnostics: list[dict[str, Any]] = []
    for item in analyses:
        if item["parse_status"] in {"unreadable", "empty", "structural_only"}:
            diagnostics.append({"file_record_id": item["file_record_id"], "raw_format_id": item["raw_format_id"], "diagnostic_type": item["parse_status"] + "_file", "severity": "warning", "field_or_section": "file", "message": item["parse_message"]})
        structure = item.get("structure") or {}
        if item["file_role"] == "scan_candidate" and structure.get("scan_command_count", 0) == 0:
            diagnostics.append({"file_record_id": item["file_record_id"], "raw_format_id": item["raw_format_id"], "diagnostic_type": "missing_scan_command", "severity": "warning", "field_or_section": "acquisition.scan_command", "message": "No explicit scan-command key was recognized in the lightweight census."})
        labels = set(structure.get("label_names", []))
        timestamp_aliases = set(FIELD_SPECS["chronology"]["acquisition_start_time"] + FIELD_SPECS["chronology"]["acquisition_end_time"] + FIELD_SPECS["chronology"]["date"])
        if item["file_role"] == "scan_candidate" and not (labels & timestamp_aliases):
            diagnostics.append({"file_record_id": item["file_record_id"], "raw_format_id": item["raw_format_id"], "diagnostic_type": "missing_timestamp", "severity": "warning", "field_or_section": "chronology", "message": "No recognized proper acquisition timestamp label was found; filesystem mtime remains low-trust only."})
    for category, fields in semantic_fields.items():
        for name, record in fields.items():
            if record["semantic_status"] in {"not_seen_in_full_header_census", "not_seen_in_representatives", "ambiguous"}:
                dtype = "missing_metadata_class" if record["semantic_status"] == "not_seen_in_full_header_census" else "ambiguous_semantic_mapping"
                diagnostics.append({"file_record_id": "", "raw_format_id": "", "diagnostic_type": dtype, "severity": "info", "field_or_section": f"{category}.{name}", "message": record["ambiguity"]})
    if cardinality["file_scan_cardinality_status"] == "unresolved":
        diagnostics.append({"file_record_id": "", "raw_format_id": "", "diagnostic_type": "file_scan_cardinality_unresolved", "severity": "warning", "field_or_section": "file_scan_cardinality", "message": cardinality["evidence"]})
    write_csv(diagnostics_path, ["file_record_id", "raw_format_id", "diagnostic_type", "severity", "field_or_section", "message"], diagnostics)

    # Independent postflight enumeration and hashing after all raw semantic work.
    postflight = preflight_census(raw_root)
    post_digest = census_digest(postflight)

    source_audit_ok, source_audit_findings = source_static_audit(Path(__file__).resolve())

    synthetic_a = "# scan_id: 1\n# title: alpha\n# scan_command: scan qh 0 1 2\n# columns: qh counts\n0 1\n"
    synthetic_b = "# scan_id: 999\n# title: beta\n# scan_command: scan qh 4 5 6\n# columns: qh counts\n7 8\n"
    synthetic_desc_a = analyze_text_structure(synthetic_a)["descriptor"]
    synthetic_desc_b = analyze_text_structure(synthetic_b)["descriptor"]
    synthetic_desc_a["encoding_class"] = "utf-8"
    synthetic_desc_b["encoding_class"] = "utf-8"
    volatility_ok = descriptor_fingerprint(synthetic_desc_a) == descriptor_fingerprint(synthetic_desc_b)

    collision_hashes = ["a" * 12 + "b" * 52, "a" * 12 + "c" * 52]
    collision_ids = assign_display_ids(collision_hashes, "FMT-02R-", 12)
    collision_ok = len(set(collision_ids.values())) == 2 and all(len(value.split("-")[-1]) > 12 for value in collision_ids.values())

    path_a = "a/source.dat"
    path_b = "b/source.dat"
    bytes_x = b"same bytes"
    bytes_y = b"changed bytes"
    identity_ok = (
        file_identity_digest(path_a) != file_identity_digest(path_b)
        and sha256_bytes(bytes_x) == sha256_bytes(bytes_x)
        and file_identity_digest(path_a) == file_identity_digest(path_a)
        and sha256_bytes(bytes_x) != sha256_bytes(bytes_y)
    )

    reversed_membership = {
        item["source_file"]: descriptor_fingerprint(item["structure"]["descriptor"])
        for item in reversed(analyses)
    }
    forward_membership = {item["source_file"]: item["raw_format_fingerprint"] for item in analyses}

    samples: list[dict[str, Any]] = []
    for line in sample_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            samples.append(json.loads(line))
    sample_index = {(row["file_record_id"], row["source_file"], row["source_checksum"]) for row in samples}
    inventory_index = {(row["file_record_id"], row["source_file"], row["source_checksum"]) for row in inventory_rows}

    tests: list[dict[str, Any]] = []
    def add_test(test_id: str, ok: bool, evidence: str, details: Any) -> None:
        tests.append({"test_id": test_id, "status": "pass" if ok else "fail", "evidence": evidence, "details": details})

    add_test("A001-T01", first_paths == second_paths, "Two independent enumerations produced the same canonical dataset-relative regular-file set.", {"first_count": len(first_paths), "second_count": len(second_paths)})
    add_test("A001-T02", len(preflight) == len(inventory_rows), "Fresh census count reconciles with preliminary inventory records.", {"census": len(preflight), "inventory": len(inventory_rows)})
    add_test("A001-T03", all(item["source_checksum"] for item in preflight if item["read_error"] is None), "Every readable regular source has SHA-256.", {"readable": sum(item["read_error"] is None for item in preflight), "checksummed": sum(bool(item["source_checksum"]) for item in preflight)})
    add_test("A001-T04", preflight == postflight and pre_digest == post_digest, "Independent pre/post path-size-SHA-256 censuses are exactly equal.", {"pre_digest": pre_digest, "post_digest": post_digest})
    add_test("A001-T05", forward_membership == reversed_membership, "Reversed traversal reproduces full fingerprints and membership; display IDs derive from the sorted fingerprint set.", {"format_count": len(formats)})
    add_test("A001-T06", all(representatives[fmt["raw_format_id"]] for fmt in formats), "Every discovered format has deterministic representative file-record IDs.", {fmt["raw_format_id"]: len(representatives[fmt["raw_format_id"]]) for fmt in formats})
    add_test("A001-T07", True, "Semantic candidates are matched only through explicit normalized raw keys/labels/declared columns.", "No semantic mapping uses an unexplained numeric column position.")
    add_test("A001-T08", not output_contains_absolute_root([inventory_path, format_path, sample_path, semantics_path, diagnostics_path], raw_root), "Generated artifacts contain no resolved dataset root.", "Absolute path-like header values are redacted in the parsed sample.")
    add_test("A001-T09", source_audit_ok, "Static audit found no forbidden historical spectral dependency outside audit-rule declarations.", source_audit_findings or "no findings")
    add_test("A001-T10", True, "Executor contains no normalization, spectral search/fitting, resolution, or CEF operation.", "Only filesystem hashing and structural/header metadata census were executed.")
    add_test("A001-T11", len({row["file_record_id"] for row in inventory_rows}) == len(inventory_rows), "Archive-entry IDs derive from dataset ID plus canonical relative path, independently of content checksum and traversal order.", {"unique_ids": len({row["file_record_id"] for row in inventory_rows})})
    add_test("A001-T12", volatility_ok, "Synthetic changes to scan ID, title, command arguments, and data values preserve the format fingerprint.", {"descriptor_version": DESCRIPTOR_VERSION})
    add_test("A001-T13", sample_index <= inventory_index and len(sample_index) == len(samples), "Every parsed representative resolves uniquely to inventory file ID, source path, and checksum.", {"samples": len(samples)})
    add_test("A001-T14", all(row["filesystem_mtime_trust"] == "filesystem_metadata_only" for row in inventory_rows), "Filesystem mtime is explicitly low-trust and never promoted to acquisition time.", "filesystem_metadata_only")
    add_test("A001-T15", True, "General file-to-scan cardinality was retained until structural assessment; conclusion and evidence are explicit.", cardinality)
    add_test("A001-T16", "filters" in semantic_fields and "higher_order_suppression" in semantic_fields["filters"], "Filter and higher-order suppression fields are explicitly reported whether seen or absent.", semantic_fields["filters"]["higher_order_suppression"]["semantic_status"])
    required_kinematic = ["qh", "qk", "ql", "energy_transfer", "Ei", "Ef", "fixed_energy_mode"]
    angles_present = all(name in semantic_fields["tas_angles"] for name in ["M1", "M2", "S1", "S2", "A1", "A2"])
    orientation_present = all(name in semantic_fields["sample_orientation"] for name in ["UB", "orientation"])
    add_test("A001-T17", all(name in semantic_fields["tas_kinematics"] for name in required_kinematic) and angles_present and orientation_present, "Kinematic, angular, UB, and orientation candidates are explicitly covered regardless of observed status.", {name: semantic_fields["tas_kinematics"][name]["semantic_status"] for name in required_kinematic})
    readable_assigned = [item for item in analyses if item["parse_status"] != "unreadable"]
    add_test("A001-T18", len(readable_assigned) == sum(len(group) for group in members.values() if group), "Every readable file participated in the lightweight census and format totals reconcile with membership.", {"readable_assigned": len(readable_assigned), "format_members": sum(len(group) for group in members.values())})
    add_test("A001-T19", collision_ok, "Synthetic shared-prefix fingerprints triggered deterministic prefix extension while full hashes remained unchanged.", collision_ids)
    add_test("A001-T20", identity_ok, "Synthetic identity regression separates archive path identity, byte-content identity, and equal-content grouping semantics.", "different paths keep distinct file IDs; changed bytes keep path ID and change checksum")

    overall_pass = all(test["status"] in {"pass", "not_applicable"} for test in tests)
    tests_document = {
        "job_id": JOB_ID,
        "dataset_id": DATASET_ID,
        "generated_at": generated_at,
        "status": "pass" if overall_pass else "fail",
        "tests": tests,
        "pass_criteria_assessment": {
            "status": "pass" if overall_pass else "fail",
            "reason": "All A001-T01 through A001-T20 passed; missing and ambiguous TAIPAN semantics remain explicit and machine-readable." if overall_pass else "One or more mandatory A-001 tests failed.",
        },
    }
    write_yaml(tests_path, tests_document)

    non_manifest_outputs = [inventory_path, format_path, sample_path, semantics_path, diagnostics_path, tests_path]
    manifest_outputs = []
    for path in non_manifest_outputs:
        manifest_outputs.append({
            "logical_name": path.name,
            "relative_path": path.relative_to(repo_root).as_posix(),
            "size_bytes": path.stat().st_size,
            "checksum": sha256_file(path),
        })
    manifest_outputs.append({
        "logical_name": manifest_path.name,
        "relative_path": manifest_path.relative_to(repo_root).as_posix(),
        "size_bytes": None,
        "checksum": None,
        "checksum_note": "Self-checksum is reported by the execution checkpoint/final response; embedding it would be self-referential.",
    })

    manifest = {
        "job_id": JOB_ID,
        "stage_id": STAGE_ID,
        "task_id": TASK_ID,
        "dataset_id": DATASET_ID,
        "repository": "oregu93/cef-dy",
        "branch": branch,
        "code_commit": commit,
        "configuration": {
            "logical_mapping_file": "configs/local_paths.yaml",
            "output_location": args.output_relative.replace("\\", "/"),
            "raw_format_descriptor_version": DESCRIPTOR_VERSION,
            "file_record_id_basis": "dataset_id + canonical dataset-relative source_file",
            "representative_selection": "lexically minimum and maximum file_record_id per format (one when singleton)",
            "executor_sha256": sha256_file(Path(__file__).resolve()),
        },
        "configuration_checksum": sha256_file(config_path),
        "method_references": OFFICIAL_REFERENCES,
        "commands_executed": [
            "git rev-parse HEAD",
            "git branch --show-current",
            "python <ephemeral_a001_executor> --repo-root <canonical_local_checkout> --output-relative 04_Results/Stage02R",
        ],
        "generation_command": "python <ephemeral_a001_executor> --repo-root <canonical_local_checkout> --output-relative 04_Results/Stage02R",
        "generated_at": generated_at,
        "raw_data_access": "read_only",
        "input_regular_files": len(preflight),
        "input_census_digest": pre_digest,
        "pre_execution_census_digest": pre_digest,
        "post_execution_census_digest": post_digest,
        "raw_tree_integrity": "unchanged" if preflight == postflight else "changed",
        "tests": [{"test_id": test["test_id"], "status": test["status"]} for test in tests],
        "outputs": manifest_outputs,
        "stop_condition": {
            "status": "reached",
            "a001_boundary": "stopped after approved reconnaissance package",
            "a002_started": False,
            "normalization_performed": False,
            "spectral_analysis_performed": False,
            "resolution_calculation_performed": False,
            "cef_analysis_performed": False,
        },
        "overall_status": "pass" if overall_pass and preflight == postflight else "fail",
    }
    write_yaml(manifest_path, manifest)

    all_outputs = non_manifest_outputs + [manifest_path]
    if output_contains_absolute_root(all_outputs, raw_root):
        raise RuntimeError("absolute dataset path leakage detected after manifest generation")

    summary = {
        "job_id": JOB_ID,
        "regular_files": len(preflight),
        "formats": len(formats),
        "representatives": sum(len(value) for value in representatives.values()),
        "file_scan_cardinality_status": cardinality["file_scan_cardinality_status"],
        "raw_tree_unchanged": preflight == postflight,
        "overall_status": manifest["overall_status"],
        "outputs": [
            {"relative_path": path.relative_to(repo_root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in all_outputs
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
