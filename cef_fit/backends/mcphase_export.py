"""Conservative canonical-Cs15 to McPhase Stevens-name export."""

from __future__ import annotations

from typing import Mapping

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
