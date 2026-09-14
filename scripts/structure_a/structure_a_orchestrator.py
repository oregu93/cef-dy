#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


EXPECTED_FP2K_SHA256 = (
    "6f3b6c13e6c33e7a696f9ff986a9e5327e848ba2fb42d6a5e8f67949b93dc4ec"
)

REAL_ARTIFACT_SHA256 = (
    "735578af432552d07acde0b8a378fdafe32b15f639e59e2db7210db2fd663a73"
)

REAL_REFINEMENT_AUTHORIZED = False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_ascii_path(path: Path) -> None:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"FullProf runtime path must be ASCII-only: {path}"
        ) from exc


def qualify_fullprof_executable(fp2k: Path) -> dict:
    if not fp2k.is_file():
        raise RuntimeError(f"fp2k not found: {fp2k}")

    if not os.access(fp2k, os.X_OK):
        raise RuntimeError(f"fp2k is not executable: {fp2k}")

    digest = sha256_file(fp2k)

    if digest != EXPECTED_FP2K_SHA256:
        raise RuntimeError(
            "fp2k SHA256 mismatch: "
            f"expected {EXPECTED_FP2K_SHA256}, got {digest}"
        )

    return {
        "status": "PASS",
        "path": str(fp2k),
        "sha256": digest,
    }


def guard_real_input(path: Path) -> None:
    if not path.exists():
        return

    digest = sha256_file(path)

    if digest == REAL_ARTIFACT_SHA256 and not REAL_REFINEMENT_AUTHORIZED:
        raise RuntimeError(
            "REAL_4K_FULLPROF_EXECUTION_NOT_AUTHORIZED"
        )


def copy_fixture(source_dir: Path, scratch_dir: Path) -> None:
    required = ("pbso4.pcr", "pbso4.dat")

    for name in required:
        source = source_dir / name
        if not source.is_file():
            raise RuntimeError(f"fixture file missing: {source}")

        shutil.copy2(source, scratch_dir / name)


def invoke_fullprof(
    fp2k: Path,
    scratch_dir: Path,
    jobid: str,
) -> dict:
    ensure_ascii_path(scratch_dir)

    pcr = scratch_dir / f"{jobid}.pcr"
    guard_real_input(pcr)

    result = subprocess.run(
        [str(fp2k), jobid],
        cwd=scratch_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def require_output(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"required output missing: {path.name}")

    if path.stat().st_size == 0:
        raise RuntimeError(f"required output empty: {path.name}")


def parse_sum_required(path: Path) -> dict:
    require_output(path)

    text = path.read_text(
        encoding="latin-1",
        errors="replace",
    )

    result = {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }

    patterns = {
        "rwp": r"\bRwp\b[^0-9+\-]*([0-9.]+)",
        "chi2": r"\bChi2\b[^0-9+\-]*([0-9.]+)",
        "bragg_r": r"\bBragg\s+R(?:-factor)?\b[^0-9+\-]*([0-9.]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            result[key] = float(match.group(1))

    return result


def parse_out_required(path: Path) -> dict:
    require_output(path)

    text = path.read_text(
        encoding="latin-1",
        errors="replace",
    )

    lower = text.lower()

    fatal_markers = [
        "fatal error",
        "forrtl:",
        "segmentation fault",
    ]

    found = [
        marker
        for marker in fatal_markers
        if marker in lower
    ]

    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "fatal_markers": found,
    }


def parse_prf_required(path: Path) -> dict:
    require_output(path)

    lines = 0
    numeric_lines = 0

    with path.open(
        "r",
        encoding="latin-1",
        errors="replace",
    ) as handle:
        for line in handle:
            lines += 1
            stripped = line.strip()

            if not stripped:
                continue

            token = stripped.split()[0]

            try:
                float(token)
            except ValueError:
                continue
            else:
                numeric_lines += 1

    if numeric_lines == 0:
        raise RuntimeError("PRF contains no numeric data")

    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "lines": lines,
        "numeric_lines": numeric_lines,
    }


def classify_convergence(
    invocation: dict,
    out_info: dict,
    scratch_dir: Path,
    jobid: str,
) -> dict:
    outputs = {
        suffix: (scratch_dir / f"{jobid}.{suffix}").is_file()
        for suffix in ("out", "sum", "prf", "new")
    }

    converged = (
        invocation["returncode"] == 0
        and not out_info["fatal_markers"]
        and outputs["out"]
        and outputs["sum"]
        and outputs["prf"]
        and outputs["new"]
    )

    return {
        "status": "PASS" if converged else "FAIL",
        "outputs_present": outputs,
    }


def preserve_block(
    scratch_dir: Path,
    destination: Path,
    jobid: str,
) -> dict:
    destination.mkdir(
        parents=True,
        exist_ok=False,
    )

    copied = {}

    for suffix in (
        "pcr",
        "dat",
        "out",
        "sum",
        "prf",
        "new",
    ):
        source = scratch_dir / f"{jobid}.{suffix}"

        if source.exists():
            target = destination / source.name
            shutil.copy2(source, target)

            copied[source.name] = {
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
            }

    return copied


def build_provenance_manifest(
    fp_info: dict,
    invocation: dict,
    sum_info: dict,
    out_info: dict,
    prf_info: dict,
    convergence: dict,
    preserved: dict,
) -> dict:
    return {
        "task_id": (
            "STRUCTURE-A-REREFINEMENT-"
            "ORCHESTRATION-IMPLEMENTATION-001"
        ),
        "mode": "fixture_preflight",
        "real_refinement_authorized": False,
        "fullprof": fp_info,
        "invocation": {
            "returncode": invocation["returncode"],
            "stderr_empty": not bool(
                invocation["stderr"].strip()
            ),
        },
        "sum": sum_info,
        "out": out_info,
        "prf": prf_info,
        "convergence": convergence,
        "artifacts": preserved,
    }


def run_fixture(
    fp2k: Path,
    fixture_dir: Path,
    output_dir: Path,
) -> dict:
    fp_info = qualify_fullprof_executable(fp2k)

    ensure_ascii_path(output_dir)

    with tempfile.TemporaryDirectory(
        prefix="structure-a-fp-",
        dir="/tmp",
    ) as temporary:
        scratch = Path(temporary)
        ensure_ascii_path(scratch)

        copy_fixture(
            fixture_dir,
            scratch,
        )

        invocation = invoke_fullprof(
            fp2k,
            scratch,
            "pbso4",
        )

        sum_info = parse_sum_required(
            scratch / "pbso4.sum"
        )

        out_info = parse_out_required(
            scratch / "pbso4.out"
        )

        prf_info = parse_prf_required(
            scratch / "pbso4.prf"
        )

        convergence = classify_convergence(
            invocation,
            out_info,
            scratch,
            "pbso4",
        )

        if convergence["status"] != "PASS":
            raise RuntimeError(
                "fixture FullProf run did not satisfy "
                "technical convergence gate"
            )

        preserved = preserve_block(
            scratch,
            output_dir,
            "pbso4",
        )

    manifest = build_provenance_manifest(
        fp_info,
        invocation,
        sum_info,
        out_info,
        prf_info,
        convergence,
        preserved,
    )

    manifest_path = output_dir / "provenance_manifest.json"

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--fp2k",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--fixture-dir",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--mode",
        choices=["fixture"],
        default="fixture",
    )

    args = parser.parse_args()

    manifest = run_fixture(
        args.fp2k,
        args.fixture_dir,
        args.output_dir,
    )

    print("STRUCTURE_A_ORCHESTRATOR_PREFLIGHT: PASS")
    print(
        "FULLPROF_BUILD:",
        manifest["fullprof"]["sha256"],
    )
    print(
        "CONVERGENCE:",
        manifest["convergence"]["status"],
    )
    print("REAL_4K_REFINEMENT: NOT_PERFORMED")


if __name__ == "__main__":
    main()
