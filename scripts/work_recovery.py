#!/usr/bin/env python3
"""Preserve interrupted work locally; diagnose, never automatically restore.

Production Git calls are read-only and have optional index writes disabled.
Only selftest unpacks/mutates its fixed disposable Git fixture, never a project.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile


RECOVERY_REL = "CEF_Dy_Backup/work_recovery"
CONTROL_FILES = ("00_Project/PROJECT_CONTROL.md", "00_Project/PROJECT_METADATA.yaml")
READ_ONLY_GIT = frozenset({"rev-parse", "symbolic-ref", "status", "diff",
                           "ls-files", "cat-file", "check-ignore"})
SNAPSHOT_RE = re.compile(r"\d{8}T\d{12}Z_[0-9a-f]{8}_(start|panic)\Z")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


class RecoveryError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(path):
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            hasher.update(chunk)
    return {"size_bytes": size, "sha256": hasher.hexdigest()}


def is_link(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def child(base, relative):
    """Reject traversal and symlink/junction components before any file access."""
    rel = PurePosixPath(relative)
    if (not relative or rel.is_absolute() or str(rel) != relative or
            ".." in rel.parts or "\\" in relative or ":" in relative):
        raise RecoveryError(f"Unsafe relative path: {relative!r}")
    target = base
    if is_link(base):
        raise RecoveryError(f"Symlink/junction not followed: {base}")
    for component in rel.parts:
        target = target / component
        if is_link(target):
            raise RecoveryError(f"Symlink/junction not followed: {target}")
    return target


def validate_job(job):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", job) or
            job.endswith(".") or job.split(".")[0].upper() in RESERVED):
        raise RecoveryError("JOB_ID must be a portable identifier, not a path")
    return job


def git(root, *args, allowed=(0,)):
    if not args or args[0] not in READ_ONLY_GIT:
        raise RecoveryError("Non-inspection Git command refused")
    env = dict(os.environ)
    for key in list(env):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                   "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                   "GIT_NAMESPACE", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"} or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            env.pop(key, None)
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", LC_ALL="C")
    command = ["git", "--no-pager", "-c", "core.fsmonitor=false",
               "-c", "core.untrackedCache=false", "-c", "diff.autoRefreshIndex=false", *args]
    try:
        result = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoveryError(f"Git inspection failed: {args[0]}: {exc}") from exc
    if result.returncode not in allowed:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RecoveryError(f"Git inspection failed ({result.returncode}): {args!r}: {detail}")
    return result


def discover_root(cwd=None):
    result = git(Path.cwd() if cwd is None else cwd, "rev-parse", "--show-toplevel")
    root = Path(os.fsdecode(result.stdout).strip()).resolve(strict=True)
    if not root.is_dir():
        raise RecoveryError("Repository root cannot be identified reliably")
    return root


def storage(root, job):
    validate_job(job)
    probe = RECOVERY_REL + "/_probe"
    if git(root, "check-ignore", "-q", "--", probe, allowed=(0, 1)).returncode:
        raise RecoveryError(f"Required recovery root is not ignored: {RECOVERY_REL}")
    for directory in (RECOVERY_REL + "/", RECOVERY_REL + "/" + job + "/"):
        if git(root, "check-ignore", "-q", "--", directory, allowed=(0, 1)).returncode:
            raise RecoveryError(f"Recovery directory itself is not ignored: {directory}")
    if git(root, "ls-files", "-z", "--", "CEF_Dy_Backup/").stdout:
        raise RecoveryError("Recovery/data tree already contains tracked paths; refusing snapshot")
    return child(root, RECOVERY_REL + "/" + job)


def nul_paths(data):
    return sorted(set(os.fsdecode(item) for item in data.split(b"\0") if item))


def index_entries(data):
    result = {}
    for record in data.split(b"\0"):
        if not record:
            continue
        header, sep, filename = record.partition(b"\t")
        parts = header.split()
        if not sep or len(parts) != 3 or not re.fullmatch(rb"[0-9a-f]{40,64}", parts[1]):
            raise RecoveryError("Unrecognized index entry")
        mode, oid, stage = (p.decode("ascii") for p in parts)
        result.setdefault(os.fsdecode(filename), []).append({"mode": mode, "oid": oid, "stage": int(stage)})
    return result


def collect_state(root):
    head = git(root, "rev-parse", "--verify", "HEAD").stdout.decode("ascii").strip()
    branch_result = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", allowed=(0, 1))
    branch = os.fsdecode(branch_result.stdout).strip() if branch_result.returncode == 0 else "(detached)"
    diff_args = ("--no-ext-diff", "--no-textconv", "--no-color", "--no-renames")
    unstaged = nul_paths(git(root, "diff", *diff_args, "--name-only", "-z", "--").stdout)
    staged = nul_paths(git(root, "diff", "--cached", *diff_args, "--name-only", "-z", "--").stdout)
    untracked = nul_paths(git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout)
    raw_index = git(root, "ls-files", "--stage", "-z").stdout
    entries = index_entries(raw_index)
    index_path = Path(os.fsdecode(git(root, "rev-parse", "--git-path", "index").stdout).strip())
    if not index_path.is_absolute():
        index_path = root / index_path
    if is_link(index_path):
        raise RecoveryError("Symlink/junction Git index refused")
    index_identity = digest(index_path) if index_path.exists() else None
    unmerged = sorted(p for p, values in entries.items() if any(v["stage"] for v in values))
    operations = []
    for label, marker in (("merge", "MERGE_HEAD"), ("rebase", "rebase-merge"),
                          ("rebase", "rebase-apply"), ("cherry-pick", "CHERRY_PICK_HEAD"),
                          ("revert", "REVERT_HEAD"), ("sequencer", "sequencer"),
                          ("bisect", "BISECT_LOG"), ("index-lock", "index.lock"),
                          ("HEAD-lock", "HEAD.lock")):
        path = Path(os.fsdecode(git(root, "rev-parse", "--git-path", marker).stdout).strip())
        if not path.is_absolute():
            path = root / path
        if path.exists() and label not in operations:
            operations.append(label)
    return {
        "head": head, "branch": branch, "unstaged": unstaged, "staged": staged,
        "untracked": untracked, "unmerged": unmerged, "operations": operations,
        "status_b64": base64.b64encode(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout).decode("ascii"),
        "index_b64": base64.b64encode(raw_index).decode("ascii"), "index_entries": entries,
        "index_file_identity": index_identity,
    }


def file_state(root, relative):
    path = child(root, relative)
    try:
        st = path.stat()
    except FileNotFoundError:
        return {"exists": False}
    if not stat.S_ISREG(st.st_mode):
        raise RecoveryError(f"Required path is not a regular file: {relative}")
    return {"exists": True, "mode": stat.S_IMODE(st.st_mode), **digest(path)}


def copy_current(root, relative, snapshot, prefix):
    before = file_state(root, relative)
    entry = {"path": relative, **before}
    if before["exists"]:
        dest_rel = prefix + "/" + relative
        target = child(snapshot, dest_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(child(root, relative), target)
        if digest(target) != {k: before[k] for k in ("sha256", "size_bytes")} or file_state(root, relative) != before:
            raise RecoveryError(f"Source changed while copying: {relative}")
        entry["stored_path"] = dest_rel
    return entry


def all_artifacts(snapshot):
    names = []
    for directory, dirs, files in os.walk(snapshot, followlinks=False):
        for name in dirs:
            path = Path(directory) / name
            if is_link(path):
                raise RecoveryError(f"Snapshot contains a symlink/junction: {path}")
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(snapshot).as_posix()
            child(snapshot, relative)
            if not path.is_file():
                raise RecoveryError(f"Non-regular snapshot artifact: {relative}")
            if relative not in {"snapshot_manifest.json", "COMPLETE"}:
                names.append(relative)
    return sorted(names)


def verify_snapshot(snapshot, require_complete=True):
    try:
        manifest_path = child(snapshot, "snapshot_manifest.json")
        manifest = json.loads(manifest_path.read_bytes())
        if not isinstance(manifest, dict):
            raise RecoveryError("Manifest must be a JSON object")
        if require_complete:
            marker = json.loads(child(snapshot, "COMPLETE").read_bytes())
            if (not isinstance(marker, dict) or marker.get("format_version") != 1 or
                    marker.get("manifest_sha256") != digest(manifest_path)["sha256"]):
                raise RecoveryError("Manifest checksum differs from COMPLETE seal")
        if manifest.get("format_version") != 1:
            raise RecoveryError("Unsupported snapshot format")
        entries = manifest["files"]
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise RecoveryError("Malformed manifest entries")
        paths = [item["path"] for item in entries]
        if paths != sorted(set(paths)) or paths != all_artifacts(snapshot):
            raise RecoveryError("Manifest coverage/order mismatch: extra, missing or duplicate file")
        for entry in entries:
            actual = digest(child(snapshot, entry["path"]))
            if actual != {k: entry[k] for k in ("size_bytes", "sha256")}:
                raise RecoveryError(f"Snapshot artifact checksum mismatch: {entry['path']}")
        metadata = json.loads(child(snapshot, "metadata.json").read_bytes())
        if metadata["snapshot_id"] != snapshot.name or metadata["job_id"] != snapshot.parent.name:
            raise RecoveryError("Snapshot/job identity mismatch")
        if not SNAPSHOT_RE.fullmatch(snapshot.name) or not snapshot.name.endswith("_" + metadata["mode"]):
            raise RecoveryError("Invalid snapshot identity/mode")
        return True, metadata, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecoveryError) as exc:
        return False, None, [str(exc)]


def write_pointer(job_dir, snapshot):
    pointer = {"format_version": 1, "job_id": job_dir.name, "snapshot_id": snapshot.name}
    with tempfile.NamedTemporaryFile(dir=job_dir, prefix=".latest_start_", suffix=".tmp", delete=False) as stream:
        stream.write(json_bytes(pointer))
        temp = Path(stream.name)
    os.replace(temp, child(job_dir, "latest_start.json"))


def make_snapshot(root, job, mode):
    job_dir = storage(root, job)
    stamp = utc_now()
    snapshot_id = stamp.strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex[:8] + "_" + mode
    snapshot = child(job_dir, snapshot_id)
    snapshot.mkdir(parents=True, exist_ok=False)
    try:
        before = collect_state(root)
        metadata = {
            "format_version": 1, "repository_root": str(root), "snapshot_id": snapshot_id,
            "timestamp_utc": stamp.isoformat().replace("+00:00", "Z"), "mode": mode,
            "job_id": job, "platform": platform.platform(), "python_executable": sys.executable,
            "python_version": platform.python_version(), "state": before,
            "worktree_files": [], "index_files": [], "control_context": [], "commands": {},
        }
        diff = ("--no-ext-diff", "--no-textconv", "--no-color", "--no-renames")
        commands = {
            "git_status_short.txt": ("status", "--short", "--untracked-files=all"),
            "git_diff.patch": ("diff", *diff, "--binary", "--"),
            "git_diff_cached.patch": ("diff", "--cached", *diff, "--binary", "--"),
            "git_diff_check.txt": ("diff", *diff, "--check", "--"),
            "git_diff_cached_check.txt": ("diff", "--cached", *diff, "--check", "--"),
            "git_diff_stat.txt": ("diff", *diff, "--stat", "--"),
            "git_diff_cached_stat.txt": ("diff", "--cached", *diff, "--stat", "--"),
        }
        failed_commands = []
        for name, args in commands.items():
            proc = git(root, *args, allowed=tuple(range(256)))
            child(snapshot, name).write_bytes(proc.stdout + (proc.stderr if name.endswith("check.txt") else b""))
            metadata["commands"][name] = {"args": list(args), "returncode": proc.returncode,
                                           "stderr": proc.stderr.decode("utf-8", "replace")}
            if proc.returncode:
                failed_commands.append(name)
        changed = sorted(set(before["unstaged"] + before["staged"] + before["unmerged"]))
        for name, paths in (("tracked_changed_files.txt", changed), ("staged_files.txt", before["staged"]),
                            ("untracked_files.txt", before["untracked"])):
            # JSON-quoted paths, one per line, preserve unusual filenames unambiguously.
            child(snapshot, name).write_bytes(("".join(json.dumps(p, ensure_ascii=True) + "\n" for p in paths)).encode())
        child(snapshot, "git_status_porcelain_z.bin").write_bytes(base64.b64decode(before["status_b64"]))
        child(snapshot, "git_index_stage_z.bin").write_bytes(base64.b64decode(before["index_b64"]))
        index_path = Path(os.fsdecode(git(root, "rev-parse", "--git-path", "index").stdout).strip())
        if not index_path.is_absolute():
            index_path = root / index_path
        if is_link(index_path):
            raise RecoveryError("Symlink/junction Git index refused")
        if before["index_file_identity"] is not None:
            shutil.copyfile(index_path, child(snapshot, "git_index.bin"))
            if digest(snapshot / "git_index.bin") != before["index_file_identity"]:
                raise RecoveryError("Git index changed while copying")
        for relative in sorted(set(changed + before["untracked"])):
            if relative == "CEF_Dy_Backup" or relative.startswith("CEF_Dy_Backup/"):
                raise RecoveryError("Refusing recursive capture of ignored recovery/data tree")
            metadata["worktree_files"].append(copy_current(root, relative, snapshot, "worktree_files"))
        for relative in sorted(set(before["staged"] + before["unmerged"])):
            versions = before["index_entries"].get(relative, [])
            if not versions:
                metadata["index_files"].append({"path": relative, "deleted": True})
            for version in versions:
                if version["mode"] == "160000":
                    raise RecoveryError(f"Changed submodule requires manual preservation: {relative}")
                prefix = "index_files" if version["stage"] == 0 else f"index_conflicts/{version['stage']}"
                stored = prefix + "/" + relative
                target = child(snapshot, stored)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git(root, "cat-file", "blob", version["oid"]).stdout)
                metadata["index_files"].append({"path": relative, "stored_path": stored, **version})
        for relative in CONTROL_FILES:
            entry = copy_current(root, relative, snapshot, "control_context")
            if not entry["exists"]:
                raise RecoveryError(f"Required control context is missing: {relative}")
            metadata["control_context"].append(entry)
        child(snapshot, "metadata.json").write_bytes(json_bytes(metadata))
        if failed_commands:
            raise RecoveryError("Required inspection failed: " + ", ".join(failed_commands))
        if collect_state(root) != before:
            raise RecoveryError("Git state changed during capture")
        for entry in metadata["worktree_files"] + metadata["control_context"]:
            expected = {k: v for k, v in entry.items() if k not in {"path", "stored_path"}}
            if file_state(root, entry["path"]) != expected:
                raise RecoveryError(f"File changed during capture: {entry['path']}")
        manifest = {"format_version": 1, "files": [
            {"path": relative, **digest(child(snapshot, relative))} for relative in all_artifacts(snapshot)
        ]}
        child(snapshot, "snapshot_manifest.json").write_bytes(json_bytes(manifest))
        valid, _, errors = verify_snapshot(snapshot, require_complete=False)
        if not valid:
            raise RecoveryError("; ".join(errors))
        # Pointer may name an incomplete snapshot after an interrupted final write;
        # selectors always require and verify COMPLETE, never trust the pointer alone.
        if mode == "start":
            write_pointer(job_dir, snapshot)
        pending = child(snapshot, ".COMPLETE.pending")
        pending.write_bytes(json_bytes({
            "format_version": 1, "manifest_sha256": digest(snapshot / "snapshot_manifest.json")["sha256"]
        }))
        os.replace(pending, child(snapshot, "COMPLETE"))
        return snapshot
    except Exception as exc:
        # Never delete partial material; COMPLETE is only attempted after success.
        raise RecoveryError(f"{exc}; partial snapshot preserved: {snapshot}") from exc


def snapshots(job_dir):
    if not job_dir.exists():
        return []
    result = []
    for path in job_dir.iterdir():
        if SNAPSHOT_RE.fullmatch(path.name):
            child(job_dir, path.name)
            if path.is_dir():
                result.append(path)
    return sorted(result, key=lambda p: p.name)


def select_snapshot(job_dir, selector=None):
    found = snapshots(job_dir)
    if selector:
        if not SNAPSHOT_RE.fullmatch(selector):
            raise RecoveryError("Snapshot selector must be a snapshot ID, not a path")
        chosen = child(job_dir, selector)
        if chosen not in found:
            raise RecoveryError("Selected snapshot does not exist for this job")
        return chosen
    complete = [p for p in found if child(p, "COMPLETE").is_file()]
    for mode in ("panic", "start"):
        matching = [p for p in complete if p.name.endswith("_" + mode)]
        if matching:
            return matching[-1]
    if found:
        return found[-1]  # Show a failed audit, never hide partial material.
    raise RecoveryError("No recovery snapshot exists for this job")


def empty_report(job):
    return {
        "RECOVERY_STATUS": "failed", "SNAPSHOT_ID": None, "SNAPSHOT_MODE": None,
        "JOB_ID": job, "SNAPSHOT_TIMESTAMP": None, "HEAD_SAVED": None, "HEAD_CURRENT": None,
        "BRANCH_SAVED": None, "BRANCH_CURRENT": None, "SNAPSHOT_INTEGRITY": "FAIL",
        "STAGED": None, "UNSTAGED": None, "UNTRACKED": None,
        "FILES_RECOVERED": {"preserved_copies": 0, "restored": 0},
        "CHANGED_SINCE_SNAPSHOT": [], "GIT_OPERATION_IN_PROGRESS": [],
        "DIFF_CHECK": "not_run", "SAFE_TO_RESUME": "no",
        "RECOMMENDED_NEXT_STEP": "Preserve current state and snapshots; obtain human review. No automatic repair.",
    }


def audit_snapshot(root, job, selector=None):
    job_dir = storage(root, job)
    chosen = select_snapshot(job_dir, selector)
    report = empty_report(job)
    report.update(SNAPSHOT_ID=chosen.name, SNAPSHOT_MODE=chosen.name.rsplit("_", 1)[1],
                  RECOVERY_ROOT=str(job_dir.parent), SNAPSHOT_PATH=str(chosen))
    good, metadata, errors = verify_snapshot(chosen)
    current = collect_state(root)
    diff = git(root, "diff", "--no-ext-diff", "--no-textconv", "--check", "--", allowed=tuple(range(256)))
    cached = git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--check", "--", allowed=tuple(range(256)))
    report.update(HEAD_CURRENT=current["head"], BRANCH_CURRENT=current["branch"],
                  STAGED=len(current["staged"]), UNSTAGED=len(current["unstaged"]),
                  UNTRACKED=len(current["untracked"]),
                  GIT_OPERATION_IN_PROGRESS=current["operations"],
                  DIFF_CHECK="PASS" if diff.returncode == 0 else "FAIL",
                  CACHED_DIFF_CHECK="PASS" if cached.returncode == 0 else "FAIL",
                  UNMERGED_PATHS=current["unmerged"])
    unsafe = list(errors)
    changed = []
    if good:
        saved = metadata["state"]
        report.update(SNAPSHOT_INTEGRITY="PASS", SNAPSHOT_TIMESTAMP=metadata["timestamp_utc"],
                      HEAD_SAVED=saved["head"], BRANCH_SAVED=saved["branch"])
        report["FILES_RECOVERED"]["preserved_copies"] = sum(
            "stored_path" in entry for key in ("worktree_files", "index_files", "control_context")
            for entry in metadata[key])
        if saved["head"] != current["head"]:
            unsafe.append("HEAD changed since snapshot")
        if saved["branch"] != current["branch"]:
            unsafe.append("Branch changed since snapshot")
        for field in ("status_b64", "index_b64"):
            if saved[field] != current[field]:
                changed.append("git_status" if field == "status_b64" else "git_index_versions")
        if saved["index_file_identity"] != current["index_file_identity"]:
            changed.append("git_index_file")
        for entry in metadata["worktree_files"] + metadata["control_context"]:
            expected = {k: v for k, v in entry.items() if k not in {"path", "stored_path"}}
            try:
                if file_state(root, entry["path"]) != expected:
                    changed.append(entry["path"])
            except (OSError, RecoveryError) as exc:
                unsafe.append(str(exc))
    if current["operations"] or current["unmerged"]:
        unsafe.append("Git operation or unresolved index entries present")
    if diff.returncode or cached.returncode:
        unsafe.append("Git whitespace check failed")
    incomplete = [p.name for p in snapshots(job_dir) if not child(p, "COMPLETE").is_file()]
    if any(name > chosen.name for name in incomplete):
        unsafe.append("A newer incomplete snapshot requires review")
    report["INCOMPLETE_SNAPSHOTS"] = incomplete
    report["CHANGED_SINCE_SNAPSHOT"] = sorted(set(changed))
    report["BLOCKERS"] = unsafe
    if not unsafe:
        report["RECOVERY_STATUS"] = "preserved_not_restored"
        report["SAFE_TO_RESUME"] = "review_required" if changed else "yes"
        report["RECOMMENDED_NEXT_STEP"] = (
            "Review differences against the snapshot before continuing; do not overwrite current work."
            if changed else
            "Review the job checkpoint and authorization; continue only the first verified unfinished step."
        )
    starts = [p for p in snapshots(job_dir) if p.name.endswith("_start") and child(p, "COMPLETE").is_file()]
    report["LATEST_START_ID"] = starts[-1].name if starts else None
    if starts:
        start_ok, baseline, start_errors = verify_snapshot(starts[-1])
        report["START_INTEGRITY"] = "PASS" if start_ok else "FAIL"
        report["HEAD_CHANGED_SINCE_START"] = current["head"] != baseline["state"]["head"] if start_ok else None
        report["BRANCH_CHANGED_SINCE_START"] = current["branch"] != baseline["state"]["branch"] if start_ok else None
        if start_errors:
            report["START_WARNINGS"] = start_errors
    return report


def emit_report(report):
    print(json.dumps(report, ensure_ascii=True, indent=2))


# Fixed test data, not a repository-operation implementation. The archive holds
# a tiny SHA-1 Git fixture and an alternate staged-index/HEAD fixture. Only the
# disposable selftest directory ever receives these bytes; no Git write command
# is called, and production commands cannot enter this setup path.
SELFTEST_FIXTURE = (
    "UEsDBBQAAAAIAAAAIVC1Y2RXFwAAABUAAAAJAAAALmdpdC9IRUFEK0pNs1IoSk0r1s9ITUwp1s9NzMzjAgBQSwMEFAAAAAgAAAAh"
    "UA4GsuNGAAAAVgAAAAsAAAAuZ2l0L2NvbmZpZ4tOzi9KjeVSKEotyC/OLMkvqkzLL8pNLClLLSrOzM9TsFUw4FJISixKBbLSEnOK"
    "U7kU0jJzUnPzU5BEEktL8pOLctLgIgBQSwMEFAAAAAgAAAAhUH5FhOYpAAAAKQAAABYAAAAuZ2l0L2ZpeHR1cmVfbmV4dF9oZWFk"
    "BcHJDQAgDAOwP9O0KUJhnB5h/xGw0RbaevWAYg0En9MVaaRDntQdan1QSwMEFAAAAAgAAAAhUAGcFvoaAQAAIAIAABkAAAAuZ2l0"
    "L2ZpeHR1cmVfc3RhZ2VkX2luZGV4c/EMcmZgYGACYjYGnKBxCTLPKO5z1tvfT3cLd1TvlYphcFiSsHA3A5deemZJZnpeflEqbnOw"
    "mycyb8GEH6yTNS5512d/ZD59/OC3hi4GWQOD+ICi/KzU5BL9gCB/L1fnkHhnf7+QIH8fvdwUkszfIHj8b/E593PfHP9Kbny1TzCc"
    "QSyfQQGL+b6uIY4ujiGOepWJuTnEm99b/WrrzLsGhStiA7S1lZR387z0L2PgS0xJSU1RSMvMSdUrqSghxb0n0tSS+7hPnHc/5blb"
    "VHUL33TzdykMXEmZeYlFlXpAioDnMczzS3wnJ7nF4ebvczJSom/aQ/rm/nzBwF1SlJicnZqC5DjJzCbuHb1el8x/b2j/szN2x8uv"
    "pfkAUEsDBBQAAAAIAAAAIVBnqBmPFAEAACACAAAKAAAALmdpdC9pbmRleHPxDHJmYGBgAmI2BpygcQkyzyjuc9bb3093C3dU75WK"
    "YXBYkrBwNwOXXnpmSWZ6Xn5RKm5zsJsnMm/BhB+skzUueddnf2Q+ffzgt4YuBlkDg/iAovys1OQS/YAgfy9X55B4Z3+/kCB/H73c"
    "FJLM3yB4/G/xOfdz3xz/Sm58tU8wnEEsn0EBi/m+riGOLo4hjnqVibk5xJt/Ik0tuY/7xHn3U567RVW38E03f5fCwJWUmZdYVKkH"
    "pEgNjxfP32XFMu6962/nx69pmeJ1/k77SwaulNSc1JJUvZKKElLNk+B2P9i9/EnLH97igD05a/sOO9ktYOAuKUpMzk5NQTLw/S3u"
    "LNOzfedsD+9e++D/6fjV/CubAVBLAwQUAAAACAAAACFQqlWObyUAAAAiAAAANgAAAC5naXQvb2JqZWN0cy8xNC85ZWEwOTBmODA1"
    "OTMyOGQyNGI3ZjZiZjEwM2NiYzdjMWY2ODA4YauY433qpH+QwZaEgLCC02s0NHW9Qj3OndfWPHX+IRNDziuOOgBQSwMEFAAAAAgA"
    "AAAhUB4Qcq4bAAAAGAAAADYAAAAuZ2l0L29iamVjdHMvMTgvMGI0N2MxOGJhN2U0ODRmYzBkNzM1MGJjNmNhZDhlYzM0MjNlYTCr"
    "mON96qR/0IYUDy8dv7Mnz3g/ZWLQjWN1AwBQSwMEFAAAAAgAAAAhUIx0uG2kAAAAnwAAADYAAAAuZ2l0L29iamVjdHMvMmMvMDNl"
    "NGVmYmYyMmI4YmQyZTIxZDZjYjNhMDg4MTJlMWE4ZTlkOGUBnwBg/3iclY5LCgIxEERd5xS9FyS/ziQgoqDiNTqZDg7Mj5CROb6D"
    "4gGsTdXiPag0DUNXQauwq4UZUuLgclDs2ZJVyBp1dGiVtLYNqI23QUbnxUyFxwqGNGmHlByyJDSaI24dyWT2qgkZU2g8N4KW+pwK"
    "3Lu1LoXhmL/jzCsNc8+HbnxR37UnkLCXW0T6PKv8jyN+KPWbOFJleNwuV/EGecRIRFBLAwQUAAAACAAAACFQBADsUSIAAAAfAAAA"
    "NgAAAC5naXQvb2JqZWN0cy8zMi81ZWYzNmFlZGZiZTViYjEzODg3YmJkMWE1YzAwNDBhNDYwYTFiYquY433qpH+QgUlqQVlpd/nK"
    "nnIvn3N6uheeMzEEL2X7BwBQSwMEFAAAAAgAAAAhUEdEp82AAAAAewAAADYAAAAuZ2l0L29iamVjdHMvM2EvMmEyNjVhYzY1ZTBh"
    "NTMyZWI1MGE1YmEzZmU4MTc5ZjVjOTc4ZTcBewCE/3iclY3BCgIhFEVb+xVvH4TaUxQiWs1/qHOHBJ0Jc2I+f6LoA7qrsziHm5Za"
    "cydlzaE3gFKCt5NXcODAykAbHa1hJZlHb/TZsZfROhHWfl8aDXnrawNdpi/csIX6KDjl+RVKHq8k6SjfE+nz1PFPI35qDE+UPEPs"
    "Eko4wFBLAwQUAAAACAAAACFQLDC2pSgAAAAlAAAANgAAAC5naXQvb2JqZWN0cy80ZS82MWVlMWUxOWI0NDBkOWZiY2UxYzFhMTVl"
    "Yzg3NTQ4ZTlkZjllOKuY433qpH+QgVGKx1oPH71ADT1PH3/fQA1vXa1zZ84/ZmKYeJ2LAQBQSwMEFAAAAAgAAAAhUDSd0ZtpAAAA"
    "ZAAAADYAAAAuZ2l0L29iamVjdHMvNWIvY2Y5ZmY1ZDFiMTFiY2NmZDBhY2NhZWYwMzFkNmY0YjI4MmI2MjkBZACb/3icKylKTVWw"
    "NGUwNDAwMzFRCAjy93J1Dol39vcLCfL30ctNYRCZt2DCD9bJGpe867M/Mp8+fvBbQxeaal/XEEcXxxBHvcrE3ByGDYLH/xafcz/3"
    "zfGv5MZX+wTDGcTyAR2lJmFQSwMEFAAAAAgAAAAhUJ6oRFQjAAAAIAAAADYAAAAuZ2l0L29iamVjdHMvOGQvN2JlYWI1OTlkZDMw"
    "NzFhODVkNTAyYjJiMjIyM2JiMGNlOTRmNzarmON96qR/kIFJsoaep4+/b6CHj+dJnZNnzj9mYkhW4hAFAFBLAwQUAAAACAAAACFQ"
    "OzakaCcAAAAkAAAANgAAAC5naXQvb2JqZWN0cy9iMC8xMWM3ZmQ3M2NlNDdjZWY2NDFmZDE5YjFlYWJlMTE1NzAwMTY2ZquY433q"
    "pH+QgVGChsap816+ep3nfTYGFXzu4eDkLXrKxNCayHEBAFBLAwQUAAAACAAAACFQgnM2+BkBAAAUAQAANgAAAC5naXQvb2JqZWN0"
    "cy9jOC82NjI2NjM4ZTBiYzhjZjQ3Y2E0OWJiMTUyNWI0MGU5NzM3ZWU2NAEUAev+eJwBCQH2/mJsb2IgMjU2AAABAgMEBQYHCAkK"
    "CwwNDg8QERITFBUWFxgZGhscHR4fICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj9AQUJDREVGR0hJSktMTU5PUFFSU1RV"
    "VldYWVpbXF1eX2BhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ent8fX5/gIGCg4SFhoeIiYqLjI2Oj5CRkpOUlZaXmJmam5ydnp+g"
    "oaKjpKWmp6ipqqusra6vsLGys7S1tre4ubq7vL2+v8DBwsPExcbHyMnKy8zNzs/Q0dLT1NXW19jZ2tvc3d7f4OHi4+Tl5ufo6err"
    "7O3u7/Dx8vP09fb3+Pn6+/z9/v8YxoHdUEsDBBQAAAAIAAAAIVC4yUhPxQAAAMAAAAA2AAAALmdpdC9vYmplY3RzL2NjL2U5NmY5"
    "MWU4ZTRhNDE1ZTI1MmI2NTQxMDQ0ZDk1MjM4NDkwYjY4AcAAP/94nCspSk1VMLQ0YDA0MDAzMVHQS88syUzPyy9KZTCK+5z19vfT"
    "3cId1XulYhgcliQs3G1iAAQKBgbxAUX5WanJJQzR5+d/vbhR+sxfrjPrPhhe+7KpaZsm1KikzLzEoko9IMVwIk0tuY/7xHn3U567"
    "RVW38E03f5cCVZWSmpNakqpXUlHC8OL5u6xYxr13/e38+DUtU7zO32l/CVVVUpSYnJ2aAlYmwe1+sHv5k5Y/vMUBe3LW9h12slsA"
    "ALF9UMdQSwMEFAAAAAgAAAAhUO6BpGQjAAAAIAAAADYAAAAuZ2l0L29iamVjdHMvZTgvZTdlZTZhNWQwMWJkZGQ0ZjNlNGUwZjI5"
    "Mzk2NDRhY2ZkYzg3ZTmrmON96qR/kIFJsofnWU9dz1APLx2/syfPeD9lYkiaysEOAFBLAwQUAAAACAAAACFQ99KGdSkAAAApAAAA"
    "FAAAAC5naXQvcmVmcy9oZWFkcy9tYWluM040SjQyM01MNjNNNUg0NTZKTTIF0kmJxmmpFobmlmmmyZbmFqnmXABQSwMEFAAAAAgA"
    "AAAhUAgazIcRAAAADwAAAAoAAAAuZ2l0aWdub3Jlc3Z1i3epjHdKTM4uLdDnAgBQSwMEFAAAAAgAAAAhUJkkLg0UAAAAEgAAAB0A"
    "AAAwMF9Qcm9qZWN0L1BST0pFQ1RfQ09OVFJPTC5tZFNWcMusKCktSlVIzs8rKcrP4QIAUEsDBBQAAAAIAAAAIVA8TrsUFgAAABQA"
    "AAAgAAAAMDBfUHJvamVjdC9QUk9KRUNUX01FVEFEQVRBLnlhbWwrKMrPSk0uic9MsVJw84wICQ1y5QIAUEsDBBQAAAAIAAAAIVBz"
    "jAUpBQEAAAABAAAKAAAAYmluYXJ5LmJpbgEAAf/+AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKiss"
    "LS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3"
    "eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHC"
    "w8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/1BLAwQUAAAACAAAACFQ"
    "HmqDxxIAAAAQAAAACgAAAGRlbGV0ZS50eHRLSc1JLUlVSEosTs3JzEvlAgBQSwMEFAAAAAgAAAAhUOX7nq0LAAAACQAAAAsAAAB0"
    "cmFja2VkLnR4dEtKLE7NycxL5QIAUEsBAhQAFAAAAAgAAAAhULVjZFcXAAAAFQAAAAkAAAAAAAAAAAAAAIABAAAAAC5naXQvSEVB"
    "RFBLAQIUABQAAAAIAAAAIVAOBrLjRgAAAFYAAAALAAAAAAAAAAAAAACAAT4AAAAuZ2l0L2NvbmZpZ1BLAQIUABQAAAAIAAAAIVB+"
    "RYTmKQAAACkAAAAWAAAAAAAAAAAAAACAAa0AAAAuZ2l0L2ZpeHR1cmVfbmV4dF9oZWFkUEsBAhQAFAAAAAgAAAAhUAGcFvoaAQAA"
    "IAIAABkAAAAAAAAAAAAAAIABCgEAAC5naXQvZml4dHVyZV9zdGFnZWRfaW5kZXhQSwECFAAUAAAACAAAACFQZ6gZjxQBAAAgAgAA"
    "CgAAAAAAAAAAAAAAgAFbAgAALmdpdC9pbmRleFBLAQIUABQAAAAIAAAAIVCqVY5vJQAAACIAAAA2AAAAAAAAAAAAAACAAZcDAAAu"
    "Z2l0L29iamVjdHMvMTQvOWVhMDkwZjgwNTkzMjhkMjRiN2Y2YmYxMDNjYmM3YzFmNjgwOGFQSwECFAAUAAAACAAAACFQHhByrhsA"
    "AAAYAAAANgAAAAAAAAAAAAAAgAEQBAAALmdpdC9vYmplY3RzLzE4LzBiNDdjMThiYTdlNDg0ZmMwZDczNTBiYzZjYWQ4ZWMzNDIz"
    "ZWEwUEsBAhQAFAAAAAgAAAAhUIx0uG2kAAAAnwAAADYAAAAAAAAAAAAAAIABfwQAAC5naXQvb2JqZWN0cy8yYy8wM2U0ZWZiZjIy"
    "YjhiZDJlMjFkNmNiM2EwODgxMmUxYThlOWQ4ZVBLAQIUABQAAAAIAAAAIVAEAOxRIgAAAB8AAAA2AAAAAAAAAAAAAACAAXcFAAAu"
    "Z2l0L29iamVjdHMvMzIvNWVmMzZhZWRmYmU1YmIxMzg4N2JiZDFhNWMwMDQwYTQ2MGExYmJQSwECFAAUAAAACAAAACFQR0SnzYAA"
    "AAB7AAAANgAAAAAAAAAAAAAAgAHtBQAALmdpdC9vYmplY3RzLzNhLzJhMjY1YWM2NWUwYTUzMmViNTBhNWJhM2ZlODE3OWY1Yzk3"
    "OGU3UEsBAhQAFAAAAAgAAAAhUCwwtqUoAAAAJQAAADYAAAAAAAAAAAAAAIABwQYAAC5naXQvb2JqZWN0cy80ZS82MWVlMWUxOWI0"
    "NDBkOWZiY2UxYzFhMTVlYzg3NTQ4ZTlkZjllOFBLAQIUABQAAAAIAAAAIVA0ndGbaQAAAGQAAAA2AAAAAAAAAAAAAACAAT0HAAAu"
    "Z2l0L29iamVjdHMvNWIvY2Y5ZmY1ZDFiMTFiY2NmZDBhY2NhZWYwMzFkNmY0YjI4MmI2MjlQSwECFAAUAAAACAAAACFQnqhEVCMA"
    "AAAgAAAANgAAAAAAAAAAAAAAgAH6BwAALmdpdC9vYmplY3RzLzhkLzdiZWFiNTk5ZGQzMDcxYTg1ZDUwMmIyYjIyMjNiYjBjZTk0"
    "Zjc2UEsBAhQAFAAAAAgAAAAhUDs2pGgnAAAAJAAAADYAAAAAAAAAAAAAAIABcQgAAC5naXQvb2JqZWN0cy9iMC8xMWM3ZmQ3M2Nl"
    "NDdjZWY2NDFmZDE5YjFlYWJlMTE1NzAwMTY2ZlBLAQIUABQAAAAIAAAAIVCCczb4GQEAABQBAAA2AAAAAAAAAAAAAACAAewIAAAu"
    "Z2l0L29iamVjdHMvYzgvNjYyNjYzOGUwYmM4Y2Y0N2NhNDliYjE1MjViNDBlOTczN2VlNjRQSwECFAAUAAAACAAAACFQuMlIT8UA"
    "AADAAAAANgAAAAAAAAAAAAAAgAFZCgAALmdpdC9vYmplY3RzL2NjL2U5NmY5MWU4ZTRhNDE1ZTI1MmI2NTQxMDQ0ZDk1MjM4NDkw"
    "YjY4UEsBAhQAFAAAAAgAAAAhUO6BpGQjAAAAIAAAADYAAAAAAAAAAAAAAIABcgsAAC5naXQvb2JqZWN0cy9lOC9lN2VlNmE1ZDAx"
    "YmRkZDRmM2U0ZTBmMjkzOTY0NGFjZmRjODdlOVBLAQIUABQAAAAIAAAAIVD30oZ1KQAAACkAAAAUAAAAAAAAAAAAAACAAekLAAAu"
    "Z2l0L3JlZnMvaGVhZHMvbWFpblBLAQIUABQAAAAIAAAAIVAIGsyHEQAAAA8AAAAKAAAAAAAAAAAAAACAAUQMAAAuZ2l0aWdub3Jl"
    "UEsBAhQAFAAAAAgAAAAhUJkkLg0UAAAAEgAAAB0AAAAAAAAAAAAAAIABfQwAADAwX1Byb2plY3QvUFJPSkVDVF9DT05UUk9MLm1k"
    "UEsBAhQAFAAAAAgAAAAhUDxOuxQWAAAAFAAAACAAAAAAAAAAAAAAAIABzAwAADAwX1Byb2plY3QvUFJPSkVDVF9NRVRBREFUQS55"
    "YW1sUEsBAhQAFAAAAAgAAAAhUHOMBSkFAQAAAAEAAAoAAAAAAAAAAAAAAIABIA0AAGJpbmFyeS5iaW5QSwECFAAUAAAACAAAACFQ"
    "HmqDxxIAAAAQAAAACgAAAAAAAAAAAAAAgAFNDgAAZGVsZXRlLnR4dFBLAQIUABQAAAAIAAAAIVDl+56tCwAAAAkAAAALAAAAAAAA"
    "AAAAAACAAYcOAAB0cmFja2VkLnR4dFBLBQYAAAAAGAAYAJ8HAAC7DgAAAAA="
)


def unpack_fixture(root):
    if any(root.iterdir()):
        raise RecoveryError("Selftest fixture destination must be a new empty directory")
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(SELFTEST_FIXTURE))) as archive:
        for member in archive.infolist():
            target = child(root, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))


def selftest():
    """All writes, including deliberate corruption, are isolated fixture writes."""
    from contextlib import redirect_stdout
    from unittest.mock import patch

    passed = []

    def check(test_id, condition):
        if not condition:
            raise RecoveryError(f"SELFTEST {test_id}: FAIL")
        passed.append(test_id)
        print(f"{test_id}: PASS", flush=True)

    with tempfile.TemporaryDirectory(prefix="work recovery selftest ") as directory:
        root = Path(directory).resolve() / "repository with spaces"
        root.mkdir()
        unpack_fixture(root)
        root = discover_root(root)
        check("T09", " " in str(root) and root.is_dir())
        job = "SELFTEST"
        index = root / ".git" / "index"
        initial_index = index.read_bytes()
        check("fixture_clean", not git(root, "status", "--porcelain=v1").stdout)
        start = make_snapshot(root, job, "start")
        check("T01", verify_snapshot(start)[0] and (start / "COMPLETE").is_file())
        check("start_audit_fallback", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "yes")
        pointer = json.loads((start.parent / "latest_start.json").read_bytes())
        check("start_pointer", pointer["snapshot_id"] == start.name and "path" not in pointer)
        check("clean_index_untouched", index.read_bytes() == initial_index)
        # Fixture mutations deliberately model an interrupted job, not recovery.
        (root / "tracked.txt").write_bytes(b"different worktree version\n")
        (root / "delete.txt").unlink()
        index.write_bytes((root / ".git" / "fixture_staged_index").read_bytes())
        (root / "added file.txt").write_bytes(b"staged addition\n")
        untracked = root / "new file unicode \u00fc.bin"
        payload = b"\x00\xff\r\n" + bytes(range(256))
        untracked.write_bytes(payload)
        (root / "CEF_Dy_Backup" / "ignored data.bin").write_bytes(b"must not be copied")
        status_before = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
        staged_index = index.read_bytes()
        panic = make_snapshot(root, job, "panic")
        check("T02", (panic / "worktree_files" / "tracked.txt").read_bytes() == b"different worktree version\n")
        check("T03", (panic / "index_files" / "tracked.txt").read_bytes() == b"exact staged version\n")
        check("full_index_copy", (panic / "git_index.bin").read_bytes() == staged_index)
        check("T04", (panic / "worktree_files" / untracked.name).read_bytes() == payload)
        saved = json.loads((panic / "metadata.json").read_bytes())
        check("deleted_paths", {"path": "delete.txt", "exists": False} in saved["worktree_files"] and
              {"path": "delete.txt", "deleted": True} in saved["index_files"])
        check("control_context", all((panic / "control_context" / p).read_bytes() == (root / p).read_bytes() for p in CONTROL_FILES))
        report = audit_snapshot(root, job)
        check("T05", report["SAFE_TO_RESUME"] == "yes" and report["SNAPSHOT_ID"] == panic.name)
        for command in ("audit", "report"):
            output = io.StringIO()
            with patch.object(Path, "cwd", return_value=root), redirect_stdout(output):
                code = main([command, "--job", job, "--snapshot", panic.name])
            parsed = json.loads(output.getvalue())
            check("cli_" + command, code == 0 and parsed["SAFE_TO_RESUME"] == "yes" and
                  set(empty_report(job)).issubset(parsed) and "git_diff.patch" not in output.getvalue())
        check("T10", index.read_bytes() == staged_index and status_before ==
              git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout and
              not git(root, "ls-files", "--", "CEF_Dy_Backup/").stdout and
              not (panic / "worktree_files" / "CEF_Dy_Backup").exists())
        (root / "tracked.txt").write_bytes(b"changed after panic\n")
        check("T06", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "review_required")
        baseline_head = (root / ".git" / "refs" / "heads" / "main").read_bytes()
        (root / ".git" / "refs" / "heads" / "main").write_bytes((root / ".git" / "fixture_next_head").read_bytes())
        check("T07", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "no")
        (root / ".git" / "refs" / "heads" / "main").write_bytes(baseline_head)
        corrupt = panic / "worktree_files" / "tracked.txt"
        old = corrupt.read_bytes()
        corrupt.write_bytes(b"corruption\n")
        check("T08", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "no")
        corrupt.write_bytes(old)
        manifest = panic / "snapshot_manifest.json"
        original_manifest = manifest.read_bytes()
        manifest.write_bytes(original_manifest + b" ")
        check("manifest_seal", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "no")
        manifest.write_bytes(original_manifest)
        (root / ".git" / "MERGE_HEAD").write_bytes(baseline_head)
        check("operation_detection", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "no")
        (root / ".git" / "MERGE_HEAD").unlink()
        old_ref = (root / ".git" / "HEAD").read_bytes()
        (root / ".git" / "refs" / "heads" / "other").write_bytes(baseline_head)
        (root / ".git" / "HEAD").write_bytes(b"ref: refs/heads/other\n")
        check("branch_change", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "no")
        (root / ".git" / "HEAD").write_bytes(old_ref)
        dirty_start = make_snapshot(root, "DIRTY-START", "start")
        check("dirty_start_allowed", verify_snapshot(dirty_start)[0])
        with patch(__name__ + ".copy_current", side_effect=OSError("simulated required copy failure")):
            try:
                make_snapshot(root, "COPY-FAIL", "panic")
                check("copy_failure", False)
            except RecoveryError:
                partial = snapshots(storage(root, "COPY-FAIL"))[-1]
                check("copy_failure", partial.exists() and not (partial / "COMPLETE").exists())
        check("partial_snapshot_invalid", audit_snapshot(root, "COPY-FAIL")["SAFE_TO_RESUME"] == "no")
        with patch(__name__ + ".copy_current", side_effect=OSError("newer partial capture")):
            try:
                make_snapshot(root, job, "panic")
            except RecoveryError:
                pass
        check("newer_partial_blocks_resume", audit_snapshot(root, job)["SAFE_TO_RESUME"] == "no")
        (root / "tracked.txt").write_bytes(b"trailing space \n")
        white = audit_snapshot(root, job)
        check("whitespace_unsafe", white["SAFE_TO_RESUME"] == "no" and white["DIFF_CHECK"] == "FAIL")
        try:
            make_snapshot(root, "CHECK-FAIL", "panic")
            check("check_failure", False)
        except RecoveryError:
            partial = snapshots(storage(root, "CHECK-FAIL"))[-1]
            check("check_failure", (partial / "worktree_files" / "tracked.txt").exists() and not (partial / "COMPLETE").exists())
        try:
            storage(root, "../escape")
        except RecoveryError:
            check("path_guard", True)
        else:
            check("path_guard", False)
        # Missing ignore rule must fail before any recovery-directory creation.
        (root / ".gitignore").write_bytes(b"")
        try:
            make_snapshot(root, "NOT-IGNORED", "panic")
            check("ignore_guard", False)
        except RecoveryError:
            check("ignore_guard", not (root / RECOVERY_REL / "NOT-IGNORED").exists())
        check("index_still_untouched", index.read_bytes() == staged_index)
    print(f"SELFTEST_CASES: {len(passed)}")
    print("SELFTEST: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "panic", "audit", "report"):
        sub = commands.add_parser(name)
        sub.add_argument("--job", required=True)
        if name in {"audit", "report"}:
            sub.add_argument("--snapshot", help="Explicit snapshot ID for the same job")
    commands.add_parser("selftest")
    args = parser.parse_args(argv)
    try:
        if args.command == "selftest":
            return selftest()
        root = discover_root()
        if args.command in {"start", "panic"}:
            path = make_snapshot(root, args.job, args.command)
            report = audit_snapshot(root, args.job, path.name)
        else:
            report = audit_snapshot(root, args.job, args.snapshot)
        emit_report(report)
        return {"yes": 0, "review_required": 1, "no": 2}[report["SAFE_TO_RESUME"]]
    except (RecoveryError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        report = empty_report(getattr(args, "job", "SELFTEST"))
        report["BLOCKERS"] = [str(exc)]
        emit_report(report)
        if args.command == "selftest":
            print("SELFTEST: FAIL")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
