#!/usr/bin/env python3
"""Apply small declarative project-control transitions with rollback safety."""

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import argparse
import os
import re
import stat
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]

META = ROOT / "00_Project" / "PROJECT_METADATA.yaml"
CONTROL = ROOT / "00_Project" / "PROJECT_CONTROL.md"
STATE = ROOT / "00_Project" / "PROJECT_STATE.md"
README = ROOT / "README.md"
REPORT = ROOT / "VALIDATION_REPORT.json"

REFRESH = ROOT / "scripts" / "kb_refresh.py"
VALIDATE = ROOT / "scripts" / "kb_validate.py"

FORBIDDEN_REGISTERS = (
    ROOT / "00_Project" / "EVIDENCE_REGISTER.yaml",
    ROOT / "00_Project" / "RESULT_REGISTER.yaml",
    ROOT / "00_Project" / "HYPOTHESIS_REGISTER.yaml",
    ROOT / "00_Project" / "MODEL_REGISTER.yaml",
    ROOT / "00_Project" / "DECISION_REGISTER.yaml",
)

TOP_LEVEL_KEYS = {
    "schema_version",
    "expected_head",
    "metadata_patch",
    "control_queue_updates",
}

METADATA_KEYS = {
    "updated",
    "current_milestone",
    "immediate_next_step",
    "control",
}

MILESTONE_KEYS = {"id", "title", "status"}
NEXT_STEP_KEYS = {"id", "text"}
CONTROL_KEYS = {
    "now",
    "why",
    "next",
    "next_work_job",
    "blocked",
    "deferred",
    "last_scientific_source",
    "last_work_checkpoint",
    "active_hypothesis_ids",
    "key_risk_ids",
}
CONTROL_LIST_KEYS = {
    "blocked",
    "deferred",
    "active_hypothesis_ids",
    "key_risk_ids",
}
CONTROL_NULLABLE_KEYS = {
    "next_work_job",
    "last_work_checkpoint",
}
QUEUE_UPDATE_KEYS = {"task_id", "status", "text"}

FOLDED_PATHS = {
    ("immediate_next_step", "text"),
    ("control", "now"),
    ("control", "why"),
    ("control", "next"),
    ("control", "last_scientific_source"),
}


class TransitionError(RuntimeError):
    pass


class PostWriteError(RuntimeError):
    pass


class FoldedString(str):
    pass


class StableDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


def represent_folded_string(dumper, value):
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str",
        str(value),
        style=">",
    )


StableDumper.add_representer(FoldedString, represent_folded_string)


def relative(path):
    return path.relative_to(ROOT).as_posix()


def run_git(arguments, check=True):
    proc = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if check and proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        raise TransitionError(
            f"git {' '.join(arguments)} failed"
            + (f": {detail}" if detail else "")
        )

    return proc


def load_yaml(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except Exception as exc:
        raise TransitionError(f"cannot read YAML {path}: {exc}") from exc


def require_mapping(value, label):
    if not isinstance(value, dict):
        raise TransitionError(f"{label} must be a mapping")
    return value


def require_nonempty_string(value, label, nullable=False):
    if value is None and nullable:
        return None

    if not isinstance(value, str) or not value.strip():
        raise TransitionError(f"{label} must be a non-empty string")

    return value


def require_string_list(value, label):
    if not isinstance(value, list):
        raise TransitionError(f"{label} must be a list")

    normalized = []

    for index, item in enumerate(value):
        normalized.append(
            require_nonempty_string(item, f"{label}[{index}]")
        )

    return normalized


def normalize_date(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    return require_nonempty_string(value, "metadata_patch.updated")


def reject_unknown(mapping, allowed, label):
    unknown = sorted(set(mapping) - allowed)

    if unknown:
        raise TransitionError(
            f"unknown {label} key(s): {', '.join(unknown)}"
        )


def validate_payload(payload):
    payload = require_mapping(payload, "payload")
    reject_unknown(payload, TOP_LEVEL_KEYS, "top-level")

    for required in ("schema_version", "expected_head"):
        if required not in payload:
            raise TransitionError(f"missing required top-level key: {required}")

    if str(payload["schema_version"]) != "1":
        raise TransitionError("schema_version must be 1")

    expected_head = require_nonempty_string(
        payload["expected_head"],
        "expected_head",
    ).lower()

    if not re.fullmatch(r"[0-9a-f]{40}", expected_head):
        raise TransitionError("expected_head must be a full 40-character Git SHA")

    normalized = {
        "schema_version": 1,
        "expected_head": expected_head,
        "metadata_patch": {},
        "control_queue_updates": [],
    }

    metadata_patch = payload.get("metadata_patch") or {}
    metadata_patch = require_mapping(metadata_patch, "metadata_patch")
    reject_unknown(metadata_patch, METADATA_KEYS, "metadata_patch")

    if "updated" in metadata_patch:
        normalized["metadata_patch"]["updated"] = normalize_date(
            metadata_patch["updated"]
        )

    for key, allowed in (
        ("current_milestone", MILESTONE_KEYS),
        ("immediate_next_step", NEXT_STEP_KEYS),
    ):
        if key not in metadata_patch:
            continue

        section = require_mapping(metadata_patch[key], f"metadata_patch.{key}")
        reject_unknown(section, allowed, f"metadata_patch.{key}")
        normalized_section = {}

        for field, value in section.items():
            normalized_section[field] = require_nonempty_string(
                value,
                f"metadata_patch.{key}.{field}",
            )

        normalized["metadata_patch"][key] = normalized_section

    if "control" in metadata_patch:
        control = require_mapping(
            metadata_patch["control"],
            "metadata_patch.control",
        )
        reject_unknown(control, CONTROL_KEYS, "metadata_patch.control")
        normalized_control = {}

        for key, value in control.items():
            label = f"metadata_patch.control.{key}"

            if key in CONTROL_LIST_KEYS:
                normalized_control[key] = require_string_list(value, label)
            else:
                normalized_control[key] = require_nonempty_string(
                    value,
                    label,
                    nullable=key in CONTROL_NULLABLE_KEYS,
                )

        normalized["metadata_patch"]["control"] = normalized_control

    queue_updates = payload.get("control_queue_updates") or []

    if not isinstance(queue_updates, list):
        raise TransitionError("control_queue_updates must be a list")

    seen_task_ids = set()

    for index, update in enumerate(queue_updates):
        label = f"control_queue_updates[{index}]"
        update = require_mapping(update, label)
        reject_unknown(update, QUEUE_UPDATE_KEYS, label)

        if "task_id" not in update:
            raise TransitionError(f"{label} missing task_id")

        if "status" not in update and "text" not in update:
            raise TransitionError(f"{label} must set status and/or text")

        normalized_update = {
            "task_id": require_nonempty_string(
                update["task_id"],
                f"{label}.task_id",
            )
        }

        for key in ("status", "text"):
            if key in update:
                normalized_update[key] = require_nonempty_string(
                    update[key],
                    f"{label}.{key}",
                )

        task_id = normalized_update["task_id"]

        if task_id in seen_task_ids:
            raise TransitionError(f"duplicate queue update for task_id {task_id}")

        seen_task_ids.add(task_id)
        normalized["control_queue_updates"].append(normalized_update)

    return normalized


def verify_head(expected_head):
    actual_head = run_git(["rev-parse", "HEAD"]).stdout.strip().lower()

    if actual_head != expected_head:
        raise TransitionError(
            f"expected_head mismatch: expected {expected_head}, actual {actual_head}"
        )


def path_modified(path, cached=False):
    arguments = ["diff", "--quiet"]

    if cached:
        arguments.append("--cached")

    arguments.extend(["--", relative(path)])
    proc = run_git(arguments, check=False)

    if proc.returncode not in (0, 1):
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        raise TransitionError(
            f"cannot inspect Git state for {relative(path)}"
            + (f": {detail}" if detail else "")
        )

    return proc.returncode == 1


def run_read_only_refresh_check():
    proc = subprocess.run(
        [sys.executable, str(REFRESH), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        raise TransitionError(
            "modified generated re-entry target is not in a safe, "
            "refresh-consistent state"
            + (f": {detail}" if detail else "")
        )


def split_table_cells(line):
    stripped = line.strip()

    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None

    body = stripped[1:-1]
    cells = []
    current = []
    index = 0

    while index < len(body):
        char = body[index]

        if char == "\\" and index + 1 < len(body):
            current.extend((char, body[index + 1]))
            index += 2
            continue

        if char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)

        index += 1

    cells.append("".join(current).strip())
    return cells


def find_queue_rows(text, task_id):
    matches = []

    for index, line in enumerate(text.splitlines()):
        cells = split_table_cells(line)

        if not cells or len(cells) != 3:
            continue

        row_task_id = cells[0].strip().strip("`")

        if row_task_id == task_id:
            matches.append((index, cells, line))

    return matches


def verify_control_row_safety(queue_updates):
    if not queue_updates or not path_modified(CONTROL):
        return

    head_proc = run_git(["show", f"HEAD:{relative(CONTROL)}"])
    head_text = head_proc.stdout
    current_text = CONTROL.read_text(encoding="utf-8")

    for update in queue_updates:
        task_id = update["task_id"]
        head_rows = find_queue_rows(head_text, task_id)
        current_rows = find_queue_rows(current_text, task_id)

        if len(head_rows) != 1 or len(current_rows) != 1:
            raise TransitionError(
                f"cannot establish safe pre-existing queue row for {task_id}"
            )

        if head_rows[0][2] != current_rows[0][2]:
            raise TransitionError(
                f"queue row {task_id} is already modified; refusing overwrite"
            )


def verify_worktree_safety(queue_updates):
    if path_modified(META) or path_modified(META, cached=True):
        raise TransitionError(
            "00_Project/PROJECT_METADATA.yaml is already modified; "
            "refusing overwrite"
        )

    generated_targets = [STATE, CONTROL]

    if README.exists():
        generated_targets.append(README)

    for path in generated_targets:
        if path_modified(path, cached=True):
            raise TransitionError(
                f"{relative(path)} has staged changes; refusing overwrite"
            )

    modified_generated = [
        path
        for path in generated_targets
        if path_modified(path)
    ]

    if modified_generated:
        # Explicit safe condition: all current AUTO blocks still exactly match
        # PROJECT_METADATA, so kb_refresh will preserve edits outside markers.
        run_read_only_refresh_check()

    verify_control_row_safety(queue_updates)


def flatten_metadata_patch(metadata_patch):
    leaves = []

    for key, value in metadata_patch.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                leaves.append(((key, nested_key), nested_value))
        else:
            leaves.append(((key,), value))

    return leaves


def get_nested(mapping, path):
    value = mapping

    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise TransitionError(
                "metadata target does not exist: " + ".".join(path)
            )
        value = value[key]

    return value


def set_nested(mapping, path, value):
    target = mapping

    for key in path[:-1]:
        if not isinstance(target, dict) or key not in target:
            raise TransitionError(
                "metadata target does not exist: " + ".".join(path)
            )
        target = target[key]

    if not isinstance(target, dict) or path[-1] not in target:
        raise TransitionError(
            "metadata target does not exist: " + ".".join(path)
        )

    target[path[-1]] = value


def mapping_entry(node, key, path_label):
    if not isinstance(node, yaml.MappingNode):
        raise TransitionError(f"metadata YAML path is not a mapping: {path_label}")

    matches = [
        (key_node, value_node)
        for key_node, value_node in node.value
        if key_node.value == key
    ]

    if len(matches) != 1:
        raise TransitionError(
            f"metadata YAML key must occur exactly once: {path_label}.{key}"
        )

    return matches[0]


def metadata_entry_span(root_node, path):
    node = root_node

    for key in path[:-1]:
        _, node = mapping_entry(node, key, ".".join(path[:-1]) or "root")

    key_node, value_node = mapping_entry(
        node,
        path[-1],
        ".".join(path[:-1]) or "root",
    )

    end_line = value_node.end_mark.line

    # PyYAML points at the end column on the same line for a plain scalar,
    # but at column zero of the following line for block scalars/sequences.
    if value_node.end_mark.column:
        end_line += 1

    return (
        key_node.start_mark.line,
        end_line,
        key_node.start_mark.column,
    )


def dump_mapping_fragment(key, value, path):
    if path in FOLDED_PATHS and isinstance(value, str):
        value = FoldedString(value)

    fragment = yaml.dump(
        {key: value},
        Dumper=StableDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=88,
    )
    return fragment.rstrip("\n").splitlines()


def render_metadata(original_text, leaves):
    if not leaves:
        return original_text

    root_node = yaml.compose(original_text)

    if root_node is None:
        raise TransitionError("PROJECT_METADATA.yaml is empty")

    replacements = []

    for path, value in leaves:
        start, end, indent = metadata_entry_span(root_node, path)
        fragment = dump_mapping_fragment(path[-1], value, path)
        prefix = " " * indent
        replacements.append(
            (start, end, [prefix + line if line else line for line in fragment])
        )

    lines = original_text.splitlines()

    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = replacement

    rendered = "\n".join(lines) + "\n"
    return rendered


def escape_table_cell(value):
    return value.replace("|", r"\|")


def render_control_queue(original_text, updates, changes):
    if not updates:
        return original_text

    lines = original_text.splitlines()

    for update in updates:
        task_id = update["task_id"]
        matches = find_queue_rows("\n".join(lines), task_id)

        if len(matches) != 1:
            raise TransitionError(
                f"PROJECT_CONTROL queue must contain exactly one row for "
                f"{task_id}; found {len(matches)}"
            )

        line_index, cells, _ = matches[0]
        old_status = cells[1]
        old_text = cells[2]
        new_status = escape_table_cell(update.get("status", old_status))
        new_text = escape_table_cell(update.get("text", old_text))

        if new_status != old_status:
            changes.append(
                (f"control_queue.{task_id}.status", old_status, new_status)
            )

        if new_text != old_text:
            changes.append(
                (f"control_queue.{task_id}.text", old_text, new_text)
            )

        if new_status == old_status and new_text == old_text:
            continue

        lines[line_index] = (
            f"| `{task_id}` | {new_status} | {new_text} |"
        )

    return "\n".join(lines) + "\n"


def build_plan(payload):
    original_metadata_text = META.read_text(encoding="utf-8")
    original_control_text = CONTROL.read_text(encoding="utf-8")
    metadata = load_yaml(META)

    if not isinstance(metadata, dict):
        raise TransitionError("PROJECT_METADATA.yaml must contain a mapping")

    new_metadata = deepcopy(metadata)
    leaves = flatten_metadata_patch(payload["metadata_patch"])
    changed_leaves = []
    changes = []

    for path, value in leaves:
        old_value = get_nested(new_metadata, path)

        if old_value != value:
            changes.append(("metadata." + ".".join(path), old_value, value))
            set_nested(new_metadata, path, value)
            changed_leaves.append((path, value))

    new_metadata_text = render_metadata(original_metadata_text, changed_leaves)

    try:
        reparsed_metadata = yaml.safe_load(new_metadata_text)
    except Exception as exc:
        raise TransitionError(f"rendered PROJECT_METADATA is invalid: {exc}") from exc

    if reparsed_metadata != new_metadata:
        raise TransitionError(
            "deterministic YAML rendering changed metadata semantics"
        )

    new_control_text = render_control_queue(
        original_control_text,
        payload["control_queue_updates"],
        changes,
    )

    files = {}

    if new_metadata_text != original_metadata_text:
        files[META] = new_metadata_text

    if new_control_text != original_control_text:
        files[CONTROL] = new_control_text

    return changes, files


def format_value(value):
    rendered = yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=True,
        sort_keys=False,
    ).strip()
    return "\n".join(
        line
        for line in rendered.splitlines()
        if line != "..."
    )


def print_plan(changes, files):
    print("PLANNED_SEMANTIC_CHANGES")

    if not changes:
        print(" - none")
    else:
        for path, old, new in changes:
            print(f" - {path}: {format_value(old)} -> {format_value(new)}")

    print("FILES_TO_TOUCH")

    planned = set(files)
    change_paths = {path for path, _, _ in changes}

    if any(
        path.startswith("metadata.current_milestone.")
        or path.startswith("metadata.immediate_next_step.")
        for path in change_paths
    ):
        planned.add(STATE)

    if any(path.startswith("metadata.control.") for path in change_paths):
        planned.add(CONTROL)

    readme_metadata_paths = {
        "metadata.updated",
        "metadata.current_milestone.id",
        "metadata.current_milestone.title",
        "metadata.current_milestone.status",
        "metadata.immediate_next_step.id",
        "metadata.immediate_next_step.text",
        "metadata.control.now",
    }

    if (
        change_paths & readme_metadata_paths
        and README.exists()
        and "AUTO:README_STATUS" in README.read_text(encoding="utf-8")
    ):
        planned.add(README)

    if not planned:
        print(" - none")
    else:
        for path in sorted(planned, key=relative):
            print(" -", relative(path))


def atomic_write_bytes(path, data, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".project_transition_",
        dir=path.parent,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        if mode is not None:
            os.chmod(temp_path, stat.S_IMODE(mode))

        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_text(path, text):
    mode = path.stat().st_mode if path.exists() else 0o644
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def snapshot(paths):
    result = {}

    for path in paths:
        if path.exists():
            result[path] = (path.read_bytes(), path.stat().st_mode)
        else:
            result[path] = (None, None)

    return result


def restore(snapshot_data):
    for path, (data, mode) in snapshot_data.items():
        if data is None:
            if path.exists():
                path.unlink()
        else:
            atomic_write_bytes(path, data, mode)


def changed_snapshot_paths(snapshot_data):
    changed = []

    for path, (data, _) in snapshot_data.items():
        current = path.read_bytes() if path.exists() else None

        if current != data:
            changed.append(path)

    return changed


def run_post_write_step(label, command):
    print(label)
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if proc.stdout.strip():
        print(proc.stdout.strip())

    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    if proc.returncode != 0:
        raise PostWriteError(f"{label} failed with exit code {proc.returncode}")


def apply_plan(files):
    snapshot_paths = [META, CONTROL, STATE, REPORT, *FORBIDDEN_REGISTERS]

    if README.exists():
        snapshot_paths.append(README)

    before = snapshot(snapshot_paths)

    try:
        for path, text in files.items():
            atomic_write_text(path, text)

        run_post_write_step(
            "RUN kb_refresh.py",
            [sys.executable, str(REFRESH)],
        )
        run_post_write_step(
            "RUN kb_refresh.py --check",
            [sys.executable, str(REFRESH), "--check"],
        )
        run_post_write_step(
            "RUN kb_validate.py --strict",
            [sys.executable, str(VALIDATE), "--strict"],
        )

        for path in FORBIDDEN_REGISTERS:
            original, _ = before[path]
            current = path.read_bytes() if path.exists() else None

            if current != original:
                raise PostWriteError(
                    f"forbidden register changed unexpectedly: {relative(path)}"
                )

    except Exception:
        restore(before)
        print("ROLLBACK: restored all files touched by the transition")
        raise

    changed = changed_snapshot_paths(before)
    print("CHANGED_FILES")

    if not changed:
        print(" - none")
    else:
        for path in sorted(changed, key=relative):
            print(" -", relative(path))

    stat_proc = run_git(["diff", "--stat"])
    print("GIT_DIFF_STAT")
    print(stat_proc.stdout.rstrip() or "(empty)")
    print("VALIDATION: PASS")


def main():
    parser = argparse.ArgumentParser(
        description="Apply a safe declarative Project Control transition",
    )
    parser.add_argument("payload", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        payload = validate_payload(load_yaml(args.payload))
        verify_head(payload["expected_head"])
        verify_worktree_safety(payload["control_queue_updates"])
        changes, files = build_plan(payload)
        print_plan(changes, files)

        if args.check:
            print("CHECK_ONLY: no files modified")
            return 0

        apply_plan(files)
        return 0

    except (TransitionError, PostWriteError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
