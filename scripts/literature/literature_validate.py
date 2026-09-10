#!/usr/bin/env python3
"""Offline validator for the LIT-INFRA-SCHEMA-SPEC v1.0 foundation."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml


SPECIFICATION_ID = "LIT-INFRA-SCHEMA-SPEC"
SPECIFICATION_VERSION = "1.0"
SPECIFICATION_PATH = "03_Protocols/LITERATURE_KNOWLEDGE_SCHEMA_V1_0.md"
SCHEMA_VERSION = "1.0"

FROZEN_PATTERNS = {
    "SOURCE_ID": r"^SRC-[0-9]{6}$",
    "GAP_ID": r"^GAP-[0-9]{6}$",
    "SEARCH_PASS_ID": r"^SP-[0-9]{8}-[A-Z0-9]+-[0-9]{2}$",
    "EDGE_ID": r"^EDGE-[0-9]{6}$",
    "WORK_FAMILY_ID": r"^WF-[0-9]{6}$",
    "PACKET_ID": r"^MP-[0-9]{8}-01A-[0-9]{2}$",
    "EVIDENCE_ID": r"^EV-SRC[0-9]{6}-[0-9]{3,}$",
    "PENDING_SOURCE_ID": r"^SRC-PENDING-[A-Za-z0-9][A-Za-z0-9._-]*$",
}

FROZEN_ENUMERATIONS = {
    "record_status": ("active", "merged"),
    "bibliographic_status": ("verified", "partial", "unresolved"),
    "primary_source_status": (
        "primary_verified", "primary_found_not_read", "secondary_only",
        "citation_only", "unresolved",
    ),
    "full_text_status": (
        "obtained", "accessible_online", "abstract_only", "metadata_only", "unavailable",
    ),
    "zotero_link_status": ("unlinked", "linked", "stale", "needs_review"),
    "workflow_state": (
        "DISCOVERED", "PROVENANCE_VERIFIED", "READY_FOR_01", "01_REVIEWED",
        "CANONICAL_PROJECT_USE", "HOLD", "REJECTED",
    ),
    "hold_scope": ("provenance", "scientific"),
    "evidence_category": (
        "MEASURED", "DERIVED", "FITTED", "ASSUMED", "CALCULATED",
        "INTERPRETED_BY_AUTHORS", "INFERENCE_FOR_DyFeO3",
    ),
    "evidence_review_state": ("preliminary_01A", "reviewed_01", "held"),
    "gap_status": ("open", "partially_resolved", "resolved", "blocked", "probably_unrecoverable"),
    "gap_importance": ("low", "medium", "high", "critical"),
    "relation_type": (
        "cites", "independent_confirmation", "derivative_citation", "historical_reference",
        "parameter_reuse", "level_scheme_reuse", "method_reference", "contradiction",
        "translation", "work_version", "conference_precursor", "expanded_version",
    ),
    "evidence_independence": ("independent", "partially_independent", "not_independent", "unknown"),
    "work_version_role": (
        "original", "translation", "preprint", "publisher_version", "conference_precursor",
        "technical_report", "thesis_version", "thesis_chapter", "expanded_journal_version",
        "later_reanalysis",
    ),
    "search_mode": ("GLOBAL_BASELINE", "INCREMENTAL_WATCH", "RETROSPECTIVE_MIGRATION"),
    "search_result_state": (
        "FOUND", "SEARCHED_NOT_FOUND", "NOT_SEARCHED", "INACCESSIBLE",
        "BIBLIOGRAPHY_UNRESOLVED",
    ),
    "branch_saturation_state": ("OPEN", "DEVELOPING", "NEAR_SATURATION", "SATURATED_V1"),
    "packet_operation_type": (
        "SOURCE_CREATE", "SOURCE_UPDATE", "EVIDENCE_ADD", "EVIDENCE_UPDATE",
        "SEARCH_PASS_ADD", "ADD_CITATION_EDGE", "GAP_CREATE", "GAP_UPDATE",
        "WORK_FAMILY_LINK", "ZOTERO_CREATE", "ZOTERO_LINK_EXISTING",
        "ADD_COLLECTION", "ADD_TAG",
    ),
}

FROZEN_BRANCHES = {
    "B01": "DyFeO3 direct",
    "B02": "stoichiometric RFeO3",
    "B03": "Soviet/Russian historical",
    "B04": "optical/Zeeman/FIR/EPR",
    "B05": "neutron CEF / INS",
    "B06": "CEF inverse problem / identifiability",
    "B07": "CEF conventions / transforms",
    "B08": "structure → CEF",
    "B09": "exchange-aware CEF",
    "B10": "magnetoelastic / phonon–CEF",
    "B11": "neutron cross section / intensity methodology",
    "B12": "software/reproducibility",
    "B13": "Fe-only controls",
    "B14": "substituted orthoferrites",
    "B15": "RCrO3 comparators",
    "B16": "RGaO3 / RAlO3 structural comparators",
}

FROZEN_REQUIRED_FIELDS = {
    "source": (
        "record_version", "record_status", "source_slug", "bibliographic_identity",
        "bibliographic_status", "citation_key", "zotero", "work_family_id",
        "primary_source_status", "full_text_status", "compounds", "techniques",
        "branches", "workflow_state", "hold_scope", "search_passes",
        "evidence_record", "last_materialization_packet",
    ),
    "bibliographic_identity": ("title_short", "first_author", "year", "doi", "other_ids"),
    "evidence_record": ("source_id", "evidence_record_version", "evidence"),
    "evidence_item": ("evidence_id", "category", "claim"),
    "gap": (
        "question", "importance", "status", "gap_type", "current_evidence",
        "search_passes_attempted", "next_search", "blocked_reason", "resolved_by",
    ),
    "search_pass": (
        "search_pass_id", "mode", "objective", "scope", "executed_at", "executed_by_role",
        "sources", "queries", "seed_sources", "sources_found", "sources_rejected",
        "duplicates", "citation_chains_followed", "unresolved_targets",
        "termination_reason", "result_state",
    ),
    "citation_edge": (
        "edge_id", "from_source", "to_source", "relation_type", "evidence_independence",
    ),
    "packet": (
        "packet_id", "packet_schema_version", "producer_role", "source_search_passes",
        "operations", "unresolved_ambiguities", "validation_status",
    ),
    "packet_operation": ("operation_id", "type", "payload"),
}

FROZEN_CONDITIONAL_INVARIANTS = {
    "SOURCE_ID_IMMUTABLE": {
        "rule": "canonical SOURCE_ID values are never renamed, recycled, or reassigned",
    },
    "CANONICAL_PENDING_SOURCE_ID": {
        "rule": "SRC-PENDING identifiers are forbidden outside materialization packets",
        "failure_code": "CANONICAL_PENDING_SOURCE_ID",
    },
    "MERGED_REQUIRES_TARGET": {
        "when": "record_status == merged",
        "require": ["merged_into"],
    },
    "LINKED_ZOTERO_REQUIRES_IDENTITY": {
        "when": "zotero.link_status == linked",
        "require": ["zotero.library_alias", "zotero.item_key"],
    },
    "HOLD_REQUIRES_SCOPE": {
        "when": "workflow_state == HOLD",
        "require": ["hold_scope"],
    },
    "NON_HOLD_REQUIRES_NULL_SCOPE": {
        "when": "workflow_state != HOLD",
        "require_null": ["hold_scope"],
    },
    "RESOLVED_GAP_REQUIRES_EVIDENCE": {
        "when": "status == resolved",
        "require_nonempty": ["resolved_by"],
    },
    "CEF_PARAMETER_CONTEXT": {
        "when": "numerical B_lm values are present",
        "require": [
            "cef.coordinate_convention.local_axes",
            "cef.coordinate_convention.formalism",
            "cef.coordinate_convention.normalization",
            "cef.coordinate_convention.parameter_units",
        ],
        "failure_code": "CEF_PARAMETER_CONTEXT_INCOMPLETE",
    },
    "CITATION_ENDPOINTS_RESOLVE": {
        "rule": "from_source and to_source resolve to canonical SOURCE_ID records",
        "failure_code": "CITATION_EDGE_DANGLING",
    },
    "PACKET_REFERENCES_RESOLVE": {
        "rule": (
            "structured source, gap, and search-pass references resolve canonically "
            "or to exactly one same-packet create operation"
        ),
        "failure_code": "MATERIALIZATION_SCHEMA_FAILURE",
    },
    "AMBIGUITY_FAILS_CLOSED": {
        "rule": "unresolved ambiguity never causes automatic create, update, or merge",
    },
    "DUPLICATE_DOI_FAILS_CLOSED": {
        "rule": "duplicate normalized DOI is a duplicate candidate and is never auto-merged",
        "failure_code": "DUPLICATE_CANDIDATE",
    },
}

FROZEN_FAILURE_CODES = (
    "SOURCE_ID_COLLISION", "SEARCH_PASS_ID_COLLISION", "BIBLIOGRAPHIC_AMBIGUITY",
    "DUPLICATE_CANDIDATE", "PRIMARY_SOURCE_UNRESOLVED",
    "MATERIALIZATION_SCHEMA_FAILURE", "PACKET_PRECONDITION_FAILURE",
    "CITATION_EDGE_DANGLING", "EVIDENCE_REFERENCE_DANGLING", "UNKNOWN_BRANCH_ID",
    "INVALID_EVIDENCE_CATEGORY", "INVALID_GAP_STATUS", "BIBTEX_KEY_COLLISION",
    "BIBTEX_EXPORT_MISMATCH", "ZOTERO_UNAVAILABLE", "ZOTERO_AUTHORIZATION_REQUIRED",
    "ZOTERO_WRITE_DENIED", "ZOTERO_IDENTITY_MISMATCH", "ZOTERO_SERVER_ID_CHANGED",
    "ZOTERO_WRITE_CONFLICT", "LOCAL_CONFIG_MISSING", "INVALID_SOURCE_ID",
    "CANONICAL_PENDING_SOURCE_ID", "INVALID_WORKFLOW_STATE", "INVALID_SEARCH_PASS_ID",
    "INVALID_EDGE_ID", "INVALID_PACKET_ID", "INVALID_RELATION_TYPE",
    "INVALID_EVIDENCE_INDEPENDENCE", "INVALID_SEARCH_MODE",
    "INVALID_SEARCH_RESULT_STATE", "CEF_PARAMETER_CONTEXT_INCOMPLETE",
    "STOP_SCHEMA_DIVERGENCE",
)


class DuplicateKeyError(ValueError):
    def __init__(self, key: object) -> None:
        super().__init__(f"duplicate mapping key: {key!r}")
        self.key = key


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


@dataclass(frozen=True, order=True)
class Issue:
    failure_code: str
    path: str
    record_id: str
    message: str

    def render(self) -> str:
        return (
            f"ISSUE failure_code={self.failure_code} path={self.path} "
            f"record={self.record_id or '-'} message={self.message}"
        )


class Validator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.issues: list[Issue] = []
        self.schema: dict[str, Any] = {}
        self.sources: dict[str, Any] = {}
        self.gaps: dict[str, Any] = {}
        self.search_passes: dict[str, Path] = {}
        self.patterns: dict[str, re.Pattern[str]] = {}
        self.enums: dict[str, set[str]] = {}
        self.seen_evidence_ids: set[str] = set()
        self.seen_edge_ids: set[str] = set()
        self.seen_search_ids: set[str] = set()
        self.seen_packet_ids: set[str] = set()

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def add(self, code: str, path: Path | str, record_id: object, message: str) -> None:
        path_text = self.rel(path) if isinstance(path, Path) else path
        self.issues.append(Issue(code, path_text, str(record_id or ""), message))

    def load(self, path: Path, collision_code: str = "MATERIALIZATION_SCHEMA_FAILURE") -> Any:
        if not path.is_file():
            self.add(collision_code, path, "", "required file is missing")
            return {}
        try:
            return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except DuplicateKeyError as exc:
            code = collision_code
            key = str(exc.key)
            if key.startswith("SRC-"):
                code = "SOURCE_ID_COLLISION"
            elif key.startswith("SP-"):
                code = "SEARCH_PASS_ID_COLLISION"
            self.add(code, path, key, str(exc))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            self.add("MATERIALIZATION_SCHEMA_FAILURE", path, "", f"YAML load failed: {exc}")
        return {}

    @staticmethod
    def mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def sequence(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def enum(self, name: str, value: Any, code: str, path: Path, record_id: str) -> None:
        if value not in self.enums.get(name, set()):
            self.add(code, path, record_id, f"{name} has invalid value {value!r}")

    def pattern(self, name: str, value: Any, code: str, path: Path, record_id: str) -> bool:
        valid = isinstance(value, str) and bool(self.patterns.get(name, re.compile(r"(?!)")).fullmatch(value))
        if not valid:
            self.add(code, path, record_id, f"{name} has invalid value {value!r}")
        return valid

    def require_fields(
        self,
        kind: str,
        record: dict[str, Any],
        path: Path,
        record_id: str,
    ) -> None:
        required = self.mapping(self.schema.get("required_fields")).get(kind, [])
        for field in required:
            if field not in record:
                self.add(
                    "MATERIALIZATION_SCHEMA_FAILURE",
                    path,
                    record_id,
                    f"missing required field {field}",
                )

    def validate_schema(self) -> None:
        path = self.root / "05_Literature/SCHEMA_V1.yaml"
        value = self.load(path)
        if not isinstance(value, dict):
            self.add("STOP_SCHEMA_DIVERGENCE", path, "", "schema root must be a mapping")
            return
        self.schema = value
        spec = self.mapping(value.get("specification"))
        expected = {
            "repository_schema_version": SCHEMA_VERSION,
            "specification_id": SPECIFICATION_ID,
            "specification_version": SPECIFICATION_VERSION,
            "specification_path": SPECIFICATION_PATH,
        }
        actual = {
            "repository_schema_version": value.get("repository_schema_version"),
            "specification_id": spec.get("specification_id"),
            "specification_version": spec.get("specification_version"),
            "specification_path": spec.get("specification_path"),
        }
        if actual != expected:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "", f"schema identity mismatch: {actual!r}")

        raw_patterns = self.mapping(value.get("id_patterns"))
        if raw_patterns != FROZEN_PATTERNS:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "id_patterns", "ID patterns differ from frozen v1")
        for name, frozen_expression in FROZEN_PATTERNS.items():
            expression = raw_patterns.get(name)
            try:
                self.patterns[name] = re.compile(expression)
            except (TypeError, re.error):
                self.add("STOP_SCHEMA_DIVERGENCE", path, name, "missing or invalid ID pattern")
                self.patterns[name] = re.compile(frozen_expression)

        raw_enums = self.mapping(value.get("enumerations"))
        if set(raw_enums) != set(FROZEN_ENUMERATIONS):
            self.add("STOP_SCHEMA_DIVERGENCE", path, "enumerations", "enumeration names differ from frozen v1")
        for name, frozen_values in FROZEN_ENUMERATIONS.items():
            values = raw_enums.get(name)
            if values != list(frozen_values):
                self.add("STOP_SCHEMA_DIVERGENCE", path, name, "enumeration differs from frozen v1")
            self.enums[name] = set(values) if isinstance(values, list) else set()

        branches = self.mapping(value.get("branches"))
        if branches != FROZEN_BRANCHES:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "branches", "branch IDs or labels differ from frozen v1")

        required_fields = self.mapping(value.get("required_fields"))
        if set(required_fields) != set(FROZEN_REQUIRED_FIELDS):
            self.add("STOP_SCHEMA_DIVERGENCE", path, "required_fields", "required-field groups differ from frozen v1")
        for name, frozen_fields in FROZEN_REQUIRED_FIELDS.items():
            if required_fields.get(name) != list(frozen_fields):
                self.add("STOP_SCHEMA_DIVERGENCE", path, name, "required fields differ from frozen v1")

        invariants = self.mapping(value.get("conditional_invariants"))
        if invariants != FROZEN_CONDITIONAL_INVARIANTS:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "conditional_invariants", "conditional invariants differ from frozen v1")

        if value.get("failure_codes") != list(FROZEN_FAILURE_CODES):
            self.add("STOP_SCHEMA_DIVERGENCE", path, "failure_codes", "failure vocabulary differs from frozen v1")

    def validate_source_registry(self) -> None:
        path = self.root / "05_Literature/SOURCE_REGISTRY.yaml"
        document = self.mapping(self.load(path, "SOURCE_ID_COLLISION"))
        if document.get("schema_version") != SCHEMA_VERSION:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "", "source registry schema_version mismatch")
        sources = document.get("sources")
        if not isinstance(sources, dict):
            self.add("MATERIALIZATION_SCHEMA_FAILURE", path, "", "sources must be a mapping")
            sources = {}
        self.sources = sources

        doi_owner: dict[str, str] = {}
        citation_owner: dict[str, str] = {}
        for source_id in sorted(sources):
            record = sources[source_id]
            if not self.pattern("SOURCE_ID", source_id, "INVALID_SOURCE_ID", path, source_id):
                if isinstance(source_id, str) and source_id.startswith("SRC-PENDING-"):
                    self.add("CANONICAL_PENDING_SOURCE_ID", path, source_id, "pending ID leaked into registry")
            if not isinstance(record, dict):
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "source record must be a mapping")
                continue
            self.require_fields("source", record, path, source_id)
            version = record.get("record_version")
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "record_version must be positive integer")
            self.enum("record_status", record.get("record_status"), "MATERIALIZATION_SCHEMA_FAILURE", path, source_id)
            self.enum("bibliographic_status", record.get("bibliographic_status"), "BIBLIOGRAPHIC_AMBIGUITY", path, source_id)
            self.enum("primary_source_status", record.get("primary_source_status"), "PRIMARY_SOURCE_UNRESOLVED", path, source_id)
            self.enum("full_text_status", record.get("full_text_status"), "MATERIALIZATION_SCHEMA_FAILURE", path, source_id)
            self.enum("workflow_state", record.get("workflow_state"), "INVALID_WORKFLOW_STATE", path, source_id)

            if record.get("record_status") == "merged":
                target = record.get("merged_into")
                if target not in sources or self.mapping(sources.get(target)).get("record_status") != "active":
                    self.add("EVIDENCE_REFERENCE_DANGLING", path, source_id, "merged_into must resolve to active source")
            elif record.get("merged_into") is not None:
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "active source must not define merged_into")

            identity = self.mapping(record.get("bibliographic_identity"))
            self.require_fields("bibliographic_identity", identity, path, source_id)
            doi = identity.get("doi")
            if doi is not None:
                if not isinstance(doi, str) or doi != doi.strip().lower() or not re.fullmatch(r"10\.[0-9]{4,9}/\S+", doi):
                    self.add("BIBLIOGRAPHIC_AMBIGUITY", path, source_id, f"DOI is not normalized: {doi!r}")
                elif record.get("record_status") == "active":
                    if doi in doi_owner:
                        self.add("DUPLICATE_CANDIDATE", path, source_id, f"DOI also belongs to {doi_owner[doi]}")
                    else:
                        doi_owner[doi] = source_id

            citation_key = record.get("citation_key")
            if citation_key is not None:
                if not isinstance(citation_key, str) or not citation_key:
                    self.add("BIBTEX_KEY_COLLISION", path, source_id, "citation_key must be non-empty string or null")
                elif citation_key in citation_owner:
                    self.add("BIBTEX_KEY_COLLISION", path, source_id, f"citation key also belongs to {citation_owner[citation_key]}")
                else:
                    citation_owner[citation_key] = source_id

            valid_branches = set(self.mapping(self.schema.get("branches")))
            branch_values = record.get("branches")
            if not isinstance(branch_values, list):
                self.add("UNKNOWN_BRANCH_ID", path, source_id, "branches must be a list")
            else:
                for branch_id in branch_values:
                    if branch_id not in valid_branches:
                        self.add("UNKNOWN_BRANCH_ID", path, source_id, f"unknown branch {branch_id!r}")

            if record.get("workflow_state") == "HOLD":
                self.enum("hold_scope", record.get("hold_scope"), "INVALID_WORKFLOW_STATE", path, source_id)
            elif record.get("hold_scope") is not None:
                self.add(
                    "INVALID_WORKFLOW_STATE",
                    path,
                    source_id,
                    "non-HOLD source requires hold_scope: null",
                )

            zotero = record.get("zotero")
            if zotero is not None:
                if not isinstance(zotero, dict):
                    self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "zotero must be mapping or null")
                else:
                    self.enum("zotero_link_status", zotero.get("link_status"), "MATERIALIZATION_SCHEMA_FAILURE", path, source_id)
                    if zotero.get("link_status") == "linked" and not (
                        zotero.get("library_alias") and zotero.get("item_key")
                    ):
                        self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "linked Zotero record lacks identity")

            work_family_id = record.get("work_family_id")
            if work_family_id is not None:
                self.pattern("WORK_FAMILY_ID", work_family_id, "MATERIALIZATION_SCHEMA_FAILURE", path, source_id)
                self.enum("work_version_role", record.get("work_version_role"), "MATERIALIZATION_SCHEMA_FAILURE", path, source_id)

            evidence_record = record.get("evidence_record")
            if evidence_record is not None:
                if not isinstance(evidence_record, str):
                    self.add("EVIDENCE_REFERENCE_DANGLING", path, source_id, "evidence_record must be path or null")
                else:
                    self.validate_evidence_reference(evidence_record, source_id, path)

            search_passes = record.get("search_passes")
            if not isinstance(search_passes, list):
                self.add("INVALID_SEARCH_PASS_ID", path, source_id, "search_passes must be a list")
            else:
                for search_id in search_passes:
                    if not self.pattern(
                        "SEARCH_PASS_ID", search_id, "INVALID_SEARCH_PASS_ID", path, source_id
                    ):
                        continue
                    if search_id not in self.search_passes:
                        self.add(
                            "EVIDENCE_REFERENCE_DANGLING",
                            path,
                            source_id,
                            f"search pass does not resolve: {search_id}",
                        )

        self.reject_pending(document, path)

    def validate_evidence_reference(self, reference: str, source_id: str, path: Path) -> None:
        logical = PurePosixPath(reference)
        expected_name = f"{source_id}.yaml"
        malformed = (
            not reference
            or "\\" in reference
            or logical.is_absolute()
            or ".." in logical.parts
            or reference != f"EVIDENCE/{expected_name}"
            or logical.parts != ("EVIDENCE", expected_name)
            or not self.patterns["SOURCE_ID"].fullmatch(logical.stem)
        )
        if malformed:
            self.add(
                "MATERIALIZATION_SCHEMA_FAILURE",
                path,
                source_id,
                f"invalid evidence_record logical path: {reference!r}",
            )
            return

        literature_root = self.root / "05_Literature"
        logical_evidence_root = literature_root / "EVIDENCE"
        logical_target = literature_root / Path(*logical.parts)
        for component in (literature_root, logical_evidence_root, logical_target):
            if component.is_symlink():
                self.add(
                    "MATERIALIZATION_SCHEMA_FAILURE",
                    path,
                    source_id,
                    "canonical evidence path component must not be a symbolic link",
                )
                return

        evidence_root = logical_evidence_root.resolve()
        target = logical_target.resolve(strict=False)
        if not target.is_relative_to(evidence_root) or target.parent != evidence_root:
            self.add(
                "MATERIALIZATION_SCHEMA_FAILURE",
                path,
                source_id,
                "evidence_record resolves outside canonical EVIDENCE directory",
            )
            return
        if logical_target.is_symlink():
            self.add(
                "MATERIALIZATION_SCHEMA_FAILURE",
                path,
                source_id,
                "evidence_record must not be a symbolic link",
            )
            return
        if not target.is_file():
            self.add(
                "EVIDENCE_REFERENCE_DANGLING",
                path,
                source_id,
                f"canonical evidence file is missing or not regular: {reference}",
            )

    def reject_pending(self, value: Any, path: Path) -> None:
        def walk(node: Any) -> Iterable[str]:
            if isinstance(node, dict):
                for key, child in node.items():
                    yield str(key)
                    yield from walk(child)
            elif isinstance(node, list):
                for child in node:
                    yield from walk(child)
            elif isinstance(node, str):
                yield node

        for token in walk(value):
            if token.startswith("SRC-PENDING-"):
                self.add("CANONICAL_PENDING_SOURCE_ID", path, token, "pending source ID in canonical store")

    def discover_search_passes(self) -> None:
        directory = self.root / "05_Literature/SEARCH_LOG"
        owners: dict[str, Path] = {}
        for path in sorted(directory.glob("*.yaml")):
            if path.name == "BRANCH_STATUS.yaml":
                continue
            document = self.mapping(self.load(path, "SEARCH_PASS_ID_COLLISION"))
            search_id = document.get("search_pass_id")
            if not isinstance(search_id, str):
                continue
            if search_id in owners:
                self.add(
                    "SEARCH_PASS_ID_COLLISION",
                    path,
                    search_id,
                    f"search_pass_id also declared in {self.rel(owners[search_id])}",
                )
            else:
                owners[search_id] = path
        self.search_passes = owners

    def validate_gaps(self) -> None:
        path = self.root / "05_Literature/GAPS.yaml"
        document = self.mapping(self.load(path))
        if document.get("schema_version") != SCHEMA_VERSION:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "", "gap registry schema_version mismatch")
        gaps = document.get("gaps")
        if not isinstance(gaps, dict):
            self.add("MATERIALIZATION_SCHEMA_FAILURE", path, "", "gaps must be a mapping")
            gaps = {}
        self.gaps = gaps
        for gap_id in sorted(gaps):
            record = gaps[gap_id]
            self.pattern("GAP_ID", gap_id, "INVALID_GAP_STATUS", path, gap_id)
            if not isinstance(record, dict):
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, gap_id, "gap record must be mapping")
                continue
            self.require_fields("gap", record, path, gap_id)
            self.enum("gap_status", record.get("status"), "INVALID_GAP_STATUS", path, gap_id)
            self.enum("gap_importance", record.get("importance"), "INVALID_GAP_STATUS", path, gap_id)
            if record.get("status") == "resolved" and not self.sequence(record.get("resolved_by")):
                self.add("INVALID_GAP_STATUS", path, gap_id, "resolved gap requires resolved_by")
            self.validate_reference_list(
                record.get("current_evidence"),
                self.sources,
                "SOURCE_ID",
                "EVIDENCE_REFERENCE_DANGLING",
                path,
                gap_id,
                "current_evidence",
            )
            self.validate_reference_list(
                record.get("search_passes_attempted"),
                self.search_passes,
                "SEARCH_PASS_ID",
                "INVALID_SEARCH_PASS_ID",
                path,
                gap_id,
                "search_passes_attempted",
            )
            resolved_by = record.get("resolved_by")
            if isinstance(resolved_by, list):
                for reference in resolved_by:
                    if not isinstance(reference, str):
                        continue
                    if reference.startswith("SRC-") and reference not in self.sources:
                        self.add("EVIDENCE_REFERENCE_DANGLING", path, gap_id, f"resolved_by source does not resolve: {reference}")
                    elif reference.startswith("SP-") and reference not in self.search_passes:
                        self.add("INVALID_SEARCH_PASS_ID", path, gap_id, f"resolved_by search pass does not resolve: {reference}")
                    elif reference.startswith("GAP-") and reference not in gaps:
                        self.add("INVALID_GAP_STATUS", path, gap_id, f"resolved_by gap does not resolve: {reference}")
        self.reject_pending(document, path)

    def validate_reference_list(
        self,
        value: Any,
        targets: dict[str, Any],
        pattern_name: str,
        code: str,
        path: Path,
        record_id: str,
        field_name: str,
    ) -> None:
        if not isinstance(value, list):
            self.add("MATERIALIZATION_SCHEMA_FAILURE", path, record_id, f"{field_name} must be a list")
            return
        for reference in value:
            if not self.pattern(pattern_name, reference, code, path, record_id):
                continue
            if reference not in targets:
                self.add(code, path, record_id, f"{field_name} reference does not resolve: {reference}")

    def validate_branch_status(self) -> None:
        path = self.root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml"
        document = self.mapping(self.load(path))
        if document.get("schema_version") != SCHEMA_VERSION:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "", "branch registry schema_version mismatch")
        branches = document.get("branches")
        expected = self.mapping(self.schema.get("branches"))
        if not isinstance(branches, dict) or set(branches) != set(expected):
            self.add("UNKNOWN_BRANCH_ID", path, "", "branch registry must contain exactly B01-B16")
            return
        for branch_id, label in sorted(expected.items()):
            record = self.mapping(branches.get(branch_id))
            if record.get("label") != label:
                self.add("UNKNOWN_BRANCH_ID", path, branch_id, "branch label differs from frozen schema")
            self.enum("branch_saturation_state", record.get("status"), "UNKNOWN_BRANCH_ID", path, branch_id)
            if record.get("status") == "OPEN" and record.get("assessment_status") != "not_assessed":
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, branch_id, "neutral OPEN initialization must be not_assessed")

    def validate_evidence(self) -> None:
        directory = self.root / "05_Literature/EVIDENCE"
        if (self.root / "05_Literature").is_symlink() or directory.is_symlink():
            self.add(
                "MATERIALIZATION_SCHEMA_FAILURE",
                directory,
                "",
                "canonical evidence path component must not be a symbolic link",
            )
            return
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.yaml")):
            if path.is_symlink():
                self.add(
                    "MATERIALIZATION_SCHEMA_FAILURE",
                    path,
                    path.stem,
                    "canonical evidence path component must not be a symbolic link",
                )
                continue
            document = self.mapping(self.load(path))
            source_id = document.get("source_id")
            self.require_fields("evidence_record", document, path, str(source_id or ""))
            if source_id not in self.sources:
                self.add("EVIDENCE_REFERENCE_DANGLING", path, source_id, "evidence source_id is not registered")
            if path.stem != source_id:
                self.add("EVIDENCE_REFERENCE_DANGLING", path, source_id, "filename/source_id mismatch")
            evidence = document.get("evidence")
            if not isinstance(evidence, list):
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "evidence must be a list")
                evidence = []
            for item in evidence:
                if not isinstance(item, dict):
                    self.add("MATERIALIZATION_SCHEMA_FAILURE", path, source_id, "evidence item must be mapping")
                    continue
                evidence_id = item.get("evidence_id")
                self.require_fields("evidence_item", item, path, str(evidence_id or source_id or ""))
                if self.pattern("EVIDENCE_ID", evidence_id, "MATERIALIZATION_SCHEMA_FAILURE", path, str(evidence_id or "")):
                    if evidence_id in self.seen_evidence_ids:
                        self.add("MATERIALIZATION_SCHEMA_FAILURE", path, evidence_id, "duplicate evidence_id")
                    self.seen_evidence_ids.add(evidence_id)
                    expected_prefix = f"EV-{str(source_id).replace('-', '')}-"
                    if not evidence_id.startswith(expected_prefix):
                        self.add(
                            "MATERIALIZATION_SCHEMA_FAILURE",
                            path,
                            evidence_id,
                            f"evidence_id does not belong to owning source {source_id}",
                        )
                self.enum("evidence_category", item.get("category"), "INVALID_EVIDENCE_CATEGORY", path, str(evidence_id or ""))
                review_state = item.get("review_state")
                if review_state is not None:
                    self.enum("evidence_review_state", review_state, "INVALID_EVIDENCE_CATEGORY", path, str(evidence_id or ""))

            self.validate_relations(document.get("relations", []), path)
            self.validate_cef(document.get("cef"), path, str(source_id or ""))
            self.reject_pending(document, path)

    def validate_relations(self, relations: Any, path: Path) -> None:
        if relations is None:
            return
        if not isinstance(relations, list):
            self.add("MATERIALIZATION_SCHEMA_FAILURE", path, "", "relations must be a list")
            return
        for edge in relations:
            if not isinstance(edge, dict):
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, "", "citation edge must be mapping")
                continue
            edge_id = edge.get("edge_id")
            self.require_fields("citation_edge", edge, path, str(edge_id or ""))
            if self.pattern("EDGE_ID", edge_id, "INVALID_EDGE_ID", path, str(edge_id or "")):
                if edge_id in self.seen_edge_ids:
                    self.add("INVALID_EDGE_ID", path, edge_id, "duplicate edge_id")
                self.seen_edge_ids.add(edge_id)
            for endpoint in ("from_source", "to_source"):
                if edge.get(endpoint) not in self.sources:
                    self.add("CITATION_EDGE_DANGLING", path, edge_id, f"{endpoint} does not resolve")
            self.enum("relation_type", edge.get("relation_type"), "INVALID_RELATION_TYPE", path, str(edge_id or ""))
            self.enum(
                "evidence_independence",
                edge.get("evidence_independence"),
                "INVALID_EVIDENCE_INDEPENDENCE",
                path,
                str(edge_id or ""),
            )

    def validate_cef(self, cef: Any, path: Path, source_id: str) -> None:
        if not isinstance(cef, dict):
            return
        values = cef.get("B_lm")

        def has_number(node: Any) -> bool:
            if isinstance(node, bool):
                return False
            if isinstance(node, (int, float)):
                return True
            if isinstance(node, dict):
                return any(has_number(v) for v in node.values())
            if isinstance(node, list):
                return any(has_number(v) for v in node)
            return False

        if has_number(values):
            convention = self.mapping(cef.get("coordinate_convention"))
            required = ("local_axes", "formalism", "normalization", "parameter_units")
            missing = [field for field in required if not convention.get(field)]
            if missing:
                self.add(
                    "CEF_PARAMETER_CONTEXT_INCOMPLETE",
                    path,
                    source_id,
                    f"numerical B_lm lacks {', '.join(missing)}",
                )

    def validate_search_passes(self) -> None:
        directory = self.root / "05_Literature/SEARCH_LOG"
        for path in sorted(directory.glob("*.yaml")):
            if path.name == "BRANCH_STATUS.yaml":
                continue
            document = self.mapping(self.load(path, "SEARCH_PASS_ID_COLLISION"))
            search_id = document.get("search_pass_id")
            self.require_fields("search_pass", document, path, str(search_id or ""))
            if self.pattern("SEARCH_PASS_ID", search_id, "INVALID_SEARCH_PASS_ID", path, str(search_id or "")):
                if search_id in self.seen_search_ids:
                    self.add("SEARCH_PASS_ID_COLLISION", path, search_id, "duplicate search_pass_id")
                self.seen_search_ids.add(search_id)
            if path.stem != search_id:
                self.add("INVALID_SEARCH_PASS_ID", path, search_id, "filename/search_pass_id mismatch")
            self.enum("search_mode", document.get("mode"), "INVALID_SEARCH_MODE", path, str(search_id or ""))
            result_state = document.get("result_state")
            self.enum("search_result_state", result_state, "INVALID_SEARCH_RESULT_STATE", path, str(search_id or ""))
            for query in self.sequence(document.get("queries")):
                if isinstance(query, dict) and query.get("result") is not None:
                    self.enum(
                        "search_result_state",
                        query.get("result"),
                        "INVALID_SEARCH_RESULT_STATE",
                        path,
                        str(search_id or ""),
                    )
            for field_name in ("seed_sources", "sources_found"):
                for source_ref in self.structured_ids(document.get(field_name), "source_id"):
                    if source_ref.startswith("SRC-") and source_ref not in self.sources:
                        self.add(
                            "EVIDENCE_REFERENCE_DANGLING",
                            path,
                            str(search_id or ""),
                            f"{field_name} source does not resolve: {source_ref}",
                        )
            for gap_ref in self.structured_ids(document.get("unresolved_targets"), "gap_id"):
                if gap_ref.startswith("GAP-") and gap_ref not in self.gaps:
                    self.add(
                        "INVALID_GAP_STATUS",
                        path,
                        str(search_id or ""),
                        f"unresolved_targets gap does not resolve: {gap_ref}",
                    )
            self.reject_pending(document, path)

    @staticmethod
    def structured_ids(value: Any, mapping_key: str) -> Iterable[str]:
        if not isinstance(value, list):
            return ()
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict) and isinstance(item.get(mapping_key), str):
                result.append(item[mapping_key])
        return result

    def validate_packets(self) -> None:
        directory = self.root / "05_Literature/PACKETS"
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.yaml")):
            document = self.mapping(self.load(path))
            packet_id = document.get("packet_id")
            self.require_fields("packet", document, path, str(packet_id or ""))
            if self.pattern("PACKET_ID", packet_id, "INVALID_PACKET_ID", path, str(packet_id or "")):
                if packet_id in self.seen_packet_ids:
                    self.add("INVALID_PACKET_ID", path, packet_id, "duplicate packet_id")
                self.seen_packet_ids.add(packet_id)
            if path.stem != packet_id:
                self.add("INVALID_PACKET_ID", path, packet_id, "filename/packet_id mismatch")
            operations = document.get("operations")
            if not isinstance(operations, list):
                self.add("MATERIALIZATION_SCHEMA_FAILURE", path, packet_id, "operations must be a list")
                operations = []
            typed_operations = [operation for operation in operations if isinstance(operation, dict)]
            definitions = self.packet_definitions(typed_operations, path, str(packet_id or ""))
            operation_ids: set[str] = set()
            for operation in operations:
                if not isinstance(operation, dict):
                    self.add("MATERIALIZATION_SCHEMA_FAILURE", path, packet_id, "operation must be mapping")
                    continue
                operation_id = operation.get("operation_id")
                self.require_fields("packet_operation", operation, path, str(operation_id or packet_id or ""))
                if not isinstance(operation_id, str) or not operation_id:
                    self.add("MATERIALIZATION_SCHEMA_FAILURE", path, packet_id, "operation_id must be string")
                elif operation_id in operation_ids:
                    self.add("MATERIALIZATION_SCHEMA_FAILURE", path, operation_id, "duplicate packet operation_id")
                operation_ids.add(operation_id)
                self.enum(
                    "packet_operation_type",
                    operation.get("type"),
                    "MATERIALIZATION_SCHEMA_FAILURE",
                    path,
                    str(operation_id or ""),
                )
                self.validate_packet_references(
                    operation,
                    definitions,
                    path,
                    str(operation_id or packet_id or ""),
                )

            packet_search_passes = document.get("source_search_passes")
            if not isinstance(packet_search_passes, list):
                self.add(
                    "MATERIALIZATION_SCHEMA_FAILURE",
                    path,
                    packet_id,
                    "source_search_passes must be a list",
                )
            else:
                for search_id in packet_search_passes:
                    self.validate_packet_search_reference(
                        search_id,
                        definitions["search"],
                        path,
                        str(packet_id or ""),
                    )

    @staticmethod
    def operation_field(operation: dict[str, Any], field: str) -> Any:
        if field in operation:
            return operation[field]
        payload = operation.get("payload")
        return payload.get(field) if isinstance(payload, dict) else None

    def packet_definitions(
        self,
        operations: list[dict[str, Any]],
        path: Path,
        packet_id: str,
    ) -> dict[str, Counter[str]]:
        definitions: dict[str, Counter[str]] = {
            "pending": Counter(),
            "source": Counter(),
            "gap": Counter(),
            "search": Counter(),
        }
        for operation in operations:
            operation_type = operation.get("type")
            if operation_type == "SOURCE_CREATE":
                temporary_ref = operation.get("temporary_ref")
                if temporary_ref is not None:
                    if not isinstance(temporary_ref, str) or not self.patterns["PENDING_SOURCE_ID"].fullmatch(temporary_ref):
                        self.add("INVALID_SOURCE_ID", path, packet_id, f"invalid temporary_ref {temporary_ref!r}")
                    else:
                        definitions["pending"][temporary_ref] += 1
                source_id = self.operation_field(operation, "source_id")
                if source_id is not None:
                    if not isinstance(source_id, str) or not self.patterns["SOURCE_ID"].fullmatch(source_id):
                        self.add("INVALID_SOURCE_ID", path, packet_id, f"invalid SOURCE_CREATE source_id {source_id!r}")
                    else:
                        definitions["source"][source_id] += 1
                        if source_id in self.sources:
                            self.add("MATERIALIZATION_SCHEMA_FAILURE", path, packet_id, f"SOURCE_CREATE already exists: {source_id}")
            elif operation_type == "GAP_CREATE":
                gap_id = self.operation_field(operation, "gap_id")
                if not isinstance(gap_id, str) or not self.patterns["GAP_ID"].fullmatch(gap_id):
                    self.add("INVALID_GAP_STATUS", path, packet_id, f"invalid GAP_CREATE gap_id {gap_id!r}")
                else:
                    definitions["gap"][gap_id] += 1
                    if gap_id in self.gaps:
                        self.add("MATERIALIZATION_SCHEMA_FAILURE", path, packet_id, f"GAP_CREATE already exists: {gap_id}")
            elif operation_type == "SEARCH_PASS_ADD":
                search_id = self.operation_field(operation, "search_pass_id")
                if not isinstance(search_id, str) or not self.patterns["SEARCH_PASS_ID"].fullmatch(search_id):
                    self.add("INVALID_SEARCH_PASS_ID", path, packet_id, f"invalid SEARCH_PASS_ADD ID {search_id!r}")
                else:
                    definitions["search"][search_id] += 1
                    if search_id in self.search_passes:
                        self.add("MATERIALIZATION_SCHEMA_FAILURE", path, packet_id, f"SEARCH_PASS_ADD already exists: {search_id}")

        for kind, counts in definitions.items():
            for reference, count in sorted(counts.items()):
                if count != 1:
                    self.add(
                        "MATERIALIZATION_SCHEMA_FAILURE",
                        path,
                        packet_id,
                        f"duplicate or ambiguous packet-local {kind} definition: {reference}",
                    )
        return definitions

    def validate_packet_references(
        self,
        operation: dict[str, Any],
        definitions: dict[str, Counter[str]],
        path: Path,
        operation_id: str,
    ) -> None:
        source_keys = {
            "source_id", "source_ref", "from_source", "to_source", "merged_into",
            "current_evidence", "seed_sources", "sources_found",
        }
        gap_keys = {"gap_id", "unresolved_targets"}
        search_keys = {
            "search_pass_id", "search_passes", "search_passes_attempted",
            "source_search_passes",
        }

        def walk(node: Any, key: str = "") -> None:
            if isinstance(node, dict):
                for child_key, child in node.items():
                    walk(child, str(child_key))
            elif isinstance(node, list):
                for child in node:
                    walk(child, key)
            elif isinstance(node, str):
                if key in source_keys and node.startswith("SRC-"):
                    self.validate_packet_source_reference(
                        node,
                        definitions,
                        path,
                        operation_id,
                    )
                elif key in gap_keys and node.startswith("GAP-"):
                    self.validate_packet_gap_reference(
                        node,
                        definitions["gap"],
                        path,
                        operation_id,
                    )
                elif key in search_keys and node.startswith("SP-"):
                    self.validate_packet_search_reference(
                        node,
                        definitions["search"],
                        path,
                        operation_id,
                    )

        walk(operation)

        preconditions = operation.get("preconditions")
        expected_version = (
            preconditions.get("expected_record_version")
            if isinstance(preconditions, dict)
            else None
        )
        source_ref = self.operation_field(operation, "source_ref")
        if expected_version is not None and isinstance(source_ref, str) and source_ref in self.sources:
            actual_version = self.mapping(self.sources[source_ref]).get("record_version")
            if expected_version != actual_version:
                self.add(
                    "PACKET_PRECONDITION_FAILURE",
                    path,
                    operation_id,
                    f"expected record_version {expected_version!r}, found {actual_version!r}",
                )

    def validate_packet_source_reference(
        self,
        reference: str,
        definitions: dict[str, Counter[str]],
        path: Path,
        operation_id: str,
    ) -> None:
        if reference.startswith("SRC-PENDING-"):
            if not self.patterns["PENDING_SOURCE_ID"].fullmatch(reference):
                self.add("INVALID_SOURCE_ID", path, operation_id, f"invalid pending source reference {reference}")
            elif definitions["pending"].get(reference, 0) != 1:
                self.add(
                    "MATERIALIZATION_SCHEMA_FAILURE",
                    path,
                    operation_id,
                    f"pending source reference does not resolve exactly once: {reference}",
                )
            return
        if not self.patterns["SOURCE_ID"].fullmatch(reference):
            self.add("INVALID_SOURCE_ID", path, operation_id, f"invalid source reference {reference}")
        elif reference not in self.sources and definitions["source"].get(reference, 0) != 1:
            self.add("EVIDENCE_REFERENCE_DANGLING", path, operation_id, f"unresolved source reference {reference}")

    def validate_packet_gap_reference(
        self,
        reference: str,
        definitions: Counter[str],
        path: Path,
        operation_id: str,
    ) -> None:
        if not self.patterns["GAP_ID"].fullmatch(reference):
            self.add("INVALID_GAP_STATUS", path, operation_id, f"invalid gap reference {reference}")
        elif reference not in self.gaps and definitions.get(reference, 0) != 1:
            self.add("INVALID_GAP_STATUS", path, operation_id, f"unresolved gap reference {reference}")

    def validate_packet_search_reference(
        self,
        reference: Any,
        definitions: Counter[str],
        path: Path,
        operation_id: str,
    ) -> None:
        if not isinstance(reference, str) or not self.patterns["SEARCH_PASS_ID"].fullmatch(reference):
            self.add("INVALID_SEARCH_PASS_ID", path, operation_id, f"invalid search-pass reference {reference!r}")
        elif reference not in self.search_passes and definitions.get(reference, 0) != 1:
            self.add("INVALID_SEARCH_PASS_ID", path, operation_id, f"unresolved search-pass reference {reference}")

    def run(self) -> list[Issue]:
        self.validate_schema()
        if not self.schema:
            return sorted(set(self.issues))
        self.discover_search_passes()
        self.validate_source_registry()
        self.validate_gaps()
        self.validate_branch_status()
        self.validate_evidence()
        self.validate_search_passes()
        self.validate_packets()
        return sorted(set(self.issues))


def print_result(issues: list[Issue]) -> int:
    for issue in issues:
        print(issue.render())
    print("LITERATURE_VALIDATION")
    print(f"errors={len(issues)}")
    print("warnings=0")
    print(f"status={'PASS' if not issues else 'FAIL'}")
    return 0 if not issues else 1


def selftest(repository_root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="lit-infra-selftest-") as temporary:
        workspace = Path(temporary)

        def write_yaml(path: Path, value: Any) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

        def build(root: Path, representative: bool) -> None:
            (root / "05_Literature/SEARCH_LOG").mkdir(parents=True)
            shutil.copy2(
                repository_root / "05_Literature/SCHEMA_V1.yaml",
                root / "05_Literature/SCHEMA_V1.yaml",
            )
            shutil.copy2(
                repository_root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml",
                root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml",
            )
            sources: dict[str, Any] = {}
            gaps: dict[str, Any] = {}
            if representative:
                source_id = "SRC-000001"
                search_id = "SP-20260910-TEST-01"
                gap_id = "GAP-000001"
                sources[source_id] = {
                    "record_version": 1,
                    "record_status": "active",
                    "source_slug": "representative-source",
                    "bibliographic_identity": {
                        "title_short": "Representative source",
                        "first_author": "Example",
                        "year": 2026,
                        "doi": "10.1234/example",
                        "other_ids": {},
                    },
                    "bibliographic_status": "verified",
                    "citation_key": None,
                    "zotero": {
                        "library_alias": None,
                        "item_key": None,
                        "link_status": "unlinked",
                    },
                    "work_family_id": None,
                    "primary_source_status": "primary_verified",
                    "full_text_status": "obtained",
                    "compounds": ["DyFeO3"],
                    "techniques": ["test"],
                    "branches": ["B01"],
                    "workflow_state": "READY_FOR_01",
                    "hold_scope": None,
                    "search_passes": [search_id],
                    "evidence_record": f"EVIDENCE/{source_id}.yaml",
                    "last_materialization_packet": None,
                }
                gaps[gap_id] = {
                    "question": "Representative gap",
                    "importance": "high",
                    "status": "resolved",
                    "gap_type": "test",
                    "current_evidence": [source_id],
                    "search_passes_attempted": [search_id],
                    "next_search": [],
                    "blocked_reason": None,
                    "resolved_by": [source_id],
                }
                write_yaml(
                    root / f"05_Literature/EVIDENCE/{source_id}.yaml",
                    {
                        "source_id": source_id,
                        "evidence_record_version": 1,
                        "evidence": [
                            {
                                "evidence_id": "EV-SRC000001-001",
                                "category": "MEASURED",
                                "claim": "Representative evidence",
                            }
                        ],
                        "relations": [],
                        "cef": None,
                    },
                )
                write_yaml(
                    root / f"05_Literature/SEARCH_LOG/{search_id}.yaml",
                    {
                        "search_pass_id": search_id,
                        "mode": "GLOBAL_BASELINE",
                        "objective": "Representative validation",
                        "scope": {},
                        "executed_at": "2026-09-10",
                        "executed_by_role": "01A",
                        "sources": {},
                        "queries": [{"source": "test", "query": "test", "result": "FOUND"}],
                        "seed_sources": [source_id],
                        "sources_found": [source_id],
                        "sources_rejected": [],
                        "duplicates": [],
                        "citation_chains_followed": [],
                        "unresolved_targets": [gap_id],
                        "termination_reason": "test_complete",
                        "result_state": "FOUND",
                    },
                )
                write_yaml(
                    root / "05_Literature/PACKETS/MP-20260910-01A-01.yaml",
                    {
                        "packet_id": "MP-20260910-01A-01",
                        "packet_schema_version": "1.0",
                        "producer_role": "01A",
                        "source_search_passes": [search_id],
                        "operations": [
                            {
                                "operation_id": "OP-001",
                                "type": "SOURCE_UPDATE",
                                "source_ref": source_id,
                                "preconditions": {"expected_record_version": 1},
                                "payload": {},
                            },
                            {
                                "operation_id": "OP-002",
                                "type": "GAP_UPDATE",
                                "gap_id": gap_id,
                                "payload": {"search_pass_id": search_id},
                            },
                        ],
                        "unresolved_ambiguities": [],
                        "validation_status": "valid",
                    },
                )
            write_yaml(
                root / "05_Literature/SOURCE_REGISTRY.yaml",
                {"schema_version": "1.0", "sources": sources},
            )
            write_yaml(
                root / "05_Literature/GAPS.yaml",
                {"schema_version": "1.0", "gaps": gaps},
            )

        def mutate(path: Path, callback: Any) -> None:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            callback(value)
            write_yaml(path, value)

        results: list[tuple[str, bool]] = []

        def positive(name: str, representative: bool) -> None:
            root = workspace / name
            build(root, representative)
            results.append((name, not Validator(root).run()))

        def negative(
            name: str,
            modifier: Any,
            expected_code: str,
            representative: bool = True,
        ) -> None:
            root = workspace / name
            build(root, representative)
            modifier(root)
            codes = {issue.failure_code for issue in Validator(root).run()}
            results.append((name, expected_code in codes))

        positive("T-CORR-15", representative=False)
        positive("T-CORR-16", representative=True)

        same_packet_root = workspace / "T-CORR-SAME-PACKET"
        build(same_packet_root, representative=True)
        mutate(
            same_packet_root / "05_Literature/PACKETS/MP-20260910-01A-01.yaml",
            lambda value: value.update(
                {
                    "source_search_passes": ["SP-20260910-NEW-01"],
                    "operations": [
                        {
                            "operation_id": "OP-001",
                            "type": "SOURCE_CREATE",
                            "temporary_ref": "SRC-PENDING-new",
                            "payload": {},
                        },
                        {
                            "operation_id": "OP-002",
                            "type": "EVIDENCE_ADD",
                            "source_ref": "SRC-PENDING-new",
                            "payload": {},
                        },
                        {
                            "operation_id": "OP-003",
                            "type": "SOURCE_CREATE",
                            "payload": {"source_id": "SRC-000002"},
                        },
                        {
                            "operation_id": "OP-004",
                            "type": "EVIDENCE_ADD",
                            "source_ref": "SRC-000002",
                            "payload": {},
                        },
                        {
                            "operation_id": "OP-005",
                            "type": "GAP_CREATE",
                            "payload": {"gap_id": "GAP-000002"},
                        },
                        {
                            "operation_id": "OP-006",
                            "type": "GAP_UPDATE",
                            "gap_id": "GAP-000002",
                            "payload": {},
                        },
                        {
                            "operation_id": "OP-007",
                            "type": "SEARCH_PASS_ADD",
                            "payload": {"search_pass_id": "SP-20260910-NEW-01"},
                        },
                    ],
                }
            ),
        )
        results.append(
            ("T-CORR-SAME-PACKET", not Validator(same_packet_root).run())
        )

        negative(
            "T-CORR-01",
            lambda root: mutate(
                root / "05_Literature/SOURCE_REGISTRY.yaml",
                lambda value: value["sources"]["SRC-000001"].update(
                    {"evidence_record": "EVIDENCE/../../README.md"}
                ),
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-02",
            lambda root: mutate(
                root / "05_Literature/SOURCE_REGISTRY.yaml",
                lambda value: value["sources"]["SRC-000001"].update(
                    {"evidence_record": "EVIDENCE/SRC-000002.yaml"}
                ),
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )

        def replace_evidence_with_escaping_symlink(root: Path) -> None:
            target = root / "outside-evidence.yaml"
            target.write_text("source_id: SRC-000001\n", encoding="utf-8")
            evidence = root / "05_Literature/EVIDENCE/SRC-000001.yaml"
            evidence.unlink()
            evidence.symlink_to(target)

        negative(
            "T-CORR-SYMLINK",
            replace_evidence_with_escaping_symlink,
            "MATERIALIZATION_SCHEMA_FAILURE",
        )

        def replace_evidence_directory_with_escaping_symlink(root: Path) -> None:
            evidence = root / "05_Literature/EVIDENCE"
            external = workspace / "T-CORR-17-external-evidence"
            external.mkdir()
            shutil.copy2(evidence / "SRC-000001.yaml", external / "SRC-000001.yaml")
            shutil.rmtree(evidence)
            evidence.symlink_to(external, target_is_directory=True)

        negative(
            "T-CORR-17",
            replace_evidence_directory_with_escaping_symlink,
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-03",
            lambda root: mutate(
                root / "05_Literature/SOURCE_REGISTRY.yaml",
                lambda value: value["sources"]["SRC-000001"].pop("citation_key"),
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-04",
            lambda root: mutate(
                root / "05_Literature/SOURCE_REGISTRY.yaml",
                lambda value: value["sources"]["SRC-000001"].update(
                    {"workflow_state": "HOLD", "hold_scope": None}
                ),
            ),
            "INVALID_WORKFLOW_STATE",
        )
        negative(
            "T-CORR-05",
            lambda root: mutate(
                root / "05_Literature/SOURCE_REGISTRY.yaml",
                lambda value: value["sources"]["SRC-000001"].update(
                    {"hold_scope": "provenance"}
                ),
            ),
            "INVALID_WORKFLOW_STATE",
        )

        def packet_mutator(callback: Any) -> Any:
            return lambda root: mutate(
                root / "05_Literature/PACKETS/MP-20260910-01A-01.yaml",
                callback,
            )

        negative(
            "T-CORR-06",
            packet_mutator(
                lambda value: value["operations"].append(
                    {
                        "operation_id": "OP-003",
                        "type": "EVIDENCE_ADD",
                        "source_ref": "SRC-PENDING-undefined",
                        "payload": {},
                    }
                )
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-07",
            packet_mutator(
                lambda value: value["operations"].extend(
                    [
                        {
                            "operation_id": "OP-003",
                            "type": "SOURCE_CREATE",
                            "temporary_ref": "SRC-PENDING-duplicate",
                            "payload": {},
                        },
                        {
                            "operation_id": "OP-004",
                            "type": "SOURCE_CREATE",
                            "temporary_ref": "SRC-PENDING-duplicate",
                            "payload": {},
                        },
                    ]
                )
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-08",
            packet_mutator(
                lambda value: value["operations"].append(
                    {
                        "operation_id": "OP-003",
                        "type": "SOURCE_UPDATE",
                        "source_ref": "SRC-999999",
                        "payload": {},
                    }
                )
            ),
            "EVIDENCE_REFERENCE_DANGLING",
        )
        negative(
            "T-CORR-09",
            packet_mutator(
                lambda value: value["operations"].append(
                    {
                        "operation_id": "OP-003",
                        "type": "GAP_UPDATE",
                        "gap_id": "GAP-999999",
                        "payload": {},
                    }
                )
            ),
            "INVALID_GAP_STATUS",
        )
        negative(
            "T-CORR-10",
            packet_mutator(
                lambda value: value.update(
                    {"source_search_passes": ["SP-20260910-TEST-99"]}
                )
            ),
            "INVALID_SEARCH_PASS_ID",
        )
        negative(
            "T-CORR-11",
            lambda root: mutate(
                root / "05_Literature/SCHEMA_V1.yaml",
                lambda value: value["enumerations"]["evidence_category"].append("OBSERVED"),
            ),
            "STOP_SCHEMA_DIVERGENCE",
        )
        negative(
            "T-CORR-12",
            lambda root: mutate(
                root / "05_Literature/SCHEMA_V1.yaml",
                lambda value: value["id_patterns"].update(
                    {"SOURCE_ID": "^SRC-.+$"}
                ),
            ),
            "STOP_SCHEMA_DIVERGENCE",
        )
        negative(
            "T-CORR-13",
            lambda root: mutate(
                root / "05_Literature/SCHEMA_V1.yaml",
                lambda value: value["branches"].update({"B01": "changed"}),
            ),
            "STOP_SCHEMA_DIVERGENCE",
        )
        negative(
            "T-CORR-14",
            lambda root: mutate(
                root / "05_Literature/EVIDENCE/SRC-000001.yaml",
                lambda value: value["evidence"][0].update(
                    {"evidence_id": "EV-SRC000002-001"}
                ),
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-CEF",
            lambda root: mutate(
                root / "05_Literature/EVIDENCE/SRC-000001.yaml",
                lambda value: value.update({"cef": {"B_lm": [{"value": 0.0}]}}),
            ),
            "CEF_PARAMETER_CONTEXT_INCOMPLETE",
        )
        negative(
            "T-CORR-PACKET-DUPLICATE-OP",
            packet_mutator(
                lambda value: value["operations"].append(
                    {
                        "operation_id": "OP-001",
                        "type": "SOURCE_UPDATE",
                        "source_ref": "SRC-000001",
                        "payload": {},
                    }
                )
            ),
            "MATERIALIZATION_SCHEMA_FAILURE",
        )
        negative(
            "T-CORR-PACKET-ID",
            packet_mutator(lambda value: value.update({"packet_id": "BAD"})),
            "INVALID_PACKET_ID",
        )

        passed = all(result for _, result in results)
        print("LITERATURE_VALIDATOR_SELFTEST")
        for name, result in results:
            print(f"{name}={'PASS' if result else 'FAIL'}")
        print(f"status={'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="run deterministic temporary-fixture selftest")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository_root = Path(__file__).resolve().parents[2]
    if args.selftest:
        return selftest(repository_root)
    return print_result(Validator(repository_root).run())


if __name__ == "__main__":
    raise SystemExit(main())
