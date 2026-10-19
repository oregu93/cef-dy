"""Read the separate, version-controlled magnetization comparison table."""

from __future__ import annotations

import csv
from pathlib import Path


def verified_temperatures(path: str | Path) -> tuple[float, ...]:
    temperatures = set()
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("provenance_status") == "REVIEWED" and row.get("temperature_K", "").strip():
                temperatures.add(float(row["temperature_K"]))
    return tuple(sorted(temperatures))
