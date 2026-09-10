#!/usr/bin/env python3
"""Offline validator for the LIT-INFRA-SCHEMA-SPEC v1.0 foundation."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


SPECIFICATION_ID = "LIT-INFRA-SCHEMA-SPEC"
SPECIFICATION_VERSION = "1.0"
SPECIFICATION_PATH = "03_Protocols/LITERATURE_KNOWLEDGE_SCHEMA_V1_0.md"
SCHEMA_VERSION = "1.0"


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
        for name in (
            "SOURCE_ID", "GAP_ID", "SEARCH_PASS_ID", "EDGE_ID",
            "WORK_FAMILY_ID", "PACKET_ID", "EVIDENCE_ID", "PENDING_SOURCE_ID",
        ):
            expression = raw_patterns.get(name)
            try:
                self.patterns[name] = re.compile(expression)
            except (TypeError, re.error):
                self.add("STOP_SCHEMA_DIVERGENCE", path, name, "missing or invalid ID pattern")

        raw_enums = self.mapping(value.get("enumerations"))
        required_enums = (
            "record_status", "bibliographic_status", "primary_source_status",
            "full_text_status", "zotero_link_status", "workflow_state", "hold_scope",
            "evidence_category", "evidence_review_state", "gap_status", "gap_importance",
            "relation_type", "evidence_independence", "work_version_role", "search_mode",
            "search_result_state", "branch_saturation_state", "packet_operation_type",
        )
        for name in required_enums:
            values = raw_enums.get(name)
            if not isinstance(values, list) or not values or not all(isinstance(x, str) for x in values):
                self.add("STOP_SCHEMA_DIVERGENCE", path, name, "missing or invalid enumeration")
                self.enums[name] = set()
            else:
                self.enums[name] = set(values)

        branches = self.mapping(value.get("branches"))
        expected_branches = {f"B{i:02d}" for i in range(1, 17)}
        if set(branches) != expected_branches:
            self.add("STOP_SCHEMA_DIVERGENCE", path, "", "schema must define exactly B01-B16")

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
                    target = self.root / "05_Literature" / evidence_record
                    if not target.is_file():
                        self.add("EVIDENCE_REFERENCE_DANGLING", path, source_id, f"missing {evidence_record}")

        self.reject_pending(document, path)

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
        self.reject_pending(document, path)

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
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.yaml")):
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
            self.reject_pending(document, path)

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
                self.validate_packet_references(operation, path, str(operation_id or packet_id or ""))

    def validate_packet_references(self, operation: dict[str, Any], path: Path, operation_id: str) -> None:
        reference_keys = {
            "source_id", "source_ref", "from_source", "to_source",
            "merged_into", "current_evidence",
        }

        def walk(node: Any, key: str = "") -> None:
            if isinstance(node, dict):
                for child_key, child in node.items():
                    walk(child, str(child_key))
            elif isinstance(node, list):
                for child in node:
                    walk(child, key)
            elif key in reference_keys and isinstance(node, str) and node.startswith("SRC-"):
                if node.startswith("SRC-PENDING-"):
                    if not self.patterns["PENDING_SOURCE_ID"].fullmatch(node):
                        self.add("INVALID_SOURCE_ID", path, operation_id, f"invalid pending source reference {node}")
                elif node not in self.sources:
                    self.add("EVIDENCE_REFERENCE_DANGLING", path, operation_id, f"unresolved source reference {node}")

        walk(operation)

    def run(self) -> list[Issue]:
        self.validate_schema()
        if not self.schema:
            return sorted(set(self.issues))
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
        root = Path(temporary)
        (root / "05_Literature/SEARCH_LOG").mkdir(parents=True)
        shutil.copy2(
            repository_root / "05_Literature/SCHEMA_V1.yaml",
            root / "05_Literature/SCHEMA_V1.yaml",
        )
        shutil.copy2(
            repository_root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml",
            root / "05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml",
        )
        (root / "05_Literature/SOURCE_REGISTRY.yaml").write_text(
            'schema_version: "1.0"\nsources: {}\n',
            encoding="utf-8",
        )
        (root / "05_Literature/GAPS.yaml").write_text(
            'schema_version: "1.0"\ngaps: {}\n',
            encoding="utf-8",
        )
        positive = Validator(root).run()
        (root / "05_Literature/SOURCE_REGISTRY.yaml").write_text(
            'schema_version: "1.0"\nsources:\n  BAD-ID: {}\n',
            encoding="utf-8",
        )
        negative = Validator(root).run()
        negative_codes = {issue.failure_code for issue in negative}
        passed = not positive and "INVALID_SOURCE_ID" in negative_codes
        print("LITERATURE_VALIDATOR_SELFTEST")
        print("positive_empty_foundation=PASS" if not positive else "positive_empty_foundation=FAIL")
        print(
            "negative_invalid_source_id=PASS"
            if "INVALID_SOURCE_ID" in negative_codes
            else "negative_invalid_source_id=FAIL"
        )
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
