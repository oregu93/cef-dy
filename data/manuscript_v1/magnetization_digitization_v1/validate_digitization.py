#!/usr/bin/env python3
"""Bounded integrity validation for the frozen M(H) digitization outputs."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "manuscript_v1"
POINTS = DATA / "literature_magnetization.csv"
INVENTORY = DATA / "literature_magnetization_curve_inventory.csv"
REPORT = Path(__file__).with_name("validation_report.json")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


points = read_csv(POINTS)
inventory = read_csv(INVENTORY)
expected_columns = [
    "source_id", "paper_doi", "figure", "panel", "axis",
    "temperature_K", "branch", "H_kOe", "H_T", "M_emu_per_g",
    "M_muB_per_fu", "sigma_H_digitization", "sigma_M_digitization",
    "source_type", "digitization_status", "notes",
]
checks: dict[str, bool] = {}
checks["schema_exact"] = list(points[0]) == expected_columns
checks["point_count_135"] = len(points) == 135
counts = Counter((row["axis"], int(row["temperature_K"])) for row in points)
checks["four_numeric_curves"] = counts == {
    ("a", 10): 34, ("a", 20): 34, ("b", 10): 34, ("b", 20): 33
}
checks["no_c_axis_numeric_points"] = all(row["axis"] != "c" for row in points)
checks["branch_frozen"] = all(row["branch"] == "SINGLE_VISIBLE_BRANCH" for row in points)
checks["source_identity"] = all(
    row["source_id"] == "KE2015_FIG2"
    and row["paper_doi"] == "10.1088/1674-1056/24/3/037501"
    and row["figure"] == "2"
    for row in points
)
checks["panel_axis_not_swapped"] = all(row["panel"] == row["axis"] for row in points)
checks["only_10_and_20_K"] = {int(row["temperature_K"]) for row in points} == {10, 20}
checks["published_units_retained"] = all(
    row["H_kOe"] != "" and row["M_emu_per_g"] != "" for row in points
)
checks["conversion_exact"] = all(
    float(row["H_T"]) == 0.1 * float(row["H_kOe"])
    and float(row["M_muB_per_fu"]) == 0.04768 * float(row["M_emu_per_g"])
    for row in points
)
checks["field_in_published_range"] = all(0.0 <= float(row["H_kOe"]) <= 70.0 for row in points)
checks["near_zero_not_interpolated"] = min(float(row["H_kOe"]) for row in points) > 0.0
checks["field_strictly_monotonic"] = all(
    all(second > first for first, second in zip(fields, fields[1:]))
    for key in counts
    for fields in [[
        float(row["H_kOe"]) for row in points
        if (row["axis"], int(row["temperature_K"])) == key
    ]]
)
checks["total_bulk_only"] = all(
    row["source_type"] == "TOTAL_BULK_MAGNETIZATION" for row in points
)
checks["digitization_status_only"] = all(
    row["digitization_status"] == "DIGITIZED" for row in points
)
checks["positive_graphical_uncertainties"] = all(
    float(row["sigma_H_digitization"]) > 0.0
    and float(row["sigma_M_digitization"]) > 0.0
    for row in points
)
checks["inventory_six_rows"] = len(inventory) == 6
inventory_counts = Counter(row["digitization_status"] for row in inventory)
checks["inventory_four_plus_two"] = inventory_counts == {
    "DIGITIZED": 4, "AMBIGUOUS_CURVE_IDENTITY": 2
}
checks["ambiguous_have_no_numbers"] = all(
    row["numerical_points"] == "0"
    and all(row[name] == "" for name in (
        "H_min_kOe", "H_max_kOe", "M_min_emu_per_g", "M_max_emu_per_g"
    ))
    and row["w03_comparator_status"]
    == "NO_RELIABLE_DIGITIZED_COMPARATOR_FROM_THIS_FIGURE"
    for row in inventory
    if row["digitization_status"] == "AMBIGUOUS_CURVE_IDENTITY"
)

failed = [name for name, passed in checks.items() if not passed]
report = {
    "status": "PASS" if not failed else "FAIL",
    "passed": sum(checks.values()),
    "failed": len(failed),
    "failed_checks": failed,
    "checks": checks,
    "sha256": {
        "literature_magnetization.csv": hashlib.sha256(POINTS.read_bytes()).hexdigest(),
        "literature_magnetization_curve_inventory.csv": hashlib.sha256(
            INVENTORY.read_bytes()
        ).hexdigest(),
    },
    "scientific_guards": {
        "cef_calculation_performed": False,
        "fe_subtraction_performed": False,
        "normalization_performed": False,
        "interpolation_used": False,
    },
}
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
if failed:
    raise SystemExit(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
