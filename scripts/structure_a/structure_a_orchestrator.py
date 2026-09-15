#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_FP2K_SHA256 = "6f3b6c13e6c33e7a696f9ff986a9e5327e848ba2fb42d6a5e8f67949b93dc4ec"
TASK_ID = "STRUCTURE-A-REREFINEMENT-ORCHESTRATION-IMPLEMENTATION-001"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_ascii_path(path: Path) -> None:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"FullProf runtime path must be ASCII-only: {path}"
        ) from exc


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or "config_id" not in config:
        raise RuntimeError("invalid orchestrator config")
    return config


def qualify_fullprof_executable(fp2k: Path) -> dict:
    if not fp2k.is_file():
        raise RuntimeError(f"fp2k not found: {fp2k}")
    if not os.access(fp2k, os.X_OK):
        raise RuntimeError(f"fp2k is not executable: {fp2k}")

    digest = sha256_file(fp2k)

    if digest != EXPECTED_FP2K_SHA256:
        raise RuntimeError(
            f"fp2k SHA256 mismatch: expected "
            f"{EXPECTED_FP2K_SHA256}, got {digest}"
        )

    return {
        "status": "PASS",
        "path": str(fp2k),
        "sha256": digest,
    }


def build_input_identity(
    artifact_id,
    path,
    sha256,
    input_role,
    real_data,
    execution_authorized,
) -> dict:
    return {
        "artifact_id": str(artifact_id),
        "path": str(path),
        "sha256": str(sha256),
        "input_role": str(input_role),
        "real_data": bool(real_data),
        "execution_authorized": bool(execution_authorized),
    }


def validate_input_identity(identity: dict, config: dict) -> dict:
    required = {
        "artifact_id",
        "path",
        "sha256",
        "input_role",
        "real_data",
        "execution_authorized",
    }

    if required - set(identity):
        raise RuntimeError(
            "PRECONDITION_FAILURE: incomplete diffraction input identity"
        )

    path = Path(identity["path"])

    if not path.is_file():
        raise RuntimeError(
            "PRECONDITION_FAILURE: diffraction input missing"
        )

    if sha256_file(path) != identity["sha256"]:
        raise RuntimeError(
            "PRECONDITION_FAILURE: diffraction input SHA256 mismatch"
        )

    registered = config.get(
        "input_authorizations", {}
    ).get("registered_inputs", [])

    matches = []

    for item in registered:
        if item.get("artifact_id") != identity["artifact_id"]:
            continue
        if item.get("input_role") != identity["input_role"]:
            continue
        if bool(item.get("real_data")) != identity["real_data"]:
            continue

        registered_sha = item.get("sha256")

        if (
            registered_sha is not None
            and registered_sha != identity["sha256"]
        ):
            continue

        if identity["real_data"] and registered_sha is None:
            continue

        matches.append(item)

    if len(matches) != 1:
        raise RuntimeError(
            "PRECONDITION_FAILURE: diffraction input not uniquely registered"
        )

    return matches[0]


def guard_diffraction_input(identity: dict, config: dict) -> None:
    registered = validate_input_identity(identity, config)

    if (
        not identity["execution_authorized"]
        or not bool(registered.get("execution_authorized"))
    ):
        raise RuntimeError(
            "PRECONDITION_FAILURE: diffraction input execution not authorized"
        )

    if identity["real_data"] and not registered.get("sha256"):
        raise RuntimeError(
            "PRECONDITION_FAILURE: real input requires exact registered SHA256"
        )


def _coerce_value(token: str, value_type: str):
    if value_type == "float":
        return float(token)
    if value_type == "int":
        return int(token)
    if value_type == "string":
        return token
    raise RuntimeError(
        f"unsupported target value_type: {value_type}"
    )


def _equal_value(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(
            float(a),
            float(b),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    return a == b


def _locate_target(text: str, spec: dict):
    selector = spec.get("selector", {})

    if selector.get("kind") != "exact_line_token":
        raise RuntimeError("unsupported PCR target selector")

    line_match = selector["line_match"]
    token_index = int(selector["token_index"])

    lines = text.splitlines(keepends=True)
    hits = [
        (i, line)
        for i, line in enumerate(lines)
        if line_match in line
    ]

    if len(hits) != 1:
        raise RuntimeError(
            "PCR target selector must match exactly one line"
        )

    i, line = hits[0]
    body = line.rstrip("\r\n")
    newline = line[len(body):]
    tokens = list(re.finditer(r"\S+", body))

    if token_index < 0 or token_index >= len(tokens):
        raise RuntimeError(
            "PCR target token index out of range"
        )

    return lines, i, body, newline, tokens[token_index]


def extract_target_state(
    pcr_text: str,
    target_specs: dict,
) -> dict:
    state = {}

    for target_id, spec in target_specs.items():
        _, _, body, _, match = _locate_target(
            pcr_text,
            spec,
        )
        state[target_id] = _coerce_value(
            match.group(0),
            spec.get("value_type", "string"),
        )

    return state


def compare_target_state(
    before_state: dict,
    after_state: dict,
    requested_delta: dict,
) -> dict:
    requested = {
        change["target_id"]: change
        for change in requested_delta.get("changes", [])
    }

    actual_changed = {
        key
        for key in before_state
        if not _equal_value(
            before_state[key],
            after_state[key],
        )
    }

    unexpected = sorted(
        actual_changed - set(requested)
    )

    if unexpected:
        return {
            "status": "REJECT_UNEXPECTED_CHANGE",
            "changed_targets": sorted(actual_changed),
            "unexpected": unexpected,
        }

    incomplete = []

    for target_id, change in requested.items():
        if (
            target_id not in before_state
            or target_id not in after_state
        ):
            incomplete.append(target_id)
            continue

        if not _equal_value(
            before_state[target_id],
            change["before"],
        ):
            incomplete.append(target_id)
            continue

        if not _equal_value(
            after_state[target_id],
            change["after"],
        ):
            incomplete.append(target_id)
            continue

        if (
            target_id not in actual_changed
            and not _equal_value(
                change["before"],
                change["after"],
            )
        ):
            incomplete.append(target_id)

    if incomplete:
        return {
            "status": "REJECT_INCOMPLETE_DELTA",
            "changed_targets": sorted(actual_changed),
            "incomplete": sorted(set(incomplete)),
        }

    return {
        "status": "PASS",
        "changed_targets": sorted(actual_changed),
    }


def apply_authorized_pcr_delta(
    baseline_text: str,
    delta_id: str,
    delta_spec: dict,
    target_specs: dict,
) -> str:
    if delta_spec.get("delta_id", delta_id) != delta_id:
        raise RuntimeError(
            "REJECT_INCOMPLETE_DELTA: delta id mismatch"
        )

    before = extract_target_state(
        baseline_text,
        target_specs,
    )

    candidate = baseline_text

    for change in delta_spec.get("changes", []):
        target_id = change["target_id"]

        if target_id not in target_specs:
            raise RuntimeError(
                "REJECT_INCOMPLETE_DELTA: unknown target"
            )

        current = extract_target_state(
            candidate,
            {target_id: target_specs[target_id]},
        )[target_id]

        if not _equal_value(
            current,
            change["before"],
        ):
            raise RuntimeError(
                "REJECT_INCOMPLETE_DELTA: baseline value mismatch"
            )

        lines, i, body, newline, match = _locate_target(
            candidate,
            target_specs[target_id],
        )

        replacement = str(change["after"])

        lines[i] = (
            body[:match.start()]
            + replacement
            + body[match.end():]
            + newline
        )

        candidate = "".join(lines)

    after = extract_target_state(
        candidate,
        target_specs,
    )

    result = compare_target_state(
        before,
        after,
        delta_spec,
    )

    if result["status"] != "PASS":
        raise RuntimeError(result["status"])

    return candidate


def validate_stage_transition(
    current_stage_id,
    requested_next_stage_id,
    permitted_transition_spec,
    actual_change_result,
    requested_delta_id=None,
) -> str:
    current = permitted_transition_spec.get(
        current_stage_id
    )

    if not current:
        return "REJECT_UNAUTHORIZED_TRANSITION"

    next_stage = current.get(
        "next", {}
    ).get(requested_next_stage_id)

    if not next_stage:
        return "REJECT_UNAUTHORIZED_TRANSITION"

    if (
        requested_delta_id is not None
        and requested_delta_id
        not in next_stage.get("permitted_delta_ids", [])
    ):
        return "REJECT_UNAUTHORIZED_TRANSITION"

    status = (
        actual_change_result.get("status")
        if isinstance(actual_change_result, dict)
        else str(actual_change_result)
    )

    if status in {
        "REJECT_UNEXPECTED_CHANGE",
        "REJECT_INCOMPLETE_DELTA",
    }:
        return status

    return (
        "PASS"
        if status == "PASS"
        else "REJECT_INCOMPLETE_DELTA"
    )


def require_output(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(
            f"MISSING_EXPECTED_OUTPUT: {path.name}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"MISSING_EXPECTED_OUTPUT: empty {path.name}"
        )


def parse_sum_required(
    path: Path,
    parser_contract: dict,
) -> dict:
    require_output(path)

    text = path.read_text(
        encoding="latin-1",
        errors="replace",
    )

    patterns = {
        "rwp": r"\bRwp\b[^0-9+\-]*([0-9.]+)",
        "chi2": r"\bChi2\b[^0-9+\-]*([0-9.]+)",
        "bragg_r":
            r"\bBragg\s+R(?:-factor)?\b[^0-9+\-]*([0-9.]+)",
    }

    result = {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "parser_status": "PASS",
    }

    for field in parser_contract.get(
        "sum_required_fields_before_readiness",
        [],
    ):
        if field not in patterns:
            raise RuntimeError(
                f"PARSE_FAILURE: unsupported required SUM field {field}"
            )

        match = re.search(
            patterns[field],
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            raise RuntimeError(
                f"PARSE_FAILURE: missing SUM field {field}"
            )

        value = float(match.group(1))

        if not math.isfinite(value):
            raise RuntimeError(
                f"NONFINITE_PARAMETER: SUM field {field}"
            )

        result[field] = value

    return result


def parse_out_required(
    path: Path,
    parser_contract: dict,
) -> dict:
    require_output(path)

    text = path.read_text(
        encoding="latin-1",
        errors="replace",
    )

    lower = text.lower()

    markers = parser_contract.get(
        "out_fatal_markers",
        [],
    )

    found = [
        marker
        for marker in markers
        if marker.lower() in lower
    ]

    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "fatal_markers": found,
        "parser_status": "PASS",
    }


def parse_prf_required(
    path: Path,
    parser_contract: dict,
) -> dict:
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

            try:
                float(stripped.split()[0])
            except ValueError:
                pass
            else:
                numeric_lines += 1

    if (
        "numeric_profile_present"
        in parser_contract.get(
            "prf_required_before_readiness",
            [],
        )
        and numeric_lines == 0
    ):
        raise RuntimeError(
            "PARSE_FAILURE: PRF numeric profile absent"
        )

    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "lines": lines,
        "numeric_lines": numeric_lines,
        "numeric_profile_present": numeric_lines > 0,
        "parser_status": "PASS",
    }


def _convergence_config_complete(config: dict) -> bool:
    required = [
        "max_blocks",
        "Rwp_change_threshold",
        "chi2_change_threshold",
        "minimum_consecutive_stable_blocks",
        "stagnation_window",
        "oscillation_window",
        "oscillation_rule",
    ]

    return (
        all(config.get(key) is not None for key in required)
        and bool(config.get("parameter_change_thresholds"))
    )


def _stable_transition(
    previous: dict,
    current: dict,
    config: dict,
) -> bool:
    if (
        abs(current["rwp"] - previous["rwp"])
        > config["Rwp_change_threshold"]
    ):
        return False

    if (
        abs(current["chi2"] - previous["chi2"])
        > config["chi2_change_threshold"]
    ):
        return False

    for name, threshold in config[
        "parameter_change_thresholds"
    ].items():
        if (
            abs(
                current.get(
                    "monitored_parameter_deltas",
                    {},
                ).get(name, math.inf)
            )
            > threshold
        ):
            return False

    return True


def classify_convergence(
    history: list[dict],
    convergence_config: dict,
) -> str:
    if not history:
        return "CONTINUE"

    current = history[-1]

    if (
        not current.get("execution_ok", False)
        or not current.get("parse_ok", False)
    ):
        return "FAILED"

    if not _convergence_config_complete(
        convergence_config
    ):
        raise RuntimeError(
            "PRECONDITION_FAILURE: unresolved convergence configuration"
        )

    stable_blocks = int(
        convergence_config[
            "minimum_consecutive_stable_blocks"
        ]
    )

    if len(history) >= stable_blocks + 1:
        window = history[-(stable_blocks + 1):]

        if all(
            _stable_transition(
                window[i],
                window[i + 1],
                convergence_config,
            )
            for i in range(len(window) - 1)
        ):
            return "CONVERGED"

    stagnation_window = int(
        convergence_config["stagnation_window"]
    )

    if len(history) >= stagnation_window + 1:
        window = history[-(stagnation_window + 1):]

        objectives_stable = all(
            abs(
                window[i + 1]["rwp"]
                - window[i]["rwp"]
            )
            <= convergence_config[
                "Rwp_change_threshold"
            ]
            and abs(
                window[i + 1]["chi2"]
                - window[i]["chi2"]
            )
            <= convergence_config[
                "chi2_change_threshold"
            ]
            for i in range(stagnation_window)
        )

        params_unstable = any(
            abs(
                window[-1].get(
                    "monitored_parameter_deltas",
                    {},
                ).get(name, 0.0)
            )
            > threshold
            for name, threshold
            in convergence_config[
                "parameter_change_thresholds"
            ].items()
        )

        if objectives_stable and params_unstable:
            return "STAGNATED"

    oscillation_window = int(
        convergence_config["oscillation_window"]
    )

    if (
        convergence_config.get("oscillation_rule")
        == "alternating_sign"
        and len(history) >= oscillation_window + 1
        and oscillation_window >= 2
    ):
        window = history[-(oscillation_window + 1):]

        differences = [
            window[i + 1]["rwp"]
            - window[i]["rwp"]
            for i in range(oscillation_window)
        ]

        if (
            all(value != 0 for value in differences)
            and all(
                differences[i]
                * differences[i + 1]
                < 0
                for i in range(
                    len(differences) - 1
                )
            )
        ):
            return "OSCILLATORY"

    if (
        int(current["block_index"])
        >= int(convergence_config["max_blocks"])
    ):
        return "MAX_BLOCKS_REACHED"

    return "CONTINUE"


def invoke_fullprof(
    fp2k: Path,
    scratch_dir: Path,
    jobid: str,
    diffraction_input_identity: dict,
    config: dict,
) -> dict:
    ensure_ascii_path(scratch_dir)

    guard_diffraction_input(
        diffraction_input_identity,
        config,
    )

    argv = [str(fp2k), jobid]

    result = subprocess.run(
        argv,
        cwd=scratch_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )

    return {
        "argv": argv,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _artifact_info(path: Path) -> dict:
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def preserve_attempt(
    scratch_dir: Path,
    destination: Path,
    attempt_context: dict,
    produced_files: list[str],
) -> dict:
    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifacts = {}

    for name in produced_files:
        source = scratch_dir / name

        if source.exists() and source.is_file():
            target = destination / name
            shutil.copy2(source, target)
            artifacts[name] = _artifact_info(target)

    stdout_path = destination / "stdout.txt"
    stderr_path = destination / "stderr.txt"

    stdout_path.write_text(
        attempt_context.get("stdout", ""),
        encoding="utf-8",
    )

    stderr_path.write_text(
        attempt_context.get("stderr", ""),
        encoding="utf-8",
    )

    artifacts["stdout.txt"] = _artifact_info(
        stdout_path
    )

    artifacts["stderr.txt"] = _artifact_info(
        stderr_path
    )

    return artifacts


def build_provenance_manifest(
    *,
    block_id,
    stage_id,
    timestamp_start,
    timestamp_end,
    argv,
    fp2k_sha256,
    config_path: Path,
    input_pcr_path: Path,
    diffraction_input: dict,
    return_code,
    stdout: str,
    stderr: str,
    produced_artifacts: dict,
    parser_status,
    convergence_status,
    failure_category,
    implementation_path: Path | None = None,
) -> dict:
    implementation_path = (
        implementation_path or Path(__file__)
    )

    return {
        "task_id": TASK_ID,
        "block_id": block_id,
        "stage_id": stage_id,
        "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end,
        "argv": argv,
        "platform": {
            "system": platform.system(),
            "architecture": platform.machine(),
        },
        "fp2k_sha256": fp2k_sha256,
        "orchestrator": {
            "implementation_identity":
                sha256_file(implementation_path)
        },
        "config": {
            "config_id":
                load_config(config_path)["config_id"],
            "sha256": sha256_file(config_path),
        },
        "input_pcr": {
            "sha256": sha256_file(input_pcr_path)
        },
        "diffraction_input": {
            key: diffraction_input[key]
            for key in (
                "artifact_id",
                "sha256",
                "input_role",
                "real_data",
                "execution_authorized",
            )
        },
        "return_code": return_code,
        "stdout_sha256":
            sha256_bytes(stdout.encode("utf-8")),
        "stderr_sha256":
            sha256_bytes(stderr.encode("utf-8")),
        "produced_artifacts": produced_artifacts,
        "parser_status": parser_status,
        "convergence_status": convergence_status,
        "failure_category": failure_category,
    }


def run_fixture(
    fp2k: Path,
    fixture_dir: Path,
    output_dir: Path,
    config_path: Path,
) -> dict:
    config = load_config(config_path)
    fp_info = qualify_fullprof_executable(fp2k)

    ensure_ascii_path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    timestamp_start = utc_now()
    failure_category = None

    invocation = {
        "argv": [str(fp2k), "pbso4"],
        "returncode": None,
        "stdout": "",
        "stderr": "",
    }

    parser_status = "NOT_RUN"

    fixture_dat = fixture_dir / "pbso4.dat"

    identity = build_input_identity(
        "PBSO4-FIXTURE",
        fixture_dat,
        sha256_file(fixture_dat),
        "fixture",
        False,
        True,
    )

    scratch = Path(
        tempfile.mkdtemp(
            prefix="structure-a-fp-",
            dir="/tmp",
        )
    )

    produced_names = [
        "pbso4.pcr",
        "pbso4.dat",
        "pbso4.out",
        "pbso4.sum",
        "pbso4.prf",
        "pbso4.new",
    ]

    try:
        ensure_ascii_path(scratch)

        for name in (
            "pbso4.pcr",
            "pbso4.dat",
        ):
            shutil.copy2(
                fixture_dir / name,
                scratch / name,
            )

        invocation = invoke_fullprof(
            fp2k,
            scratch,
            "pbso4",
            identity,
            config,
        )

        if invocation["returncode"] != 0:
            failure_category = "NONZERO_RETURN"
            raise RuntimeError("NONZERO_RETURN")

        out_info = parse_out_required(
            scratch / "pbso4.out",
            config["parser_contract"],
        )

        if out_info["fatal_markers"]:
            failure_category = (
                "FULLPROF_REPORTED_ERROR"
            )
            raise RuntimeError(
                "FULLPROF_REPORTED_ERROR"
            )

        parse_sum_required(
            scratch / "pbso4.sum",
            config["parser_contract"],
        )

        parse_prf_required(
            scratch / "pbso4.prf",
            config["parser_contract"],
        )

        require_output(
            scratch / "pbso4.new"
        )

        parser_status = "PASS"
        convergence_status = (
            "FIXTURE_TECHNICAL_PASS"
        )

    except subprocess.TimeoutExpired:
        failure_category = "TIMEOUT"
        convergence_status = "FAILED"
        raise

    except Exception:
        if failure_category is None:
            failure_category = (
                "PARSE_FAILURE"
                if parser_status != "PASS"
                else "PRECONDITION_FAILURE"
            )

        convergence_status = "FAILED"
        raise

    finally:
        artifacts = preserve_attempt(
            scratch,
            output_dir,
            invocation,
            produced_names,
        )

        manifest = build_provenance_manifest(
            block_id="FIXTURE-BLOCK-001",
            stage_id="FIXTURE-PREFLIGHT",
            timestamp_start=timestamp_start,
            timestamp_end=utc_now(),
            argv=invocation.get("argv", []),
            fp2k_sha256=fp_info["sha256"],
            config_path=config_path,
            input_pcr_path=scratch / "pbso4.pcr",
            diffraction_input=identity,
            return_code=invocation.get(
                "returncode"
            ),
            stdout=invocation.get(
                "stdout", ""
            ),
            stderr=invocation.get(
                "stderr", ""
            ),
            produced_artifacts=artifacts,
            parser_status=parser_status,
            convergence_status=locals().get(
                "convergence_status",
                "FAILED",
            ),
            failure_category=failure_category,
        )

        (
            output_dir / "provenance_manifest.json"
        ).write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="ascii",
        )

        shutil.rmtree(
            scratch,
            ignore_errors=True,
        )

    return manifest


def main():
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
        "--config",
        type=Path,
        default=Path(__file__).with_name(
            "structure_a_orchestrator_config.json"
        ),
    )

    args = parser.parse_args()

    manifest = run_fixture(
        args.fp2k,
        args.fixture_dir,
        args.output_dir,
        args.config,
    )

    print(
        "STRUCTURE_A_ORCHESTRATOR_PREFLIGHT: PASS"
    )

    print(
        "CONVERGENCE:",
        manifest["convergence_status"],
    )

    print(
        "REAL_4K_REFINEMENT: NOT_PERFORMED"
    )


if __name__ == "__main__":
    main()
