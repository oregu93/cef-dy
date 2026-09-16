#!/usr/bin/env python3
"""Validate the frozen Scientific Understanding v1.0 structural contract.

This validator deliberately does not adjudicate scientific truth.  The
canonical corpus directory may be absent until a separately authorized pilot.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
import tempfile
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_REL = Path("06_Scientific_Understanding")

SU_RE = re.compile(r"^SU-[0-9]{6}$")
SRC_RE = re.compile(r"^SRC-[0-9]{6}$")
EV_SRC_RE = re.compile(r"^EV-SRC[0-9]{6}-[0-9]{3,}$")
EV_RE = re.compile(r"^EV-[A-Za-z0-9][A-Za-z0-9._-]*$")
R_RE = re.compile(r"^R-[0-9]{3}$")
H_RE = re.compile(r"^H-[0-9]{3}$")
D_RE = re.compile(r"^D-[0-9]{3}$")
MOD_RE = re.compile(r"^MOD-[A-Z0-9][A-Za-z0-9._-]*$")
NAMED_ARTIFACT_RE = re.compile(r"^[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+$")
REPO_ARTIFACT_RE = re.compile(
    r"^(?:02_Work_Checkpoints|03_Protocols|04_Results)/[A-Za-z0-9_./-]+$"
)

KNOWLEDGE_KINDS = {"concept", "method_explanation", "derivation"}
REVIEW_STATUSES = {"working", "reviewed", "superseded"}
EPISTEMIC_BASES = {
    "GENERAL_OR_TEXTBOOK",
    "LITERATURE_SUPPORTED",
    "PROJECT_DERIVED",
    "PROJECT_ASSUMPTION",
    "OPEN_OR_CONTESTED",
}
SCOPE_LEVELS = {
    "GENERAL_PHYSICS",
    "METHOD_CLASS",
    "RFEO3_FAMILY",
    "RARE_EARTH_CLASS",
    "COMPOUND_SPECIFIC",
    "EXPERIMENT_SPECIFIC",
}
TRANSFER_STATUSES = {"GENERAL", "CONDITIONAL", "BOUND_TO_SCOPE", "NOT_ASSESSED"}
KRAMERS_FACETS = {"ANY", "KRAMERS", "NON_KRAMERS", "UNKNOWN", "NOT_APPLICABLE"}
MAGNETIC_FACETS = {"ANY", "ORDERED", "DISORDERED", "UNKNOWN", "NOT_APPLICABLE"}
EXCHANGE_FACETS = {"ANY", "INCLUDED", "NEGLECTED", "UNKNOWN", "NOT_APPLICABLE"}
RELATION_KEYS = {
    "depends_on",
    "specializes",
    "contrasts_with",
    "derived_from",
    "project_examples",
    "related_concepts",
}
SU_RELATIONS = {"depends_on", "specializes", "contrasts_with", "related_concepts"}
CONVENTION_STATUSES = {"EXPLICIT", "UNRESOLVED", "NOT_APPLICABLE"}
DISSERTATION_ROLES = {
    "theoretical_background",
    "literature_review",
    "experimental_methods",
    "analysis_methodology",
    "results_interpretation",
    "defense_preparation",
}
ORIGIN_TYPES = {"chat", "archive"}
REQUIRED_FIELDS = {
    "id",
    "title",
    "knowledge_kind",
    "review_status",
    "epistemic_basis",
    "scope",
    "transferability",
    "relations",
    "sources",
    "convention_refs",
    "common_confusions",
    "dissertation_roles",
}


class Validator:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.corpus = self.root / CORPUS_REL
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: dict[str, tuple[Path, dict]] = {}
        self.source_ids: set[str] = set()
        self.evidence: dict[str, dict] = {}

    def error(self, path: Path | str, code: str, detail: str) -> None:
        try:
            shown = Path(path).resolve().relative_to(self.root).as_posix()
        except Exception:
            shown = str(path)
        self.errors.append(f"{code}: {shown}: {detail}")

    def load_yaml(self, path: Path):
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.error(path, "YAML_PARSE_ERROR", str(exc))
            return None

    def load_indexes(self) -> None:
        registry_path = self.root / "05_Literature" / "SOURCE_REGISTRY.yaml"
        if registry_path.exists():
            registry = self.load_yaml(registry_path)
            if isinstance(registry, dict) and isinstance(registry.get("sources"), dict):
                self.source_ids = set(registry["sources"])

        evidence_dir = self.root / "05_Literature" / "EVIDENCE"
        if evidence_dir.exists():
            for path in sorted(evidence_dir.glob("*.yaml")):
                document = self.load_yaml(path)
                if not isinstance(document, dict):
                    continue
                items = document.get("evidence", [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and isinstance(item.get("evidence_id"), str):
                        self.evidence[item["evidence_id"]] = item

    @staticmethod
    def parse_front_matter(path: Path) -> dict | None:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("Markdown file must start with YAML front matter")
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        except StopIteration as exc:
            raise ValueError("YAML front matter is not closed") from exc
        data = yaml.safe_load("\n".join(lines[1:end]))
        if not isinstance(data, dict):
            raise ValueError("YAML front matter must be a mapping")
        return data

    def load_notes(self) -> None:
        if not self.corpus.exists():
            return
        if not self.corpus.is_dir():
            self.error(self.corpus, "CORPUS_PATH_INVALID", "must be a directory")
            return
        for path in sorted(self.corpus.rglob("*.md")):
            try:
                note = self.parse_front_matter(path)
            except Exception as exc:
                self.error(path, "FRONT_MATTER_INVALID", str(exc))
                continue
            note_id = note.get("id")
            key = str(note_id)
            if key in self.notes:
                self.error(path, "SU_ID_UNIQUE", f"duplicate {key}")
            else:
                self.notes[key] = (path, note)

    def require_mapping(self, value, path: Path, code: str, field: str) -> dict:
        if not isinstance(value, dict):
            self.error(path, code, f"{field} must be a mapping")
            return {}
        return value

    def require_list(self, value, path: Path, code: str, field: str) -> list:
        if not isinstance(value, list):
            self.error(path, code, f"{field} must be a list")
            return []
        return value

    def enum(self, value, allowed: set[str], path: Path, code: str, field: str) -> None:
        if value not in allowed:
            self.error(path, code, f"{field}={value!r}; allowed={sorted(allowed)}")

    @staticmethod
    def epistemic_values(block: dict) -> list[str]:
        values = [block.get("primary")]
        additional = block.get("additional", [])
        if isinstance(additional, list):
            values.extend(additional)
        return values

    @staticmethod
    def project_ref_valid(value: str) -> bool:
        if SU_RE.fullmatch(value) or SRC_RE.fullmatch(value):
            return False
        return any(
            pattern.fullmatch(value)
            for pattern in (EV_RE, R_RE, H_RE, MOD_RE, D_RE, NAMED_ARTIFACT_RE, REPO_ARTIFACT_RE)
        )

    def validate_note(self, note_id: str, path: Path, note: dict) -> None:
        missing = sorted(REQUIRED_FIELDS - set(note))
        if missing:
            self.error(path, "REQUIRED_FIELD_MISSING", ", ".join(missing))

        if not isinstance(note.get("id"), str) or not SU_RE.fullmatch(note["id"]):
            self.error(path, "SU_ID_VALID", f"invalid id {note.get('id')!r}")
        if not isinstance(note.get("title"), str) or not note["title"].strip():
            self.error(path, "TITLE_VALID", "title must be a nonempty string")

        self.enum(note.get("knowledge_kind"), KNOWLEDGE_KINDS, path, "KNOWLEDGE_KIND_VALID", "knowledge_kind")
        review = note.get("review_status")
        self.enum(review, REVIEW_STATUSES, path, "REVIEW_STATUS_VALID", "review_status")

        if review == "superseded":
            target = note.get("superseded_by")
            if not isinstance(target, str) or not SU_RE.fullmatch(target):
                self.error(path, "SUPERSEDED_REQUIRES_TARGET", "superseded_by must be a valid SU ID")
            elif target == note_id or target not in self.notes:
                self.error(path, "SUPERSEDED_TARGET_RESOLVES", f"unresolved/self target {target}")

        basis = self.require_mapping(note.get("epistemic_basis"), path, "EPISTEMIC_BASIS_VALID", "epistemic_basis")
        primary = basis.get("primary")
        additional = self.require_list(basis.get("additional", []), path, "EPISTEMIC_BASIS_VALID", "epistemic_basis.additional")
        values = [primary] + additional
        for value in values:
            self.enum(value, EPISTEMIC_BASES, path, "EPISTEMIC_BASIS_VALID", "epistemic_basis")
        if len(values) != len(set(values)):
            self.error(path, "EPISTEMIC_BASIS_VALID", "basis values must be unique")

        scope = self.require_mapping(note.get("scope"), path, "SCOPE_LEVEL_VALID", "scope")
        level = scope.get("level")
        self.enum(level, SCOPE_LEVELS, path, "SCOPE_LEVEL_VALID", "scope.level")
        if level == "METHOD_CLASS" and not scope.get("method_classes"):
            self.error(path, "SCOPE_CONDITIONAL_FIELDS_VALID", "METHOD_CLASS requires method_classes")
        if level == "COMPOUND_SPECIFIC" and not scope.get("compounds"):
            self.error(path, "SCOPE_CONDITIONAL_FIELDS_VALID", "COMPOUND_SPECIFIC requires compounds")

        transfer = self.require_mapping(note.get("transferability"), path, "TRANSFERABILITY_STATUS_VALID", "transferability")
        self.enum(transfer.get("status"), TRANSFER_STATUSES, path, "TRANSFERABILITY_STATUS_VALID", "transferability.status")
        self.require_list(transfer.get("conditions", []), path, "TRANSFERABILITY_STATUS_VALID", "transferability.conditions")
        self.require_list(transfer.get("exclusions", []), path, "TRANSFERABILITY_STATUS_VALID", "transferability.exclusions")
        facets = self.require_mapping(transfer.get("facets"), path, "TRANSFERABILITY_FACETS_VALID", "transferability.facets")
        self.enum(facets.get("kramers_class"), KRAMERS_FACETS, path, "KRAMERS_FACET_VALID", "kramers_class")
        self.enum(facets.get("magnetic_order"), MAGNETIC_FACETS, path, "MAGNETIC_ORDER_FACET_VALID", "magnetic_order")
        self.enum(facets.get("exchange_treatment"), EXCHANGE_FACETS, path, "EXCHANGE_TREATMENT_FACET_VALID", "exchange_treatment")

        relations = self.require_mapping(note.get("relations"), path, "RELATIONS_VALID", "relations")
        unknown_relations = set(relations) - RELATION_KEYS
        if unknown_relations:
            self.error(path, "NO_MANUAL_GENERALIZES_TO", f"unsupported relations {sorted(unknown_relations)}")
        for relation in RELATION_KEYS:
            targets = self.require_list(relations.get(relation), path, "RELATIONS_VALID", f"relations.{relation}")
            if len(targets) != len(set(map(str, targets))):
                self.error(path, "NO_DUPLICATE_RELATION_ENTRY", relation)
            for target in targets:
                if not isinstance(target, str):
                    self.error(path, "RELATION_TARGET_CLASS_VALID", f"{relation} target must be string")
                    continue
                if relation in SU_RELATIONS:
                    if not SU_RE.fullmatch(target):
                        self.error(path, "RELATION_TARGET_CLASS_VALID", f"{relation}: {target}")
                    elif target not in self.notes:
                        self.error(path, "RELATION_TARGET_RESOLVES", f"{relation}: {target}")
                elif relation == "derived_from":
                    if not (SU_RE.fullmatch(target) or self.project_ref_valid(target)):
                        self.error(path, "RELATION_TARGET_CLASS_VALID", f"derived_from: {target}")
                    elif SU_RE.fullmatch(target) and target not in self.notes:
                        self.error(path, "RELATION_TARGET_RESOLVES", f"derived_from: {target}")
                elif relation == "project_examples" and not self.project_ref_valid(target):
                    self.error(path, "RELATION_TARGET_CLASS_VALID", f"project_examples: {target}")
            if relation == "depends_on" and note_id in targets:
                self.error(path, "NO_SELF_DEPENDENCY", note_id)
            if relation == "specializes" and note_id in targets:
                self.error(path, "NO_SELF_SPECIALIZATION", note_id)

        derived = relations.get("derived_from", []) if isinstance(relations.get("derived_from"), list) else []
        if "PROJECT_DERIVED" in values and not derived:
            self.error(path, "PROJECT_DERIVED_REQUIRES_PROVENANCE", "derived_from is empty")
        if any(isinstance(x, str) and (H_RE.fullmatch(x) or MOD_RE.fullmatch(x)) for x in derived):
            if "PROJECT_ASSUMPTION" not in values:
                self.error(path, "PROJECT_ASSUMPTION_PRESERVED", "H/MOD provenance requires PROJECT_ASSUMPTION")
        if "PROJECT_ASSUMPTION" in values:
            assumption_refs = [
                x for x in derived
                if isinstance(x, str)
                and (
                    H_RE.fullmatch(x)
                    or MOD_RE.fullmatch(x)
                    or D_RE.fullmatch(x)
                    or "SPEC" in x
                )
            ]
            if not assumption_refs:
                self.error(
                    path,
                    "PROJECT_ASSUMPTION_REQUIRES_PROVENANCE",
                    "explicit H/MOD/D/specification provenance required",
                )

        sources = self.require_mapping(note.get("sources"), path, "SOURCE_REFERENCE_VALID", "sources")
        background = self.require_list(sources.get("background"), path, "SOURCE_REFERENCE_VALID", "sources.background")
        support = self.require_list(sources.get("claim_support"), path, "SOURCE_REFERENCE_VALID", "sources.claim_support")
        for source_id in background:
            if not isinstance(source_id, str) or not SRC_RE.fullmatch(source_id):
                self.error(path, "SOURCE_REFERENCE_VALID", f"invalid background {source_id!r}")
            elif source_id not in self.source_ids:
                self.error(path, "SOURCE_REFERENCE_RESOLVES", f"unresolved {source_id}")
        for evidence_id in support:
            if not isinstance(evidence_id, str) or not EV_SRC_RE.fullmatch(evidence_id):
                self.error(path, "SOURCE_REFERENCE_VALID", f"invalid claim_support {evidence_id!r}")
            elif evidence_id not in self.evidence:
                self.error(path, "SOURCE_REFERENCE_RESOLVES", f"unresolved {evidence_id}")
        if review == "reviewed" and "LITERATURE_SUPPORTED" in values:
            if not any(self.evidence.get(item, {}).get("review_state") == "reviewed_01" for item in support):
                self.error(path, "LITERATURE_REVIEWED_GATE", "reviewed_01 EV-SRC support required")

        if values == ["GENERAL_OR_TEXTBOOK"] and level in {"COMPOUND_SPECIFIC", "EXPERIMENT_SPECIFIC"}:
            self.error(path, "GENERAL_TEXTBOOK_SCOPE_GATE", f"basis incompatible with {level}")
        if level == "EXPERIMENT_SPECIFIC":
            experiment_classes = scope.get("experiment_classes", [])
            project_refs = [x for x in derived if isinstance(x, str) and self.project_ref_valid(x)]
            if not experiment_classes and not project_refs:
                self.error(path, "SCOPE_CONDITIONAL_FIELDS_VALID", "EXPERIMENT_SPECIFIC requires experiment class/reference")

        refs = self.require_list(note.get("convention_refs"), path, "CONVENTION_BINDING_VALID", "convention_refs")
        for ref in refs:
            if not isinstance(ref, str) or Path(ref).is_absolute() or ".." in Path(ref).parts:
                self.error(path, "CONVENTION_BINDING_VALID", f"unsafe convention ref {ref!r}")
                continue
            if ref:
                try:
                    resolved = (self.root / ref).resolve(strict=True)
                    resolved.relative_to(self.root)
                except (FileNotFoundError, RuntimeError, ValueError):
                    self.error(path, "CONVENTION_REF_RESOLVES", f"unresolved/outside repository {ref!r}")
        binding = note.get("convention_binding")
        if binding is not None:
            binding = self.require_mapping(binding, path, "CONVENTION_BINDING_VALID", "convention_binding")
            status = binding.get("status")
            self.enum(status, CONVENTION_STATUSES, path, "CONVENTION_BINDING_STATUS_VALID", "convention_binding.status")
            site = binding.get("site") if isinstance(binding.get("site"), dict) else {}
            details = [
                binding.get("crystallographic_setting"),
                binding.get("origin_choice"),
                binding.get("global_frame"),
                binding.get("local_frame"),
                site.get("species"), site.get("wyckoff"), site.get("site_symmetry"),
            ]
            nonempty = any(value not in (None, "", [], {}) for value in details)
            if status == "EXPLICIT" and (not refs or not nonempty):
                self.error(path, "CONVENTION_BINDING_VALID", "EXPLICIT requires refs and active detail")
            if status == "UNRESOLVED" and transfer.get("status") == "GENERAL":
                self.error(path, "CONVENTION_BINDING_VALID", "UNRESOLVED cannot be GENERAL")
            if status == "NOT_APPLICABLE" and nonempty:
                self.error(path, "CONVENTION_BINDING_VALID", "NOT_APPLICABLE requires empty details")

        self.require_list(note.get("common_confusions"), path, "COMMON_CONFUSIONS_VALID", "common_confusions")
        roles = self.require_list(note.get("dissertation_roles"), path, "DISSERTATION_ROLE_VALID", "dissertation_roles")
        for role in roles:
            self.enum(role, DISSERTATION_ROLES, path, "DISSERTATION_ROLE_VALID", "dissertation_roles")

        origin = note.get("origin_trail", [])
        for item in self.require_list(origin, path, "ORIGIN_TRAIL_VALID", "origin_trail"):
            if not isinstance(item, dict) or item.get("source_type") not in ORIGIN_TYPES or not item.get("locator"):
                self.error(path, "ORIGIN_TRAIL_VALID", f"invalid entry {item!r}")

    def validate_cycles(self, relation: str, code: str) -> None:
        graph: dict[str, list[str]] = {}
        for note_id, (_, note) in self.notes.items():
            rel = note.get("relations", {})
            graph[note_id] = [x for x in rel.get(relation, []) if isinstance(x, str) and x in self.notes]
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str, stack: list[str]) -> None:
            if node in visiting:
                cycle = stack[stack.index(node):] + [node]
                path = self.notes[node][0]
                self.error(path, code, " -> ".join(cycle))
                return
            if node in visited:
                return
            visiting.add(node)
            stack.append(node)
            for target in graph.get(node, []):
                visit(target, stack)
            stack.pop()
            visiting.remove(node)
            visited.add(node)

        for node in sorted(graph):
            visit(node, [])

    def run(self) -> bool:
        self.load_indexes()
        self.load_notes()
        for note_id, (path, note) in sorted(self.notes.items()):
            self.validate_note(note_id, path, note)
        self.validate_cycles("depends_on", "NO_DEPENDENCY_CYCLE")
        self.validate_cycles("specializes", "NO_SPECIALIZATION_CYCLE")
        return not self.errors

    def report(self) -> str:
        lines = [
            "SCIENTIFIC_UNDERSTANDING_VALIDATION",
            f"notes={len(self.notes)}",
            f"errors={len(self.errors)}",
            f"warnings={len(self.warnings)}",
        ]
        lines.extend(f"ERROR {item}" for item in self.errors)
        lines.extend(f"WARNING {item}" for item in self.warnings)
        lines.append(f"status={'PASS' if not self.errors else 'FAIL'}")
        return "\n".join(lines)


def valid_note(note_id: str = "SU-900001") -> dict:
    return {
        "id": note_id,
        "title": "Synthetic structural fixture",
        "knowledge_kind": "concept",
        "review_status": "working",
        "epistemic_basis": {"primary": "GENERAL_OR_TEXTBOOK", "additional": []},
        "scope": {"level": "GENERAL_PHYSICS"},
        "transferability": {
            "status": "GENERAL",
            "conditions": [],
            "exclusions": [],
            "facets": {
                "kramers_class": "NOT_APPLICABLE",
                "magnetic_order": "NOT_APPLICABLE",
                "exchange_treatment": "NOT_APPLICABLE",
                "temperature_regime": None,
                "field_regime": None,
            },
        },
        "relations": {key: [] for key in sorted(RELATION_KEYS)},
        "sources": {"background": [], "claim_support": []},
        "convention_refs": [],
        "common_confusions": [],
        "dissertation_roles": [],
    }


def write_note(root: Path, name: str, note: dict) -> None:
    path = root / CORPUS_REL / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(note, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{body}---\n\n# Synthetic fixture\n", encoding="utf-8")


def run_fixture(notes: list[dict], evidence_state: str | None = None) -> Validator:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    (root / "05_Literature" / "EVIDENCE").mkdir(parents=True)
    (root / "05_Literature" / "SOURCE_REGISTRY.yaml").write_text(
        'schema_version: "1.0"\nsources:\n  SRC-900001: {}\n', encoding="utf-8"
    )
    (root / "03_Protocols").mkdir(parents=True)
    (root / "03_Protocols" / "SCIENTIFIC_TERMINOLOGY.md").write_text(
        "# Synthetic convention fixture\n", encoding="utf-8"
    )
    if evidence_state:
        (root / "05_Literature" / "EVIDENCE" / "SRC-900001.yaml").write_text(
            yaml.safe_dump({"evidence": [{"evidence_id": "EV-SRC900001-001", "review_state": evidence_state}]}),
            encoding="utf-8",
        )
    for index, note in enumerate(notes):
        write_note(root, f"fixture-{index}.md", note)
    validator = Validator(root)
    validator.run()
    validator._temporary = temporary  # retain directory through assertions
    return validator


def selftest() -> bool:
    tests = 0

    def expect(notes: list[dict], ok: bool, code: str | None = None, evidence_state: str | None = None):
        nonlocal tests
        tests += 1
        result = run_fixture(notes, evidence_state)
        assert (not result.errors) is ok, result.report()
        if code:
            assert any(item.startswith(code + ":") for item in result.errors), result.report()

    expect([valid_note()], True)

    reviewed = valid_note()
    reviewed["review_status"] = "reviewed"
    reviewed["epistemic_basis"] = {"primary": "LITERATURE_SUPPORTED", "additional": []}
    reviewed["sources"]["background"] = ["SRC-900001"]
    reviewed["sources"]["claim_support"] = ["EV-SRC900001-001"]
    expect([reviewed], True, evidence_state="reviewed_01")
    expect([reviewed], False, "LITERATURE_REVIEWED_GATE", "preliminary_01A")

    bad = valid_note(); bad["id"] = "SU-1"
    expect([bad], False, "SU_ID_VALID")
    first = valid_note("SU-900001"); duplicate = valid_note("SU-900001")
    expect([first, duplicate], False, "SU_ID_UNIQUE")
    bad = valid_note(); bad["knowledge_kind"] = "principle"
    expect([bad], False, "KNOWLEDGE_KIND_VALID")
    bad = valid_note(); bad["review_status"] = "validated"
    expect([bad], False, "REVIEW_STATUS_VALID")
    bad = valid_note(); bad["epistemic_basis"]["primary"] = "FACT"
    expect([bad], False, "EPISTEMIC_BASIS_VALID")
    bad = valid_note(); bad["relations"]["depends_on"] = [bad["id"]]
    expect([bad], False, "NO_SELF_DEPENDENCY")
    bad = valid_note(); bad["relations"]["specializes"] = [bad["id"]]
    expect([bad], False, "NO_SELF_SPECIALIZATION")
    bad = valid_note(); bad["relations"]["depends_on"] = ["SU-900002"]
    expect([bad], False, "RELATION_TARGET_RESOLVES")
    first = valid_note("SU-900001"); second = valid_note("SU-900002"); first["relations"]["related_concepts"] = [second["id"], second["id"]]
    expect([first, second], False, "NO_DUPLICATE_RELATION_ENTRY")
    bad = valid_note(); bad["relations"]["generalizes_to"] = []
    expect([bad], False, "NO_MANUAL_GENERALIZES_TO")
    bad = valid_note(); bad["relations"]["project_examples"] = ["SU-900002"]
    expect([bad], False, "RELATION_TARGET_CLASS_VALID")
    bad = valid_note(); bad["scope"] = {"level": "METHOD_CLASS"}
    expect([bad], False, "SCOPE_CONDITIONAL_FIELDS_VALID")
    bad = valid_note(); bad["scope"] = {"level": "COMPOUND_SPECIFIC", "compounds": ["DyFeO3"]}
    expect([bad], False, "GENERAL_TEXTBOOK_SCOPE_GATE")
    bad = valid_note(); bad["scope"] = {"level": "EXPERIMENT_SPECIFIC"}; bad["epistemic_basis"] = {"primary": "PROJECT_DERIVED", "additional": []}; bad["relations"]["derived_from"] = ["R-001"]
    expect([bad], True)
    bad = valid_note(); bad["transferability"]["status"] = "UNIVERSAL"
    expect([bad], False, "TRANSFERABILITY_STATUS_VALID")
    bad = valid_note(); bad["transferability"]["facets"]["kramers_class"] = "NONE"
    expect([bad], False, "KRAMERS_FACET_VALID")
    good = valid_note(); good["transferability"]["facets"]["kramers_class"] = "UNKNOWN"; good["transferability"]["facets"]["magnetic_order"] = "NOT_APPLICABLE"
    expect([good], True)
    bad = valid_note(); bad["epistemic_basis"] = {"primary": "PROJECT_DERIVED", "additional": []}
    expect([bad], False, "PROJECT_DERIVED_REQUIRES_PROVENANCE")
    bad = valid_note(); bad["relations"]["derived_from"] = ["MOD-CEF-CS15"]
    expect([bad], False, "PROJECT_ASSUMPTION_PRESERVED")
    bad = valid_note(); bad["epistemic_basis"] = {"primary": "PROJECT_ASSUMPTION", "additional": []}
    expect([bad], False, "PROJECT_ASSUMPTION_REQUIRES_PROVENANCE")
    good = valid_note(); good["epistemic_basis"] = {"primary": "PROJECT_ASSUMPTION", "additional": []}; good["relations"]["derived_from"] = ["H-001"]
    expect([good], True)
    bad = valid_note(); bad["convention_binding"] = {"status": "EXPLICIT"}
    expect([bad], False, "CONVENTION_BINDING_VALID")
    good = valid_note(); good["convention_refs"] = ["03_Protocols/SCIENTIFIC_TERMINOLOGY.md"]; good["convention_binding"] = {"status": "EXPLICIT", "local_frame": "X=b, Y=c, Z=a"}
    expect([good], True)
    bad = valid_note(); bad["convention_refs"] = ["03_Protocols/DOES_NOT_EXIST.md"]
    expect([bad], False, "CONVENTION_REF_RESOLVES")
    bad = valid_note(); bad["convention_binding"] = {"status": "UNRESOLVED"}
    expect([bad], False, "CONVENTION_BINDING_VALID")
    bad = valid_note(); bad["convention_binding"] = {"status": "NOT_APPLICABLE", "local_frame": "X=b"}
    expect([bad], False, "CONVENTION_BINDING_VALID")
    bad = valid_note(); bad["review_status"] = "superseded"
    expect([bad], False, "SUPERSEDED_REQUIRES_TARGET")
    first = valid_note("SU-900001"); first["review_status"] = "superseded"; first["superseded_by"] = "SU-900002"; second = valid_note("SU-900002")
    expect([first, second], True)
    bad = valid_note(); bad["review_status"] = "superseded"; bad["superseded_by"] = "SU-900002"
    expect([bad], False, "SUPERSEDED_TARGET_RESOLVES")
    bad = valid_note(); bad["sources"]["background"] = ["SRC-900001"]
    expect([bad], True)
    bad = valid_note(); bad["sources"]["background"] = ["SRC-999999"]
    expect([bad], False, "SOURCE_REFERENCE_RESOLVES")
    bad = valid_note(); bad["origin_trail"] = [{"source_type": "chat", "locator": "test"}]
    expect([bad], True)
    bad = valid_note(); bad["origin_trail"] = [{"source_type": "memory", "locator": "test"}]
    expect([bad], False, "ORIGIN_TRAIL_VALID")
    bad = valid_note(); bad["dissertation_roles"] = ["chapter_1"]
    expect([bad], False, "DISSERTATION_ROLE_VALID")

    first = valid_note("SU-900001")
    second = valid_note("SU-900002")
    first["relations"]["depends_on"] = [second["id"]]
    second["relations"]["depends_on"] = [first["id"]]
    expect([first, second], False, "NO_DEPENDENCY_CYCLE")

    first = valid_note("SU-900001")
    second = valid_note("SU-900002")
    first["relations"]["specializes"] = [second["id"]]
    second["relations"]["specializes"] = [first["id"]]
    expect([first, second], False, "NO_SPECIALIZATION_CYCLE")

    print(f"SCIENTIFIC_UNDERSTANDING_SELFTEST\ntests={tests}\nfailed=0\nstatus=PASS")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        try:
            selftest()
            return 0
        except Exception as exc:
            print(f"SCIENTIFIC_UNDERSTANDING_SELFTEST\nstatus=FAIL\nerror={exc}")
            return 1
    validator = Validator(args.root)
    validator.run()
    print(validator.report())
    return 0 if not validator.errors else 1


if __name__ == "__main__":
    sys.exit(main())
