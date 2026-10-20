"""Ke et al. M(H) loader and frozen-Dy comparison diagnostics."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .cef_model import CEFModel
from .conventions import DIRECT_LM
from .magnetization import abc_direction_in_direct_frame, magnetization_curve


MH_SOURCE_COMMIT = "2c17955c405ef9698781dfd5364ef7be0245ba15"
MH_DOI = "10.1088/1674-1056/24/3/037501"


@dataclass(frozen=True)
class LiteratureMHCurve:
    axis: str
    temperature_K: float
    fields_T: tuple[float, ...]
    fields_kOe: tuple[float, ...]
    magnetization_emu_per_g: tuple[float, ...]
    magnetization_muB_per_fu: tuple[float, ...]
    sigma_H_digitization_kOe: tuple[float, ...]
    sigma_M_digitization_emu_per_g: tuple[float, ...]
    source_type: str = "TOTAL_BULK_MAGNETIZATION"


@dataclass(frozen=True)
class LiteratureMHData:
    curves: tuple[LiteratureMHCurve, ...]
    unavailable_comparators: tuple[str, ...]
    source_commit: str = MH_SOURCE_COMMIT


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_literature_mh(
    points_path: str | Path,
    inventory_path: str | Path,
) -> LiteratureMHData:
    points = _read_rows(points_path)
    inventory = _read_rows(inventory_path)
    if len(points) != 135:
        raise ValueError(f"Expected 135 digitized M(H) points; found {len(points)}")
    if any(row["source_type"] != "TOTAL_BULK_MAGNETIZATION" for row in points):
        raise ValueError("Literature M(H) must retain TOTAL_BULK_MAGNETIZATION semantics")
    if any(row["paper_doi"] != MH_DOI for row in points):
        raise ValueError("Unexpected M(H) literature source")
    curves: list[LiteratureMHCurve] = []
    for axis, temperature in (("a", 10.0), ("a", 20.0), ("b", 10.0), ("b", 20.0)):
        selected = [
            row
            for row in points
            if row["axis"] == axis and float(row["temperature_K"]) == temperature
        ]
        if not selected:
            raise ValueError(f"Missing literature comparator {axis},{temperature:g} K")
        curves.append(
            LiteratureMHCurve(
                axis=axis,
                temperature_K=temperature,
                fields_T=tuple(float(row["H_T"]) for row in selected),
                fields_kOe=tuple(float(row["H_kOe"]) for row in selected),
                magnetization_emu_per_g=tuple(float(row["M_emu_per_g"]) for row in selected),
                magnetization_muB_per_fu=tuple(float(row["M_muB_per_fu"]) for row in selected),
                sigma_H_digitization_kOe=tuple(
                    float(row["sigma_H_digitization"]) for row in selected
                ),
                sigma_M_digitization_emu_per_g=tuple(
                    float(row["sigma_M_digitization"]) for row in selected
                ),
            )
        )
    unavailable = tuple(
        f"{row['axis']},{row['temperature_K']}K:{row['digitization_status']}"
        for row in inventory
        if row["w03_comparator_status"] == "NO_RELIABLE_DIGITIZED_COMPARATOR_FROM_THIS_FIGURE"
    )
    if set(unavailable) != {
        "c,10K:AMBIGUOUS_CURVE_IDENTITY",
        "c,20K:AMBIGUOUS_CURVE_IDENTITY",
    }:
        raise ValueError("c-axis comparator inventory does not match the reviewed source")
    return LiteratureMHData(tuple(curves), unavailable)


def verified_temperatures(path: str | Path) -> tuple[float, ...]:
    """Compatibility helper for the reviewed digitization schema."""

    rows = _read_rows(path)
    return tuple(
        sorted(
            {
                float(row["temperature_K"])
                for row in rows
                if row.get("digitization_status") == "DIGITIZED"
            }
        )
    )


def calculate_frozen_dy_mh(
    direct_parameters_meV: Mapping[str, float],
    literature: LiteratureMHData,
    candidate_id: str,
    j: float = 7.5,
    g_j: float = 4.0 / 3.0,
) -> list[dict[str, object]]:
    """Evaluate frozen single-ion Dy curves at the exact digitized H points."""

    h_cef = CEFModel.from_coefficients(
        direct_parameters_meV, DIRECT_LM, j=j, g_j=g_j
    ).hamiltonian_meV
    rows: list[dict[str, object]] = []
    for experimental in literature.curves:
        calculated = magnetization_curve(
            h_cef,
            experimental.fields_T,
            experimental.temperature_K,
            abc_direction_in_direct_frame(experimental.axis),
            j=j,
            g_j=g_j,
        )
        for index, field in enumerate(experimental.fields_T):
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "axis_abc": experimental.axis,
                    "temperature_K": experimental.temperature_K,
                    "field_T": field,
                    "M_Dy_CEF_muB_per_Dy": float(calculated.magnetization_muB_per_ion[index]),
                    "M_bulk_exp_emu_per_g": experimental.magnetization_emu_per_g[index],
                    "M_bulk_exp_muB_per_fu": experimental.magnetization_muB_per_fu[index],
                    "experimental_quantity": "TOTAL_BULK_MAGNETIZATION",
                    "calculated_quantity": "SINGLE_ION_DY_CEF_CONTRIBUTION",
                    "diagnostic_residual_bulk_muB_per_fu_minus_Dy_muB_per_Dy": (
                        experimental.magnetization_muB_per_fu[index]
                        - float(calculated.magnetization_muB_per_ion[index])
                    ),
                    "residual_semantics": "MIXED_BULK_EXPERIMENT_MINUS_DY_ONLY_CALCULATION",
                    "comparison_role": "VALIDATION_DIAGNOSTIC_NOT_FORMAL_CHI_SQUARE",
                    "blm_frozen": True,
                    "exchange_enabled": False,
                }
            )
    return rows


def mh_curve_diagnostics(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Curve-shape/high-field diagnostics without a formal score or ranking."""

    grouped: dict[tuple[str, float, str], list[Mapping[str, object]]] = {}
    for row in rows:
        key = (str(row["axis_abc"]), float(row["temperature_K"]), str(row["candidate_id"]))
        grouped.setdefault(key, []).append(row)
    diagnostics = []
    for (axis, temperature, candidate), curve in sorted(grouped.items()):
        curve = sorted(curve, key=lambda row: float(row["field_T"]))
        calc = np.asarray([float(row["M_Dy_CEF_muB_per_Dy"]) for row in curve])
        bulk = np.asarray([float(row["M_bulk_exp_muB_per_fu"]) for row in curve])
        calc_shape = calc / max(float(np.max(np.abs(calc))), np.finfo(float).eps)
        bulk_shape = bulk / max(float(np.max(np.abs(bulk))), np.finfo(float).eps)
        diagnostics.append(
            {
                "candidate_id": candidate,
                "axis_abc": axis,
                "temperature_K": temperature,
                "curve_shape_rms_difference": float(
                    np.sqrt(np.mean((calc_shape - bulk_shape) ** 2))
                ),
                "high_field_M_Dy_CEF_muB_per_Dy": float(calc[-1]),
                "high_field_M_bulk_exp_muB_per_fu": float(bulk[-1]),
                "formal_chi_square": None,
                "ranking_allowed": False,
                "semantic_warning": "DY_ONLY_CALCULATION_VS_TOTAL_BULK_EXPERIMENT",
            }
        )
    return diagnostics


def mh_anisotropy_diagnostics(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Compare a/b shape and high-field anisotropy without defining a fit score."""

    grouped: dict[tuple[str, float, str], list[Mapping[str, object]]] = {}
    for row in rows:
        key = (str(row["candidate_id"]), float(row["temperature_K"]), str(row["axis_abc"]))
        grouped.setdefault(key, []).append(row)
    results: list[dict[str, object]] = []
    candidate_temperatures = sorted({(key[0], key[1]) for key in grouped})
    for candidate, temperature in candidate_temperatures:
        a_rows = sorted(grouped[(candidate, temperature, "a")], key=lambda row: float(row["field_T"]))
        b_rows = sorted(grouped[(candidate, temperature, "b")], key=lambda row: float(row["field_T"]))
        a_fields = np.asarray([float(row["field_T"]) for row in a_rows])
        b_fields = np.asarray([float(row["field_T"]) for row in b_rows])
        lower = max(float(a_fields.min()), float(b_fields.min()))
        upper = min(float(a_fields.max()), float(b_fields.max()))
        common_fields = np.linspace(lower, upper, 128)
        calc_a = np.interp(
            common_fields,
            a_fields,
            [float(row["M_Dy_CEF_muB_per_Dy"]) for row in a_rows],
        )
        calc_b = np.interp(
            common_fields,
            b_fields,
            [float(row["M_Dy_CEF_muB_per_Dy"]) for row in b_rows],
        )
        bulk_a = np.interp(
            common_fields,
            a_fields,
            [float(row["M_bulk_exp_muB_per_fu"]) for row in a_rows],
        )
        bulk_b = np.interp(
            common_fields,
            b_fields,
            [float(row["M_bulk_exp_muB_per_fu"]) for row in b_rows],
        )
        results.append(
            {
                "candidate_id": candidate,
                "temperature_K": temperature,
                "common_field_range_T": [lower, upper],
                "calculated_b_minus_a_shape_rms_muB_per_Dy": float(
                    np.sqrt(np.mean(np.square(calc_b - calc_a)))
                ),
                "experimental_b_minus_a_shape_rms_muB_per_fu": float(
                    np.sqrt(np.mean(np.square(bulk_b - bulk_a)))
                ),
                "calculated_high_field_b_over_a": float(
                    calc_b[-1] / max(abs(calc_a[-1]), np.finfo(float).eps)
                ),
                "experimental_high_field_b_over_a": float(
                    bulk_b[-1] / max(abs(bulk_a[-1]), np.finfo(float).eps)
                ),
                "formal_score": None,
                "ranking_allowed": False,
                "semantic_warning": "DY_ONLY_CALCULATION_VS_TOTAL_BULK_EXPERIMENT",
            }
        )
    return results
