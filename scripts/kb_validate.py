#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]

REPORT = ROOT / "VALIDATION_REPORT.json"
MANIFEST = ROOT / "PROJECT_MANIFEST.yaml"
META = ROOT / "00_Project" / "PROJECT_METADATA.yaml"

RESULTS = ROOT / "00_Project" / "RESULT_REGISTER.yaml"
HYPOTHESES = ROOT / "00_Project" / "HYPOTHESIS_REGISTER.yaml"
DECISIONS = ROOT / "00_Project" / "DECISION_REGISTER.yaml"
EVIDENCE = ROOT / "00_Project" / "EVIDENCE_REGISTER.yaml"
MODELS = ROOT / "00_Project" / "MODEL_REGISTER.yaml"

EXPECTED_SCHEMA_VERSION = "2.2"

VALIDATION_EXCLUDED_PREFIXES = (
    "Archive/legacy/",
    "CEF_Dy_Backup/",
)

RESULT_STATUSES = {
    "candidate",
    "working",
    "reviewed",
    "validated",
    "rejected",
    "superseded",
}

HYP_STATUSES = {
    "candidate",
    "working",
    "disfavored",
    "rejected",
    "superseded",
}

DECISION_STATUSES = {
    "active",
    "superseded",
    "rejected",
}

EVIDENCE_REVIEW_STATUSES = RESULT_STATUSES

PROVENANCE_STATUSES = {
    "complete",
    "partial",
    "legacy_only",
    "missing",
}

ORIGIN_TYPES = {
    "experiment_raw",
    "experiment_derived",
    "literature",
    "model_calculation",
    "hypothesis",
    "methodological_decision",
}

MODEL_STATUSES = {
    "baseline",
    "retained",
    "working",
    "exploratory",
    "suspended",
    "suspended_pending_rebaseline",
    "deferred",
    "rejected",
    "superseded",
}

REPRO_KINDS = {
    "checkpoint",
    "artifact",
    "dataset",
    "code_run",
}


def rel(path):
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def rel_posix(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def excluded_from_validation(path):
    return rel_posix(path).startswith(
        VALIDATION_EXCLUDED_PREFIXES
    )


def add_issue(issues, level, file, message):
    issues.append(
        {
            "level": level,
            "file": str(file),
            "message": str(message),
        }
    )


def load_yaml(path, issues):
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    except FileNotFoundError:
        add_issue(
            issues,
            "error",
            rel(path),
            "required file is missing",
        )
        return None

    except Exception as exc:
        add_issue(
            issues,
            "error",
            rel(path),
            f"YAML parse error: {exc}",
        )
        return None


def require_mapping(data, path, issues):
    if not isinstance(data, dict):
        add_issue(
            issues,
            "error",
            rel(path),
            "top-level YAML value must be a mapping",
        )
        return {}

    return data


def require_list(data, path, issues):
    if not isinstance(data, list):
        add_issue(
            issues,
            "error",
            rel(path),
            "top-level YAML value must be a list",
        )
        return []

    return data


FENCE_OPEN_RE = re.compile(
    r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$"
)

HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")

CHEMICAL_LATEX_PATTERNS = (
    (
        re.compile(r"\b[A-Z][a-z]?\$\^\{?\d+[+-]\}?\$"),
        "plain-text ion notation is preferred",
    ),
    (
        re.compile(r"\b(?:[A-Z][a-z]?|R)FeO\$_(?:3|\{3\})\$"),
        "plain-text orthoferrite formula is preferred",
    ),
)


def is_escaped(text, index):
    backslashes = 0
    index -= 1

    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1

    return backslashes % 2 == 1


def strip_inline_code(line):
    """Blank CommonMark-style inline code spans while preserving columns."""
    chars = list(line)
    index = 0

    while index < len(line):
        if line[index] != "`":
            index += 1
            continue

        run_end = index
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1

        marker = line[index:run_end]
        close = line.find(marker, run_end)

        if close < 0:
            index = run_end
            continue

        for pos in range(index, close + len(marker)):
            chars[pos] = " "

        index = close + len(marker)

    return "".join(chars)


def scan_markdown(text):
    """Return code-free lines and exact fenced-code spans.

    Fences may use backticks or tildes and any length of at least three.
    Closing fences must use the same character and at least the opening
    length, following CommonMark's up-to-three-space indentation rule.
    """
    raw_lines = text.splitlines()
    clean_lines = []
    fence = None
    fence_pairs = []

    for index, line in enumerate(raw_lines):
        if fence is not None:
            close_re = re.compile(
                r"^ {0,3}"
                + re.escape(fence["char"])
                + "{"
                + str(fence["length"])
                + r",}[ \t]*$"
            )

            if close_re.match(line):
                fence_pairs.append(
                    {
                        "start": fence["start"],
                        "end": index,
                        "char": fence["char"],
                        "length": fence["length"],
                    }
                )
                fence = None

            clean_lines.append("")
            continue

        match = FENCE_OPEN_RE.match(line)

        if match:
            marker = match.group("fence")
            info = match.group("info")

            # A backtick fence cannot have a backtick in its info string.
            if marker[0] != "`" or "`" not in info:
                fence = {
                    "start": index,
                    "char": marker[0],
                    "length": len(marker),
                }
                clean_lines.append("")
                continue

        clean_lines.append(strip_inline_code(line))

    return {
        "raw_lines": raw_lines,
        "clean_lines": clean_lines,
        "fence_pairs": fence_pairs,
        "unclosed_fence": fence,
    }


def strip_fences(text):
    return "\n".join(scan_markdown(text)["clean_lines"])


def dollar_runs(line):
    runs = []
    index = 0

    while index < len(line):
        if line[index] != "$" or is_escaped(line, index):
            index += 1
            continue

        end = index + 1
        while end < len(line) and line[end] == "$":
            end += 1

        runs.append((index, end - index))
        index = end

    return runs


def latex_checks(path, text, issues):
    scan = scan_markdown(text)
    raw_lines = scan["raw_lines"]
    clean_lines = scan["clean_lines"]
    clean = "\n".join(clean_lines)

    meaningful = [
        index
        for index, line in enumerate(raw_lines)
        if line.strip()
    ]

    if meaningful:
        first = meaningful[0]
        last = meaningful[-1]

        if any(
            pair["start"] == first and pair["end"] == last
            for pair in scan["fence_pairs"]
        ):
            add_issue(
                issues,
                "error",
                rel(path),
                "entire Markdown document is wrapped in an outer code fence",
            )

    begins = re.findall(r"\\begin\{([^}]+)\}", clean)
    ends = re.findall(r"\\end\{([^}]+)\}", clean)

    if sorted(begins) != sorted(ends):
        add_issue(
            issues,
            "error",
            rel(path),
            f"LaTeX environment mismatch: begin={begins}, end={ends}",
        )

    display_open = None
    display_lines = set()
    display_delimiter_lines = set()

    for line_no, line in enumerate(clean_lines, 1):
        runs = dollar_runs(line)
        display_runs = [run for run in runs if run[1] >= 2]

        if display_runs:
            if (
                len(display_runs) == 1
                and display_runs[0][1] == 2
                and line.strip() == "$$"
            ):
                display_delimiter_lines.add(line_no)

                if display_open is None:
                    display_open = line_no
                else:
                    display_open = None

            else:
                add_issue(
                    issues,
                    "error",
                    rel(path),
                    "display math delimiter must be standalone $$ "
                    f"at line {line_no}",
                )

        elif display_open is not None:
            display_lines.add(line_no)
        else:
            inline_count = sum(
                length == 1
                for _, length in runs
            )

            if inline_count % 2:
                add_issue(
                    issues,
                    "error",
                    rel(path),
                    f"unpaired inline $ delimiter at line {line_no}",
                )

    if display_open is not None:
        add_issue(
            issues,
            "error",
            rel(path),
            f"unpaired standalone $$ delimiter opened at line {display_open}",
        )

    for line_no, line in enumerate(clean_lines, 1):
        if HEADING_RE.match(line) and (
            dollar_runs(line)
            or "\\(" in line
            or "\\[" in line
        ):
            add_issue(
                issues,
                "error",
                rel(path),
                f"math delimiter in Markdown heading at line {line_no}",
            )

        if "\\[" in line or "\\]" in line:
            add_issue(
                issues,
                "error",
                rel(path),
                "non-portable \\[ or \\] display delimiter "
                f"at line {line_no}; use standalone $$",
            )

        if re.match(r"^ {4,}\$\$", line):
            add_issue(
                issues,
                "warning",
                rel(path),
                f"indented display math at line {line_no}",
            )

        if (
            line_no not in display_lines
            and line_no not in display_delimiter_lines
        ):
            for pattern, message in CHEMICAL_LATEX_PATTERNS:
                for match in pattern.finditer(line):
                    add_issue(
                        issues,
                        "warning",
                        rel(path),
                        f"{message} at line {line_no}: {match.group(0)}",
                    )

    for env in (
        "aligned",
        "pmatrix",
        "matrix",
        "bmatrix",
        "cases",
    ):
        pattern = re.compile(r"\\begin\{" + env + r"\}")

        for line_no, line in enumerate(clean_lines, 1):
            if pattern.search(line) and line_no not in display_lines:
                add_issue(
                    issues,
                    "error",
                    rel(path),
                    f"{env} environment outside $$ math block",
                )


def markdown_links(path, text, issues):
    for target in re.findall(
        r"\[[^\]]+\]\(([^)]+)\)",
        text,
    ):
        if (
            re.match(r"^[a-z]+://", target)
            or target.startswith("#")
            or target.startswith("mailto:")
        ):
            continue

        target_path = target.split("#", 1)[0]

        if not target_path:
            continue

        resolved = (
            path.parent / target_path
        ).resolve()

        try:
            resolved.relative_to(ROOT.resolve())
        except Exception:
            continue

        if not resolved.exists():
            add_issue(
                issues,
                "warning",
                rel(path),
                f"broken relative link: {target}",
            )


def path_leak_checks(path, text, issues):
    path_str = rel_posix(path)

    if excluded_from_validation(path):
        return

    if path.name in {
        "local_paths.example.yaml",
        "local_paths.yaml",
    }:
        return

    if re.search(
        r"(?i)\b[A-Z]:\\Users\\[^\\\s]+\\",
        text,
    ):
        add_issue(
            issues,
            "warning",
            path_str,
            "possible absolute Windows user path",
        )


def metadata_checks(issues):
    meta = require_mapping(
        load_yaml(META, issues),
        META,
        issues,
    )

    if not meta:
        return

    if (
        str(meta.get("schema_version"))
        != EXPECTED_SCHEMA_VERSION
    ):
        add_issue(
            issues,
            "error",
            rel(META),
            f"schema_version must be {EXPECTED_SCHEMA_VERSION}",
        )

    required = [
        "project_id",
        "scientific_question",
        "scientific_facade",
        "experimental_evidence_summary",
        "interpretation_summary",
        "model_status_summary",
        "main_uncertainties",
        "current_milestone",
        "immediate_next_step",
        "do_not_assume",
        "control",
    ]

    for key in required:
        if key not in meta:
            add_issue(
                issues,
                "error",
                rel(META),
                f"missing required key: {key}",
            )

    milestone = meta.get("current_milestone")

    if isinstance(milestone, dict):
        for key in (
            "id",
            "title",
            "status",
        ):
            if key not in milestone:
                add_issue(
                    issues,
                    "error",
                    rel(META),
                    f"current_milestone missing key: {key}",
                )

    elif milestone is not None:
        add_issue(
            issues,
            "error",
            rel(META),
            "current_milestone must be a mapping",
        )

    next_step = meta.get("immediate_next_step")

    if isinstance(next_step, dict):
        for key in (
            "id",
            "text",
        ):
            if key not in next_step:
                add_issue(
                    issues,
                    "error",
                    rel(META),
                    f"immediate_next_step missing key: {key}",
                )

    elif next_step is not None:
        add_issue(
            issues,
            "error",
            rel(META),
            "immediate_next_step must be a mapping",
        )

    control = meta.get("control")

    if isinstance(control, dict):
        for key in (
            "now",
            "why",
            "next",
            "blocked",
            "deferred",
            "active_hypothesis_ids",
            "key_risk_ids",
        ):
            if key not in control:
                add_issue(
                    issues,
                    "error",
                    rel(META),
                    f"control missing key: {key}",
                )

    elif control is not None:
        add_issue(
            issues,
            "error",
            rel(META),
            "control must be a mapping",
        )

    facade = meta.get("scientific_facade")

    if facade is not None and not isinstance(facade, dict):
        add_issue(
            issues,
            "error",
            rel(META),
            "scientific_facade must be a mapping",
        )


def manifest_checks(issues):
    manifest = require_mapping(
        load_yaml(MANIFEST, issues),
        MANIFEST,
        issues,
    )

    if not manifest:
        return

    if (
        str(manifest.get("schema_version"))
        != EXPECTED_SCHEMA_VERSION
    ):
        add_issue(
            issues,
            "error",
            rel(MANIFEST),
            f"schema_version must be {EXPECTED_SCHEMA_VERSION}",
        )

    canonical = manifest.get("canonical_repository")

    if not isinstance(canonical, dict):
        add_issue(
            issues,
            "error",
            rel(MANIFEST),
            "canonical_repository must be a mapping",
        )

    else:
        if canonical.get("repository") != "oregu93/cef-dy":
            add_issue(
                issues,
                "warning",
                rel(MANIFEST),
                "canonical_repository.repository is not oregu93/cef-dy",
            )

        if canonical.get("branch") != "main":
            add_issue(
                issues,
                "warning",
                rel(MANIFEST),
                "canonical_repository.branch is not main",
            )

    authoritative = manifest.get("authoritative")

    if not isinstance(authoritative, dict):
        add_issue(
            issues,
            "error",
            rel(MANIFEST),
            "authoritative must be a mapping",
        )
        return

    required_authoritative = {
        "project_state",
        "project_control",
        "project_metadata",
        "evidence",
        "results",
        "hypotheses",
        "models",
        "decisions",
        "scientific_terminology",
        "knowledge_rules",
        "data_contracts",
        "chat_bootstraps",
        "logbook",
        "checkpoints",
    }

    for key in sorted(
        required_authoritative
    ):
        if key not in authoritative:
            add_issue(
                issues,
                "error",
                rel(MANIFEST),
                f"authoritative missing key: {key}",
            )
            continue

        target = ROOT / str(
            authoritative[key]
        )

        if not target.exists():
            add_issue(
                issues,
                "error",
                rel(MANIFEST),
                f"authoritative path does not exist: "
                f"{authoritative[key]}",
            )


def register_checks(issues):
    result_items = require_list(
        load_yaml(RESULTS, issues),
        RESULTS,
        issues,
    )

    hypothesis_items = require_list(
        load_yaml(HYPOTHESES, issues),
        HYPOTHESES,
        issues,
    )

    decision_items = require_list(
        load_yaml(DECISIONS, issues),
        DECISIONS,
        issues,
    )

    evidence_items = require_list(
        load_yaml(EVIDENCE, issues),
        EVIDENCE,
        issues,
    )

    model_data = require_mapping(
        load_yaml(MODELS, issues),
        MODELS,
        issues,
    )

    model_items = (
        model_data.get("models", [])
        if model_data
        else []
    )

    if not isinstance(
        model_items,
        list,
    ):
        add_issue(
            issues,
            "error",
            rel(MODELS),
            "models must be a list",
        )
        model_items = []

    collections = {
        "results": (
            RESULTS,
            result_items,
        ),
        "hypotheses": (
            HYPOTHESES,
            hypothesis_items,
        ),
        "decisions": (
            DECISIONS,
            decision_items,
        ),
        "evidence": (
            EVIDENCE,
            evidence_items,
        ),
        "models": (
            MODELS,
            model_items,
        ),
    }

    seen = {}

    for collection_name, (
        path,
        items,
    ) in collections.items():

        for item in items:
            if not isinstance(
                item,
                dict,
            ):
                add_issue(
                    issues,
                    "error",
                    rel(path),
                    f"{collection_name} record is not a mapping",
                )
                continue

            item_id = item.get("id")

            if not item_id:
                add_issue(
                    issues,
                    "error",
                    rel(path),
                    "record without id",
                )
                continue

            if item_id in seen:
                add_issue(
                    issues,
                    "error",
                    "registers",
                    f"duplicate ID {item_id} "
                    f"in {seen[item_id]} and "
                    f"{collection_name}",
                )

            seen[item_id] = collection_name

    for item in result_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        status = item.get("status")

        if status not in RESULT_STATUSES:
            add_issue(
                issues,
                "error",
                rel(RESULTS),
                f"{item.get('id')}: "
                f"invalid result status {status}",
            )

        if status in {
            "reviewed",
            "validated",
        }:
            if not item.get("evidence"):
                add_issue(
                    issues,
                    "error",
                    rel(RESULTS),
                    f"{item.get('id')}: "
                    f"{status} requires evidence",
                )

            if not item.get("review_date"):
                add_issue(
                    issues,
                    "error",
                    rel(RESULTS),
                    f"{item.get('id')}: "
                    f"{status} requires review_date",
                )

        if status == "validated":
            if not item.get(
                "validation_criteria"
            ):
                add_issue(
                    issues,
                    "error",
                    rel(RESULTS),
                    f"{item.get('id')}: "
                    "validated requires validation_criteria",
                )

            kinds = {
                evidence.get("kind")
                for evidence
                in item.get(
                    "evidence",
                    [],
                )
                if isinstance(
                    evidence,
                    dict,
                )
            }

            if not (
                kinds & REPRO_KINDS
            ):
                add_issue(
                    issues,
                    "error",
                    rel(RESULTS),
                    f"{item.get('id')}: "
                    "validated requires reproducible "
                    f"evidence kind {sorted(REPRO_KINDS)}",
                )

    for item in hypothesis_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            item.get("status")
            not in HYP_STATUSES
        ):
            add_issue(
                issues,
                "error",
                rel(HYPOTHESES),
                f"{item.get('id')}: "
                "invalid hypothesis status "
                f"{item.get('status')}",
            )

    for item in decision_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            item.get("status")
            not in DECISION_STATUSES
        ):
            add_issue(
                issues,
                "error",
                rel(DECISIONS),
                f"{item.get('id')}: "
                "invalid decision status "
                f"{item.get('status')}",
            )

    hypothesis_ids = {
        item.get("id")
        for item in hypothesis_items
        if isinstance(
            item,
            dict,
        )
    }

    result_ids = {
        item.get("id")
        for item in result_items
        if isinstance(
            item,
            dict,
        )
    }

    evidence_ids = {
        item.get("id")
        for item in evidence_items
        if isinstance(
            item,
            dict,
        )
    }

    model_ids = {
        item.get("id")
        for item in model_items
        if isinstance(
            item,
            dict,
        )
    }

    for item in hypothesis_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        for key in (
            "supporting_evidence",
            "conflicting_evidence",
            "relevant_evidence",
            "historical_target_evidence",
        ):
            for evidence_id in (
                item.get(key, [])
                or []
            ):
                if (
                    evidence_id
                    not in evidence_ids
                ):
                    add_issue(
                        issues,
                        "error",
                        rel(HYPOTHESES),
                        f"{item.get('id')}: "
                        f"unknown evidence ID "
                        f"{evidence_id}",
                    )

    for item in evidence_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        evidence_id = item.get("id")

        if (
            evidence_id
            and not str(
                evidence_id
            ).startswith("EV-")
        ):
            add_issue(
                issues,
                "warning",
                rel(EVIDENCE),
                f"{evidence_id}: "
                "evidence ID should start with EV-",
            )

        origin_type = item.get(
            "origin_type"
        )

        if (
            origin_type
            not in ORIGIN_TYPES
        ):
            add_issue(
                issues,
                "error",
                rel(EVIDENCE),
                f"{evidence_id}: "
                f"invalid origin_type "
                f"{origin_type}",
            )

        review_status = item.get(
            "review_status"
        )

        if (
            review_status
            not in EVIDENCE_REVIEW_STATUSES
        ):
            add_issue(
                issues,
                "error",
                rel(EVIDENCE),
                f"{evidence_id}: "
                f"invalid review_status "
                f"{review_status}",
            )

        provenance_status = item.get(
            "provenance_status"
        )

        if (
            provenance_status
            not in PROVENANCE_STATUSES
        ):
            add_issue(
                issues,
                "error",
                rel(EVIDENCE),
                f"{evidence_id}: "
                "invalid provenance_status "
                f"{provenance_status}",
            )

        interpretation = item.get(
            "interpretation"
        )

        if isinstance(
            interpretation,
            dict,
        ):
            hypothesis_id = (
                interpretation.get(
                    "hypothesis_id"
                )
            )

            if (
                hypothesis_id
                and hypothesis_id
                not in hypothesis_ids
            ):
                add_issue(
                    issues,
                    "error",
                    rel(EVIDENCE),
                    f"{evidence_id}: "
                    f"unknown hypothesis_id "
                    f"{hypothesis_id}",
                )

    for item in model_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        model_id = item.get("id")

        if (
            model_id
            and not str(
                model_id
            ).startswith("MOD-")
        ):
            add_issue(
                issues,
                "warning",
                rel(MODELS),
                f"{model_id}: "
                "model ID should start with MOD-",
            )

        if not item.get("purpose"):
            add_issue(
                issues,
                "error",
                rel(MODELS),
                f"{model_id}: "
                "model requires purpose",
            )

        status = item.get("status")

        if (
            status
            not in MODEL_STATUSES
        ):
            add_issue(
                issues,
                "error",
                rel(MODELS),
                f"{model_id}: "
                f"invalid model status {status}",
            )

        parent = item.get(
            "parent_model"
        )

        if (
            parent
            and parent
            not in model_ids
        ):
            add_issue(
                issues,
                "error",
                rel(MODELS),
                f"{model_id}: "
                f"unknown parent_model {parent}",
            )

    meta = require_mapping(
        load_yaml(META, issues),
        META,
        issues,
    )

    if meta:
        active_hypotheses = (
            meta.get(
                "control",
                {},
            ).get(
                "active_hypothesis_ids",
                [],
            )
            if isinstance(
                meta.get("control"),
                dict,
            )
            else []
        )

        for hypothesis_id in (
            active_hypotheses
        ):
            if (
                hypothesis_id
                not in hypothesis_ids
            ):
                add_issue(
                    issues,
                    "error",
                    rel(META),
                    f"unknown active_hypothesis_id "
                    f"{hypothesis_id}",
                )


def markdown_and_path_checks(issues):
    for path in ROOT.rglob("*.md"):
        if excluded_from_validation(path):
            continue

        text = path.read_text(
            encoding="utf-8"
        )

        latex_checks(
            path,
            text,
            issues,
        )

        markdown_links(
            path,
            text,
            issues,
        )

        path_leak_checks(
            path,
            text,
            issues,
        )

    for path in ROOT.rglob("*.yaml"):
        if excluded_from_validation(path):
            continue

        text = path.read_text(
            encoding="utf-8"
        )

        path_leak_checks(
            path,
            text,
            issues,
        )


def reentry_check(issues):
    refresh_script = (
        ROOT
        / "scripts"
        / "kb_refresh.py"
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(refresh_script),
            "--check",
        ],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        detail = (
            proc.stdout
            + "\n"
            + proc.stderr
        ).strip()

        message = (
            "generated re-entry blocks "
            "are out of sync; "
            "run scripts/kb_refresh.py"
        )

        if detail:
            message += f" [{detail}]"

        add_issue(
            issues,
            "error",
            "reentry",
            message,
        )


def file_size_checks(issues):
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        path_str = rel(path).replace(
            "\\",
            "/",
        )

        if excluded_from_validation(path):
            continue

        if path_str.startswith(".git/"):
            continue

        if (
            path.stat().st_size
            > 10 * 1024 * 1024
        ):
            add_issue(
                issues,
                "warning",
                rel(path),
                "file larger than 10 MiB; "
                "check Git policy",
            )


def git_whitespace_checks(issues):
    commands = (
        ("working tree", ["git", "diff", "--check"]),
        ("index", ["git", "diff", "--cached", "--check"]),
    )

    for label, command in commands:
        try:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            add_issue(
                issues,
                "error",
                "git",
                "Git executable is unavailable; whitespace checks did not run",
            )
            return

        if proc.returncode != 0:
            detail = (proc.stdout + "\n" + proc.stderr).strip()
            message = f"git whitespace check failed for {label}"

            if detail:
                message += f": {detail}"

            add_issue(
                issues,
                "error",
                "git",
                message,
            )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--strict",
        action="store_true",
    )

    args = parser.parse_args()

    issues = []

    # Parse every active YAML file at least once.
    for path in ROOT.rglob("*.yaml"):
        if excluded_from_validation(path):
            continue

        load_yaml(
            path,
            issues,
        )

    metadata_checks(issues)
    manifest_checks(issues)
    register_checks(issues)
    markdown_and_path_checks(issues)
    reentry_check(issues)
    file_size_checks(issues)
    git_whitespace_checks(issues)

    report = {
        "root": str(ROOT),
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "errors": sum(
            item["level"] == "error"
            for item in issues
        ),
        "warnings": sum(
            item["level"] == "warning"
            for item in issues
        ),
        "issues": issues,
    }

    REPORT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "errors": report["errors"],
                "warnings": report["warnings"],
            },
            ensure_ascii=False,
        )
    )

    for item in issues:
        print(
            f"{item['level'].upper()}: "
            f"{item['file']}: "
            f"{item['message']}"
        )

    if report["errors"]:
        return 2

    if (
        args.strict
        and report["warnings"]
    ):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
