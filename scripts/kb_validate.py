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


def strip_fences(text):
    text = re.sub(
        r"```.*?```",
        "",
        text,
        flags=re.S,
    )

    text = re.sub(
        r"~~~.*?~~~",
        "",
        text,
        flags=re.S,
    )

    text = re.sub(
        r"`[^`\n]*`",
        "",
        text,
    )

    return text


def latex_checks(path, text, issues):
    clean = strip_fences(text)

    if clean.count("$$") % 2:
        add_issue(
            issues,
            "error",
            rel(path),
            "odd number of $$ delimiters",
        )

    begins = re.findall(
        r"\\begin\{([^}]+)\}",
        clean,
    )

    ends = re.findall(
        r"\\end\{([^}]+)\}",
        clean,
    )

    if sorted(begins) != sorted(ends):
        add_issue(
            issues,
            "error",
            rel(path),
            f"LaTeX environment mismatch: begin={begins}, end={ends}",
        )

    display_spans = [
        match.span()
        for match in re.finditer(
            r"\$\$.*?\$\$",
            clean,
            flags=re.S,
        )
    ]

    for env in (
        "aligned",
        "pmatrix",
        "matrix",
        "bmatrix",
        "cases",
    ):
        for match in re.finditer(
            r"\\begin\{" + env + r"\}",
            clean,
        ):
            if not any(
                start <= match.start() < end
                for start, end in display_spans
            ):
                add_issue(
                    issues,
                    "error",
                    rel(path),
                    f"{env} environment outside $$ math block",
                )

    for line_no, line in enumerate(
        clean.splitlines(),
        1,
    ):
        if re.match(
            r"^ {4,}\$\$",
            line,
        ):
            add_issue(
                issues,
                "warning",
                rel(path),
                f"indented display math at line {line_no}",
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

    if path_str.startswith("Archive/legacy/"):
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
        if rel_posix(path).startswith("Archive/legacy/"):
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
        if rel_posix(path).startswith("Archive/legacy/"):
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

        if (
            "Archive/legacy/"
            in path_str
        ):
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
        if rel_posix(path).startswith("Archive/legacy/"):
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
