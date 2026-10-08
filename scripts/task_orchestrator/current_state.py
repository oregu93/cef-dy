"""Repository-derived canonical-state freshness and materialization debt.

The authority in this module is deliberately read-only.  It validates tracked
Project-Control records and returns exact identities for authoring, validation,
and human projections; it never infers scientific promotion from Issue prose.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

import yaml

from .model import ValidationError
from .routing import canonical_role


FRESHNESS_PATH = Path("00_Project/CANONICAL_STATE_FRESHNESS.yaml")
DEBT_LEDGER_PATH = Path("00_Project/MATERIALIZATION_DEBT_LEDGER.yaml")
DEBT_STATES = frozenset({
    "MATERIALIZED",
    "PENDING_MATERIALIZATION",
    "EXPLICITLY_DEFERRED_WITH_REASON",
    "NOT_STATE_CHANGING",
    "UNRESOLVED_SOURCE_RECOVERY",
})
BLOCKING_DEBT_STATES = frozenset({
    "PENDING_MATERIALIZATION", "UNRESOLVED_SOURCE_RECOVERY",
})
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"cannot load {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a mapping")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValidationError(f"{label} must be a list of non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValidationError(f"{label} contains duplicates")
    return normalized


def load_repository_authority(
    repository_root: Path | str, *, expected_canonical_head: str,
) -> dict[str, Any]:
    """Load and validate exact-head freshness plus the complete debt ledger."""
    root = Path(repository_root).resolve()
    expected = str(expected_canonical_head).lower()
    if SHA40.fullmatch(expected) is None:
        raise ValidationError("expected canonical HEAD has invalid identity format")
    freshness = _load_mapping(root / FRESHNESS_PATH, "canonical-state freshness")
    ledger = _load_mapping(root / DEBT_LEDGER_PATH, "materialization debt ledger")

    required_freshness = {
        "schema_version", "record_id", "status", "assessed_at",
        "assessed_head", "authority", "purpose", "freshness_semantics",
        "layers", "materialization_commit_policy", "materialization_paths",
        "consequential_task_gate", "scientific_boundary", "prohibitions",
    }
    if set(freshness) != required_freshness:
        raise ValidationError("canonical-state freshness fields mismatch")
    if freshness["schema_version"] != 2:
        raise ValidationError("canonical-state freshness schema must be 2")
    assessed = str(freshness["assessed_head"]).lower()
    if SHA40.fullmatch(assessed) is None:
        raise ValidationError("canonical-state freshness assessed_head is invalid")
    if freshness["status"] not in {"FRESH", "CURRENT_WITH_SCOPED_DEBT"}:
        raise ValidationError("canonical-state freshness status is not admissible")
    if freshness["authority"] != "PROJECT_CONTROL":
        raise ValidationError("canonical-state freshness lacks Project Control authority")
    boundary = freshness["scientific_boundary"]
    if boundary != {
        "milestone": "M03R",
        "state": "LEVEL_2_established_LEVEL_3_blocked",
        "level_3": "absent",
        "level_4": "absent",
        "stage03d": "suspended",
        "exchange": "deferred",
        "holdout": "unauthorized",
        "taipan_18_247_meV": "candidate_with_caveat_only",
        "new_scientific_interpretation": "none",
    }:
        raise ValidationError("canonical scientific boundary drift")
    layers = freshness["layers"]
    if (
        not isinstance(layers, dict)
        or set(layers) != {
            "scientific_core", "project_control", "infrastructure",
            "literature_and_supporting_knowledge",
        }
        or layers["project_control"].get("status") != "FRESH"
        or layers["infrastructure"].get("status") != "FRESH"
    ):
        raise ValidationError("canonical freshness layer drift")
    materialization_paths = _string_list(
        freshness["materialization_paths"], "materialization_paths",
    )
    if tuple(sorted(materialization_paths)) != materialization_paths:
        raise ValidationError("materialization_paths must be sorted")
    if assessed != expected:
        parent = subprocess.run(
            ["git", "rev-parse", f"{expected}^"], cwd=root,
            capture_output=True, text=True,
        )
        changed = subprocess.run(
            ["git", "diff", "--name-only", assessed, expected], cwd=root,
            capture_output=True, text=True,
        )
        actual = tuple(sorted(filter(None, changed.stdout.splitlines())))
        if (
            parent.returncode != 0 or parent.stdout.strip() != assessed
            or changed.returncode != 0 or actual != materialization_paths
        ):
            raise ValidationError("canonical-state freshness assessed_head drift")

    required_ledger = {
        "schema_version", "ledger_id", "assessed_head", "authority",
        "derivation_rule", "states", "inventory_ids", "items",
    }
    if set(ledger) != required_ledger:
        raise ValidationError("materialization debt ledger fields mismatch")
    if ledger["schema_version"] != 1 or ledger["authority"] != "PROJECT_CONTROL":
        raise ValidationError("materialization debt ledger authority is invalid")
    if str(ledger["assessed_head"]).lower() != assessed:
        raise ValidationError("freshness and debt ledger assessed_head disagree")
    states = _string_list(ledger["states"], "ledger states")
    if set(states) != DEBT_STATES:
        raise ValidationError("materialization debt ledger state vocabulary mismatch")
    if not isinstance(ledger["items"], list):
        raise ValidationError("materialization debt ledger items must be a list")

    items: list[dict[str, Any]] = []
    for index, raw in enumerate(ledger["items"]):
        required = {
            "identity", "state", "reason", "source", "evidence_paths",
            "affected_roles", "affected_paths", "affected_task_ids", "decision_changing",
            "target_batch", "materialization_commit",
        }
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValidationError(f"debt item {index} fields mismatch")
        identity = _nonempty(raw["identity"], f"debt item {index} identity")
        state = raw["state"]
        if state not in DEBT_STATES:
            raise ValidationError(f"debt item {identity} has unsupported state")
        source = raw["source"]
        if not isinstance(source, dict) or set(source) != {
            "kind", "identity", "result_sha256",
        }:
            raise ValidationError(f"debt item {identity} source is incomplete")
        _nonempty(source["kind"], f"debt item {identity} source kind")
        _nonempty(source["identity"], f"debt item {identity} source identity")
        source_sha = str(source["result_sha256"]).lower()
        if SHA256.fullmatch(source_sha) is None:
            raise ValidationError(f"debt item {identity} source hash is invalid")
        evidence_paths = _string_list(
            raw["evidence_paths"], f"debt item {identity} evidence_paths",
        )
        if not evidence_paths or any(not (root / path).exists() for path in evidence_paths):
            raise ValidationError(f"debt item {identity} repository evidence is missing")
        roles = _string_list(raw["affected_roles"], f"debt item {identity} roles")
        if any(canonical_role(role) is None for role in roles):
            raise ValidationError(f"debt item {identity} has unknown affected role")
        paths = _string_list(raw["affected_paths"], f"debt item {identity} paths")
        task_ids = _string_list(
            raw["affected_task_ids"], f"debt item {identity} task IDs",
        )
        if type(raw["decision_changing"]) is not bool:
            raise ValidationError(f"debt item {identity} decision_changing must be boolean")
        commit = raw["materialization_commit"]
        if state == "MATERIALIZED":
            if not isinstance(commit, str) or SHA40.fullmatch(commit.lower()) is None:
                raise ValidationError(f"debt item {identity} lacks materialization commit")
        elif commit is not None:
            raise ValidationError(f"debt item {identity} must not claim a materialization commit")
        if state == "EXPLICITLY_DEFERRED_WITH_REASON" and not str(raw["reason"] or "").strip():
            raise ValidationError(f"debt item {identity} lacks deferral reason")
        if state != "EXPLICITLY_DEFERRED_WITH_REASON" and raw["reason"] is not None:
            raise ValidationError(f"debt item {identity} has an invalid reason")
        item = dict(raw)
        item["source"] = dict(source, result_sha256=source_sha)
        item["evidence_paths"] = list(evidence_paths)
        item["affected_roles"] = list(roles)
        item["affected_paths"] = list(paths)
        item["affected_task_ids"] = list(task_ids)
        items.append(item)
    identities = [item["identity"] for item in items]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValidationError("materialization debt items must be unique and sorted")
    inventory_ids = _string_list(ledger["inventory_ids"], "ledger inventory_ids")
    if tuple(identities) != inventory_ids:
        raise ValidationError("materialization debt inventory is incomplete")

    normalized_ledger = dict(ledger, items=items)
    authority = {
        "schema_version": 1,
        "assessed_head": assessed,
        "observed_canonical_head": expected,
        "freshness_record_id": _nonempty(freshness["record_id"], "freshness record_id"),
        "freshness_status": freshness["status"],
        "ledger_id": _nonempty(ledger["ledger_id"], "ledger_id"),
        "items": items,
        "materialization_paths": list(materialization_paths),
    }
    authority["authority_sha256"] = _digest({
        "freshness": freshness, "ledger": normalized_ledger,
    })
    return authority


def _path_intersects(left: str, right: str) -> bool:
    a, b = left.rstrip("/"), right.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def relevant_repository_debt(
    authority: dict[str, Any], *, role: str,
    task_id: str, required_paths: Iterable[str], allowed_paths: Iterable[str],
) -> tuple[dict[str, Any], ...]:
    """Return only decision-relevant debt intersecting this task's scope."""
    task_role = canonical_role(role)
    paths = tuple(required_paths) or tuple(allowed_paths)
    result = []
    for item in authority["items"]:
        if item["state"] not in BLOCKING_DEBT_STATES or not item["decision_changing"]:
            continue
        role_match = task_role in {
            canonical_role(value) for value in item["affected_roles"]
        }
        identity_match = task_id in item["affected_task_ids"]
        path_match = any(
            _path_intersects(task_path, debt_path)
            for task_path in paths for debt_path in item["affected_paths"]
        )
        # Exact task identity is strongest.  Paths scope repository work; role
        # alone is used only when a debt item has no narrower path identity.
        if identity_match or path_match or (role_match and not item["affected_paths"]):
            result.append(item)
    return tuple(sorted(result, key=lambda item: item["identity"]))


def verify_declared_relevant_debt(
    relevant: Iterable[dict[str, Any]], declared_changes: Iterable[dict[str, Any]],
) -> tuple[str, ...]:
    """Fail closed when relevant repository debt is omitted or misstated."""
    declared = {row["identity"]: row for row in declared_changes}
    pending: list[str] = []
    for item in relevant:
        identity = item["identity"]
        row = declared.get(identity)
        if row is None:
            raise ValidationError(f"known relevant repository debt omitted: {identity}")
        if row["result_sha256"] != item["source"]["result_sha256"]:
            raise ValidationError(f"repository debt source hash mismatch: {identity}")
        if item["state"] == "UNRESOLVED_SOURCE_RECOVERY":
            raise ValidationError(f"relevant source recovery is unresolved: {identity}")
        if row["materialization_state"] != "PENDING_MATERIALIZATION":
            raise ValidationError(f"repository debt state mismatch: {identity}")
        pending.append(identity)
    return tuple(sorted(pending))


def freshness_projection(
    repository_root: Path | str, *, observed_canonical_head: str | None,
) -> dict[str, Any]:
    """Return a fail-closed dashboard facet without mutating repository state."""
    if observed_canonical_head is None or SHA40.fullmatch(observed_canonical_head) is None:
        return {
            "state": "UNKNOWN", "assessed_head": None,
            "authority_sha256": None, "blocking_debt": [],
            "reason": "canonical Git identity is unavailable",
        }
    try:
        authority = load_repository_authority(
            repository_root, expected_canonical_head=observed_canonical_head,
        )
    except (ValidationError, OSError, ValueError) as exc:
        return {
            "state": "STALE", "assessed_head": None,
            "authority_sha256": None, "blocking_debt": [],
            "reason": str(exc),
        }
    blocking = [
        item["identity"] for item in authority["items"]
        if item["state"] in BLOCKING_DEBT_STATES and item["decision_changing"]
    ]
    return {
        "state": authority["freshness_status"],
        "assessed_head": authority["assessed_head"],
        "authority_sha256": authority["authority_sha256"],
        "blocking_debt": blocking,
        "reason": "repository authority loaded and exact-head validated",
    }
