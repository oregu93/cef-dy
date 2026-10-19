"""Model-dependent conditional-energy analysis with no scalar energy admission."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml
from scipy.optimize import minimize

from .cef_model import CEFModel, Eigensystem
from .conventions import DIRECT_LABELS, DIRECT_LM, direct_parameters_to_canonical
from .fit_cs15 import h_to_parameters, operator_scales
from .g_tensor import g_tensor
from .operators import stevens_operator
from .pcm_model import UniformPCM
from .provenance import git_provenance, sha256_file
from .wavefunctions import export_wavefunctions, projector_overlap


PRIMARY_SOURCE_ROLE = "COMMON_CENTROID_CONDITIONAL"
STRESS_SOURCE_ROLE = "BLOCK_STRESS_TEST_ONLY"
PRIMARY_ROLE = "PRIMARY_CONDITIONAL"
STRESS_ROLE = "STRESS_ONLY"
SCIENTIFIC_LABELS = (
    "MODEL_DEPENDENT_ENERGY",
    "NO_UNIQUE_HAMILTONIAN_CLAIM",
    "NO_INTENSITY_CONSTRAINT",
    "NO_EXCHANGE",
)
SCIENTIFIC_LABEL = "|".join(SCIENTIFIC_LABELS)


@dataclass(frozen=True)
class EnergyVariant:
    energy_variant_id: str
    energy_meV: float
    conditional_sigma_meV: float
    analysis_model: str
    background_model: str
    window: float
    width_treatment: str
    block_scope: str
    role: str
    source_role: str
    source_scan_ids: tuple[str, ...]

    def record(self) -> dict[str, object]:
        return {
            "energy_variant_id": self.energy_variant_id,
            "energy_meV": self.energy_meV,
            "conditional_sigma_meV": self.conditional_sigma_meV,
            "analysis_model": self.analysis_model,
            "background_model": self.background_model,
            "window": self.window,
            "width_treatment": self.width_treatment,
            "block_scope": self.block_scope,
            "role": self.role,
            "source_role": self.source_role,
            "source_scan_ids": ";".join(self.source_scan_ids),
        }


def _resolve(repository: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository / path


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty result table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _projector_fingerprint(projectors: Sequence[np.ndarray]) -> str:
    values = np.stack([np.asarray(projector, dtype=complex) for projector in projectors])
    canonical = np.stack((values.real, values.imag), axis=-1).astype("<f8", copy=False)
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def conditional_deviance(predicted_energy_meV: float, variant: EnergyVariant) -> float:
    """Evaluate exactly one alternative reduction; variants are never summed."""
    residual = (float(predicted_energy_meV) - variant.energy_meV) / variant.conditional_sigma_meV
    return float(residual * residual)


def load_energy_variants(
    path: str | Path,
    expected_primary: int = 18,
    expected_stress: int = 18,
) -> tuple[EnergyVariant, ...]:
    variants: list[EnergyVariant] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            source_role = raw["role"]
            if source_role == PRIMARY_SOURCE_ROLE:
                role = PRIMARY_ROLE
                analysis_model = "JOINT_SHARED_CENTROID"
                block_scope = "ALL_INSTRUMENT_BLOCKS"
            elif source_role == STRESS_SOURCE_ROLE:
                role = STRESS_ROLE
                analysis_model = "SINGLE_BLOCK_CENTROID"
                block_scope = raw["variant_id"].split("_w", 1)[0].removeprefix("block_")
            else:
                raise ValueError(f"Unknown W02 energy-variant role: {source_role}")
            energy = float(raw["energy_meV"])
            sigma = float(raw["conditional_sigma_meV"])
            if not np.isfinite(energy) or not np.isfinite(sigma) or sigma <= 0:
                raise ValueError(f"Invalid conditional energy row: {raw['variant_id']}")
            variants.append(EnergyVariant(
                energy_variant_id=raw["variant_id"],
                energy_meV=energy,
                conditional_sigma_meV=sigma,
                analysis_model=analysis_model,
                background_model=f"POLYNOMIAL_ORDER_{int(raw['background_order'])}",
                window=float(raw["half_window_meV"]),
                width_treatment=raw["width_mode"],
                block_scope=block_scope,
                role=role,
                source_role=source_role,
                source_scan_ids=tuple(item for item in raw["source_scan_ids"].split(";") if item),
            ))
    identifiers = [variant.energy_variant_id for variant in variants]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate energy_variant_id values")
    primary_count = sum(variant.role == PRIMARY_ROLE for variant in variants)
    stress_count = sum(variant.role == STRESS_ROLE for variant in variants)
    if (primary_count, stress_count) != (expected_primary, expected_stress):
        raise ValueError(
            f"W02 variant count mismatch: primary={primary_count}, stress={stress_count}"
        )
    return tuple(variants)


def _background_order(variant: EnergyVariant) -> int:
    return int(variant.background_model.rsplit("_", 1)[1])


def select_cs15_variants(variants: Iterable[EnergyVariant]) -> tuple[dict[str, object], ...]:
    variants = tuple(variants)
    primary = tuple(item for item in variants if item.role == PRIMARY_ROLE)
    stress = tuple(item for item in variants if item.role == STRESS_ROLE)
    if not primary or not stress:
        raise ValueError("Both primary and stress variants are required")

    selected: dict[str, dict[str, object]] = {}

    def add(variant: EnergyVariant, reason: str) -> None:
        record = selected.setdefault(variant.energy_variant_id, {
            **variant.record(), "selection_reasons": []
        })
        record["selection_reasons"].append(reason)

    add(min(primary, key=lambda item: (item.energy_meV, item.energy_variant_id)), "PRIMARY_MIN_CENTROID")
    add(max(primary, key=lambda item: (item.energy_meV, item.energy_variant_id)), "PRIMARY_MAX_CENTROID")

    background_range = max(_background_order(item) for item in primary) - min(
        _background_order(item) for item in primary
    )
    window_range = max(item.window for item in primary) - min(item.window for item in primary)

    def metadata_distance(first: EnergyVariant, second: EnergyVariant) -> float:
        background = abs(_background_order(first) - _background_order(second)) / max(
            1, background_range
        )
        window = abs(first.window - second.window) / max(1.0, window_range)
        width = float(first.width_treatment != second.width_treatment)
        return background + window + width

    medoid = min(
        primary,
        key=lambda candidate: (
            sum(metadata_distance(candidate, other) for other in primary),
            candidate.energy_variant_id,
        ),
    )
    add(medoid, "PRIMARY_METADATA_MEDOID")

    block_scopes = sorted({item.block_scope for item in stress})
    for block_scope in block_scopes:
        block = tuple(item for item in stress if item.block_scope == block_scope)
        add(
            min(block, key=lambda item: (item.energy_meV, item.energy_variant_id)),
            f"STRESS_{block_scope}_MIN_CENTROID",
        )
        add(
            max(block, key=lambda item: (item.energy_meV, item.energy_variant_id)),
            f"STRESS_{block_scope}_MAX_CENTROID",
        )

    records = []
    for identifier in sorted(selected):
        record = dict(selected[identifier])
        record["selection_reasons"] = tuple(record["selection_reasons"])
        records.append(record)
    return tuple(records)


def _model_observables(
    model: CEFModel, system: Eigensystem
) -> tuple[list[float], list[float], list[list[float]], str]:
    strengths = [float(item.powder_strength) for item in model.ground_transitions(system)]
    ground_g = g_tensor(system.pair(0), j=model.j, g_j=model.g_j)
    fingerprint = _projector_fingerprint(system.projectors)
    return (
        strengths,
        ground_g.principal_values.tolist(),
        ground_g.principal_axes.tolist(),
        fingerprint,
    )


def run_pcm_conditional(
    variants: Iterable[EnergyVariant],
    formal_parameters: Mapping[str, float],
    assignments: Sequence[int],
    scale_bounds: tuple[float, float],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> tuple[dict[str, object], ...]:
    formal_model = CEFModel.from_coefficients(formal_parameters, DIRECT_LM, j=j, g_j=g_j)
    formal_system = formal_model.eigensystem()
    family = UniformPCM(formal_model.hamiltonian_meV, j=j, g_j=g_j)
    lower, upper = map(float, scale_bounds)
    if not 0 < lower < upper:
        raise ValueError("Invalid PCM M0 scale bounds")
    rows: list[dict[str, object]] = []
    for variant in variants:
        for assignment in assignments:
            unscaled_energy = float(formal_system.doublet_energies_meV[assignment])
            unconstrained_scale = variant.energy_meV / unscaled_energy
            scale = float(np.clip(unconstrained_scale, lower, upper))
            model = family.model(scale)
            system = model.eigensystem()
            predicted = float(system.doublet_energies_meV[assignment])
            q_value = conditional_deviance(predicted, variant)
            boundary_side = "NONE"
            if np.isclose(scale, lower, atol=1e-12, rtol=0):
                boundary_side = "LOWER"
            elif np.isclose(scale, upper, atol=1e-12, rtol=0):
                boundary_side = "UPPER"
            strengths, g_values, g_axes, fingerprint = _model_observables(model, system)
            rows.append({
                "scientific_labels": SCIENTIFIC_LABEL,
                "execution_class": "MODEL_DEPENDENT_ENERGY_CONDITIONAL",
                "model_id": "MOD-PCM-M0",
                "solution_id": f"PCM-M0__{variant.energy_variant_id}__D{assignment}",
                "energy_variant_id": variant.energy_variant_id,
                "variant_role": variant.role,
                "assignment": f"D0->D{assignment}",
                "assignment_final_doublet": int(assignment),
                "observed_conditional_energy_meV": variant.energy_meV,
                "conditional_sigma_meV": variant.conditional_sigma_meV,
                "scale": scale,
                "unconstrained_scale": unconstrained_scale,
                "scale_boundary_occupied": boundary_side != "NONE",
                "scale_boundary_side": boundary_side,
                "predicted_assignment_energy_meV": predicted,
                "conditional_q": q_value,
                "fit_within_one_conditional_sigma": q_value <= 1.0,
                "doublet_energies_meV": _json(system.doublet_energies_meV.tolist()),
                "transition_strengths": _json(strengths),
                "ground_g_principal_values": _json(g_values),
                "ground_g_principal_axes_direct": _json(g_axes),
                "wavefunction_projector_identity": fingerprint,
            })
    return tuple(rows)


def summarize_pcm_robustness(
    rows: Iterable[Mapping[str, object]], assignments: Sequence[int]
) -> tuple[dict[str, object], ...]:
    rows = tuple(rows)
    summaries: list[dict[str, object]] = []
    for assignment in assignments:
        branch = tuple(row for row in rows if row["assignment_final_doublet"] == assignment)
        primary = tuple(row for row in branch if row["variant_role"] == PRIMARY_ROLE)
        stress = tuple(row for row in branch if row["variant_role"] == STRESS_ROLE)
        robust_primary = bool(primary) and all(
            not row["scale_boundary_occupied"] and row["fit_within_one_conditional_sigma"]
            for row in primary
        )
        robust_stress = bool(stress) and all(
            not row["scale_boundary_occupied"] and row["fit_within_one_conditional_sigma"]
            for row in stress
        )
        primary_levels = np.array([json.loads(str(row["doublet_energies_meV"])) for row in primary])
        level_ranges = [
            [float(primary_levels[:, index].min()), float(primary_levels[:, index].max())]
            for index in range(primary_levels.shape[1])
        ]
        summaries.append({
            "scientific_labels": SCIENTIFIC_LABEL,
            "assignment": f"D0->D{assignment}",
            "assignment_final_doublet": int(assignment),
            "primary_variant_count": len(primary),
            "stress_variant_count": len(stress),
            "robust_across_primary_variants": robust_primary,
            "robust_across_stress_variants": robust_stress,
            "classification": "ROBUST_ACROSS_PRIMARY_VARIANTS" if robust_primary else "VARIANT_DEPENDENT",
            "primary_scale_min": min(float(row["scale"]) for row in primary),
            "primary_scale_max": max(float(row["scale"]) for row in primary),
            "primary_max_conditional_q": max(float(row["conditional_q"]) for row in primary),
            "primary_boundary_variant_count": sum(bool(row["scale_boundary_occupied"]) for row in primary),
            "stress_boundary_variant_count": sum(bool(row["scale_boundary_occupied"]) for row in stress),
            "primary_level_ranges_meV": _json(level_ranges),
            "primary_projector_identity_count": len({row["wavefunction_projector_identity"] for row in primary}),
        })
    return tuple(summaries)


def _normalized_operator_basis(j: float) -> np.ndarray:
    scales = operator_scales(j)
    operators = np.stack([stevens_operator(j, rank, m) for rank, m in DIRECT_LM])
    return operators / scales[:, None, None]


def _levels_from_h(h_coordinates: Sequence[float], normalized_operators: np.ndarray) -> np.ndarray:
    hamiltonian = np.tensordot(np.asarray(h_coordinates, dtype=float), normalized_operators, axes=1)
    eigenvalues = np.linalg.eigvalsh(hamiltonian).real
    eigenvalues -= eigenvalues[0]
    levels = np.array([
        np.mean(eigenvalues[index:index + 2])
        for index in range(0, len(eigenvalues), 2)
    ])
    levels -= levels[0]
    return levels


def _restart_seed(base_seed: int, variant_id: str, assignment: int) -> int:
    digest = hashlib.sha256(f"{variant_id}|D{assignment}".encode("utf-8")).hexdigest()
    return int(base_seed + int(digest[:8], 16) % 1_000_000)


def run_cs15_global_search(
    variants: Iterable[EnergyVariant],
    assignments: Sequence[int],
    h_bounds: tuple[float, float],
    sigma0: float,
    max_cma_evaluations: int,
    max_polish_evaluations: int,
    restart_seeds: Sequence[int],
    fit_acceptance_q_max: float,
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    try:
        import cma
    except ImportError as error:
        raise RuntimeError("CMA-ES package is required for conditional Cs15 analysis") from error

    variants = tuple(variants)
    lower, upper = map(float, h_bounds)
    if not lower < upper or sigma0 <= 0 or len(restart_seeds) < 2:
        raise ValueError("Invalid Cs15 global-search configuration")
    normalized_operators = _normalized_operator_basis(j)
    bounds = [(lower, upper)] * len(DIRECT_LM)
    rows: list[dict[str, object]] = []
    cache: dict[str, dict[str, object]] = {}

    for variant_index, variant in enumerate(variants, start=1):
        for assignment in assignments:
            for restart_index, base_seed in enumerate(restart_seeds, start=1):
                seed = _restart_seed(int(base_seed), variant.energy_variant_id, int(assignment))
                rng = np.random.default_rng(seed)
                x0 = rng.uniform(0.55 * lower, 0.55 * upper, size=len(DIRECT_LM))

                def objective(h_values: Sequence[float]) -> float:
                    levels = _levels_from_h(h_values, normalized_operators)
                    return conditional_deviance(float(levels[assignment]), variant)

                optimizer = cma.CMAEvolutionStrategy(
                    x0.tolist(),
                    float(sigma0),
                    {
                        "bounds": [lower, upper],
                        "seed": seed,
                        "maxfevals": int(max_cma_evaluations),
                        "verb_disp": 0,
                        "verb_log": 0,
                        "verbose": -9,
                    },
                )
                while not optimizer.stop():
                    candidates = optimizer.ask()
                    optimizer.tell(candidates, [objective(candidate) for candidate in candidates])
                cma_best = np.asarray(optimizer.result.xbest, dtype=float)
                polished = minimize(
                    objective,
                    cma_best,
                    method="L-BFGS-B",
                    bounds=bounds,
                    options={
                        "maxfun": int(max_polish_evaluations),
                        "maxiter": int(max_polish_evaluations),
                        "ftol": 1e-14,
                    },
                )
                best_h = np.asarray(polished.x, dtype=float)
                parameters = h_to_parameters(best_h, j=j)
                model = CEFModel.from_coefficients(parameters, DIRECT_LM, j=j, g_j=g_j)
                system = model.eigensystem()
                predicted = float(system.doublet_energies_meV[assignment])
                q_value = conditional_deviance(predicted, variant)
                canonical = direct_parameters_to_canonical(parameters, j=j)
                strengths, g_values, g_axes, fingerprint = _model_observables(model, system)
                boundary_distance = np.minimum(best_h - lower, upper - best_h)
                boundary = bool(np.any(boundary_distance <= 0.02 * (upper - lower)))
                solution_id = (
                    f"CS15__{variant.energy_variant_id}__D{assignment}__R{restart_index}"
                )
                row = {
                    "scientific_labels": SCIENTIFIC_LABEL,
                    "execution_class": "MODEL_DEPENDENT_ENERGY_CONDITIONAL",
                    "model_id": "MOD-CEF-CS15",
                    "solution_id": solution_id,
                    "energy_variant_id": variant.energy_variant_id,
                    "variant_role": variant.role,
                    "assignment": f"D0->D{assignment}",
                    "assignment_final_doublet": int(assignment),
                    "restart": int(restart_index),
                    "seed": int(seed),
                    "observed_conditional_energy_meV": variant.energy_meV,
                    "conditional_sigma_meV": variant.conditional_sigma_meV,
                    "predicted_assignment_energy_meV": predicted,
                    "conditional_q": q_value,
                    "fit_accepted": q_value <= fit_acceptance_q_max,
                    "cma_evaluations": int(optimizer.result.evaluations),
                    "polish_evaluations": int(polished.nfev),
                    "cma_stop": _json(dict(optimizer.stop())),
                    "polish_success": bool(polished.success),
                    "search_boundary_occupied": boundary,
                    "h_coordinates_meV": _json(best_h.tolist()),
                    "direct_parameters_meV": _json(parameters),
                    "canonical_parameters_meV": _json(canonical.coefficients),
                    "canonical_projection_relative_residual": float(canonical.relative_residual),
                    "doublet_energies_meV": _json(system.doublet_energies_meV.tolist()),
                    "transition_strengths": _json(strengths),
                    "ground_g_principal_values": _json(g_values),
                    "ground_g_principal_axes_direct": _json(g_axes),
                    "wavefunction_projector_identity": fingerprint,
                    "parameter_family_id": "",
                }
                rows.append(row)
                cache[solution_id] = {
                    "model": model,
                    "system": system,
                    "h": best_h,
                    "ground_projector": system.projectors[0],
                }
        print(
            f"CS15 variant {variant_index}/{len(variants)} complete: {variant.energy_variant_id}",
            flush=True,
        )
    return rows, cache


def assign_parameter_families(
    rows: list[dict[str, object]],
    cache: Mapping[str, Mapping[str, object]],
    h_bounds: tuple[float, float],
    rms_fraction_threshold: float,
) -> tuple[dict[str, object], ...]:
    lower, upper = map(float, h_bounds)
    width = upper - lower
    family_summaries: list[dict[str, object]] = []
    for assignment in sorted({int(row["assignment_final_doublet"]) for row in rows}):
        branch = sorted(
            (
                row for row in rows
                if int(row["assignment_final_doublet"]) == assignment and bool(row["fit_accepted"])
            ),
            key=lambda row: (float(row["conditional_q"]), str(row["solution_id"])),
        )
        representatives: list[dict[str, object]] = []
        for row in branch:
            h_values = np.asarray(cache[str(row["solution_id"])]["h"], dtype=float)
            family_index = None
            for index, representative in enumerate(representatives):
                rep_h = np.asarray(cache[str(representative["solution_id"])]["h"], dtype=float)
                rms_fraction = float(np.sqrt(np.mean(((h_values - rep_h) / width) ** 2)))
                if rms_fraction <= rms_fraction_threshold:
                    family_index = index
                    break
            if family_index is None:
                family_index = len(representatives)
                representatives.append(row)
            row["parameter_family_id"] = f"D{assignment}-PF{family_index + 1:03d}"

        for family_id in sorted({str(row["parameter_family_id"]) for row in branch}):
            members = tuple(row for row in branch if row["parameter_family_id"] == family_id)
            h_values = np.array([cache[str(row["solution_id"])]["h"] for row in members])
            levels = np.array([json.loads(str(row["doublet_energies_meV"])) for row in members])
            strengths = np.array([json.loads(str(row["transition_strengths"])) for row in members])
            g_values = np.array([json.loads(str(row["ground_g_principal_values"])) for row in members])
            projectors = [
                np.asarray(cache[str(row["solution_id"])]["ground_projector"], dtype=complex)
                for row in members
            ]
            overlaps = [
                projector_overlap(projectors[first], projectors[second])
                for first in range(len(projectors))
                for second in range(first + 1, len(projectors))
            ]
            family_summaries.append({
                "scientific_labels": SCIENTIFIC_LABEL,
                "assignment": f"D0->D{assignment}",
                "parameter_family_id": family_id,
                "member_count": len(members),
                "variant_count": len({row["energy_variant_id"] for row in members}),
                "restart_count": len({row["seed"] for row in members}),
                "conditional_q_min": min(float(row["conditional_q"]) for row in members),
                "conditional_q_max": max(float(row["conditional_q"]) for row in members),
                "parameter_h_min_meV": _json(h_values.min(axis=0).tolist()),
                "parameter_h_max_meV": _json(h_values.max(axis=0).tolist()),
                "level_min_meV": _json(levels.min(axis=0).tolist()),
                "level_max_meV": _json(levels.max(axis=0).tolist()),
                "transition_strength_min": _json(strengths.min(axis=0).tolist()),
                "transition_strength_max": _json(strengths.max(axis=0).tolist()),
                "ground_g_min": _json(g_values.min(axis=0).tolist()),
                "ground_g_max": _json(g_values.max(axis=0).tolist()),
                "minimum_within_family_ground_projector_overlap": min(overlaps) if overlaps else 1.0,
                "family_definition": (
                    f"GREEDY_H_COORDINATE_RMS_FRACTION_LE_{rms_fraction_threshold}"
                ),
            })
    return tuple(family_summaries)


def evaluate_historical_solutions(
    bundle_paths: Sequence[Path],
    primary_variants: Iterable[EnergyVariant],
    assignments: Sequence[int],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for path in bundle_paths:
        bundle = yaml.safe_load(path.read_text(encoding="utf-8"))
        model = CEFModel.from_coefficients(bundle["parameters"], DIRECT_LM, j=j, g_j=g_j)
        system = model.eigensystem()
        strengths, g_values, g_axes, fingerprint = _model_observables(model, system)
        for variant in primary_variants:
            for assignment in assignments:
                predicted = float(system.doublet_energies_meV[assignment])
                rows.append({
                    "scientific_labels": SCIENTIFIC_LABEL,
                    "evaluation_mode": "FROZEN_HISTORICAL_NO_REFIT",
                    "parameter_set_id": bundle["parameter_set_id"],
                    "prediction_bundle_id": bundle["prediction_bundle_id"],
                    "source_bundle": str(path),
                    "energy_variant_id": variant.energy_variant_id,
                    "assignment": f"D0->D{assignment}",
                    "assignment_final_doublet": int(assignment),
                    "observed_conditional_energy_meV": variant.energy_meV,
                    "conditional_sigma_meV": variant.conditional_sigma_meV,
                    "predicted_assignment_energy_meV": predicted,
                    "conditional_q": conditional_deviance(predicted, variant),
                    "transition_strength": strengths[assignment - 1],
                    "ground_g_principal_values": _json(g_values),
                    "ground_g_principal_axes_direct": _json(g_axes),
                    "wavefunction_projector_identity": fingerprint,
                })
    return tuple(rows)


def _export_representative(
    output_root: Path,
    model_class: str,
    solution_id: str,
    energy_variant_id: str,
    assignment: str,
    model: CEFModel,
    system: Eigensystem,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    safe_id = solution_id.replace("/", "_")
    stem = output_root / "wavefunctions" / safe_id
    export_wavefunctions(
        stem,
        tuple(system.pair(index) for index in range(len(system.doublet_energies_meV))),
        j=model.j,
        g_j=model.g_j,
        metadata={
            "scientific_labels": list(SCIENTIFIC_LABELS),
            "execution_class": "MODEL_DEPENDENT_ENERGY_CONDITIONAL",
            "model_class": model_class,
            "solution_id": solution_id,
            "energy_variant_id": energy_variant_id,
            "assignment": assignment,
        },
    )
    transition_tensors = np.stack([
        model.transition_tensor(0, final, system)
        for final in range(1, len(system.doublet_energies_meV))
    ])
    all_g = [g_tensor(system.pair(index), j=model.j, g_j=model.g_j) for index in range(8)]
    np.savez_compressed(
        stem.with_name(stem.name + "__observables.npz"),
        doublet_energies_meV=system.doublet_energies_meV,
        transition_tensors=transition_tensors,
        g_principal_values=np.stack([item.principal_values for item in all_g]),
        g_principal_axes_direct=np.stack([item.principal_axes for item in all_g]),
        scientific_labels=np.array(SCIENTIFIC_LABELS),
        execution_class=np.array("MODEL_DEPENDENT_ENERGY_CONDITIONAL"),
        solution_id=np.array(solution_id),
    )

    levels = [{
        "scientific_labels": SCIENTIFIC_LABEL,
        "model_class": model_class,
        "solution_id": solution_id,
        "energy_variant_id": energy_variant_id,
        "assignment": assignment,
        "doublet": f"D{index}",
        "energy_meV": float(energy),
    } for index, energy in enumerate(system.doublet_energies_meV)]
    strengths = [{
        "scientific_labels": SCIENTIFIC_LABEL,
        "model_class": model_class,
        "solution_id": solution_id,
        "energy_variant_id": energy_variant_id,
        "assignment": assignment,
        "transition": f"D0->D{final}",
        "energy_meV": float(system.doublet_energies_meV[final]),
        "powder_strength": float(np.trace(transition_tensors[final - 1]).real),
        "tensor_real": _json(transition_tensors[final - 1].real.tolist()),
        "tensor_imag": _json(transition_tensors[final - 1].imag.tolist()),
    } for final in range(1, len(system.doublet_energies_meV))]
    g_rows: list[dict[str, object]] = []
    for doublet, tensor in enumerate(all_g):
        for principal_index in range(3):
            g_rows.append({
                "scientific_labels": SCIENTIFIC_LABEL,
                "model_class": model_class,
                "solution_id": solution_id,
                "energy_variant_id": energy_variant_id,
                "assignment": assignment,
                "doublet": f"D{doublet}",
                "principal_index": principal_index + 1,
                "principal_g": float(tensor.principal_values[principal_index]),
                "axis_x_direct_b": float(tensor.principal_axes[0, principal_index]),
                "axis_y_direct_c": float(tensor.principal_axes[1, principal_index]),
                "axis_z_direct_a": float(tensor.principal_axes[2, principal_index]),
            })
    return levels, strengths, g_rows


def export_representative_families(
    output_root: Path,
    variants: Sequence[EnergyVariant],
    selection_records: Sequence[Mapping[str, object]],
    pcm_rows: Sequence[Mapping[str, object]],
    formal_parameters: Mapping[str, float],
    cs15_rows: Sequence[Mapping[str, object]],
    cs15_cache: Mapping[str, Mapping[str, object]],
    historical_bundle_paths: Sequence[Path],
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> None:
    levels: list[dict[str, object]] = []
    strengths: list[dict[str, object]] = []
    g_rows: list[dict[str, object]] = []
    by_id = {variant.energy_variant_id: variant for variant in variants}
    medoid_id = next(
        str(record["energy_variant_id"])
        for record in selection_records
        if "PRIMARY_METADATA_MEDOID" in record["selection_reasons"]
    )

    formal_model = CEFModel.from_coefficients(formal_parameters, DIRECT_LM, j=j, g_j=g_j)
    pcm_family = UniformPCM(formal_model.hamiltonian_meV, j=j, g_j=g_j)
    for row in pcm_rows:
        if row["energy_variant_id"] != medoid_id:
            continue
        model = pcm_family.model(float(row["scale"]))
        system = model.eigensystem()
        exported = _export_representative(
            output_root, "PCM_M0", str(row["solution_id"]), medoid_id,
            str(row["assignment"]), model, system,
        )
        levels.extend(exported[0]); strengths.extend(exported[1]); g_rows.extend(exported[2])

    accepted = [row for row in cs15_rows if bool(row["fit_accepted"])]
    representative_cs15: dict[tuple[int, str], Mapping[str, object]] = {}
    for row in accepted:
        key = (int(row["assignment_final_doublet"]), str(row["parameter_family_id"]))
        current = representative_cs15.get(key)
        if current is None or (float(row["conditional_q"]), str(row["solution_id"])) < (
            float(current["conditional_q"]), str(current["solution_id"])
        ):
            representative_cs15[key] = row
    for row in representative_cs15.values():
        cached = cs15_cache[str(row["solution_id"])]
        exported = _export_representative(
            output_root, "CS15_DIAGNOSTIC", str(row["solution_id"]),
            str(row["energy_variant_id"]), str(row["assignment"]),
            cached["model"], cached["system"],
        )
        levels.extend(exported[0]); strengths.extend(exported[1]); g_rows.extend(exported[2])

    for path in historical_bundle_paths:
        bundle = yaml.safe_load(path.read_text(encoding="utf-8"))
        model = CEFModel.from_coefficients(bundle["parameters"], DIRECT_LM, j=j, g_j=g_j)
        system = model.eigensystem()
        exported = _export_representative(
            output_root, "HISTORICAL_FROZEN", bundle["parameter_set_id"], medoid_id,
            "NO_REFIT", model, system,
        )
        levels.extend(exported[0]); strengths.extend(exported[1]); g_rows.extend(exported[2])

    _write_csv(output_root / "representative_levels.csv", levels)
    _write_csv(output_root / "representative_transition_strengths.csv", strengths)
    _write_csv(output_root / "representative_g_tensors.csv", g_rows)


def _global_projector_overlap_min(
    rows: Sequence[Mapping[str, object]], cache: Mapping[str, Mapping[str, object]]
) -> float:
    accepted = [row for row in rows if bool(row["fit_accepted"])]
    projectors = [np.asarray(cache[str(row["solution_id"])]["ground_projector"]) for row in accepted]
    if len(projectors) < 2:
        return 1.0
    return min(
        projector_overlap(projectors[first], projectors[second])
        for first in range(len(projectors))
        for second in range(first + 1, len(projectors))
    )


def build_robustness_matrix(
    variants: Sequence[EnergyVariant],
    pcm_summary: Sequence[Mapping[str, object]],
    cs15_rows: Sequence[Mapping[str, object]],
    cs15_cache: Mapping[str, Mapping[str, object]],
    cs15_family_summary: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    primary = [variant for variant in variants if variant.role == PRIMARY_ROLE]
    energy_min = min(item.energy_meV for item in primary)
    energy_max = max(item.energy_meV for item in primary)
    accepted = [row for row in cs15_rows if bool(row["fit_accepted"])]
    projector_min = _global_projector_overlap_min(cs15_rows, cs15_cache)
    rows: list[dict[str, object]] = [{
        "scientific_labels": SCIENTIFIC_LABEL,
        "question": "single_scalar_TAIPAN_energy",
        "model_scope": "W02_PRIMARY_CONDITIONAL_ENSEMBLE",
        "classification": "VARIANT_DEPENDENT",
        "evidence": f"18 alternatives span {energy_min:.12g} to {energy_max:.12g} meV",
        "caution": "Alternative reductions of the same data; never sum their likelihoods",
    }]
    for summary in pcm_summary:
        rows.append({
            "scientific_labels": SCIENTIFIC_LABEL,
            "question": f"PCM_{summary['assignment']}_viability",
            "model_scope": "PCM_M0_ALL_PRIMARY_VARIANTS",
            "classification": summary["classification"],
            "evidence": (
                f"primary_boundary_count={summary['primary_boundary_variant_count']};"
                f"max_q={float(summary['primary_max_conditional_q']):.6g}"
            ),
            "caution": "Conditional one-parameter structural baseline, not a unique CEF determination",
        })
    rows.extend((
        {
            "scientific_labels": SCIENTIFIC_LABEL,
            "question": "Cs15_parameter_identifiability",
            "model_scope": "BOUNDED_REPRESENTATIVE_GLOBAL_SEARCH",
            "classification": "VARIANT_DEPENDENT",
            "evidence": (
                f"accepted_solutions={len(accepted)};"
                f"operational_parameter_families={len(cs15_family_summary)}"
            ),
            "caution": "Operational families are not confidence regions",
        },
        {
            "scientific_labels": SCIENTIFIC_LABEL,
            "question": "Cs15_ground_doublet_projector_stability",
            "model_scope": "BOUNDED_REPRESENTATIVE_GLOBAL_SEARCH",
            "classification": "ROBUST_ACROSS_PRIMARY_VARIANTS" if projector_min >= 0.95 else "VARIANT_DEPENDENT",
            "evidence": f"minimum_pairwise_projector_overlap={projector_min:.12g}",
            "caution": "Search demonstrates compatible families; it does not sample a posterior",
        },
    ))
    return tuple(rows)


def _scientific_summary(
    variants: Sequence[EnergyVariant],
    pcm_summary: Sequence[Mapping[str, object]],
    cs15_rows: Sequence[Mapping[str, object]],
    cs15_cache: Mapping[str, Mapping[str, object]],
    cs15_family_summary: Sequence[Mapping[str, object]],
    historical_rows: Sequence[Mapping[str, object]],
    mh_status: str,
) -> str:
    primary = [item for item in variants if item.role == PRIMARY_ROLE]
    stress = [item for item in variants if item.role == STRESS_ROLE]
    energy_min = min(item.energy_meV for item in primary)
    energy_max = max(item.energy_meV for item in primary)
    stress_min = min(item.energy_meV for item in stress)
    stress_max = max(item.energy_meV for item in stress)
    pcm_remaining = [
        str(row["assignment"]) for row in pcm_summary
        if bool(row["robust_across_primary_variants"])
    ]
    pcm_stress = [
        str(row["assignment"]) for row in pcm_summary
        if bool(row["robust_across_stress_variants"])
    ]
    accepted = [row for row in cs15_rows if bool(row["fit_accepted"])]
    cs15_assignments = sorted({str(row["assignment"]) for row in accepted})
    projector_min = _global_projector_overlap_min(cs15_rows, cs15_cache)
    g_values = np.array([
        json.loads(str(row["ground_g_principal_values"])) for row in accepted
    ])
    g_ranges = [
        [float(g_values[:, index].min()), float(g_values[:, index].max())]
        for index in range(3)
    ] if len(g_values) else []
    boundary_count = sum(bool(row["search_boundary_occupied"]) for row in cs15_rows)
    historical_lines = []
    for parameter_set in sorted({str(row["parameter_set_id"]) for row in historical_rows}):
        d2 = [
            float(row["conditional_q"]) for row in historical_rows
            if row["parameter_set_id"] == parameter_set
            and int(row["assignment_final_doublet"]) == 2
        ]
        historical_lines.append(
            f"- `{parameter_set}`: D2 q range `{min(d2):.3f}`–`{max(d2):.3f}`; "
            f"`{sum(value <= 1.0 for value in d2)}/18` primary variants within q <= 1."
        )
    return f"""# Model-dependent conditional-energy analysis v1

Required labels: `{SCIENTIFIC_LABEL}`.

## A. What TAIPAN currently establishes

W02 supports an excitation feature near 18 meV only through 18 alternative
primary conditional reductions of the same scans. There is no admitted scalar
TAIPAN energy and no likelihood is formed by summing variants.

## B. Centroid model dependence

The primary joint-centroid variants span `{energy_min:.6f}` to `{energy_max:.6f}`
meV (full span `{energy_max - energy_min:.6f}` meV). Single-block stress variants
span `{stress_min:.6f}` to `{stress_max:.6f}` meV. These ranges describe analysis
model dependence, not a statistical confidence interval.

## C. One-parameter PCM M0

Assignments robustly inside the scale box across all primary variants:
`{', '.join(pcm_remaining) if pcm_remaining else 'none'}`. Assignments that also
remain inside the scale box across all single-block stress variants:
`{', '.join(pcm_stress) if pcm_stress else 'none'}`. PCM M0 is quantitatively
interpretable as a one-scale conditional baseline; it does not identify a
general CEF Hamiltonian. Because M0 is a uniform positive scale, its projectors,
transition strengths, and g tensors are invariant; the predicted level-energy
scale changes with the W02 variant and assignment.

## D. Fifteen-parameter Cs15 model

The bounded representative CMA-ES campaign found `{len(accepted)}` accepted
conditional solutions in `{len(cs15_family_summary)}` operational parameter
families. Compatible assignments were `{', '.join(cs15_assignments)}`. One
energy condition cannot identify 15 coefficients, rank a unique solution, or
define a confidence region. `{boundary_count}/{len(cs15_rows)}` solutions touch
the operational search-boundary margin. The family labels are descriptive
search outcomes, not confidence regions or optimizer probabilities.

## Historical R3/R5/R7 continuity check

The frozen historical solutions were evaluated without refitting. Only their
D2 energies are near the W02 conditional ensemble:

{chr(10).join(historical_lines)}

This does not promote any historical solution or make its prior ~18.2-meV
lineage an independent confirmation.

## E. Wavefunctions and g tensor

The minimum pairwise ground-doublet projector overlap across accepted Cs15
solutions is `{projector_min:.6f}`. Principal-g ranges are `{_json(g_ranges)}`.
Accordingly, wavefunctions and g tensors are
`{'stable within this design' if projector_min >= 0.95 else 'not experimentally determined by the conditional energy alone'}`.

## F. Viable level assignments

PCM M0 retains `{', '.join(pcm_remaining) if pcm_remaining else 'no assignment'}`
across every primary variant without a scale-boundary conflict. The diagnostic
Cs15 search can satisfy `{', '.join(cs15_assignments)}`, illustrating rather
than resolving assignment ambiguity.

## G. Most informative next observable

Reviewed, Q-resolved relative transition intensities for at least two distinct
CEF excitations would most directly constrain eigenvectors and assignments.
Additional independently resolved transition energies would constrain the
level scheme; polarization information would further constrain wavefunctions.

## Magnetization

`{mh_status}`. Literature M(H) was not used for selection.
"""


def _validate_execution_guards(
    repository: Path,
    config: Mapping[str, Any],
    manuscript_config: Mapping[str, Any],
) -> dict[str, object]:
    if manuscript_config["profiles"]["production"].get("enabled", False):
        raise RuntimeError("Normal manuscript production profile must remain disabled")
    if manuscript_config["scientific_scope"].get("exchange_enabled", False):
        raise RuntimeError("Exchange must remain disabled")

    source = config["w02_source"]
    identity = {}
    for key, path_key in (
        ("variants", "variants_path"),
        ("summary", "summary_path"),
        ("source_scans", "source_scans_path"),
    ):
        path = _resolve(repository, source[path_key])
        actual = sha256_file(path)
        expected = source["sha256"][key]
        if actual != expected:
            raise RuntimeError(f"W02 identity mismatch for {path}: {actual} != {expected}")
        identity[key] = {"path": source[path_key], "sha256": actual}

    summary_path = _resolve(repository, source["summary_path"])
    adjudication = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
    if adjudication.get("energy_admission") != "MODEL_DEPENDENT_ENERGY":
        raise RuntimeError("W02 adjudication is not MODEL_DEPENDENT_ENERGY")
    if adjudication.get("admitted_energy_meV") is not None:
        raise RuntimeError("W02 unexpectedly admits a scalar energy")

    observables_path = _resolve(repository, manuscript_config["inputs"]["observables"])
    forbidden = (6.447, 18.226, 18.247178, 27.896, 44.4)
    active_energy_rows = []
    with observables_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("likelihood_role") != "ENERGY_CANDIDATE":
                continue
            value = row.get("energy_meV", "").strip()
            if value and any(np.isclose(float(value), target) for target in forbidden):
                active_energy_rows.append(row["observation_id"])
    if active_energy_rows:
        raise RuntimeError(f"Forbidden scalar energy likelihood rows remain active: {active_energy_rows}")

    return {
        "w02_artifact_identity": identity,
        "w02_energy_adjudication": "MODEL_DEPENDENT_ENERGY",
        "scalar_energy_admitted": False,
        "normal_production_profile_enabled": False,
        "exchange_enabled": False,
        "forbidden_historical_or_aggregate_likelihood_rows": [],
    }


def run_conditional_analysis(
    config_path: str | Path,
    *,
    preflight_tests_pass: bool,
) -> dict[str, object]:
    if not preflight_tests_pass:
        raise RuntimeError("Full tests must pass before scientific execution")
    config_path = Path(config_path).expanduser().resolve()
    repository = config_path.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("execution_class") != "MODEL_DEPENDENT_ENERGY_CONDITIONAL":
        raise RuntimeError("Wrong execution class")
    if tuple(config.get("scientific_labels", ())) != SCIENTIFIC_LABELS:
        raise RuntimeError("Required scientific labels are missing or reordered")

    manuscript_path = _resolve(repository, config["manuscript_config"])
    manuscript_config = yaml.safe_load(manuscript_path.read_text(encoding="utf-8"))
    guards = _validate_execution_guards(repository, config, manuscript_config)
    source = config["w02_source"]
    variants = load_energy_variants(
        _resolve(repository, source["variants_path"]),
        expected_primary=int(source["expected_primary_variants"]),
        expected_stress=int(source["expected_stress_variants"]),
    )
    assignments = tuple(map(int, config["assignments"]))
    output_root = _resolve(repository, config["outputs"]["root"])
    output_root.mkdir(parents=True, exist_ok=True)

    energy_rows = []
    for variant in variants:
        energy_rows.append({
            "scientific_labels": SCIENTIFIC_LABEL,
            "source_commit": source["commit"],
            "source_path": source["variants_path"],
            "source_sha256": source["sha256"]["variants"],
            **variant.record(),
        })
    _write_csv(output_root / "energy_variants_used.csv", energy_rows)

    formal_parameters = manuscript_config["pcm"]["formal_parameters_meV"]
    pcm_rows = run_pcm_conditional(
        variants,
        formal_parameters,
        assignments,
        tuple(map(float, config["pcm"]["scale_bounds"])),
        j=float(manuscript_config["scientific_scope"]["J"]),
        g_j=float(manuscript_config["scientific_scope"]["gJ"]),
    )
    pcm_summary = summarize_pcm_robustness(pcm_rows, assignments)
    _write_csv(output_root / "pcm_conditional_results.csv", pcm_rows)
    _write_csv(output_root / "pcm_robustness_summary.csv", pcm_summary)

    selection_records = select_cs15_variants(variants)
    selection_payload = {
        "scientific_labels": list(SCIENTIFIC_LABELS),
        "selection_uses_cef_fit_quality": False,
        "primary_rule": {
            "extrema": "minimum and maximum W02 centroid",
            "metadata_medoid": (
                "minimize total normalized Manhattan distance in background_order, "
                "half_window_meV, and categorical width_mode; tie-break by variant_id"
            ),
        },
        "stress_rule": "minimum and maximum W02 centroid independently within each block_scope",
        "selected_variants": [
            {**record, "selection_reasons": list(record["selection_reasons"])}
            for record in selection_records
        ],
    }
    (output_root / "cs15_variant_selection.yaml").write_text(
        yaml.safe_dump(selection_payload, sort_keys=False), encoding="utf-8"
    )
    by_id = {variant.energy_variant_id: variant for variant in variants}
    selected_variants = tuple(by_id[str(record["energy_variant_id"])] for record in selection_records)

    cs_config = config["cs15"]
    cs15_rows, cs15_cache = run_cs15_global_search(
        selected_variants,
        assignments,
        tuple(map(float, cs_config["h_bounds_meV"])),
        float(cs_config["sigma0_meV"]),
        int(cs_config["max_cma_evaluations"]),
        int(cs_config["max_polish_evaluations"]),
        tuple(map(int, cs_config["fixed_restart_seeds"])),
        float(cs_config["fit_acceptance_q_max"]),
        j=float(manuscript_config["scientific_scope"]["J"]),
        g_j=float(manuscript_config["scientific_scope"]["gJ"]),
    )
    cs15_family_summary = assign_parameter_families(
        cs15_rows,
        cs15_cache,
        tuple(map(float, cs_config["h_bounds_meV"])),
        float(cs_config["parameter_family_rms_fraction"]),
    )
    _write_csv(output_root / "cs15_all_solutions.csv", cs15_rows)
    _write_csv(output_root / "cs15_family_summary.csv", cs15_family_summary)

    bundle_paths = tuple(_resolve(repository, path) for path in config["historical_bundles"])
    primary_variants = tuple(variant for variant in variants if variant.role == PRIMARY_ROLE)
    historical_rows = evaluate_historical_solutions(
        bundle_paths,
        primary_variants,
        assignments,
        j=float(manuscript_config["scientific_scope"]["J"]),
        g_j=float(manuscript_config["scientific_scope"]["gJ"]),
    )
    _write_csv(output_root / "historical_R3_R5_R7_variant_evaluation.csv", historical_rows)

    export_representative_families(
        output_root,
        variants,
        selection_records,
        pcm_rows,
        formal_parameters,
        cs15_rows,
        cs15_cache,
        bundle_paths,
        j=float(manuscript_config["scientific_scope"]["J"]),
        g_j=float(manuscript_config["scientific_scope"]["gJ"]),
    )

    robustness = build_robustness_matrix(
        variants, pcm_summary, cs15_rows, cs15_cache, cs15_family_summary
    )
    _write_csv(output_root / "robustness_matrix.csv", robustness)

    literature_path = _resolve(repository, manuscript_config["inputs"]["literature_magnetization"])
    with literature_path.open(newline="", encoding="utf-8") as handle:
        literature_rows = list(csv.DictReader(handle))
    reviewed_temperatures = sorted({
        float(row["temperature_K"])
        for row in literature_rows
        if row.get("temperature_K", "").strip()
        and row.get("provenance_status", "").upper().startswith("REVIEWED")
    })
    mh_status = (
        "SKIPPED__NO_REVIEWED_TEMPERATURE_LIST"
        if not reviewed_temperatures
        else "SKIPPED_BY_DESIGN__LITERATURE_NOT_USED_FOR_SELECTION"
    )
    summary_text = _scientific_summary(
        variants,
        pcm_summary,
        cs15_rows,
        cs15_cache,
        cs15_family_summary,
        historical_rows,
        mh_status,
    )
    (output_root / "SCIENTIFIC_SUMMARY.md").write_text(summary_text, encoding="utf-8")

    required_artifacts = (
        "energy_variants_used.csv",
        "pcm_conditional_results.csv",
        "pcm_robustness_summary.csv",
        "cs15_variant_selection.yaml",
        "cs15_all_solutions.csv",
        "cs15_family_summary.csv",
        "historical_R3_R5_R7_variant_evaluation.csv",
        "representative_levels.csv",
        "representative_transition_strengths.csv",
        "representative_g_tensors.csv",
        "robustness_matrix.csv",
        "SCIENTIFIC_SUMMARY.md",
    )
    artifact_hashes = {
        name: sha256_file(output_root / name) for name in required_artifacts
    }
    wavefunction_files = sorted((output_root / "wavefunctions").glob("*"))
    manifest = {
        "schema_version": 1,
        "execution_class": config["execution_class"],
        "scientific_labels": list(SCIENTIFIC_LABELS),
        "implementation_base": config["implementation_base"],
        "git_at_execution": git_provenance(repository),
        "pre_execution_validation": {
            "full_tests": "PASS",
            **guards,
        },
        "w02_source_commit": source["commit"],
        "variant_counts": {
            "primary": len(primary_variants),
            "stress": sum(variant.role == STRESS_ROLE for variant in variants),
        },
        "pcm": {
            "runs": len(pcm_rows),
            "variants_are_separate_runs": True,
            "variant_objectives_summed": False,
        },
        "cs15": {
            "status": "DIAGNOSTIC_LANDSCAPE_ONLY",
            "selected_variant_count": len(selected_variants),
            "restarts_per_variant_assignment": len(cs_config["fixed_restart_seeds"]),
            "solution_count": len(cs15_rows),
            "accepted_solution_count": sum(bool(row["fit_accepted"]) for row in cs15_rows),
            "operational_parameter_family_count": len(cs15_family_summary),
            "project_owned_forward_kernel_reevaluation": True,
        },
        "historical": {
            "mode": "FROZEN_NO_REFIT",
            "parameter_sets": [path.stem for path in bundle_paths],
            "evaluation_rows": len(historical_rows),
        },
        "magnetization": {
            "status": mh_status,
            "reviewed_temperatures": reviewed_temperatures,
            "literature_used_for_selection": False,
        },
        "artifact_sha256": artifact_hashes,
        "wavefunction_artifact_count": len(wavefunction_files),
    }
    (output_root / "RUN_MANIFEST.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )

    return {
        "result_path": str(output_root),
        "primary_variants": len(primary_variants),
        "stress_variants": sum(variant.role == STRESS_ROLE for variant in variants),
        "pcm_runs": len(pcm_rows),
        "pcm_assignments_remaining": [
            row["assignment"] for row in pcm_summary
            if bool(row["robust_across_primary_variants"])
        ],
        "cs15_variants_run": len(selected_variants),
        "cs15_restarts": len(cs_config["fixed_restart_seeds"]),
        "cs15_solutions": len(cs15_rows),
        "cs15_accepted_solutions": sum(bool(row["fit_accepted"]) for row in cs15_rows),
        "cs15_families": len(cs15_family_summary),
        "mh_status": mh_status,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--preflight-tests-pass",
        action="store_true",
        help="Assert that the full test suite passed immediately before execution",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_conditional_analysis(
        args.config, preflight_tests_pass=bool(args.preflight_tests_pass)
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
