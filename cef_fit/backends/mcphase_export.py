"""Conservative canonical-Cs15 to McPhase Stevens-name export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from ..conventions import CANONICAL_LABELS, CANONICAL_CS_LM


def mcphase_name(rank: int, m: int) -> str:
    return f"B{rank}{abs(m)}{'S' if m < 0 else ''}"


def export_parameter_lines(parameters: Mapping[str, float]) -> str:
    missing = [label for label in CANONICAL_LABELS if label not in parameters]
    if missing:
        raise ValueError(f"Missing canonical parameters: {missing}")
    header = (
        "# Stevens-normalized canonical Cs parameters; units=meV\n"
        "# frame=(x,y,z)=(b,-a,c); verify McPhase axis and normalization settings\n"
    )
    lines = [f"{mcphase_name(rank, m)}={float(parameters[label]):.16g}" for label, (rank, m) in zip(CANONICAL_LABELS, CANONICAL_CS_LM)]
    return header + "\n".join(lines) + "\n"


def parse_parameter_lines(text: str) -> dict[str, float]:
    """Parse the conservative exporter output for a convention round trip."""

    by_mcphase_name = {
        mcphase_name(rank, m): label
        for label, (rank, m) in zip(CANONICAL_LABELS, CANONICAL_CS_LM)
    }
    parsed: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid McPhase parameter line: {raw_line}")
        name, raw_value = line.split("=", 1)
        if name not in by_mcphase_name:
            raise ValueError(f"Unsupported McPhase parameter name: {name}")
        parsed[by_mcphase_name[name]] = float(raw_value)
    missing = [label for label in CANONICAL_LABELS if label not in parsed]
    if missing:
        raise ValueError(f"McPhase parameter text is missing: {missing}")
    return parsed


def write_mcphase_bundle(
    directory: str | Path,
    solution_id: str,
    canonical_parameters_meV: Mapping[str, float],
    metadata: Mapping[str, object],
) -> tuple[Path, Path]:
    """Write parameters plus an explicit convention/provenance sidecar."""

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    parameter_path = destination / f"{solution_id}.sipf"
    metadata_path = destination / f"{solution_id}.mcphase.json"
    text = export_parameter_lines(canonical_parameters_meV)
    round_trip = parse_parameter_lines(text)
    if any(
        not np.isclose(round_trip[label], float(canonical_parameters_meV[label]), rtol=0, atol=1e-14)
        for label in CANONICAL_LABELS
    ):
        raise ValueError("McPhase parameter export failed its internal round-trip check")
    parameter_path.write_text(text, encoding="utf-8")
    payload = {
        "solution_id": solution_id,
        "parameter_units": "meV",
        "parameter_basis": "canonical_Cs15",
        "canonical_axes": ["b", "-a", "c"],
        "internal_axes": ["b", "c", "a"],
        "validation_status": "EXPORT_ONLY__EXTERNAL_MCPHASE_RUN_REQUIRED",
        "automatic_refit_on_mismatch": False,
        **dict(metadata),
    }
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return parameter_path, metadata_path


def compare_mcphase_levels(
    project_levels_meV: Sequence[float],
    mcphase_levels_meV: Sequence[float],
    tolerance_meV: float = 1.0e-6,
) -> dict[str, object]:
    """Compare independent levels; never modify or refit parameters."""

    project = np.array(project_levels_meV, dtype=float, copy=True)
    external = np.array(mcphase_levels_meV, dtype=float, copy=True)
    if project.shape != external.shape:
        raise ValueError("Project and McPhase level arrays must have the same shape")
    project -= project.min()
    external -= external.min()
    maximum = float(np.max(np.abs(project - external)))
    return {
        "status": "PASS" if maximum <= tolerance_meV else "MISMATCH_REVIEW_CONVENTIONS",
        "max_abs_level_difference_meV": maximum,
        "tolerance_meV": float(tolerance_meV),
        "automatic_refit_performed": False,
        "review_order_on_mismatch": [
            "Stevens convention",
            "units",
            "coordinate axes",
            "parameter normalization",
            "operator definition",
        ],
    }


def compare_mcphase_observables(
    *,
    project_levels_meV: Sequence[float],
    external: Mapping[str, object],
    project_canonical_hamiltonian_meV: np.ndarray | None = None,
    project_g_principal_values: Sequence[float] | None = None,
    project_mh_muB_per_Dy: Sequence[float] | None = None,
    level_tolerance_meV: float = 1.0e-6,
    hamiltonian_tolerance_meV: float = 1.0e-8,
    g_tolerance: float = 1.0e-6,
    mh_tolerance_muB: float = 1.0e-5,
) -> dict[str, object]:
    """Validate available independent McPhase observables without refitting."""

    if "levels_meV" not in external:
        raise ValueError("External McPhase result must provide levels_meV")
    checks: dict[str, object] = {
        "levels": compare_mcphase_levels(
            project_levels_meV, external["levels_meV"], level_tolerance_meV
        ),
        "frame_conversion": {
            "status": (
                "PASS"
                if external.get("frame_axes") == ["b", "-a", "c"]
                else ("NOT_PROVIDED" if external.get("frame_axes") is None else "MISMATCH")
            ),
            "expected_axes": ["b", "-a", "c"],
            "reported_axes": external.get("frame_axes"),
        },
    }
    if project_canonical_hamiltonian_meV is not None and "canonical_hamiltonian_real" in external:
        real = np.asarray(external["canonical_hamiltonian_real"], dtype=float)
        imag = np.asarray(
            external.get("canonical_hamiltonian_imag", np.zeros_like(real)), dtype=float
        )
        external_hamiltonian = real + 1j * imag
        project_hamiltonian = np.asarray(project_canonical_hamiltonian_meV, dtype=complex)
        if external_hamiltonian.shape != project_hamiltonian.shape:
            raise ValueError("External canonical Hamiltonian has the wrong shape")
        maximum = float(np.max(np.abs(project_hamiltonian - external_hamiltonian)))
        checks["hamiltonian_convention"] = {
            "status": "PASS" if maximum <= hamiltonian_tolerance_meV else "MISMATCH",
            "max_abs_difference_meV": maximum,
            "tolerance_meV": hamiltonian_tolerance_meV,
        }
    else:
        checks["hamiltonian_convention"] = {"status": "NOT_PROVIDED"}
    if project_g_principal_values is not None and "g_principal_values" in external:
        project_g = np.sort(np.asarray(project_g_principal_values, dtype=float))
        external_g = np.sort(np.asarray(external["g_principal_values"], dtype=float))
        if project_g.shape != external_g.shape:
            raise ValueError("External principal-g array has the wrong shape")
        maximum = float(np.max(np.abs(project_g - external_g)))
        checks["principal_g_anisotropy"] = {
            "status": "PASS" if maximum <= g_tolerance else "MISMATCH",
            "max_abs_difference": maximum,
            "tolerance": g_tolerance,
        }
    else:
        checks["principal_g_anisotropy"] = {"status": "NOT_PROVIDED"}
    if project_mh_muB_per_Dy is not None and "mh_muB_per_Dy" in external:
        project_mh = np.asarray(project_mh_muB_per_Dy, dtype=float)
        external_mh = np.asarray(external["mh_muB_per_Dy"], dtype=float)
        if project_mh.shape != external_mh.shape:
            raise ValueError("External M(H) array has the wrong shape")
        maximum = float(np.max(np.abs(project_mh - external_mh)))
        checks["magnetization"] = {
            "status": "PASS" if maximum <= mh_tolerance_muB else "MISMATCH",
            "max_abs_difference_muB": maximum,
            "tolerance_muB": mh_tolerance_muB,
        }
    else:
        checks["magnetization"] = {"status": "NOT_PROVIDED"}
    statuses = [str(value["status"]) for value in checks.values() if isinstance(value, Mapping)]
    failed = any(status in {"MISMATCH", "MISMATCH_REVIEW_CONVENTIONS"} for status in statuses)
    return {
        "status": "MISMATCH_REVIEW_CONVENTIONS" if failed else "PASS_AVAILABLE_CHECKS",
        "checks": checks,
        "automatic_refit_performed": False,
        "review_order_on_mismatch": [
            "Stevens convention",
            "units",
            "coordinate axes",
            "parameter normalization",
            "operator definition",
        ],
    }
