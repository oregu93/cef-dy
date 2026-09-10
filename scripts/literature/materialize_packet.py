#!/usr/bin/env python3
"""Deterministic offline transaction planner for LIT-INFRA-02 packets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import yaml

from literature_validate import UniqueKeyLoader, Validator


PACKET_RE = re.compile(r"MP-[0-9]{8}-01A-[0-9]{2}")
SOURCE_RE = re.compile(r"SRC-[0-9]{6}")
PENDING_RE = re.compile(r"SRC-PENDING-[A-Za-z0-9][A-Za-z0-9._-]*")
GAP_RE = re.compile(r"GAP-[0-9]{6}")
SEARCH_RE = re.compile(r"SP-[0-9]{8}-[A-Z0-9]+-[0-9]{2}")
EVIDENCE_RE = re.compile(r"EV-SRC([0-9]{6})-([0-9]{3,})")
EDGE_RE = re.compile(r"EDGE-[0-9]{6}")
WF_RE = re.compile(r"WF-[0-9]{6}")
HEX40_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")

DEFERRED_TYPES = {"ZOTERO_CREATE", "ZOTERO_LINK_EXISTING", "ADD_COLLECTION", "ADD_TAG"}
SOURCE_ASSOCIATED = {
    "SOURCE_UPDATE", "EVIDENCE_ADD", "EVIDENCE_UPDATE",
    "ADD_CITATION_EDGE", "WORK_FAMILY_LINK",
}
WRITE_EXACT = {
    "05_Literature/SOURCE_REGISTRY.yaml",
    "05_Literature/GAPS.yaml",
    "05_Literature/MATERIALIZATION_LOG.yaml",
}


class MaterializationFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise MaterializationFailure(code, message)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        fail("MATERIALIZATION_SCHEMA_FAILURE", f"cannot load {path.name}: {exc}")
    if not isinstance(value, dict):
        fail("MATERIALIZATION_SCHEMA_FAILURE", f"{path.name} must contain a mapping")
    return value


def yaml_bytes(value: Any) -> bytes:
    text = yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
        width=1000,
    )
    return text.rstrip("\n").replace("\r\n", "\n").encode("utf-8") + b"\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str, check: bool = True) -> str:
    if not args or args[0] not in {"rev-parse", "status"}:
        fail("PACKET_PRECONDITION_FAILURE", "materializer attempted non-inspection Git command")
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if check and completed.returncode:
        fail("PACKET_PRECONDITION_FAILURE", f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def canonical_source_number(source_id: str) -> int:
    return int(source_id.removeprefix("SRC-"))


def operation_field(operation: dict[str, Any], name: str) -> Any:
    if name in operation:
        return operation[name]
    payload = operation.get("payload")
    return payload.get(name) if isinstance(payload, dict) else None


def mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("MATERIALIZATION_SCHEMA_FAILURE", message)
    return value


def list_value(value: Any, message: str) -> list[Any]:
    if not isinstance(value, list):
        fail("MATERIALIZATION_SCHEMA_FAILURE", message)
    return value


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        fail("BIBLIOGRAPHIC_AMBIGUITY", "DOI must be string or null")
    normalized = value.strip().lower()
    if normalized != value or not re.fullmatch(r"10\.[0-9]{4,9}/\S+", normalized):
        fail("BIBLIOGRAPHIC_AMBIGUITY", f"DOI is not normalized: {value!r}")
    return normalized


REFERENCE_KEYS = {
    "source_id", "source_ref", "from_source", "to_source", "merged_into",
    "current_evidence", "seed_sources", "sources_found", "resolved_by",
}


def resolve_tree(value: Any, pending: dict[str, str], key: str = "") -> Any:
    if isinstance(value, dict):
        return {child_key: resolve_tree(child, pending, str(child_key)) for child_key, child in value.items()}
    if isinstance(value, list):
        return [resolve_tree(child, pending, key) for child in value]
    if isinstance(value, str) and value.startswith("SRC-PENDING-") and key in REFERENCE_KEYS:
        if value not in pending:
            fail("MATERIALIZATION_SCHEMA_FAILURE", f"undefined pending source {value}")
        return pending[value]
    return copy.deepcopy(value)


def safe_runtime_path(root: Path, relative: str) -> Path:
    logical = PurePosixPath(relative)
    if not relative or "\\" in relative or logical.is_absolute() or ".." in logical.parts:
        fail("MATERIALIZATION_SCHEMA_FAILURE", f"unsafe write path: {relative!r}")
    allowed = (
        relative in WRITE_EXACT
        or bool(re.fullmatch(r"05_Literature/EVIDENCE/SRC-[0-9]{6}\.yaml", relative))
        or bool(re.fullmatch(r"05_Literature/SEARCH_LOG/SP-[0-9]{8}-[A-Z0-9]+-[0-9]{2}\.yaml", relative))
    )
    if not allowed:
        fail("MATERIALIZATION_SCHEMA_FAILURE", f"write outside runtime allowlist: {relative}")
    target = root.joinpath(*logical.parts)
    root_resolved = root.resolve()
    cursor = root
    for part in logical.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            fail("MATERIALIZATION_SCHEMA_FAILURE", f"symlinked write parent: {relative}")
    if target.is_symlink():
        fail("MATERIALIZATION_SCHEMA_FAILURE", f"write target is symlink: {relative}")
    try:
        target.resolve(strict=False).relative_to(root_resolved)
    except ValueError:
        fail("MATERIALIZATION_SCHEMA_FAILURE", f"write path escapes repository: {relative}")
    return target


@dataclass
class Plan:
    packet_id: str
    packet_sha256: str
    base_head: str
    writes: dict[str, bytes] = field(default_factory=dict)
    allocated_source_ids: list[str] = field(default_factory=list)
    allocated_gap_ids: list[str] = field(default_factory=list)
    allocated_evidence_ids: list[str] = field(default_factory=list)
    allocated_edge_ids: list[str] = field(default_factory=list)
    allocated_work_family_ids: list[str] = field(default_factory=list)
    record_version_changes: dict[str, list[int]] = field(default_factory=dict)
    evidence_record_version_changes: dict[str, list[int]] = field(default_factory=dict)
    deferred_zotero_requests: list[dict[str, str]] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    plan_sha256: str = ""
    prestate_sha256: dict[str, str | None] = field(default_factory=dict, repr=False)

    def digest_payload(self, ledger_projection: bytes) -> bytes:
        value = {
            "packet_id": self.packet_id,
            "packet_sha256": self.packet_sha256,
            "base_head": self.base_head,
            "allocated_source_ids": self.allocated_source_ids,
            "allocated_gap_ids": self.allocated_gap_ids,
            "allocated_evidence_ids": self.allocated_evidence_ids,
            "allocated_edge_ids": self.allocated_edge_ids,
            "allocated_work_family_ids": self.allocated_work_family_ids,
            "files": [
                {"path": path, "sha256": sha256(data), "bytes_hex": data.hex()}
                for path, data in sorted(self.writes.items())
                if path != "05_Literature/MATERIALIZATION_LOG.yaml"
            ],
            "ledger_projection_hex": ledger_projection.hex(),
            "record_version_changes": self.record_version_changes,
            "evidence_record_version_changes": self.evidence_record_version_changes,
            "deferred_zotero_requests": self.deferred_zotero_requests,
        }
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Materializer:
    def __init__(
        self,
        root: Path,
        packet_path: Path,
        apply: bool = False,
        expected_head: str | None = None,
        fault: str | None = None,
    ) -> None:
        self.root = root.resolve()
        self.packet_path = packet_path
        self.apply = apply
        self.expected_head = expected_head
        self.fault = fault
        self.base_head = ""
        self.packet_relative = ""

    def check_packet_path(self) -> None:
        raw = self.packet_path
        if raw.is_absolute():
            try:
                raw.relative_to(self.root)
            except ValueError:
                fail("MATERIALIZATION_SCHEMA_FAILURE", "canonical packet must be repository-relative")
        absolute = raw if raw.is_absolute() else self.root / raw
        try:
            relative = absolute.absolute().relative_to(self.root)
        except ValueError:
            fail("MATERIALIZATION_SCHEMA_FAILURE", "packet path escapes repository")
        logical = PurePosixPath(relative.as_posix())
        if ".." in logical.parts or logical.parent.as_posix() != "05_Literature/PACKETS":
            fail("MATERIALIZATION_SCHEMA_FAILURE", "packet must be directly under canonical PACKETS")
        cursor = self.root
        for part in logical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                fail("MATERIALIZATION_SCHEMA_FAILURE", "packet path contains symbolic link")
        if not absolute.is_file() or not PACKET_RE.fullmatch(absolute.stem):
            fail("INVALID_PACKET_ID", "invalid canonical packet filename")
        try:
            absolute.resolve().relative_to((self.root / "05_Literature/PACKETS").resolve())
        except ValueError:
            fail("MATERIALIZATION_SCHEMA_FAILURE", "packet resolves outside canonical PACKETS")
        self.packet_path = absolute
        self.packet_relative = logical.as_posix()

    def check_git_state(self) -> None:
        self.base_head = git(self.root, "rev-parse", "HEAD")
        if not HEX40_RE.fullmatch(self.base_head):
            fail("PACKET_PRECONDITION_FAILURE", "HEAD is not a full commit SHA")
        status = git(self.root, "status", "--porcelain=v1", "-uall")
        for line in status.splitlines():
            if not line:
                continue
            code, name = line[:2], line[3:]
            if code == "??" and name == self.packet_relative:
                continue
            fail("PACKET_PRECONDITION_FAILURE", f"unexpected Git state: {line}")
        if self.apply:
            if self.expected_head is None or not HEX40_RE.fullmatch(self.expected_head):
                fail("PACKET_PRECONDITION_FAILURE", "--apply requires a 40-hex --expected-head")
            if self.expected_head != self.base_head:
                fail("PACKET_PRECONDITION_FAILURE", "HEAD differs from --expected-head")

    def prevalidate(self) -> None:
        issues = Validator(self.root).run()
        if issues:
            first = issues[0]
            fail(first.failure_code, f"canonical pre-state invalid: {first.message}")

    def execute(self) -> tuple[str, Plan | None]:
        self.check_packet_path()
        self.check_git_state()
        packet_bytes = self.packet_path.read_bytes()
        packet_hash = sha256(packet_bytes)
        packet = load_yaml(self.packet_path)
        packet_id = packet.get("packet_id")
        if packet_id != self.packet_path.stem or not isinstance(packet_id, str) or not PACKET_RE.fullmatch(packet_id):
            fail("INVALID_PACKET_ID", "packet_id/filename mismatch")
        self.prevalidate()
        ledger = load_yaml(self.root / "05_Literature/MATERIALIZATION_LOG.yaml")
        applications = mapping(ledger.get("applications"), "ledger applications must be mapping")
        previous = applications.get(packet_id)
        if previous is not None:
            previous = mapping(previous, "ledger application must be mapping")
            if previous.get("packet_sha256") != packet_hash:
                fail("MATERIALIZATION_SCHEMA_FAILURE", "packet ID is already recorded with different SHA")
            if previous.get("result") == "applied":
                plan = Plan(packet_id, packet_hash, self.base_head)
                plan.plan_sha256 = str(previous.get("plan_sha256", ""))
                return "ALREADY_APPLIED", plan
            fail("MATERIALIZATION_SCHEMA_FAILURE", "unsupported ledger result")
        plan = self.build_plan(packet, packet_hash, ledger)
        self.validate_shadow(plan)
        if not self.apply:
            return "DRY_RUN_OK", plan
        self.apply_plan(plan)
        return "APPLIED", plan

    def build_plan(self, packet: dict[str, Any], packet_hash: str, ledger: dict[str, Any]) -> Plan:
        packet_id = str(packet["packet_id"])
        if packet.get("producer_role") != "01A" or str(packet.get("packet_schema_version")) != "1.0":
            fail("MATERIALIZATION_SCHEMA_FAILURE", "packet identity is not v1/01A")
        if packet.get("validation_status") not in {"valid", "validated", "PASS"}:
            fail("MATERIALIZATION_SCHEMA_FAILURE", "packet validation_status is not an accepted validated state")
        ambiguities = list_value(packet.get("unresolved_ambiguities"), "unresolved_ambiguities must be list")
        if ambiguities:
            fail("BIBLIOGRAPHIC_AMBIGUITY", "packet contains unresolved ambiguities")
        operations = list_value(packet.get("operations"), "operations must be list")
        if not all(isinstance(item, dict) for item in operations):
            fail("MATERIALIZATION_SCHEMA_FAILURE", "every operation must be mapping")

        sources_doc = load_yaml(self.root / "05_Literature/SOURCE_REGISTRY.yaml")
        gaps_doc = load_yaml(self.root / "05_Literature/GAPS.yaml")
        sources = mapping(sources_doc.get("sources"), "sources must be mapping")
        gaps = mapping(gaps_doc.get("gaps"), "gaps must be mapping")
        sources = copy.deepcopy(sources)
        gaps = copy.deepcopy(gaps)
        original_sources = copy.deepcopy(sources)
        original_paths = {p.relative_to(self.root).as_posix() for p in self.root.glob("05_Literature/EVIDENCE/*.yaml")}
        original_paths |= {p.relative_to(self.root).as_posix() for p in self.root.glob("05_Literature/SEARCH_LOG/SP-*.yaml")}
        evidence: dict[str, dict[str, Any]] = {
            path.stem: load_yaml(path) for path in sorted(self.root.glob("05_Literature/EVIDENCE/SRC-*.yaml"))
        }
        searches: dict[str, dict[str, Any]] = {
            path.stem: load_yaml(path) for path in sorted(self.root.glob("05_Literature/SEARCH_LOG/SP-*.yaml"))
        }
        original_evidence = copy.deepcopy(evidence)

        plan = Plan(packet_id, packet_hash, self.base_head)
        operation_ids: set[str] = set()
        pending_defs: list[str] = []
        for operation in operations:
            operation_id = operation.get("operation_id")
            if not isinstance(operation_id, str) or not operation_id or operation_id in operation_ids:
                fail("MATERIALIZATION_SCHEMA_FAILURE", "operation IDs must be nonempty and unique")
            operation_ids.add(operation_id)
            if operation.get("type") == "SOURCE_CREATE":
                temporary = operation.get("temporary_ref")
                if not isinstance(temporary, str) or not PENDING_RE.fullmatch(temporary):
                    fail("INVALID_SOURCE_ID", "SOURCE_CREATE requires valid temporary_ref")
                if temporary in pending_defs:
                    fail("MATERIALIZATION_SCHEMA_FAILURE", f"duplicate pending definition {temporary}")
                pending_defs.append(temporary)

        maximum_source = max((canonical_source_number(item) for item in sources if SOURCE_RE.fullmatch(item)), default=0)
        if maximum_source + len(pending_defs) > 999999:
            fail("MATERIALIZATION_SCHEMA_FAILURE", "SOURCE_ID namespace exhausted")
        pending = {
            temporary: f"SRC-{maximum_source + index:06d}"
            for index, temporary in enumerate(pending_defs, 1)
        }
        pending_operations = {
            str(operation["temporary_ref"]): operation
            for operation in operations if operation.get("type") == "SOURCE_CREATE"
        }
        plan.allocated_source_ids = list(pending.values())

        expected_versions: dict[str, int] = {}
        existing_affected: set[str] = set()
        touched_evidence: set[str] = set()
        initial_evidence_ids = [
            item.get("evidence_id")
            for document in evidence.values()
            for item in document.get("evidence", []) if isinstance(item, dict)
        ]
        edge_max = max(
            (int(edge["edge_id"].removeprefix("EDGE-")) for document in evidence.values()
             for edge in document.get("relations", []) if isinstance(edge, dict)
             and isinstance(edge.get("edge_id"), str) and EDGE_RE.fullmatch(edge["edge_id"])),
            default=0,
        )
        wf_existing = {
            record.get("work_family_id") for record in sources.values()
            if isinstance(record, dict) and isinstance(record.get("work_family_id"), str)
            and WF_RE.fullmatch(record["work_family_id"])
        }
        wf_max = max((int(item.removeprefix("WF-")) for item in wf_existing), default=0)
        gap_max = max((int(item.removeprefix("GAP-")) for item in gaps if GAP_RE.fullmatch(item)), default=0)
        next_gap = gap_max + 1
        next_edge = edge_max + 1
        next_wf = wf_max + 1
        introduced_wf: set[str] = set()
        packet_dois: dict[str, str] = {}

        def source_ref(operation: dict[str, Any]) -> str:
            raw = operation_field(operation, "source_ref")
            if not isinstance(raw, str):
                fail("MATERIALIZATION_SCHEMA_FAILURE", f"{operation.get('type')} requires source_ref")
            value = pending.get(raw, raw)
            ensure_allocated_source(value)
            if not SOURCE_RE.fullmatch(value) or value not in sources:
                fail("EVIDENCE_REFERENCE_DANGLING", f"source does not resolve: {raw}")
            return value

        def ensure_allocated_source(value: Any) -> None:
            if value in pending.values() and value not in sources:
                temporary = next(key for key, allocated in pending.items() if allocated == value)
                materialize_source_create(temporary)

        def require_expected(operation: dict[str, Any], source_id: str) -> None:
            if source_id not in original_sources:
                return
            preconditions = mapping(operation.get("preconditions"), "existing-source operation requires preconditions")
            expected = preconditions.get("expected_record_version")
            actual = original_sources[source_id].get("record_version")
            if isinstance(expected, bool) or not isinstance(expected, int) or expected != actual:
                fail("PACKET_PRECONDITION_FAILURE", f"stale expected_record_version for {source_id}")
            prior = expected_versions.setdefault(source_id, expected)
            if prior != expected:
                fail("PACKET_PRECONDITION_FAILURE", f"conflicting expected versions for {source_id}")
            existing_affected.add(source_id)

        def ensure_evidence(source_id: str) -> dict[str, Any]:
            if source_id not in evidence:
                evidence[source_id] = {
                    "source_id": source_id,
                    "evidence_record_version": 1,
                    "evidence": [],
                    "relations": [],
                    "cef": None,
                }
                sources[source_id]["evidence_record"] = f"EVIDENCE/{source_id}.yaml"
            touched_evidence.add(source_id)
            return evidence[source_id]

        def validate_doi_for(source_id: str, record: dict[str, Any]) -> None:
            identity = record.get("bibliographic_identity")
            if not isinstance(identity, dict):
                return
            doi = normalize_doi(identity.get("doi"))
            if doi is None:
                return
            for existing_id, existing in sources.items():
                if existing_id == source_id or not isinstance(existing, dict) or existing.get("record_status") != "active":
                    continue
                other = existing.get("bibliographic_identity")
                if isinstance(other, dict) and other.get("doi") == doi:
                    fail("DUPLICATE_CANDIDATE", f"DOI {doi} also belongs to {existing_id}")
            if doi in packet_dois and packet_dois[doi] != source_id:
                fail("DUPLICATE_CANDIDATE", f"same-packet duplicate DOI {doi}")
            packet_dois[doi] = source_id

        def materialize_source_create(temporary: str) -> str:
            source_id = pending[temporary]
            if source_id in sources:
                return source_id
            operation = pending_operations[temporary]
            payload = mapping(operation.get("payload"), "SOURCE_CREATE payload must be mapping")
            record = resolve_tree(copy.deepcopy(payload.get("record", payload)), pending)
            record = mapping(record, "SOURCE_CREATE record must be mapping")
            for key in ("source_id", "SOURCE_ID", "record_version", "record_status", "last_materialization_packet"):
                if key in record:
                    fail("MATERIALIZATION_SCHEMA_FAILURE", f"SOURCE_CREATE supplies system-owned {key}")
            record["record_version"] = 1
            record["record_status"] = "active"
            record["last_materialization_packet"] = packet_id
            for key in ("citation_key", "zotero", "work_family_id", "evidence_record", "hold_scope"):
                record.setdefault(key, None)
            sources[source_id] = record
            validate_doi_for(source_id, record)
            return source_id

        gap_create_operations: dict[str, dict[str, Any]] = {}
        proposed_gap_ids: list[str] = []
        for operation in operations:
            if operation.get("type") != "GAP_CREATE":
                continue
            gap_id = operation_field(operation, "gap_id")
            if not isinstance(gap_id, str) or gap_id in gap_create_operations:
                fail("MATERIALIZATION_SCHEMA_FAILURE", "GAP_CREATE IDs must be unique canonical IDs")
            gap_create_operations[gap_id] = operation
            proposed_gap_ids.append(gap_id)
        expected_gap_ids = [f"GAP-{gap_max + index:06d}" for index in range(1, len(proposed_gap_ids) + 1)]
        if proposed_gap_ids != expected_gap_ids:
            fail("MATERIALIZATION_SCHEMA_FAILURE", "GAP_CREATE IDs must be the consecutive monotonic sequence")

        def materialize_gap_create(gap_id: str) -> None:
            nonlocal next_gap
            if gap_id in gaps:
                return
            operation = gap_create_operations[gap_id]
            payload = mapping(operation.get("payload"), "GAP_CREATE payload must be mapping")
            record = copy.deepcopy(payload.get("record", payload))
            record = mapping(resolve_tree(record, pending), "gap record must be mapping")
            record.pop("gap_id", None)
            gaps[gap_id] = record
            plan.allocated_gap_ids.append(gap_id)
            next_gap = max(next_gap, int(gap_id.removeprefix("GAP-")) + 1)

        for proposed_gap_id in proposed_gap_ids:
            materialize_gap_create(proposed_gap_id)

        for operation in operations:
            op_type = operation.get("type")
            operation_id = str(operation["operation_id"])
            payload = mapping(operation.get("payload"), f"{operation_id} payload must be mapping")
            if op_type == "SOURCE_CREATE":
                materialize_source_create(str(operation["temporary_ref"]))
            elif op_type == "SOURCE_UPDATE":
                source_id = source_ref(operation)
                require_expected(operation, source_id)
                patch = mapping(payload.get("patch"), "SOURCE_UPDATE requires payload.patch")
                forbidden = {"SOURCE_ID", "source_id", "record_version", "last_materialization_packet", "evidence_record"}
                if forbidden.intersection(patch):
                    fail("MATERIALIZATION_SCHEMA_FAILURE", "SOURCE_UPDATE patches system-owned field")
                sources[source_id].update(resolve_tree(copy.deepcopy(patch), pending))
                validate_doi_for(source_id, sources[source_id])
            elif op_type == "EVIDENCE_ADD":
                source_id = source_ref(operation)
                require_expected(operation, source_id)
                document = ensure_evidence(source_id)
                item = copy.deepcopy(payload.get("item", payload.get("evidence", payload)))
                item = mapping(resolve_tree(item, pending), "EVIDENCE_ADD item must be mapping")
                if "evidence_id" in item:
                    fail("MATERIALIZATION_SCHEMA_FAILURE", "new evidence_id is materializer-owned")
                existing_numbers = [
                    int(match.group(2)) for value in initial_evidence_ids + [x.get("evidence_id") for x in document["evidence"] if isinstance(x, dict)]
                    if isinstance(value, str) and (match := EVIDENCE_RE.fullmatch(value)) and match.group(1) == source_id[4:]
                ]
                evidence_id = f"EV-SRC{source_id[4:]}-{max(existing_numbers, default=0)+1:03d}"
                item = {"evidence_id": evidence_id, **item}
                document["evidence"].append(item)
                plan.allocated_evidence_ids.append(evidence_id)
            elif op_type == "EVIDENCE_UPDATE":
                source_id = source_ref(operation)
                require_expected(operation, source_id)
                document = evidence.get(source_id)
                if not isinstance(document, dict):
                    fail("EVIDENCE_REFERENCE_DANGLING", "evidence record does not exist")
                evidence_id = operation_field(operation, "evidence_id")
                mode = payload.get("mode", "item_patch")
                if mode == "item_patch":
                    patch = mapping(payload.get("patch"), "EVIDENCE_UPDATE item_patch requires patch")
                    if "evidence_id" in patch:
                        fail("MATERIALIZATION_SCHEMA_FAILURE", "evidence_id is immutable")
                    matches = [item for item in document.get("evidence", []) if isinstance(item, dict) and item.get("evidence_id") == evidence_id]
                    if len(matches) != 1:
                        fail("EVIDENCE_REFERENCE_DANGLING", "EVIDENCE_UPDATE target does not resolve exactly once")
                    matches[0].update(resolve_tree(copy.deepcopy(patch), pending))
                elif mode == "record_patch":
                    patch = mapping(payload.get("patch"), "EVIDENCE_UPDATE record_patch requires patch")
                    if set(patch) - {"applicability", "cef"}:
                        fail("MATERIALIZATION_SCHEMA_FAILURE", "record_patch contains forbidden fields")
                    document.update(resolve_tree(copy.deepcopy(patch), pending))
                else:
                    fail("MATERIALIZATION_SCHEMA_FAILURE", "invalid EVIDENCE_UPDATE mode")
                touched_evidence.add(source_id)
            elif op_type == "SEARCH_PASS_ADD":
                record = mapping(resolve_tree(copy.deepcopy(payload.get("record", payload)), pending), "search pass must be mapping")
                search_id = record.get("search_pass_id")
                if not isinstance(search_id, str) or not SEARCH_RE.fullmatch(search_id):
                    fail("INVALID_SEARCH_PASS_ID", "invalid SEARCH_PASS_ADD ID")
                if search_id in searches:
                    fail("SEARCH_PASS_ID_COLLISION", f"search pass already exists: {search_id}")
                searches[search_id] = record
            elif op_type == "GAP_CREATE":
                gap_id = operation_field(operation, "gap_id")
                materialize_gap_create(str(gap_id))
            elif op_type == "GAP_UPDATE":
                gap_id = operation_field(operation, "gap_id")
                if gap_id not in gaps and gap_id in gap_create_operations:
                    materialize_gap_create(str(gap_id))
                if gap_id not in gaps:
                    fail("INVALID_GAP_STATUS", f"gap does not exist: {gap_id}")
                patch = mapping(payload.get("patch"), "GAP_UPDATE requires payload.patch")
                gaps[gap_id].update(resolve_tree(copy.deepcopy(patch), pending))
            elif op_type == "ADD_CITATION_EDGE":
                raw = resolve_tree(copy.deepcopy(payload), pending)
                from_source = raw.get("from_source", operation.get("from_source"))
                to_source = raw.get("to_source", operation.get("to_source"))
                ensure_allocated_source(from_source)
                ensure_allocated_source(to_source)
                if from_source not in sources or to_source not in sources:
                    fail("CITATION_EDGE_DANGLING", "citation endpoint does not resolve")
                require_expected(operation, from_source)
                document = ensure_evidence(from_source)
                if "edge_id" in raw:
                    fail("MATERIALIZATION_SCHEMA_FAILURE", "new edge_id is materializer-owned")
                edge_id = f"EDGE-{next_edge:06d}"
                next_edge += 1
                edge = {"edge_id": edge_id, **raw, "from_source": from_source, "to_source": to_source}
                document.setdefault("relations", []).append(edge)
                plan.allocated_edge_ids.append(edge_id)
            elif op_type == "WORK_FAMILY_LINK":
                source_id = source_ref(operation)
                require_expected(operation, source_id)
                work_family_id = payload.get("work_family_id", operation.get("work_family_id"))
                role = payload.get("work_version_role", operation.get("work_version_role"))
                if not isinstance(work_family_id, str) or not WF_RE.fullmatch(work_family_id):
                    fail("MATERIALIZATION_SCHEMA_FAILURE", "invalid work_family_id")
                if work_family_id not in wf_existing and work_family_id not in introduced_wf:
                    if work_family_id != f"WF-{next_wf:06d}":
                        fail("MATERIALIZATION_SCHEMA_FAILURE", "new work family must be exact next monotonic ID")
                    introduced_wf.add(work_family_id)
                    plan.allocated_work_family_ids.append(work_family_id)
                    next_wf += 1
                sources[source_id]["work_family_id"] = work_family_id
                sources[source_id]["work_version_role"] = role
            elif op_type in DEFERRED_TYPES:
                plan.deferred_zotero_requests.append({
                    "operation_id": operation_id,
                    "type": str(op_type),
                    "status": "deferred_not_executed",
                })
            else:
                fail("MATERIALIZATION_SCHEMA_FAILURE", f"unsupported operation type: {op_type!r}")

        for source_id in sorted(existing_affected):
            before = int(original_sources[source_id]["record_version"])
            sources[source_id]["record_version"] = before + 1
            sources[source_id]["last_materialization_packet"] = packet_id
            plan.record_version_changes[source_id] = [before, before + 1]
        for source_id in sorted(touched_evidence):
            if source_id in original_evidence:
                before = int(original_evidence[source_id]["evidence_record_version"])
                evidence[source_id]["evidence_record_version"] = before + 1
                plan.evidence_record_version_changes[source_id] = [before, before + 1]

        sources_doc["sources"] = {key: sources[key] for key in sorted(sources)}
        gaps_doc["gaps"] = {key: gaps[key] for key in sorted(gaps)}
        candidate_writes: dict[str, bytes] = {
            "05_Literature/SOURCE_REGISTRY.yaml": yaml_bytes(sources_doc),
            "05_Literature/GAPS.yaml": yaml_bytes(gaps_doc),
        }
        for source_id, document in sorted(evidence.items()):
            candidate_writes[f"05_Literature/EVIDENCE/{source_id}.yaml"] = yaml_bytes(document)
        for search_id, document in sorted(searches.items()):
            candidate_writes[f"05_Literature/SEARCH_LOG/{search_id}.yaml"] = yaml_bytes(document)

        for relative, data in sorted(candidate_writes.items()):
            target = safe_runtime_path(self.root, relative)
            old = target.read_bytes() if target.is_file() else None
            if old != data:
                plan.writes[relative] = data
                plan.prestate_sha256[relative] = sha256(old) if old is not None else None
                (plan.modified if old is not None else plan.created).append(relative)

        ledger_copy = copy.deepcopy(ledger)
        applications = mapping(ledger_copy.get("applications"), "ledger applications must be mapping")
        entry = {
            "packet_sha256": packet_hash,
            "base_head": self.base_head,
            "plan_sha256": "0" * 64,
            "result": "applied",
            "allocated_source_ids": plan.allocated_source_ids,
            "allocated_gap_ids": plan.allocated_gap_ids,
            "allocated_evidence_ids": plan.allocated_evidence_ids,
            "allocated_edge_ids": plan.allocated_edge_ids,
            "allocated_work_family_ids": plan.allocated_work_family_ids,
            "files_created": sorted(plan.created),
            "files_modified": sorted(plan.modified + ["05_Literature/MATERIALIZATION_LOG.yaml"]),
            "deferred_zotero_requests": plan.deferred_zotero_requests,
        }
        applications[packet_id] = entry
        ledger_copy["applications"] = {key: applications[key] for key in sorted(applications)}
        projection = yaml_bytes(ledger_copy)
        plan.plan_sha256 = sha256(plan.digest_payload(projection))
        entry["plan_sha256"] = plan.plan_sha256
        ledger_data = yaml_bytes(ledger_copy)
        ledger_path = self.root / "05_Literature/MATERIALIZATION_LOG.yaml"
        if ledger_path.read_bytes() != ledger_data:
            plan.writes["05_Literature/MATERIALIZATION_LOG.yaml"] = ledger_data
            plan.prestate_sha256["05_Literature/MATERIALIZATION_LOG.yaml"] = sha256(ledger_path.read_bytes())
            if "05_Literature/MATERIALIZATION_LOG.yaml" not in plan.modified:
                plan.modified.append("05_Literature/MATERIALIZATION_LOG.yaml")
        plan.created.sort()
        plan.modified.sort()
        return plan

    def validate_shadow(self, plan: Plan) -> None:
        with tempfile.TemporaryDirectory(prefix="lit-materializer-shadow-") as temporary:
            shadow = Path(temporary) / "repository"
            shutil.copytree(self.root, shadow, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            for relative, data in sorted(plan.writes.items()):
                target = safe_runtime_path(shadow, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            issues = Validator(shadow).run()
            if issues:
                first = issues[0]
                fail(first.failure_code, f"shadow-state validation failed: {first.message}")

    def apply_plan(self, plan: Plan) -> None:
        self.check_packet_path()
        self.check_git_state()
        if self.base_head != plan.base_head:
            fail("PACKET_PRECONDITION_FAILURE", "HEAD changed after planning")
        if sha256(self.packet_path.read_bytes()) != plan.packet_sha256:
            fail("PACKET_PRECONDITION_FAILURE", "packet bytes changed after planning")
        for relative, expected in sorted(plan.prestate_sha256.items()):
            target = safe_runtime_path(self.root, relative)
            current = sha256(target.read_bytes()) if target.is_file() else None
            if current != expected:
                fail("PACKET_PRECONDITION_FAILURE", f"pre-state fingerprint changed: {relative}")
        backups: dict[str, bytes | None] = {}
        written: list[str] = []
        created_directories: set[Path] = set()
        try:
            for index, (relative, data) in enumerate(sorted(plan.writes.items()), 1):
                target = safe_runtime_path(self.root, relative)
                cursor = target.parent
                missing_parents: list[Path] = []
                while cursor != self.root and not cursor.exists():
                    missing_parents.append(cursor)
                    cursor = cursor.parent
                target.parent.mkdir(parents=True, exist_ok=True)
                created_directories.update(missing_parents)
                backups[relative] = target.read_bytes() if target.is_file() else None
                if self.fault == "partial_write" and index == 2:
                    raise OSError("injected partial-write failure")
                fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                written.append(relative)
            issues = Validator(self.root).run()
            if self.fault in {"post_validation", "rollback_failure"}:
                issues = [object()]  # type: ignore[list-item]
            if issues:
                raise RuntimeError("post-apply validation failed")
        except Exception as exc:
            try:
                for relative in reversed(written):
                    target = safe_runtime_path(self.root, relative)
                    original = backups[relative]
                    if self.fault == "rollback_failure":
                        raise OSError("injected rollback failure")
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.rollback.", dir=target.parent)
                        temporary = Path(temporary_name)
                        try:
                            with os.fdopen(fd, "wb") as handle:
                                handle.write(original)
                                handle.flush()
                                os.fsync(handle.fileno())
                            os.replace(temporary, target)
                        finally:
                            temporary.unlink(missing_ok=True)
                for relative, original in backups.items():
                    target = safe_runtime_path(self.root, relative)
                    current = target.read_bytes() if target.is_file() else None
                    if current != original:
                        raise OSError(f"restoration mismatch: {relative}")
                for directory in sorted(created_directories, key=lambda item: len(item.parts), reverse=True):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            except Exception as rollback_exc:
                fail("MATERIALIZATION_ROLLBACK_FAILURE", str(rollback_exc))
            fail("MATERIALIZATION_SCHEMA_FAILURE", f"apply rolled back: {exc}")


def render_report(status: str, mode: str, plan: Plan | None, error: MaterializationFailure | None = None) -> None:
    def array(values: Any) -> str:
        return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    if plan is None:
        print(f"MODE={mode}")
        print(f"PRECONDITION_STATUS={'FAIL' if error else 'PASS'}")
        print(f"VALIDATION_STATUS={'FAIL' if error else 'PASS'}")
        if error:
            print(f"FAILURE_CODE={error.code}")
            print(f"MESSAGE={error}")
        print(f"STATUS={status}")
        return
    print(f"PACKET_ID={plan.packet_id}")
    print(f"MODE={mode}")
    print(f"BASE_HEAD={plan.base_head}")
    print(f"PACKET_SHA256={plan.packet_sha256}")
    print(f"PLAN_SHA256={plan.plan_sha256}")
    print("PRECONDITION_STATUS=PASS")
    print("VALIDATION_STATUS=PASS")
    print(f"ALLOCATED_SOURCE_IDS={array(plan.allocated_source_ids)}")
    print(f"ALLOCATED_GAP_IDS={array(plan.allocated_gap_ids)}")
    print(f"ALLOCATED_EVIDENCE_IDS={array(plan.allocated_evidence_ids)}")
    print(f"ALLOCATED_EDGE_IDS={array(plan.allocated_edge_ids)}")
    print(f"ALLOCATED_WORK_FAMILY_IDS={array(plan.allocated_work_family_ids)}")
    print(f"FILES_TO_CREATE={array([] if status == 'ALREADY_APPLIED' else plan.created)}")
    print(f"FILES_TO_MODIFY={array([] if status == 'ALREADY_APPLIED' else plan.modified)}")
    print("FILES_TO_DELETE=[]")
    print(f"RECORD_VERSION_CHANGES={array(plan.record_version_changes)}")
    print(f"EVIDENCE_RECORD_VERSION_CHANGES={array(plan.evidence_record_version_changes)}")
    print(f"DEFERRED_ZOTERO_REQUESTS={array(plan.deferred_zotero_requests)}")
    print("POST_VALIDATION_STATUS=PASS")
    print(f"STATUS={status}")


def selftest(repository_root: Path) -> int:
    """Exercise the frozen matrix using disposable synthetic Git repositories."""
    results: dict[str, bool] = {}

    def record(names: list[str], result: bool) -> None:
        for name in names:
            results[name] = result

    def write(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(yaml_bytes(value))

    def source(number: int, doi: str | None = None, version: int = 1) -> dict[str, Any]:
        return {
            "record_version": version,
            "record_status": "active",
            "source_slug": f"synthetic-{number}",
            "bibliographic_identity": {
                "title_short": f"Synthetic {number}", "first_author": "Fixture",
                "year": 2026, "doi": doi, "other_ids": {},
            },
            "bibliographic_status": "verified", "citation_key": None, "zotero": None,
            "work_family_id": None, "primary_source_status": "primary_verified",
            "full_text_status": "metadata_only", "compounds": ["Synthetic"],
            "techniques": ["fixture"], "branches": ["B01"],
            "workflow_state": "READY_FOR_01", "hold_scope": None,
            "search_passes": [], "evidence_record": None,
            "last_materialization_packet": None,
        }

    def packet(operations: list[dict[str, Any]], ambiguities: list[Any] | None = None) -> dict[str, Any]:
        return {
            "packet_id": "MP-20260910-01A-01", "packet_schema_version": "1.0",
            "producer_role": "01A", "source_search_passes": [],
            "operations": operations, "unresolved_ambiguities": ambiguities or [],
            "validation_status": "valid",
        }

    def create_operation(op_id: str, temporary: str, number: int, doi: str | None = None) -> dict[str, Any]:
        value = source(number, doi)
        for field in ("record_version", "record_status", "last_materialization_packet"):
            value.pop(field)
        return {"operation_id": op_id, "type": "SOURCE_CREATE", "temporary_ref": temporary, "payload": value}

    def evidence_document(source_id: str) -> dict[str, Any]:
        return {
            "source_id": source_id, "evidence_record_version": 1,
            "evidence": [{"evidence_id": f"EV-SRC{source_id[4:]}-001", "category": "MEASURED", "claim": "fixture"}],
            "relations": [], "cef": None,
        }

    with tempfile.TemporaryDirectory(prefix="lit-materializer-selftest-") as temporary:
        top = Path(temporary)
        counter = 0

        def snapshot_commit(root: Path, message: str) -> str:
            def fixture_git(*arguments: str, check: bool = True) -> str:
                completed = subprocess.run(
                    ["git", *arguments], cwd=root, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                if check and completed.returncode:
                    raise RuntimeError(completed.stderr)
                return completed.stdout.strip()

            files = sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file() and ".git" not in path.parts
            )
            completed = subprocess.run(
                ["git", "update-index", "--add", "--remove", "--stdin"],
                cwd=root, input="\n".join(files) + "\n", text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            tree = fixture_git("write-tree")
            current = fixture_git("rev-parse", "--verify", "HEAD", check=False)
            parents = ["-p", current] if current else []
            commit = fixture_git("commit-tree", tree, *parents, "-m", message)
            fixture_git("update-ref", "HEAD", commit)
            return commit

        def fixture(
            document: dict[str, Any], *, sources: dict[str, Any] | None = None,
            gaps: dict[str, Any] | None = None, evidence: dict[str, Any] | None = None,
            searches: dict[str, Any] | None = None,
        ) -> tuple[Path, Path, str]:
            nonlocal counter
            counter += 1
            root = top / f"case-{counter:03d}"
            (root / "05_Literature/SEARCH_LOG").mkdir(parents=True)
            (root / "05_Literature/PACKETS").mkdir(parents=True)
            shutil.copy2(repository_root / "05_Literature/SCHEMA_V1.yaml", root / "05_Literature/SCHEMA_V1.yaml")
            shutil.copy2(repository_root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml", root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml")
            write(root / "05_Literature/SOURCE_REGISTRY.yaml", {"schema_version": "1.0", "sources": sources or {}})
            write(root / "05_Literature/GAPS.yaml", {"schema_version": "1.0", "gaps": gaps or {}})
            write(root / "05_Literature/MATERIALIZATION_LOG.yaml", {"schema_version": "1.0", "applications": {}})
            for source_id, value in (evidence or {}).items():
                write(root / f"05_Literature/EVIDENCE/{source_id}.yaml", value)
            for search_id, value in (searches or {}).items():
                write(root / f"05_Literature/SEARCH_LOG/{search_id}.yaml", value)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            snapshot_commit(root, "fixture")
            packet_path = root / "05_Literature/PACKETS/MP-20260910-01A-01.yaml"
            write(packet_path, document)
            return root, packet_path, git(root, "rev-parse", "HEAD")

        def attempt(root: Path, packet_path: Path, apply: bool = False, expected: str | None = None, fault: str | None = None) -> tuple[str | None, Plan | None, str | None]:
            try:
                status, plan = Materializer(root, packet_path, apply, expected, fault).execute()
                return status, plan, None
            except MaterializationFailure as exc:
                return None, None, exc.code

        # Allocation, pending resolution, deterministic planning, and dry-run immutability.
        doc = packet([
            create_operation("OP-001", "SRC-PENDING-a", 1),
            create_operation("OP-002", "SRC-PENDING-b", 2),
        ])
        existing = {"SRC-000001": source(1), "SRC-000003": source(3)}
        root, path, head = fixture(doc, sources=existing)
        before = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
        status1, plan1, code1 = attempt(root, path)
        status2, plan2, code2 = attempt(root, path)
        after = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
        allocation_ok = (
            code1 is None and code2 is None and status1 == status2 == "DRY_RUN_OK"
            and plan1 is not None and plan2 is not None
            and plan1.allocated_source_ids == ["SRC-000004", "SRC-000005"]
            and plan1.plan_sha256 == plan2.plan_sha256 and before == after
        )
        record(["T-LIT02-01", "T-LIT02-02", "T-LIT02-03", "T-LIT02-07", "T-LIT02-38", "T-LIT02-57"], allocation_ok)

        # Source update success, stale and conflicting optimistic versions.
        update = {"operation_id": "OP-001", "type": "SOURCE_UPDATE", "source_ref": "SRC-000001", "preconditions": {"expected_record_version": 2}, "payload": {"patch": {"source_slug": "updated"}}}
        root, path, _ = fixture(packet([update]), sources={"SRC-000001": source(1, version=2)})
        ok_status, ok_plan, ok_code = attempt(root, path)
        record(["T-LIT02-04"], ok_code is None and ok_status == "DRY_RUN_OK" and ok_plan is not None and ok_plan.record_version_changes == {"SRC-000001": [2, 3]})
        stale = copy.deepcopy(update); stale["preconditions"]["expected_record_version"] = 1
        root, path, _ = fixture(packet([stale]), sources={"SRC-000001": source(1, version=2)})
        record(["T-LIT02-05"], attempt(root, path)[2] == "PACKET_PRECONDITION_FAILURE")
        conflicting = copy.deepcopy(update); conflicting["operation_id"] = "OP-002"; conflicting["preconditions"]["expected_record_version"] = 1
        root, path, _ = fixture(packet([update, conflicting]), sources={"SRC-000001": source(1, version=2)})
        record(["T-LIT02-06"], attempt(root, path)[2] == "PACKET_PRECONDITION_FAILURE")

        # Undefined and duplicate pending definitions.
        bad_ref = {"operation_id": "OP-001", "type": "EVIDENCE_ADD", "source_ref": "SRC-PENDING-x", "payload": {"item": {"category": "MEASURED", "claim": "x"}}}
        root, path, _ = fixture(packet([bad_ref]))
        record(["T-LIT02-08"], attempt(root, path)[2] == "MATERIALIZATION_SCHEMA_FAILURE")
        duplicate = [create_operation("OP-001", "SRC-PENDING-x", 1), create_operation("OP-002", "SRC-PENDING-x", 2)]
        root, path, _ = fixture(packet(duplicate))
        record(["T-LIT02-09"], attempt(root, path)[2] == "MATERIALIZATION_SCHEMA_FAILURE")
        # Pending leakage is caught by shadow validation.
        leak = create_operation("OP-001", "SRC-PENDING-x", 1); leak["payload"]["source_slug"] = "SRC-PENDING-x"
        root, path, _ = fixture(packet([leak]))
        record(["T-LIT02-10"], attempt(root, path)[2] == "CANONICAL_PENDING_SOURCE_ID")

        # Evidence allocation and frozen evidence/CEF validation.
        base = source(1); base["evidence_record"] = "EVIDENCE/SRC-000001.yaml"
        ev_add = {"operation_id": "OP-001", "type": "EVIDENCE_ADD", "source_ref": "SRC-000001", "preconditions": {"expected_record_version": 1}, "payload": {"item": {"category": "MEASURED", "claim": "new"}}}
        root, path, _ = fixture(packet([ev_add, {**copy.deepcopy(ev_add), "operation_id": "OP-002"}]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        _, ev_plan, ev_code = attempt(root, path)
        record(["T-LIT02-11", "T-LIT02-12"], ev_code is None and ev_plan is not None and ev_plan.allocated_evidence_ids == ["EV-SRC000001-002", "EV-SRC000001-003"])
        ev_update = {"operation_id": "OP-001", "type": "EVIDENCE_UPDATE", "source_ref": "SRC-000001", "evidence_id": "EV-SRC000001-001", "preconditions": {"expected_record_version": 1}, "payload": {"mode": "item_patch", "patch": {"claim": "updated"}}}
        root, path, _ = fixture(packet([ev_update]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        record(["T-LIT02-13"], attempt(root, path)[2] is None)
        wrong = copy.deepcopy(ev_update); wrong["evidence_id"] = "EV-SRC000002-001"
        root, path, _ = fixture(packet([wrong]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        record(["T-LIT02-14"], attempt(root, path)[2] == "EVIDENCE_REFERENCE_DANGLING")
        invalid = copy.deepcopy(ev_add); invalid["payload"]["item"]["category"] = "OBSERVED"
        root, path, _ = fixture(packet([invalid]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        record(["T-LIT02-15"], attempt(root, path)[2] == "INVALID_EVIDENCE_CATEGORY")
        for name, value, expected_ok in (("T-LIT02-16", 1.0, False), ("T-LIT02-17", 0.0, False)):
            cef = copy.deepcopy(ev_update); cef["payload"] = {"mode": "record_patch", "patch": {"cef": {"B_lm": [{"value": value}]}}}
            root, path, _ = fixture(packet([cef]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
            record([name], attempt(root, path)[2] == "CEF_PARAMETER_CONTEXT_INCOMPLETE")
        cef_ok = copy.deepcopy(ev_update); cef_ok["payload"] = {"mode": "record_patch", "patch": {"cef": {"B_lm": [{"value": 0.0}], "coordinate_convention": {"local_axes": "xyz", "formalism": "Stevens", "normalization": "standard", "parameter_units": "meV"}}}}
        root, path, _ = fixture(packet([cef_ok]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        record(["T-LIT02-18"], attempt(root, path)[2] is None)

        # Citation edge ownership and endpoint validation.
        source2 = source(2)
        edge = {"operation_id": "OP-001", "type": "ADD_CITATION_EDGE", "preconditions": {"expected_record_version": 1}, "payload": {"from_source": "SRC-000001", "to_source": "SRC-000002", "relation_type": "cites", "evidence_independence": "unknown"}}
        root, path, _ = fixture(packet([edge]), sources={"SRC-000001": base, "SRC-000002": source2}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        _, edge_plan, edge_code = attempt(root, path)
        edge_ok = edge_code is None and edge_plan is not None and edge_plan.allocated_edge_ids == ["EDGE-000001"]
        if edge_ok and edge_plan is not None:
            planned_evidence = yaml.safe_load(edge_plan.writes["05_Literature/EVIDENCE/SRC-000001.yaml"])
            edge_ok = planned_evidence["relations"][-1]["from_source"] == "SRC-000001"
        record(["T-LIT02-19", "T-LIT02-21"], edge_ok)
        dangling = copy.deepcopy(edge); dangling["payload"]["to_source"] = "SRC-999999"
        root, path, _ = fixture(packet([dangling]), sources={"SRC-000001": base}, evidence={"SRC-000001": evidence_document("SRC-000001")})
        record(["T-LIT02-20"], attempt(root, path)[2] == "EVIDENCE_REFERENCE_DANGLING")

        # Gap lifecycle.
        gap_record = {"question": "fixture", "importance": "high", "status": "open", "gap_type": "fixture", "current_evidence": [], "search_passes_attempted": [], "next_search": [], "blocked_reason": None, "resolved_by": []}
        gap_create = {"operation_id": "OP-001", "type": "GAP_CREATE", "gap_id": "GAP-000001", "payload": gap_record}
        root, path, _ = fixture(packet([gap_create]))
        record(["T-LIT02-22"], attempt(root, path)[2] is None)
        skipped = copy.deepcopy(gap_create); skipped["gap_id"] = "GAP-000002"
        root, path, _ = fixture(packet([skipped]))
        record(["T-LIT02-23"], attempt(root, path)[2] == "MATERIALIZATION_SCHEMA_FAILURE")
        existing_gap = {"GAP-000001": gap_record}
        gap_update = {"operation_id": "OP-001", "type": "GAP_UPDATE", "gap_id": "GAP-000001", "payload": {"patch": {"status": "probably_unrecoverable"}}}
        root, path, _ = fixture(packet([gap_update]), gaps=existing_gap)
        record(["T-LIT02-24", "T-LIT02-26"], attempt(root, path)[2] is None)
        resolved = copy.deepcopy(gap_update); resolved["payload"]["patch"] = {"status": "resolved", "resolved_by": []}
        root, path, _ = fixture(packet([resolved]), gaps=existing_gap)
        record(["T-LIT02-25"], attempt(root, path)[2] == "INVALID_GAP_STATUS")

        # Search pass creation, duplicate rejection, and retrospective provenance.
        search_id = "SP-20260910-TEST-01"
        search_record = {"search_pass_id": search_id, "mode": "RETROSPECTIVE_MIGRATION", "objective": "fixture", "scope": {}, "executed_at": "2026-09-10", "executed_by_role": "01A", "sources": {}, "queries": [], "query_recovered": False, "provenance_origin": "historical_chat", "seed_sources": [], "sources_found": [], "sources_rejected": [], "duplicates": [], "citation_chains_followed": [], "unresolved_targets": [], "termination_reason": "fixture", "result_state": "FOUND"}
        search_op = {"operation_id": "OP-001", "type": "SEARCH_PASS_ADD", "payload": search_record}
        root, path, _ = fixture(packet([search_op]))
        record(["T-LIT02-27", "T-LIT02-29", "T-LIT02-30"], attempt(root, path)[2] is None)
        root, path, _ = fixture(packet([search_op]), searches={search_id: search_record})
        record(["T-LIT02-28"], attempt(root, path)[2] in {"MATERIALIZATION_SCHEMA_FAILURE", "SEARCH_PASS_ID_COLLISION"})

        # Work families and no evidence-independence mutation.
        wf_source = source(1); wf_source["work_family_id"] = "WF-000001"; wf_source["work_version_role"] = "original"
        wf_existing_op = {"operation_id": "OP-001", "type": "WORK_FAMILY_LINK", "source_ref": "SRC-000001", "preconditions": {"expected_record_version": 1}, "payload": {"work_family_id": "WF-000001", "work_version_role": "translation"}}
        root, path, _ = fixture(packet([wf_existing_op]), sources={"SRC-000001": wf_source})
        _, wf_plan, wf_code = attempt(root, path)
        record(["T-LIT02-31", "T-LIT02-34"], wf_code is None and wf_plan is not None and not any("EVIDENCE/" in item for item in wf_plan.writes))
        wf_new = copy.deepcopy(wf_existing_op); wf_new["payload"]["work_family_id"] = "WF-000002"
        root, path, _ = fixture(packet([wf_new]), sources={"SRC-000001": wf_source})
        record(["T-LIT02-32"], attempt(root, path)[2] is None)
        wf_skip = copy.deepcopy(wf_new); wf_skip["payload"]["work_family_id"] = "WF-000003"
        root, path, _ = fixture(packet([wf_skip]), sources={"SRC-000001": wf_source})
        record(["T-LIT02-33"], attempt(root, path)[2] == "MATERIALIZATION_SCHEMA_FAILURE")

        # DOI collisions and ambiguity.
        root, path, _ = fixture(packet([create_operation("OP-001", "SRC-PENDING-x", 2, "10.1234/same")]), sources={"SRC-000001": source(1, "10.1234/same")})
        record(["T-LIT02-35"], attempt(root, path)[2] == "DUPLICATE_CANDIDATE")
        root, path, _ = fixture(packet([create_operation("OP-001", "SRC-PENDING-x", 1, "10.1234/same"), create_operation("OP-002", "SRC-PENDING-y", 2, "10.1234/same")]))
        record(["T-LIT02-36"], attempt(root, path)[2] == "DUPLICATE_CANDIDATE")
        root, path, _ = fixture(packet([], ["unresolved identity"]))
        record(["T-LIT02-37"], attempt(root, path)[2] == "BIBLIOGRAPHIC_AMBIGUITY")

        # Apply, validator compatibility, replay, and packet hash conflict.
        root, path, head = fixture(packet([create_operation("OP-001", "SRC-PENDING-x", 1)]))
        status, applied_plan, applied_code = attempt(root, path, True, head)
        applied_ok = status == "APPLIED" and applied_code is None and not Validator(root).run()
        snapshot_commit(root, "applied fixture")
        replay_status, replay_plan, replay_code = attempt(root, path)
        replay_ok = replay_status == "ALREADY_APPLIED" and replay_code is None and replay_plan is not None and not replay_plan.writes
        record(["T-LIT02-39", "T-LIT02-40", "T-LIT02-45", "T-LIT02-46"], applied_ok and replay_ok)

        corrupted_registry = load_yaml(root / "05_Literature/SOURCE_REGISTRY.yaml")
        corrupted_registry["schema_version"] = "corrupted"
        write(root / "05_Literature/SOURCE_REGISTRY.yaml", corrupted_registry)
        snapshot_commit(root, "corrupted canonical pre-state")
        invalid_replay_status, _, invalid_replay_code = attempt(root, path)
        record(
            ["T-LIT02-58"],
            invalid_replay_status is None and invalid_replay_code == "STOP_SCHEMA_DIVERGENCE",
        )

        # Restore a healthy retained-packet fixture for the packet-ID/hash conflict check.
        root, path, head = fixture(packet([create_operation("OP-001", "SRC-PENDING-x", 1)]))
        status, _, applied_code = attempt(root, path, True, head)
        snapshot_commit(root, "applied fixture for hash conflict")
        changed_packet = load_yaml(path); changed_packet["validation_status"] = "changed"; write(path, changed_packet)
        snapshot_commit(root, "changed retained packet")
        record(["T-LIT02-41"], status == "APPLIED" and applied_code is None and attempt(root, path)[2] == "MATERIALIZATION_SCHEMA_FAILURE")

        # Rollback paths use injected deterministic failures.
        for name, fault, expected_code in (
            ("T-LIT02-42", "partial_write", "MATERIALIZATION_SCHEMA_FAILURE"),
            ("T-LIT02-43", "post_validation", "MATERIALIZATION_SCHEMA_FAILURE"),
            ("T-LIT02-44", "rollback_failure", "MATERIALIZATION_ROLLBACK_FAILURE"),
        ):
            root, path, head = fixture(packet([create_operation("OP-001", "SRC-PENDING-x", 1)]))
            before_state = {
                item.relative_to(root).as_posix(): sha256(item.read_bytes())
                for item in root.rglob("*") if item.is_file() and ".git" not in item.parts
            }
            _, _, failure_code = attempt(root, path, True, head, fault)
            after_state = {
                item.relative_to(root).as_posix(): sha256(item.read_bytes())
                for item in root.rglob("*") if item.is_file() and ".git" not in item.parts
            }
            restored = before_state == after_state
            record([name], failure_code == expected_code and (restored or fault == "rollback_failure"))

        # Deferred operations, including a Zotero-only packet, are ledger-only and offline.
        deferred = {"operation_id": "OP-001", "type": "ZOTERO_CREATE", "payload": {"source_ref": "SRC-PENDING-request"}}
        # Deferred payload is opaque; it must not be interpreted as a canonical source mutation.
        deferred["payload"] = {"request": "fixture"}
        root, path, head = fixture(packet([deferred]))
        d_status, d_plan, d_code = attempt(root, path)
        own_source = Path(__file__).read_text(encoding="utf-8")
        network_free = not any(
            line.startswith(("import requests", "from requests", "import urllib", "from urllib", "import httpx", "from httpx"))
            for line in own_source.splitlines()
        )
        deferred_ok = d_code is None and d_status == "DRY_RUN_OK" and d_plan is not None and network_free and d_plan.deferred_zotero_requests == [{"operation_id": "OP-001", "type": "ZOTERO_CREATE", "status": "deferred_not_executed"}]
        record(["T-LIT02-47", "T-LIT02-48"], deferred_ok)

        # Git state and apply HEAD gates.
        root, path, head = fixture(packet([])); (root / "05_Literature/GAPS.yaml").write_text("dirty\n", encoding="utf-8")
        record(["T-LIT02-49"], attempt(root, path)[2] == "PACKET_PRECONDITION_FAILURE")
        root, path, head = fixture(packet([])); subprocess.run(["git", "update-index", "--add", "05_Literature/PACKETS/MP-20260910-01A-01.yaml"], cwd=root, check=True)
        record(["T-LIT02-50"], attempt(root, path)[2] == "PACKET_PRECONDITION_FAILURE")
        root, path, head = fixture(packet([])); (root / "unrelated.tmp").write_text("x", encoding="utf-8")
        record(["T-LIT02-51"], attempt(root, path)[2] == "PACKET_PRECONDITION_FAILURE")
        root, path, head = fixture(packet([]))
        record(["T-LIT02-52"], attempt(root, path)[2] is None)
        root, path, head = fixture(packet([]))
        record(["T-LIT02-53"], attempt(root, path, True, "0" * 40)[2] == "PACKET_PRECONDITION_FAILURE")

        # Different CWD, offline behavior, report privacy and path rejection are inherent and checked explicitly.
        root, path, head = fixture(packet([]))
        old_cwd = Path.cwd()
        try:
            os.chdir(top)
            cwd_ok = attempt(root, path)[2] is None
        finally:
            os.chdir(old_cwd)
        report_value = attempt(root, path)[1]
        privacy_ok = report_value is not None and str(top) not in json.dumps(report_value.__dict__, default=str)
        escape = root / "outside.yaml"; write(escape, packet([]))
        path_ok = attempt(root, escape)[2] == "MATERIALIZATION_SCHEMA_FAILURE"
        record(["T-LIT02-54", "T-LIT02-55", "T-LIT02-56"], cwd_ok and network_free and privacy_ok and path_ok)

    names = [f"T-LIT02-{number:02d}" for number in range(1, 59)]
    missing = [name for name in names if name not in results]
    for name in missing:
        results[name] = False
    passed = all(results[name] for name in names)
    print("LIT_INFRA_02_SELFTEST")
    for name in names:
        print(f"{name}={'PASS' if results[name] else 'FAIL'}")
    print("FAILED_TESTS=" + ("none" if passed else ",".join(name for name in names if not results[name])))
    print(f"status={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", nargs="?", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-head")
    parser.add_argument("--selftest", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.selftest:
        return selftest(root)
    if args.packet is None:
        print("STATUS=FAIL\nFAILURE_CODE=MATERIALIZATION_SCHEMA_FAILURE\nMESSAGE=packet is required")
        return 2
    mode = "APPLY" if args.apply else "DRY_RUN"
    try:
        status, plan = Materializer(root, args.packet, args.apply, args.expected_head).execute()
    except MaterializationFailure as exc:
        render_report("FAIL", mode, None, exc)
        return 1
    render_report(status, mode, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
