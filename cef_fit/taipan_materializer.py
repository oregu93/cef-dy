"""Deterministic Stage02R-to-user-table bridge; this is not a raw-data parser."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from .polarization_factor import orthorhombic_hkl_to_q_direct
from .provenance import sha256_file


OUTPUT_COLUMNS = (
    "point_id",
    "scan_record_id",
    "raw_scan_id",
    "point_index",
    "energy_meV",
    "Ei_meV",
    "Ef_meV",
    "h_pbnm",
    "k_pbnm",
    "l_pbnm",
    "Q_Ainv",
    "qhat_direct_x",
    "qhat_direct_y",
    "qhat_direct_z",
    "detector_counts",
    "monitor",
    "time",
    "count_control_mode",
    "instrument_config_id",
    "normalization_compatibility_group_id",
    "acquisition_state_id",
    "lattice_state_id",
    "UB_state_id",
    "temperature_status",
    "temperature_K_if_verified",
    "temperature_scan_mean_K",
    "temperature_scan_min_K",
    "temperature_scan_max_K",
    "temperature_source_field",
    "temperature_controller_channel",
    "temperature_unit",
    "discovery_holdout_role",
    "intensity_linear",
    "intensity_units",
    "constraint_class",
    "feature_id",
    "validity_status",
    "mask_status",
    "mask_flags",
    "source_artifact",
    "source_commit",
    # Compatibility aliases consumed by the visible E-Q loader.
    "normalized_intensity",
    "instrument_block_id",
    "scan_id",
    "normalization_metadata",
)


@dataclass(frozen=True)
class MaterializationReport:
    status: str
    output_path: str
    output_sha256: str
    output_rows: int
    source_artifacts: tuple[dict[str, str], ...]
    ten_k_block_status: str
    ten_k_scan_record_ids: tuple[str, ...]
    ten_k_scan_ids_source: str
    ten_k_scan_count: int
    effective_temperature_K: float | None
    discovery_points: int
    holdout_points_used: int
    holdout_detector_access_count: int
    count_control_modes: tuple[str, ...]
    normalization_groups: tuple[str, ...]
    lattice_states: tuple[str, ...]
    ub_states: tuple[str, ...]
    q_direction_unavailable_points: int
    blind_feature_windows: tuple[dict[str, object], ...]
    feature_overlaps: tuple[dict[str, object], ...]
    mandatory_cef_assignments_from_b001: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _resolve(repository: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else repository / path


def load_reuse_config(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("reuse_map_id") != "TAIPAN_PRIOR_ARTIFACT_REUSE_V1":
        raise ValueError("Unexpected TAIPAN reuse-map configuration")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _validated_artifact_paths(
    reuse: Mapping[str, Any], repository: Path
) -> tuple[dict[str, Path], tuple[dict[str, str], ...]]:
    paths: dict[str, Path] = {}
    identities: list[dict[str, str]] = []
    for name, raw in reuse["artifacts"].items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"Artifact entry {name} must be a mapping")
        path = _resolve(repository, str(raw["path"]))
        if not path.exists():
            raise FileNotFoundError(path)
        expected = raw.get("sha256")
        observed = sha256_file(path)
        if expected is not None and str(expected) != observed:
            raise ValueError(f"Stage02R artifact identity mismatch: {name}")
        paths[str(name)] = path
        identities.append(
            {
                "artifact_id": str(name),
                "path": str(path.relative_to(repository)),
                "sha256": observed,
                "classification": str(raw["classification"]),
            }
        )
    return paths, tuple(identities)


def _feature_windows(catalogue_path: Path) -> tuple[dict[str, object], ...]:
    payload = yaml.safe_load(catalogue_path.read_text(encoding="utf-8"))
    windows = []
    for feature in payload["features"]:
        lower, upper = map(float, feature["discovery_energy_interval"])
        windows.append(
            {
                "feature_id": str(feature["blind_feature_id"]),
                "energy_min_meV": lower,
                "energy_max_meV": upper,
                "count_control_mode": str(feature["count_control_mode"]),
                "role": "DISCOVERY_FEATURE_WINDOW__NOT_MANDATORY_CEF_LEVEL",
            }
        )
    return tuple(windows)


def _overlaps(windows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for index, left in enumerate(windows):
        for right in windows[index + 1 :]:
            lower = max(float(left["energy_min_meV"]), float(right["energy_min_meV"]))
            upper = min(float(left["energy_max_meV"]), float(right["energy_max_meV"]))
            if lower <= upper:
                result.append(
                    {
                        "feature_ids": [left["feature_id"], right["feature_id"]],
                        "overlap_energy_min_meV": lower,
                        "overlap_energy_max_meV": upper,
                    }
                )
    return tuple(result)


def _feature_ids(
    energy_meV: float,
    count_control_mode: str,
    windows: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    return tuple(
        str(window["feature_id"])
        for window in windows
        if str(window["count_control_mode"]) == count_control_mode
        and float(window["energy_min_meV"]) <= energy_meV <= float(window["energy_max_meV"])
    )


def _atomic_write_csv(destination: Path, rows: list[dict[str, object]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _temperature_rows(
    reuse: Mapping[str, Any], repository: Path
) -> tuple[dict[str, dict[str, str]], tuple[str, ...], float]:
    """Load and verify the accepted scan-temperature mapping and 10-K rule."""

    temperature = reuse["temperature_mapping"]
    mapping_path = _resolve(repository, str(temperature["mapping_csv"]))
    summary_path = _resolve(repository, str(temperature["summary_yaml"]))
    if sha256_file(mapping_path) != str(temperature["mapping_csv_sha256"]):
        raise ValueError("Accepted temperature mapping CSV identity mismatch")
    if sha256_file(summary_path) != str(temperature["summary_yaml_sha256"]):
        raise ValueError("Accepted temperature mapping summary identity mismatch")
    rows = {row["scan_record_id"]: row for row in _read_csv(mapping_path)}
    summary = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
    summary_ids = tuple(map(str, summary["classification"]["ten_K"]["scan_record_ids"]))
    configured_ids = tuple(map(str, temperature["ten_k_scan_record_ids"]))
    if configured_ids != summary_ids:
        raise ValueError("Configured and accepted-summary 10-K scan identities differ")
    mean_bounds = tuple(map(float, temperature["accepted_scan_mean_K"]))
    maximum_range = float(temperature["accepted_maximum_within_scan_range_K"])
    accepted: list[str] = []
    for scan_id in configured_ids:
        row = rows[scan_id]
        mean = float(row["temperature_K"])
        observed_range = float(row["temperature_max_K"]) - float(row["temperature_min_K"])
        if mean_bounds[0] <= mean <= mean_bounds[1] and observed_range <= maximum_range:
            accepted.append(scan_id)
    if tuple(accepted) != configured_ids or len(accepted) != 20:
        raise ValueError("Accepted 10-K operational rule did not reproduce exactly 20 scans")
    effective = float(temperature["effective_temperature_K"])
    if abs(effective - float(summary["classification"]["ten_K"]["mean_of_scan_means_K"])) > 5e-7:
        raise ValueError("Configured effective temperature disagrees with accepted summary")
    return rows, configured_ids, effective


def materialize_taipan_eq_dataset(
    reuse_config_path: str | Path,
    repository: str | Path,
    output_path: str | Path | None = None,
) -> MaterializationReport:
    """Build the long-form discovery-only bridge from reviewed Stage02R layers.

    Detector values come from B001's already decoded discovery representation.
    A002 is used only for acquisition quantities and is never queried for a
    holdout detector value.
    """

    repository_path = Path(repository).resolve()
    reuse = load_reuse_config(reuse_config_path)
    paths, identities = _validated_artifact_paths(reuse, repository_path)
    materialization = reuse["materialization"]
    destination = _resolve(
        repository_path,
        str(output_path or materialization["output"]),
    )

    inventory = {
        row["scan_record_id"]: row
        for row in _read_csv(paths["a002_scan_inventory"])
    }
    classifications = {
        row["scan_record_id"]: row
        for row in _read_csv(paths["a003_scan_classification"])
    }
    split = {
        row["scan_record_id"]: row
        for row in _read_csv(paths["b001_blind_split"])
    }
    discovery_rows = _read_csv(paths["b001_discovery_points"])
    if any(row["split_role"] != "discovery" for row in discovery_rows):
        raise ValueError("B001 discovery representation contains a non-discovery row")
    if any(split[row["scan_record_id"]]["split_role"] != "discovery" for row in discovery_rows):
        raise ValueError("B001 discovery representation disagrees with the sealed blind split")
    discovery_keys = {
        (row["scan_record_id"], int(row["point_index"])) for row in discovery_rows
    }
    if len(discovery_keys) != len(discovery_rows):
        raise ValueError("B001 discovery point keys must be unique")

    # Only acquisition fields are retained here. detector_raw is deliberately
    # not read into the lookup, keeping holdout detector access at exactly zero.
    acquisition: dict[tuple[str, int], dict[str, str]] = {}
    with paths["a002_scan_points"].open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["scan_record_id"], int(row["point_index"]))
            if key not in discovery_keys:
                continue
            acquisition[key] = {
                name: row[name]
                for name in (
                    "scan_record_id",
                    "point_index",
                    "e_raw",
                    "ei_raw",
                    "ef_raw",
                    "h_raw",
                    "k_raw",
                    "l_raw",
                )
            }
    if set(acquisition) != discovery_keys:
        raise ValueError("A002 is missing B001 discovery point keys")

    lattices = yaml.safe_load(paths["a002_lattice_states"].read_text(encoding="utf-8"))
    windows = _feature_windows(paths["b001_feature_catalogue"])
    overlaps = _overlaps(windows)
    diagnostic_features = {str(value) for value in materialization["diagnostic_mixed_feature_ids"]}
    temperature = reuse["temperature_mapping"]
    temperature_status = str(temperature["ten_k_block_status"])
    temperature_by_scan, selected_ten_k_scans, effective_temperature = _temperature_rows(
        reuse, repository_path
    )
    temperature_identities = (
        {
            "artifact_id": "taipan_temperature_mapping_v1",
            "path": str(temperature["mapping_csv"]),
            "sha256": str(temperature["mapping_csv_sha256"]),
            "classification": "REUSE_DIRECTLY",
        },
        {
            "artifact_id": "taipan_temperature_mapping_v1_summary",
            "path": str(temperature["summary_yaml"]),
            "sha256": str(temperature["summary_yaml_sha256"]),
            "classification": "REUSE_DIRECTLY",
        },
    )
    if temperature_status in {"VERIFIED", "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"} and not selected_ten_k_scans:
        raise ValueError("Established 10-K status requires explicit scan_record_ids")
    if temperature_status not in {"VERIFIED", "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"}:
        raise ValueError("Primary materializer requires the accepted 10-K mapping")
    if temperature_status == "NOT_YET_ESTABLISHED" and selected_ten_k_scans:
        raise ValueError("Unestablished 10-K status cannot contain scan_record_ids")
    selected_set = set(selected_ten_k_scans)

    output_rows: list[dict[str, object]] = []
    q_unavailable = 0
    for discovery in discovery_rows:
        scan = discovery["scan_record_id"]
        if selected_set and scan not in selected_set:
            continue
        classification = classifications[scan]
        if classification["count_control_mode"] != "monitor_controlled":
            continue
        key = (scan, int(discovery["point_index"]))
        point = acquisition[key]
        energy = float(point["e_raw"])
        hkl = [float(point["h_raw"]), float(point["k_raw"]), float(point["l_raw"])]
        lattice_id = classification["lattice_state_id"]
        lattice = lattices[lattice_id]
        features = _feature_ids(energy, classification["count_control_mode"], windows)
        flags: list[str] = []
        validity = "VALID"
        try:
            q_ainv, qhat = orthorhombic_hkl_to_q_direct(
                hkl,
                [float(lattice["a_A"]), float(lattice["b_A"]), float(lattice["c_A"])],
            )
        except ValueError:
            q_ainv, qhat = float("nan"), [float("nan")] * 3
            validity = "INVALID_Q_DIRECTION"
            flags.append("Q_DIRECTION_UNAVAILABLE__NO_POWDER_FALLBACK")
            q_unavailable += 1
        if temperature_status == "NOT_YET_ESTABLISHED":
            flags.append("TEMPERATURE_BLOCK_UNRESOLVED")
        if diagnostic_features.intersection(features):
            flags.append("DIAGNOSTIC_OR_POSSIBLY_MIXED_44_MEV_REGION")
        monitor = float(discovery["monitor_counts"])
        detector = float(discovery["detector_counts"])
        if not (monitor > 0.0):
            flags.append("INVALID_MONITOR")
            validity = "INVALID_NORMALIZATION"
            intensity = float("nan")
        else:
            intensity = detector / monitor * float(materialization["intensity_multiplier"])
        if validity != "VALID":
            mask_status = "EXCLUDE_INVALID_GEOMETRY_OR_NORMALIZATION"
        elif temperature_status == "NOT_YET_ESTABLISHED":
            mask_status = "EXCLUDE_TEMPERATURE_BLOCK_UNRESOLVED"
        elif diagnostic_features.intersection(features):
            mask_status = "EXCLUDE_DIAGNOSTIC_OR_POSSIBLY_MIXED"
        else:
            mask_status = "INCLUDE"
        constraint = (
            "SPECTRAL_SHAPE_CONSTRAINT"
            if features
            else "EXPLORATORY_RELATIVE_INTENSITY_CONSTRAINT"
        )
        source_commits = reuse["source_commits"]
        source_commit = ";".join(
            [
                str(source_commits["A002"]),
                str(source_commits["A003"]),
                str(source_commits["B001"]),
                str(source_commits["temperature_mapping"]),
            ]
        )
        normalization_group = classification["normalization_compatibility_group_id"]
        instrument_block = f"{classification['instrument_config_id']}__{normalization_group}"
        scan_temperature = temperature_by_scan[scan]
        output_rows.append(
            {
                "point_id": f"{scan}:{int(discovery['point_index'])}",
                "scan_record_id": scan,
                "raw_scan_id": inventory[scan]["raw_scan_id"],
                "point_index": int(discovery["point_index"]),
                "energy_meV": format(energy, ".15g"),
                "Ei_meV": point["ei_raw"],
                "Ef_meV": point["ef_raw"],
                "h_pbnm": point["h_raw"],
                "k_pbnm": point["k_raw"],
                "l_pbnm": point["l_raw"],
                "Q_Ainv": format(q_ainv, ".15g"),
                "qhat_direct_x": format(float(qhat[0]), ".15g"),
                "qhat_direct_y": format(float(qhat[1]), ".15g"),
                "qhat_direct_z": format(float(qhat[2]), ".15g"),
                "detector_counts": format(detector, ".15g"),
                "monitor": format(monitor, ".15g"),
                "time": discovery["time_exposure"],
                "count_control_mode": classification["count_control_mode"],
                "instrument_config_id": classification["instrument_config_id"],
                "normalization_compatibility_group_id": normalization_group,
                "acquisition_state_id": classification["acquisition_state_id"],
                "lattice_state_id": lattice_id,
                "UB_state_id": classification["UB_state_id"],
                "temperature_status": temperature_status,
                "temperature_K_if_verified": (
                    format(float(scan_temperature["temperature_K"]), ".15g")
                    if selected_set
                    else ""
                ),
                "temperature_scan_mean_K": scan_temperature["temperature_K"],
                "temperature_scan_min_K": scan_temperature["temperature_min_K"],
                "temperature_scan_max_K": scan_temperature["temperature_max_K"],
                "temperature_source_field": scan_temperature["temperature_source_field"],
                "temperature_controller_channel": scan_temperature[
                    "temperature_controller_channel"
                ],
                "temperature_unit": scan_temperature["temperature_unit"],
                "discovery_holdout_role": "discovery",
                "intensity_linear": format(intensity, ".15g"),
                "intensity_units": materialization["intensity_units"],
                "constraint_class": constraint,
                "feature_id": ";".join(features),
                "validity_status": validity,
                "mask_status": mask_status,
                "mask_flags": ";".join(flags) if flags else "NONE",
                "source_artifact": materialization["source_artifact_label"],
                "source_commit": source_commit,
                "normalized_intensity": format(intensity, ".15g"),
                "instrument_block_id": instrument_block,
                "scan_id": inventory[scan]["raw_scan_id"],
                "normalization_metadata": (
                    f"detector_counts/monitor*{float(materialization['intensity_multiplier']):g};"
                    f"{normalization_group};EXPLORATORY_RELATIVE_INTENSITY"
                ),
            }
        )

    output_rows.sort(key=lambda row: (int(str(row["raw_scan_id"])), int(row["point_index"])))
    _atomic_write_csv(destination, output_rows)
    if not output_rows:
        status = "MATERIALIZED_EMPTY__NO_SELECTED_DISCOVERY_POINTS"
    elif temperature_status == "NOT_YET_ESTABLISHED":
        status = "MATERIALIZED_DISCOVERY_ONLY__TEMPERATURE_UNRESOLVED"
    else:
        status = "MATERIALIZED_10_K_DISCOVERY_ONLY"
    groups = tuple(sorted({str(row["normalization_compatibility_group_id"]) for row in output_rows}))
    modes = tuple(sorted({str(row["count_control_mode"]) for row in output_rows}))
    lattice_ids = tuple(sorted({str(row["lattice_state_id"]) for row in output_rows}))
    ub_ids = tuple(sorted({str(row["UB_state_id"]) for row in output_rows}))
    report = MaterializationReport(
        status=status,
        output_path=str(destination),
        output_sha256=sha256_file(destination),
        output_rows=len(output_rows),
        source_artifacts=identities + temperature_identities,
        ten_k_block_status=temperature_status,
        ten_k_scan_record_ids=selected_ten_k_scans,
        ten_k_scan_ids_source=str(temperature["ten_k_scan_ids_source"]),
        ten_k_scan_count=len(selected_ten_k_scans),
        effective_temperature_K=effective_temperature,
        discovery_points=len(output_rows),
        holdout_points_used=0,
        holdout_detector_access_count=0,
        count_control_modes=modes,
        normalization_groups=groups,
        lattice_states=lattice_ids,
        ub_states=ub_ids,
        q_direction_unavailable_points=q_unavailable,
        blind_feature_windows=windows,
        feature_overlaps=overlaps,
        mandatory_cef_assignments_from_b001=(),
    )
    return report
