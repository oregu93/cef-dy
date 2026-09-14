#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

EXPECTED_RAW_SHA256 = (
    "735578af432552d07acde0b8a378fdafe32b15f639e59e2db7210db2fd663a73"
)

EXPECTED_BLOCKS = [
    {
        "block_index": 1,
        "role": "primary_diffraction",
        "points": 13501,
        "start": 20.0000,
        "stop": 155.0000,
        "step": 0.0100,
    },
    {
        "block_index": 2,
        "role": "secondary_ignored",
        "points": 11,
        "start": 15.0000,
        "stop": 15.1000,
        "step": 0.0100,
    },
]

GRID_TOL = 1.0e-8


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_number(text: str) -> float:
    return float(text.strip().strip('"'))


def parse_int_like(text: str) -> int:
    return int(round(parse_number(text)))


def parse_metadata_line(line: str):
    if not line.startswith("*") or " " not in line:
        return None, None
    key, value = line.split(" ", 1)
    return key.strip(), value.strip().strip('"')


def parse_ras(path: Path):
    raw = path.read_bytes()
    text = raw.decode("latin-1")
    lines = text.splitlines()

    blocks = []
    pending_metadata = {}
    current = None

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped == "*RAS_HEADER_START":
            pending_metadata = {}
            continue

        if stripped == "*RAS_INT_START":
            if current is not None:
                raise RuntimeError(
                    f"nested RAS_INT_START at line {lineno}"
                )
            current = {
                "start_line": lineno,
                "end_line": None,
                "metadata": dict(pending_metadata),
                "rows": [],
            }
            continue

        if stripped == "*RAS_INT_END":
            if current is None:
                raise RuntimeError(
                    f"RAS_INT_END without active block at line {lineno}"
                )
            current["end_line"] = lineno
            blocks.append(current)
            current = None
            continue

        if current is not None:
            if not stripped:
                continue
            fields = stripped.split()
            if len(fields) < 2:
                raise RuntimeError(
                    f"invalid numeric row at line {lineno}: {line!r}"
                )
            try:
                x = float(fields[0])
                y = float(fields[1])
                third = fields[2] if len(fields) >= 3 else None
            except ValueError as exc:
                raise RuntimeError(
                    f"non-numeric RAS_INT row at line {lineno}: {line!r}"
                ) from exc

            if not math.isfinite(x) or not math.isfinite(y):
                raise RuntimeError(
                    f"non-finite value at line {lineno}"
                )

            current["rows"].append(
                {
                    "line": lineno,
                    "x": x,
                    "y": y,
                    "x_token": fields[0],
                    "y_token": fields[1],
                    "third_token": third,
                }
            )
            continue

        key, value = parse_metadata_line(stripped)
        if key is not None:
            pending_metadata[key] = value

    if current is not None:
        raise RuntimeError("unterminated RAS_INT block")

    return blocks


def validate_block(block, expected):
    rows = block["rows"]
    n = len(rows)

    if n != expected["points"]:
        raise RuntimeError(
            f"block {expected['block_index']}: "
            f"point count {n} != {expected['points']}"
        )

    xs = [row["x"] for row in rows]
    ys = [row["y"] for row in rows]

    if abs(xs[0] - expected["start"]) > GRID_TOL:
        raise RuntimeError(
            f"block {expected['block_index']}: "
            f"start {xs[0]} != {expected['start']}"
        )

    if abs(xs[-1] - expected["stop"]) > GRID_TOL:
        raise RuntimeError(
            f"block {expected['block_index']}: "
            f"stop {xs[-1]} != {expected['stop']}"
        )

    mismatch_count = 0
    for i in range(1, n):
        observed_step = xs[i] - xs[i - 1]
        if abs(observed_step - expected["step"]) > GRID_TOL:
            mismatch_count += 1

    if mismatch_count:
        raise RuntimeError(
            f"block {expected['block_index']}: "
            f"{mismatch_count} grid-step mismatches"
        )

    if any(not math.isfinite(y) for y in ys):
        raise RuntimeError(
            f"block {expected['block_index']}: non-finite intensity"
        )

    nonpositive = sum(y <= 0.0 for y in ys)

    thirds = [row["third_token"] for row in rows]
    third_unique = sorted(set(thirds), key=lambda x: str(x))

    metadata = block["metadata"]

    if "*MEAS_DATA_COUNT" in metadata:
        meta_count = parse_int_like(metadata["*MEAS_DATA_COUNT"])
        if meta_count != n:
            raise RuntimeError(
                f"block {expected['block_index']}: "
                f"MEAS_DATA_COUNT {meta_count} != parsed {n}"
            )

    checks = {
        "block_index": expected["block_index"],
        "role": expected["role"],
        "start_line": block["start_line"],
        "end_line": block["end_line"],
        "points": n,
        "two_theta_start_deg": xs[0],
        "two_theta_stop_deg": xs[-1],
        "step_deg": expected["step"],
        "step_mismatch_count": mismatch_count,
        "intensity_min": min(ys),
        "intensity_max": max(ys),
        "zero_count": sum(y == 0.0 for y in ys),
        "negative_count": sum(y < 0.0 for y in ys),
        "nonpositive_count": nonpositive,
        "third_column_unique_values": third_unique,
        "metadata_MEAS_DATA_COUNT": metadata.get("*MEAS_DATA_COUNT"),
        "metadata_MEAS_SCAN_START": metadata.get("*MEAS_SCAN_START"),
        "metadata_MEAS_SCAN_STOP": metadata.get("*MEAS_SCAN_STOP"),
        "metadata_MEAS_SCAN_STEP": metadata.get("*MEAS_SCAN_STEP"),
        "metadata_MEAS_SCAN_UNIT_Y": metadata.get("*MEAS_SCAN_UNIT_Y"),
    }

    return checks


def write_instrm0(primary, output_path: Path):
    rows = primary["rows"]

    if any(row["y"] <= 0.0 for row in rows):
        raise RuntimeError(
            "primary diffraction block contains non-positive intensities"
        )

    # FullProf INSTRM=0:
    # first numerical line = 2theta_start, step, 2theta_stop
    # then observed intensities only.
    #
    # Preserve source intensity lexical tokens exactly.
    tokens = [row["y_token"] for row in rows]

    out = []
    out.append("20.0000 0.0100 155.0000")

    values_per_line = 10
    for i in range(0, len(tokens), values_per_line):
        out.append(" ".join(tokens[i : i + values_per_line]))

    output_path.write_text("\n".join(out) + "\n", encoding="ascii")


def convert(source: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=False)

    actual_sha = sha256_file(source)
    if actual_sha != EXPECTED_RAW_SHA256:
        raise RuntimeError(
            "RAW SHA256 mismatch:\n"
            f"expected: {EXPECTED_RAW_SHA256}\n"
            f"actual:   {actual_sha}"
        )

    blocks = parse_ras(source)

    if len(blocks) != len(EXPECTED_BLOCKS):
        raise RuntimeError(
            f"RAS_INT topology mismatch: "
            f"expected {len(EXPECTED_BLOCKS)} blocks, found {len(blocks)}"
        )

    block_checks = []
    for block, expected in zip(blocks, EXPECTED_BLOCKS):
        block_checks.append(validate_block(block, expected))

    primary = blocks[0]

    if block_checks[0]["nonpositive_count"] != 0:
        raise RuntimeError(
            "primary block failed positive-count weighting precondition"
        )

    dat_path = output_dir / "dyfeo3_4k_instrm0.dat"
    write_instrm0(primary, dat_path)

    manifest = {
        "converter_id": "STRUCTURE-A-RAS-INSTRM0-CONVERTER-PREFLIGHT-001",
        "converter_scope": "authorized_preflight_only",
        "source_artifact_id": "ART-XRDDY-RAS-101-001",
        "source_path_name": source.name,
        "source_sha256": actual_sha,
        "ras_int_block_count": len(blocks),
        "blocks": block_checks,
        "selected_primary_block_index": 1,
        "selection_contract": {
            "points": 13501,
            "two_theta_start_deg": 20.0,
            "two_theta_stop_deg": 155.0,
            "step_deg": 0.01,
            "positive_intensity_required": True,
        },
        "ignored_block_indices": [2],
        "third_column_policy": (
            "ignored_for_FullProf_weighting_and_not_written_to_execution_input"
        ),
        "fullprof_contract": {
            "JOBTYP": 0,
            "INSTRM": 0,
            "IWGT": 0,
            "explicit_sigma": False,
            "native_observed_counts": True,
            "smoothing": False,
            "normalization": False,
            "background_subtraction": False,
        },
        "output": {
            "filename": dat_path.name,
            "sha256": sha256_file(dat_path),
            "bytes": dat_path.stat().st_size,
            "intensity_count": 13501,
        },
        "real_fullprof_execution_authorized": False,
    }

    manifest_path = output_dir / "conversion_manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n",
        encoding="ascii",
    )

    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    manifest = convert(args.source, args.output_dir)

    print("CONVERSION_STATUS: PASS")
    print(f"source_sha256: {manifest['source_sha256']}")
    print(f"ras_int_blocks: {manifest['ras_int_block_count']}")

    for b in manifest["blocks"]:
        print(
            "block_{idx}: role={role} points={points} "
            "range={start:.4f}..{stop:.4f} "
            "step={step:.4f} nonpositive={nonpositive}".format(
                idx=b["block_index"],
                role=b["role"],
                points=b["points"],
                start=b["two_theta_start_deg"],
                stop=b["two_theta_stop_deg"],
                step=b["step_deg"],
                nonpositive=b["nonpositive_count"],
            )
        )

    print(
        "output_sha256:",
        manifest["output"]["sha256"],
    )
    print(
        "output_bytes:",
        manifest["output"]["bytes"],
    )
    print("REAL_FULLPROF_EXECUTION: NOT_PERFORMED")


if __name__ == "__main__":
    main()
