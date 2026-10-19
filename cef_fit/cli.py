"""Command-line frontend for local VS Code/Windows and Colab use."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from .fit_cs15 import run_cs15_smoke
from .fit_pcm import run_pcm_smoke
from .cef_model import CEFModel
from .conventions import DIRECT_LM
from .provenance import git_provenance, sha256_file, write_json
from .taipan_observables import (
    AdmissionPolicy,
    InputAudit,
    admitted_energy_rows,
    audit_observations,
    load_observations,
)
from .wavefunctions import export_wavefunctions


def _load_config(path: str | Path) -> tuple[dict[str, Any], Path, Path]:
    config_path = Path(path).expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    repository = config_path.parent.parent
    return config, config_path, repository


def _resolve(repository: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository / path


def _audit_payload(config: dict[str, Any], config_path: Path, repository: Path) -> dict[str, Any]:
    observables_path = _resolve(repository, config["inputs"]["observables"])
    rows = load_observations(observables_path)
    policy = AdmissionPolicy.from_mapping(config["inputs"].get("admission"))
    audit = audit_observations(rows, policy)
    return {
        "design_id": config["design_id"],
        "status": audit.status,
        "objective_readiness": (
            audit.objective_readiness.value if audit.objective_readiness is not None else None
        ),
        "production_ready": audit.production_ready,
        "full_joint_ready": audit.full_joint_ready,
        "counts": {
            "rows": audit.row_count,
            "admitted_energy": audit.admitted_energy_count,
            "admitted_detected_intensity": audit.admitted_detected_intensity_count,
            "admitted_censored": audit.admitted_censored_count,
        },
        "admissible_instrument_blocks": list(audit.admissible_instrument_blocks),
        "blockers": list(audit.blockers),
        "warnings": list(audit.warnings),
        "inputs": {
            "config": str(config_path),
            "config_sha256": sha256_file(config_path),
            "observables": str(observables_path),
            "observables_sha256": sha256_file(observables_path),
        },
        "git": git_provenance(repository),
    }


def audit_inputs(args: argparse.Namespace) -> int:
    config, config_path, repository = _load_config(args.config)
    payload = _audit_payload(config, config_path, repository)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _require_smoke(profile: str, config: dict[str, Any], audit: InputAudit) -> None:
    if profile == "smoke":
        return
    production = config["profiles"]["production"]
    if not production.get("enabled", False):
        raise SystemExit("Production profile is disabled pending independent review")
    required = production["requires_input_readiness"]
    if not audit.satisfies(required):
        raise SystemExit(f"Production input gate failed: {audit.status}; requires {required}")


def _candidate(config: dict[str, Any], repository: Path):
    rows = load_observations(_resolve(repository, config["inputs"]["observables"]))
    policy = AdmissionPolicy.from_mapping(config["inputs"].get("admission"))
    audit = audit_observations(rows, policy)
    admitted = admitted_energy_rows(rows)
    if len(admitted) != 1:
        raise SystemExit(f"Expected exactly one admitted manuscript-v1 energy candidate; found {len(admitted)}")
    return admitted[0], audit


def fit_pcm(args: argparse.Namespace) -> int:
    config, config_path, repository = _load_config(args.config)
    candidate, audit = _candidate(config, repository)
    _require_smoke(args.profile, config, audit)
    result = run_pcm_smoke(
        formal_parameters=config["pcm"]["formal_parameters_meV"],
        energy_meV=float(candidate.energy_meV),
        energy_sigma_meV=float(candidate.energy_sigma_meV),
        assignments=config["assignment"]["allowed_final_doublets"],
        scale_bounds=tuple(config["pcm"]["A1_scale_bounds"]),
        j=float(config["scientific_scope"]["J"]),
        g_j=float(config["scientific_scope"]["gJ"]),
    )
    payload = {
        "design_id": config["design_id"],
        "input_audit_status": audit.status,
        "production_intensity_fit_blocked": not audit.production_ready,
        "config_sha256": sha256_file(config_path),
        "git": git_provenance(repository),
        **result,
    }
    output = _resolve(repository, config["outputs"]["root"]) / "pcm_smoke.json"
    write_json(output, payload)
    print(json.dumps({"status": "SMOKE_ONLY", "output": str(output), "branches": len(result["branches"])}, indent=2))
    return 0


def fit_cs15(args: argparse.Namespace) -> int:
    config, config_path, repository = _load_config(args.config)
    candidate, audit = _candidate(config, repository)
    _require_smoke(args.profile, config, audit)
    seed_path = _resolve(repository, config["cs15"]["seed_bundle"])
    seed = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    profile = config["profiles"][args.profile]
    result = run_cs15_smoke(
        seed_parameters=seed["parameters"],
        energy_meV=float(candidate.energy_meV),
        energy_sigma_meV=float(candidate.energy_sigma_meV),
        assignments=config["assignment"]["allowed_final_doublets"],
        h_bounds=tuple(config["cs15"]["h_bounds_meV"]),
        max_evaluations=int(profile["cs15_max_evaluations"]),
        random_seed=int(profile["random_seed"]),
        boundary_fraction=float(config["cs15"]["boundary_fraction"]),
        j=float(config["scientific_scope"]["J"]),
        g_j=float(config["scientific_scope"]["gJ"]),
    )
    payload = {
        "design_id": config["design_id"],
        "input_audit_status": audit.status,
        "production_intensity_fit_blocked": not audit.production_ready,
        "seed_bundle_sha256": sha256_file(seed_path),
        "config_sha256": sha256_file(config_path),
        "git": git_provenance(repository),
        **result,
    }
    output = _resolve(repository, config["outputs"]["root"]) / "cs15_smoke.json"
    write_json(output, payload)
    wavefunction_root = output.parent / "wavefunctions"
    for branch in result["branches"]:
        system = CEFModel.from_coefficients(
            branch["direct_parameters_meV"], DIRECT_LM,
            j=float(config["scientific_scope"]["J"]),
            g_j=float(config["scientific_scope"]["gJ"]),
        ).eigensystem()
        export_wavefunctions(
            wavefunction_root / branch["solution_id"],
            tuple(system.pair(index) for index in range(len(system.doublet_energies_meV))),
            j=float(config["scientific_scope"]["J"]),
            g_j=float(config["scientific_scope"]["gJ"]),
        )
    print(json.dumps({"status": "SMOKE_ONLY", "output": str(output), "branches": len(result["branches"])}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cef_fit.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit-inputs", help="Audit manuscript input provenance")
    audit.add_argument("--config", required=True)
    audit.set_defaults(function=audit_inputs)
    for name, function in (("fit-pcm", fit_pcm), ("fit-cs15", fit_cs15)):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--profile", choices=("smoke", "production"), default="smoke")
        command.set_defaults(function=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return int(arguments.function(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
