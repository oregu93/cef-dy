#!/usr/bin/env python3
"""Build the metadata-only TAIPAN experiment 1296 temperature mapping."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import math
import re
import statistics
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "taipan_temperature_mapping_v1"
MAPPING_STATUS = "RECONSTRUCTED_WITH_EXPLICIT_LIMITATION"
PRIORITY_RAW_IDS = (104095, 104098, 104099, 104215, 104225)
ALLOWED_POINT_FIELDS = {
    "ptsamp",
    "tfloat",
    "temp",
    "t1_sensor1",
    "t1_sensor2",
    "t1_sensor3",
    "t1_sensor4",
    "t1_setpoint1",
    "t1_setpoint2",
    "t1_setpoint3",
    "t1_setpoint4",
}
OUTPUT_COLUMNS = (
    "scan_record_id",
    "raw_scan_id",
    "temperature_K",
    "temperature_min_K",
    "temperature_max_K",
    "temperature_source_field",
    "temperature_controller_channel",
    "temperature_unit",
    "temperature_status",
    "source_artifact",
    "source_checksum",
)
MANUAL_URL = "https://www.ansto.gov.au/media/1429/download?inline="
MANUAL_SHA256 = "dfd8c60e6da82dedc0b86d39b3985c08333d237f3af7ac63d95630691c977579"
TAIPAN_SCRIPTS_COMMIT = "43ebed46af51167c9439358af2b350d951b76e79"
TAIPAN_SOURCE_HASHES = {
    "Experiment/lib/export.py": "aecd9059aead28aebb37eeccff69d91696d465954f6e9bfa2504e9c8eda01cd7",
    "Experiment/config.py": "57f9eda766eb50e085e32dd2c71687880bffe7d9ec64ed3a6a4bc03ff16d7b8a",
    "Experiment/path_table": "207ed6548acbbede977f028c0755f5f0afdd6a9f8722a862c0f0482935626fc8",
    "New_scripts/Martin/2023/August/dfo03.tcl": "2a9176a30a6674b152c65b81dbfaca1c9a52cccf9c8de1d6048d59a4036ae0bc",
    "New_scripts/Martin/2023/August/dfo09.tcl": "726a7f602f5cf5d1bac74179a446ec50e49a5e80c87bd7dffcb39219cdce17d6",
    "New_scripts/Martin/2023/August/dfo10.tcl": "18e98e7de7d392d385e8870ebfe8555f6aeabafc7ab4664cc80170ffed5febc1",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", value.lower())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_whitelisted_temperature_fields(path: Path) -> dict[str, list[float]]:
    """Read only explicitly permitted sample-environment values from a raw ASCII file."""
    declaration: list[str] | None = None
    selected: dict[str, int] = {}
    values: dict[str, list[float]] = {}
    in_data = False

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not in_data:
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    candidate = [normalize_field(item) for item in stripped[1:].split()]
                    if ALLOWED_POINT_FIELDS.intersection(candidate):
                        declaration = candidate
                    continue
                if declaration is None:
                    raise ValueError(f"{path}: no temperature-bearing column declaration")
                selected = {
                    name: index
                    for index, name in enumerate(declaration)
                    if name in ALLOWED_POINT_FIELDS
                }
                missing = ALLOWED_POINT_FIELDS.difference(selected)
                if missing:
                    raise ValueError(f"{path}: missing permitted fields {sorted(missing)}")
                values = {name: [] for name in selected}
                in_data = True

            if not stripped:
                continue
            if stripped.startswith("#"):
                raise ValueError(f"{path}:{line_number}: unexpected second comment block")
            tokens = stripped.split()
            if len(tokens) != len(declaration):
                raise ValueError(
                    f"{path}:{line_number}: row width {len(tokens)} != {len(declaration)}"
                )
            for name, index in selected.items():
                value = float(tokens[index])
                if not math.isfinite(value):
                    raise ValueError(f"{path}:{line_number}: non-finite {name}")
                values[name].append(value)

    if not values or not values["t1_sensor1"]:
        raise ValueError(f"{path}: no sample-environment points")
    return values


def stats(values: list[float]) -> dict[str, float | int]:
    return {
        "points": len(values),
        "mean_K": round(statistics.fmean(values), 6),
        "median_K": round(statistics.median(values), 6),
        "minimum_K": round(min(values), 4),
        "maximum_K": round(max(values), 4),
        "point_to_point_range_K": round(max(values) - min(values), 4),
    }


def scalar_setpoint(values: list[float]) -> float | None:
    unique = sorted(set(values))
    return unique[0] if len(unique) == 1 else None


def load_discovery_records(
    repo_root: Path, raw_root: Path
) -> tuple[list[dict[str, Any]], dict[str, str], float]:
    selection_path = repo_root / "04_Results/Stage02R/W02-02R-B-001/scan_selection.csv"
    inventory_path = repo_root / "04_Results/Stage02R/W02-02R-A-002/scan_inventory.csv"
    selection = [
        row for row in read_csv(selection_path) if row["split_role"] == "discovery"
    ]
    inventory = {int(row["raw_scan_id"]): row for row in read_csv(inventory_path)}

    if len(selection) != 57:
        raise ValueError(f"expected 57 B001 discovery scans, found {len(selection)}")

    records: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, int]] = set()
    max_temp_sensor_delta = 0.0

    for selected_row in selection:
        raw_scan_id = int(selected_row["raw_scan_id"])
        scan_record_id = selected_row["scan_record_id"]
        pair = (scan_record_id, raw_scan_id)
        if pair in seen_pairs:
            raise ValueError(f"duplicate discovery identity {pair}")
        seen_pairs.add(pair)

        inventory_row = inventory.get(raw_scan_id)
        if inventory_row is None:
            raise ValueError(f"raw scan {raw_scan_id} absent from A002 inventory")
        if inventory_row["scan_record_id"] != scan_record_id:
            raise ValueError(f"identity mismatch for raw scan {raw_scan_id}")

        source_file = inventory_row["source_file"]
        source_path = raw_root / source_file
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source_checksum = sha256_file(source_path)
        if source_checksum != inventory_row["source_checksum"]:
            raise ValueError(f"source checksum mismatch for {source_file}")

        channels = read_whitelisted_temperature_fields(source_path)
        lengths = {len(value) for value in channels.values()}
        if len(lengths) != 1:
            raise ValueError(f"sample-environment column length mismatch in {source_file}")

        temp_sensor_delta = max(
            abs(a - b) for a, b in zip(channels["temp"], channels["t1_sensor1"])
        )
        max_temp_sensor_delta = max(max_temp_sensor_delta, temp_sensor_delta)
        if temp_sensor_delta > 0.00051:
            raise ValueError(f"temp/T1_Sensor1 mismatch in {source_file}")
        if channels["tfloat"] != channels["t1_sensor3"]:
            raise ValueError(f"tfloat/T1_Sensor3 mismatch in {source_file}")
        if any(value != 0.0 for value in channels["t1_sensor2"]):
            raise ValueError(f"active T1_Sensor2 unexpectedly present in {source_file}")
        if any(value != 0.0 for value in channels["t1_sensor4"]):
            raise ValueError(f"active T1_Sensor4 unexpectedly present in {source_file}")

        sensor_stats = stats(channels["t1_sensor1"])
        records.append(
            {
                "scan_record_id": scan_record_id,
                "raw_scan_id": raw_scan_id,
                "source_file": source_file,
                "source_checksum": source_checksum,
                "discovery_runtime_status": selected_row["discovery_runtime_status"],
                "stats": sensor_stats,
                "setpoint1_K": scalar_setpoint(channels["t1_setpoint1"]),
                "setpoint2_K": scalar_setpoint(channels["t1_setpoint2"]),
            }
        )

    records.sort(key=lambda row: row["raw_scan_id"])
    source_hashes = {
        str(selection_path.relative_to(repo_root)): sha256_file(selection_path),
        str(inventory_path.relative_to(repo_root)): sha256_file(inventory_path),
    }
    return records, source_hashes, max_temp_sensor_delta


def classify_temperature_blocks(
    records: list[dict[str, Any]]
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, float],
]:
    means = sorted(float(row["stats"]["mean_K"]) for row in records)
    gaps = [(right - left, left, right) for left, right in zip(means, means[1:])]
    ranked = sorted(gaps, reverse=True)
    if len(ranked) < 3 or ranked[1][0] <= 5.0 * ranked[2][0]:
        raise ValueError("temperature values do not contain three separated blocks")
    separators = sorted(ranked[:2], key=lambda item: item[1])
    low_other_gap, low_upper, other_lower = separators[0]
    other_ten_gap, other_upper, ten_lower = separators[1]
    low_other_boundary = (low_upper + other_lower) / 2.0
    other_ten_boundary = (other_upper + ten_lower) / 2.0

    low = [
        row for row in records if row["stats"]["mean_K"] < low_other_boundary
    ]
    other = [
        row
        for row in records
        if low_other_boundary
        <= row["stats"]["mean_K"]
        < other_ten_boundary
    ]
    ten = [
        row for row in records if row["stats"]["mean_K"] >= other_ten_boundary
    ]
    if not low or not other or not ten:
        raise ValueError("expected low, intermediate, and 10 K value clusters")
    if not all(8.0 <= row["stats"]["mean_K"] <= 12.0 for row in ten):
        raise ValueError("upper cluster is not a 10 K cluster")
    return low, ten, other, {
        "low_other_gap_K": low_other_gap,
        "low_other_boundary_K": low_other_boundary,
        "other_ten_gap_K": other_ten_gap,
        "other_ten_boundary_K": other_ten_boundary,
        "next_largest_gap_K": ranked[2][0],
        "second_to_third_gap_ratio": ranked[1][0] / ranked[2][0],
    }


def cluster_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    means = [float(row["stats"]["mean_K"]) for row in records]
    medians = [float(row["stats"]["median_K"]) for row in records]
    ranges = [float(row["stats"]["point_to_point_range_K"]) for row in records]
    return {
        "scan_count": len(records),
        "scan_mean_temperature_min_K": round(min(means), 6),
        "scan_mean_temperature_max_K": round(max(means), 6),
        "mean_of_scan_means_K": round(statistics.fmean(means), 6),
        "median_of_scan_medians_K": round(statistics.median(medians), 6),
        "maximum_within_scan_point_to_point_range_K": round(max(ranges), 4),
        "scan_record_ids": [row["scan_record_id"] for row in records],
        "raw_scan_ids": [row["raw_scan_id"] for row in records],
    }


def csv_bytes(records: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        summary = record["stats"]
        writer.writerow(
            {
                "scan_record_id": record["scan_record_id"],
                "raw_scan_id": record["raw_scan_id"],
                "temperature_K": f"{summary['mean_K']:.6f}",
                "temperature_min_K": f"{summary['minimum_K']:.4f}",
                "temperature_max_K": f"{summary['maximum_K']:.4f}",
                "temperature_source_field": "T1_Sensor1",
                "temperature_controller_channel": "T1 channel A (reconstructed)",
                "temperature_unit": "K",
                "temperature_status": MAPPING_STATUS,
                "source_artifact": record["source_file"],
                "source_checksum": record["source_checksum"],
            }
        )
    return stream.getvalue().encode("utf-8")


def summary_document(
    repo_root: Path,
    raw_root: Path,
    records: list[dict[str, Any]],
    source_hashes: dict[str, str],
    low: list[dict[str, Any]],
    ten: list[dict[str, Any]],
    other: list[dict[str, Any]],
    boundaries: dict[str, float],
    mapping_csv_sha256: str,
    max_temp_sensor_delta: float,
) -> dict[str, Any]:
    by_raw = {row["raw_scan_id"]: row for row in records}
    priority = {}
    for raw_scan_id in PRIORITY_RAW_IDS:
        record = by_raw[raw_scan_id]
        setpoint_note = (
            "Both exported setpoints are 10 K and agree with the measured block."
            if raw_scan_id in (104215, 104225)
            else (
                "Both exported setpoints are 300 K and are stale or inactive for this scan; "
                "they are reported but not used as the physical sample temperature."
            )
        )
        priority[str(raw_scan_id)] = {
            "scan_record_id": record["scan_record_id"],
            "source_field": "T1_Sensor1",
            "controller_channel": "T1 channel A (reconstructed)",
            "unit": "K",
            **record["stats"],
            "setpoint1_K": record["setpoint1_K"],
            "setpoint2_K": record["setpoint2_K"],
            "status": MAPPING_STATUS,
            "limitation": (
                "The exact experiment-1296 configSICS hardware selection was not recovered; "
                "the T1 channel-A mapping is reconstructed from official export/schema code, "
                f"the experiment scripts, and pointwise cross-checks. {setpoint_note}"
            ),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_on": "2026-10-21",
        "temperature_mapping_status": MAPPING_STATUS,
        "sample_environment_status": MAPPING_STATUS,
        "sample_environment": (
            "tc1/T1 cryostat and sample-stick configuration; exact configSICS hardware "
            "profile unresolved"
        ),
        "controller_status": "T1_controller_verified_hardware_model_unresolved",
        "sample_temperature_channel": "T1 channel A",
        "exported_column": "T1_Sensor1",
        "exported_column_mapping_status": MAPPING_STATUS,
        "exported_column_mapping": {
            "T1_Sensor1": {
                "controller_channel": "A",
                "role": "physical sample temperature",
                "status": MAPPING_STATUS,
            },
            "T1_Sensor2": {
                "controller_channel": "B",
                "role": "inactive_zero_in_all_discovery_scans",
                "status": "ROLE_UNRESOLVED",
            },
            "T1_Sensor3": {
                "controller_channel": "C",
                "role": "auxiliary_tfloat_temperature",
                "status": MAPPING_STATUS,
            },
            "T1_Sensor4": {
                "controller_channel": "D",
                "role": "inactive_zero_in_all_discovery_scans",
                "status": "ROLE_UNRESOLVED",
            },
            "T1_Setpoint1": {
                "controller_loop": 1,
                "experiment_script_role": "cryostat temperature",
                "status": MAPPING_STATUS,
            },
            "T1_Setpoint2": {
                "controller_loop": 2,
                "experiment_script_role": "sample-stick temperature",
                "status": MAPPING_STATUS,
            },
        },
        "unit": "K",
        "limitation": (
            "No experiment-1296 configSICS snapshot or controller hardware log was found. "
            "The mapping is therefore not promoted to fully verified hardware provenance."
        ),
        "evidence": {
            "manual": {
                "title": "TAIPAN User Manual v14",
                "date": "2017-02-20",
                "url": MANUAL_URL,
                "sha256": MANUAL_SHA256,
                "semantics": [
                    "Gumtree writes configured sample-environment temperature to exported .dat files.",
                    "For the ordinary CF1/tc1 setup, tc1_driveable2 reads sample channel A.",
                    "Temperature-controller values are in K.",
                ],
            },
            "official_taipan_scripts": {
                "repository": "https://github.com/Gumtree/Taipan_scripts",
                "commit": TAIPAN_SCRIPTS_COMMIT,
                "files_sha256": TAIPAN_SOURCE_HASHES,
                "semantics": [
                    "Experiment/path_table maps tc1 sensor A-D and controller-loop values to NeXus paths.",
                    "Experiment/config.py maps temp to ctrlLp1_value and tfloat to sensorValueC.",
                    "Experiment/lib/export.py emits sample-target NeXus items and converts T1S1 to T1_Sensor1.",
                    "dfo03.tcl labels setpoint1 as cryostat temperature and setpoint2 as sample-stick temperature.",
                    "dfo09.tcl and dfo10.tcl identify the corresponding experiment sequence as T=10 K.",
                ],
            },
            "pointwise_cross_checks": {
                "all_57_discovery_scans": True,
                "temp_matches_T1_Sensor1_within_K": 0.00051,
                "maximum_observed_abs_difference_K": round(max_temp_sensor_delta, 7),
                "tfloat_equals_T1_Sensor3_exactly": True,
                "T1_Sensor2_all_zero": True,
                "T1_Sensor4_all_zero": True,
            },
        },
        "canonical_sources": {
            "repository": "https://github.com/oregu93/cef-dy",
            "repository_relative_source_paths": True,
            "raw_source_locator": (
                "operator-supplied directory; filenames and SHA-256 values are fixed by "
                "A002 scan_inventory.csv"
            ),
            "source_hashes": source_hashes,
            "mapping_csv_sha256": mapping_csv_sha256,
        },
        "counts": {
            "B001_discovery_scans": len(records),
            "temperature_mapped": len(records),
            "unresolved": 0,
            "holdout_detector_access_count": 0,
        },
        "priority_scans": priority,
        "classification": {
            "basis": (
                "two dominant adjacent gaps in sorted T1_Sensor1 scan means; "
                "the smaller separator exceeds five times the next-largest gap; "
                "no scan chronology used"
            ),
            "low_other_boundary_K": round(boundaries["low_other_boundary_K"], 6),
            "low_other_gap_K": round(boundaries["low_other_gap_K"], 6),
            "other_ten_boundary_K": round(boundaries["other_ten_boundary_K"], 6),
            "other_ten_gap_K": round(boundaries["other_ten_gap_K"], 6),
            "next_largest_within_cluster_gap_K": round(
                boundaries["next_largest_gap_K"], 6
            ),
            "second_to_third_gap_ratio": round(
                boundaries["second_to_third_gap_ratio"], 3
            ),
            "ten_K": {
                "status": MAPPING_STATUS,
                **cluster_summary(ten),
            },
            "low_temperature": {
                "status": MAPPING_STATUS,
                **cluster_summary(low),
            },
            "other_temperature": {
                "status": MAPPING_STATUS,
                **cluster_summary(other),
            },
        },
        "stability": {
            "observed_ten_K_scan_mean_range_K": [
                round(min(row["stats"]["mean_K"] for row in ten), 6),
                round(max(row["stats"]["mean_K"] for row in ten), 6),
            ],
            "observed_ten_K_maximum_within_scan_range_K": round(
                max(row["stats"]["point_to_point_range_K"] for row in ten), 4
            ),
            "proposed_review_tolerance": {
                "scan_mean_K": [9.95, 10.05],
                "maximum_within_scan_range_K": 0.05,
                "basis": (
                    "Rounded envelope wider than the observed scan-mean deviations and "
                    "the observed maximum within-scan range; requires Project Control acceptance."
                ),
                "current_ten_K_scans_passing": len(ten),
            },
        },
        "safety_boundaries": {
            "detector_fields_read": False,
            "detector_reanalysis_performed": False,
            "spectral_fit_performed": False,
            "cef_analysis_performed": False,
            "holdout_detector_access_count": 0,
        },
    }


def fmt(value: float, places: int = 6) -> str:
    return f"{value:.{places}f}"


def review_bytes(
    records: list[dict[str, Any]],
    low: list[dict[str, Any]],
    ten: list[dict[str, Any]],
    other: list[dict[str, Any]],
    boundaries: dict[str, float],
    mapping_csv_sha256: str,
    summary_sha256: str,
) -> bytes:
    by_raw = {row["raw_scan_id"]: row for row in records}
    priority_lines = []
    for raw_scan_id in PRIORITY_RAW_IDS:
        record = by_raw[raw_scan_id]
        item = record["stats"]
        priority_lines.append(
            "| {raw} | {scan} | {mean} | {median} | {minimum} | {maximum} | {spread} | "
            "{sp1} / {sp2} |".format(
                raw=raw_scan_id,
                scan=record["scan_record_id"],
                mean=fmt(item["mean_K"]),
                median=fmt(item["median_K"]),
                minimum=fmt(item["minimum_K"], 4),
                maximum=fmt(item["maximum_K"], 4),
                spread=fmt(item["point_to_point_range_K"], 4),
                sp1=fmt(record["setpoint1_K"], 1),
                sp2=fmt(record["setpoint2_K"], 1),
            )
        )

    ten_summary = cluster_summary(ten)
    low_summary = cluster_summary(low)
    other_summary = cluster_summary(other)
    text = f"""# Восстановление температурного соответствия TAIPAN

## Решение

Для всех 57 discovery scans B001 восстановлена однозначная связь с температурой образца. Принято поле
T1_Sensor1 в K, соответствующее каналу A контроллера T1. Статус результата:
RECONSTRUCTED_WITH_EXPLICIT_LIMITATION. Ограничение состоит в том, что отдельный снимок configSICS или
аппаратный журнал эксперимента 1296 не найден; поэтому конкретная модель контроллера и выбранная аппаратная
конфигурация не объявляются полностью проверенными.

Машиночитаемые результаты находятся в [таблице температур](taipan_temperature_mapping_v1.csv) и
[сводке доказательств](taipan_temperature_mapping_v1_summary.yaml). SHA-256 таблицы:
{mapping_csv_sha256}. SHA-256 сводки: {summary_sha256}.

## Основание для соответствия канала

Официальное [руководство TAIPAN v14]({MANUAL_URL}) с SHA-256 {MANUAL_SHA256} указывает, что после настройки
sample environment Gumtree переносит температуру в экспортируемые .dat-файлы; для обычной схемы CF1/tc1
физическая температура образца читается из канала A, единицы — K.

В официальном репозитории [Gumtree/Taipan_scripts](https://github.com/Gumtree/Taipan_scripts/tree/{TAIPAN_SCRIPTS_COMMIT})
зафиксированы дополнительные семантические связи:

- [path_table](https://github.com/Gumtree/Taipan_scripts/blob/{TAIPAN_SCRIPTS_COMMIT}/Experiment/path_table)
  связывает sensorValueA-D, TSample и значения контуров управления с NeXus;
- [config.py](https://github.com/Gumtree/Taipan_scripts/blob/{TAIPAN_SCRIPTS_COMMIT}/Experiment/config.py)
  задаёт temp как ctrlLp1_value и tfloat как sensorValueC;
- [export.py](https://github.com/Gumtree/Taipan_scripts/blob/{TAIPAN_SCRIPTS_COMMIT}/Experiment/lib/export.py)
  экспортирует sample-target поля и преобразует T1S1 в T1_Sensor1;
- экспериментальный [dfo03.tcl](https://github.com/Gumtree/Taipan_scripts/blob/{TAIPAN_SCRIPTS_COMMIT}/New_scripts/Martin/2023/August/dfo03.tcl)
  отдельно называет setpoint1 температурой криостата, а setpoint2 температурой sample stick;
- [dfo09.tcl](https://github.com/Gumtree/Taipan_scripts/blob/{TAIPAN_SCRIPTS_COMMIT}/New_scripts/Martin/2023/August/dfo09.tcl)
  и [dfo10.tcl](https://github.com/Gumtree/Taipan_scripts/blob/{TAIPAN_SCRIPTS_COMMIT}/New_scripts/Martin/2023/August/dfo10.tcl)
  маркируют соответствующую серию эксперимента как T=10 K.

Во всех 57 discovery scans поле temp совпадает с T1_Sensor1 с максимальным расхождением 0.0005 K,
обусловленным разной точностью печати. tfloat во всех точках точно совпадает с T1_Sensor3, а T1_Sensor2 и
T1_Sensor4 равны нулю. Это независимая внутренняя проверка экспортной схемы; выбор канала не основан на том,
что значения близки к 3.5 или 10 K.

## Приоритетные CX-02 scans

Источник температуры для каждой строки: T1_Sensor1, T1 channel A (reconstructed), K.

| raw_scan_id | scan_record_id | mean K | median K | min K | max K | range K | setpoint1 / setpoint2 K |
|---:|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(priority_lines)}

Сканы 104095, 104098 и 104099 принадлежат отдельному промежуточному кластеру около 3.7 K; 104215 и 104225
принадлежат кластеру 10 K. Здесь фиксируется только метаданные температуры, без интерпретации спектральных
различий.
Значения setpoint1/setpoint2 в первых трёх scans равны 300 K и явно не описывают физическую температуру
образца в этих scans; они сохранены как stale/inactive metadata и не использованы для выбора температуры.
В scans 104215 и 104225 оба setpoint равны 10 K и согласуются с измеренным температурным блоком.

## Все discovery scans и классификация

[B001 scan_selection.csv](../../04_Results/Stage02R/W02-02R-B-001/scan_selection.csv) содержит 57 discovery
scans, а [A002 scan_inventory.csv](../../04_Results/Stage02R/W02-02R-A-002/scan_inventory.csv) задаёт их
идентичности и контрольные суммы. Все 57 исходных .dat проверены по этим SHA-256; неразрешённых scans нет.
SCAN-02R-7acd4c14a0007418 (raw 104209) сохранён в таблице как discovery scan с температурными метаданными;
его прежнее численное исключение B001 не пересчитывалось.

Три кластера получены из двух доминирующих разрывов в отсортированных средних T1_Sensor1:
{fmt(boundaries["low_other_gap_K"])} K и {fmt(boundaries["other_ten_gap_K"])} K. Меньший из них в
{fmt(boundaries["second_to_third_gap_ratio"], 3)} раза превышает следующий крупнейший разрыв
{fmt(boundaries["next_largest_gap_K"])} K. Производные границы равны
{fmt(boundaries["low_other_boundary_K"])} K и {fmt(boundaries["other_ten_boundary_K"])} K.
Номер scan и время регистрации при классификации не использовались.

- Низкотемпературный кластер: {len(low)} scans; средние по scans
  {fmt(low_summary["scan_mean_temperature_min_K"])}–{fmt(low_summary["scan_mean_temperature_max_K"])} K;
  максимальный внутрискановый диапазон {fmt(low_summary["maximum_within_scan_point_to_point_range_K"], 4)} K.
- Промежуточный кластер: {len(other)} scans; средние по scans
  {fmt(other_summary["scan_mean_temperature_min_K"])}–{fmt(other_summary["scan_mean_temperature_max_K"])} K;
  максимальный внутрискановый диапазон {fmt(other_summary["maximum_within_scan_point_to_point_range_K"], 4)} K.
- Кластер 10 K: {len(ten)} scans; средние по scans
  {fmt(ten_summary["scan_mean_temperature_min_K"])}–{fmt(ten_summary["scan_mean_temperature_max_K"])} K;
  максимальный внутрискановый диапазон {fmt(ten_summary["maximum_within_scan_point_to_point_range_K"], 4)} K.

Для рассмотрения Project Control предлагается прозрачный допуск: средняя температура scan 9.95–10.05 K
и внутрискановый max-minus-min не более 0.05 K. Он шире фактически наблюдавшихся отклонений; все 20 scans
кластера 10 K проходят этот предлагаемый критерий. Это предложение, а не уже утверждённое правило включения.

## Границы задачи

Читались только заголовки, идентичности и явно разрешённые поля sample environment. Значения detector,
intensity и monitor не извлекались. Holdout scans не открывались. Детекторный пересчёт, спектральный fit и
CEF-анализ не выполнялись. Этот результат предоставляет W03 температурную таблицу; принятие ограничения и
правила стабильности остаётся отдельным review-решением.
"""
    return text.encode("utf-8")


def build_artifacts(
    repo_root: Path, raw_root: Path
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    records, source_hashes, max_temp_sensor_delta = load_discovery_records(
        repo_root, raw_root
    )
    low, ten, other, boundaries = classify_temperature_blocks(records)
    csv_data = csv_bytes(records)
    csv_sha256 = sha256_bytes(csv_data)

    summary = summary_document(
        repo_root,
        raw_root,
        records,
        source_hashes,
        low,
        ten,
        other,
        boundaries,
        csv_sha256,
        max_temp_sensor_delta,
    )
    summary_data = yaml.safe_dump(
        summary, sort_keys=False, allow_unicode=True, width=120, line_break="\n"
    ).encode("utf-8")
    review_data = review_bytes(
        records,
        low,
        ten,
        other,
        boundaries,
        csv_sha256,
        sha256_bytes(summary_data),
    )
    output_root = repo_root / "data/manuscript_v1"
    artifacts = {
        output_root / "taipan_temperature_mapping_v1.csv": csv_data,
        output_root / "taipan_temperature_mapping_v1_summary.yaml": summary_data,
        output_root / "TAIPAN_TEMPERATURE_MAPPING_REVIEW.md": review_data,
    }
    return artifacts, summary


def validate_artifacts(artifacts: dict[Path, bytes], summary: dict[str, Any]) -> None:
    if summary["counts"]["B001_discovery_scans"] != 57:
        raise AssertionError("B001 discovery count")
    if summary["counts"]["temperature_mapped"] != 57:
        raise AssertionError("mapped scan count")
    if summary["counts"]["unresolved"] != 0:
        raise AssertionError("unresolved scans")
    if set(summary["priority_scans"]) != {str(value) for value in PRIORITY_RAW_IDS}:
        raise AssertionError("priority scan coverage")
    if summary["classification"]["ten_K"]["scan_count"] != 20:
        raise AssertionError("10 K scan count")
    if summary["classification"]["low_temperature"]["scan_count"] != 29:
        raise AssertionError("low-temperature scan count")
    if summary["classification"]["other_temperature"]["scan_count"] != 8:
        raise AssertionError("other-temperature scan count")
    if summary["safety_boundaries"]["holdout_detector_access_count"] != 0:
        raise AssertionError("holdout boundary")
    if summary["safety_boundaries"]["detector_fields_read"]:
        raise AssertionError("detector read boundary")
    if len(artifacts) != 3 or any(not value for value in artifacts.values()):
        raise AssertionError("artifact completeness")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    raw_root = args.raw_root.resolve()
    artifacts, summary = build_artifacts(repo_root, raw_root)
    validate_artifacts(artifacts, summary)

    if args.check:
        mismatches = [
            str(path)
            for path, expected in artifacts.items()
            if not path.is_file() or path.read_bytes() != expected
        ]
        if mismatches:
            raise SystemExit("artifact mismatch: " + ", ".join(mismatches))
        print("PASS: deterministic artifacts and all bounded metadata-only checks")
        return 0

    for path, data in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"{path}: {len(data)} bytes sha256={sha256_bytes(data)}")
    print("PASS: 57/57 discovery scans mapped; holdout detector access count 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
