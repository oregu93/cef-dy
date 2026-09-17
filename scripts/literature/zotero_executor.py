#!/usr/bin/env python3
"""Offline-only Phase-2 planner for the frozen Zotero integration contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import yaml


SOURCE_ID_RE = re.compile(r"SRC-[0-9]{6}")
DOI_RE = re.compile(r"10\.[0-9]{4,9}/\S+", re.IGNORECASE)
HEX40_RE = re.compile(r"[0-9a-f]{40}")
INTEGER_ID_RE = re.compile(r"[1-9][0-9]*")
ITEM_KEY_RE = re.compile(r"[A-Za-z0-9]{1,64}")

SECRET_KEY_NORMAL_FORMS = {
    "apikey",
    "token",
    "accesstoken",
    "authorization",
    "password",
    "secret",
    "clientsecret",
    "localapikey",
}

BBT_COMPATIBILITY_STATES = {
    "not_verified",
    "verified",
    "incompatible",
    "needs_review",
}


class ExecutorFailure(RuntimeError):
    """Bounded machine-readable failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OperationType(str, Enum):
    ZOTERO_CREATE = "ZOTERO_CREATE"
    ZOTERO_LINK_EXISTING = "ZOTERO_LINK_EXISTING"
    ADD_COLLECTION = "ADD_COLLECTION"
    ADD_TAG = "ADD_TAG"


class LedgerState(str, Enum):
    PENDING = "PENDING"
    DRY_RUN_VALID = "DRY_RUN_VALID"
    EXTERNAL_WRITE_ATTEMPTED = "EXTERNAL_WRITE_ATTEMPTED"
    EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT = "EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT"
    GIT_RECONCILIATION_PREPARED = "GIT_RECONCILIATION_PREPARED"
    GIT_RECONCILED = "GIT_RECONCILED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DuplicateDecision(str, Enum):
    NO_MATCH = "NO_MATCH"
    EXACT_SINGLE_MATCH = "EXACT_SINGLE_MATCH"
    MULTIPLE_EXACT_MATCHES = "MULTIPLE_EXACT_MATCHES"
    FUZZY_ONLY = "FUZZY_ONLY"
    ALREADY_LINKED_SAME = "ALREADY_LINKED_SAME"
    ALREADY_LINKED_DIFFERENT = "ALREADY_LINKED_DIFFERENT"


class ExactIdentityBasis(str, Enum):
    EXACT_DOI = "EXACT_DOI"
    EXACT_STABLE_IDENTIFIER = "EXACT_STABLE_IDENTIFIER"
    KNOWN_ITEM_KEY = "KNOWN_ITEM_KEY"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"


class DecisionState(str, Enum):
    CREATE = "CREATE"
    LINK_EXISTING = "LINK_EXISTING"
    MUTATE_EXISTING = "MUTATE_EXISTING"
    RETRY_ELIGIBLE = "RETRY_ELIGIBLE"
    SAFE_RETRY_CANDIDATE = "SAFE_RETRY_CANDIDATE"
    RECOVER_EXISTING_WRITE = "RECOVER_EXISTING_WRITE"
    SUCCESS_NOOP = "SUCCESS_NOOP"
    NEEDS_REVIEW = "NEEDS_REVIEW"


ALLOWED_LEDGER_TRANSITIONS: frozenset[tuple[LedgerState, LedgerState]] = frozenset(
    {
        (LedgerState.PENDING, LedgerState.DRY_RUN_VALID),
        (LedgerState.PENDING, LedgerState.NEEDS_REVIEW),
        (LedgerState.PENDING, LedgerState.FAILED_TERMINAL),
        (LedgerState.DRY_RUN_VALID, LedgerState.EXTERNAL_WRITE_ATTEMPTED),
        (LedgerState.DRY_RUN_VALID, LedgerState.FAILED_TERMINAL),
        (
            LedgerState.EXTERNAL_WRITE_ATTEMPTED,
            LedgerState.EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT,
        ),
        (LedgerState.EXTERNAL_WRITE_ATTEMPTED, LedgerState.FAILED_RETRYABLE),
        (LedgerState.EXTERNAL_WRITE_ATTEMPTED, LedgerState.NEEDS_REVIEW),
        (LedgerState.FAILED_RETRYABLE, LedgerState.DRY_RUN_VALID),
        (LedgerState.FAILED_RETRYABLE, LedgerState.NEEDS_REVIEW),
        (LedgerState.FAILED_RETRYABLE, LedgerState.FAILED_TERMINAL),
        (
            LedgerState.EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT,
            LedgerState.GIT_RECONCILIATION_PREPARED,
        ),
        (LedgerState.GIT_RECONCILIATION_PREPARED, LedgerState.GIT_RECONCILED),
        (
            LedgerState.GIT_RECONCILIATION_PREPARED,
            LedgerState.EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT,
        ),
    }
)


def fail(code: str, message: str) -> None:
    raise ExecutorFailure(code, message)


def _secret_key_form(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def reject_secret_keys(value: Any, location: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                fail("CONFIG_INVALID", f"{location} contains a non-string key")
            if _secret_key_form(key) in SECRET_KEY_NORMAL_FORMS:
                fail("CONFIG_INVALID", f"{location} contains forbidden secret-like key {key!r}")
            reject_secret_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secret_keys(child, f"{location}[{index}]")


def normalize_semantic_value(value: Any) -> Any:
    """Return JSON-safe semantic data with deterministic recursive mappings."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            fail("REQUEST_INVALID", "non-finite numeric payload values are forbidden")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                fail("REQUEST_INVALID", "semantic payload mapping keys must be strings")
            normalized[key] = normalize_semantic_value(child)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [normalize_semantic_value(child) for child in value]
    fail("REQUEST_INVALID", f"unsupported semantic payload type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    normalized = normalize_semantic_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_payload_sha256(payload: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(normalize_operation_payload(payload)))


def external_operation_identity(
    operation_type: OperationType,
    source_id: str,
    library_alias: str,
    payload_sha256: str,
) -> str:
    preimage = {
        "identity_schema_version": "1.0",
        "operation_type": operation_type.value,
        "source_id": source_id,
        "library_alias": library_alias,
        "normalized_payload_sha256": payload_sha256,
    }
    return "ZOP-" + sha256_bytes(canonical_json_bytes(preimage))


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        fail("IDENTITY_AMBIGUOUS", "DOI must be a string or null")
    normalized = value.strip().casefold()
    normalized = re.sub(
        r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    if not DOI_RE.fullmatch(normalized):
        fail("IDENTITY_AMBIGUOUS", f"invalid DOI syntax: {value!r}")
    return normalized


def normalize_operation_payload(value: Any, field_name: str | None = None) -> Any:
    """Apply only frozen field-specific rules before canonical JSON encoding."""
    if field_name is not None and field_name.casefold() == "doi":
        return normalize_doi(value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                fail("REQUEST_INVALID", "semantic payload mapping keys must be strings")
            normalized[key] = normalize_operation_payload(child, key)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [normalize_operation_payload(child) for child in value]
    return normalize_semantic_value(value)


def _integer_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return isinstance(value, str) and INTEGER_ID_RE.fullmatch(value) is not None


def _require_mapping(value: Any, code: str, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(code, message)
    return value


def _load_yaml_mapping(path: Path, code: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(code, f"cannot load {path}: {exc}")
    return _require_mapping(value, code, f"{path} must contain a mapping")


@dataclass(frozen=True)
class IntegrationConfig:
    schema_version: str
    configuration_status: str
    api_version: int
    primary_transport: str
    secondary_transport: str
    libraries: Mapping[str, Mapping[str, Any]]
    citation_configuration_status: str
    bbt_compatibility_status: str
    bibliography_scope_alias: str
    offline_plan_allowed: bool = True
    external_execution_eligible: bool = False

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> "IntegrationConfig":
        reject_secret_keys(document)
        if str(document.get("schema_version")) != "1.0":
            fail("CONFIG_INVALID", "schema_version must be '1.0'")
        status = document.get("configuration_status")
        if status not in {"unconfigured", "configured"}:
            fail("CONFIG_INVALID", "configuration_status must be unconfigured or configured")

        api = _require_mapping(document.get("zotero_api"), "CONFIG_INVALID", "zotero_api must be a mapping")
        if api.get("version") != 3:
            fail("CONFIG_INVALID", "zotero_api.version must be 3")
        if api.get("primary_transport") != "web_api":
            fail("CONFIG_INVALID", "primary_transport must be web_api")
        if api.get("secondary_transport") != "local_api":
            fail("CONFIG_INVALID", "secondary_transport must be local_api")

        libraries = _require_mapping(document.get("libraries"), "CONFIG_INVALID", "libraries must be a mapping")
        if not libraries:
            fail("CONFIG_INVALID", "at least one library alias is required")
        for alias, library in libraries.items():
            if not isinstance(alias, str) or not alias:
                fail("CONFIG_INVALID", "library aliases must be non-empty strings")
            library_map = _require_mapping(library, "CONFIG_INVALID", f"library {alias} must be a mapping")
            if status == "configured":
                if library_map.get("type") not in {"user", "group"}:
                    fail("CONFIG_INVALID", f"configured library {alias} type must be user or group")
                if not _integer_like(library_map.get("library_id")):
                    fail("CONFIG_INVALID", f"configured library {alias} library_id must be integer-like")

        citation = _require_mapping(
            document.get("citation_keys"), "CONFIG_INVALID", "citation_keys must be a mapping"
        )
        if citation.get("generator") != "better-bibtex":
            fail("CONFIG_INVALID", "citation key generator must be better-bibtex")
        if citation.get("regenerate_on_metadata_change") is not False:
            fail("CONFIG_INVALID", "regenerate_on_metadata_change must be false")
        citation_status = citation.get("configuration_status")
        if citation_status not in {"unverified", "verified"}:
            fail("CONFIG_INVALID", "citation configuration_status is invalid")
        if citation_status == "verified":
            if not isinstance(citation.get("formula"), str) or not citation["formula"].strip():
                fail("CONFIG_INVALID", "verified citation configuration requires formula")
            if not isinstance(citation.get("uniqueness_scope"), str) or not citation["uniqueness_scope"].strip():
                fail("CONFIG_INVALID", "verified citation configuration requires uniqueness_scope")

        bbt = _require_mapping(document.get("better_bibtex"), "CONFIG_INVALID", "better_bibtex must be a mapping")
        bbt_status = bbt.get("compatibility_status")
        if bbt_status not in BBT_COMPATIBILITY_STATES:
            fail("CONFIG_INVALID", "Better BibTeX compatibility_status is invalid")

        export = _require_mapping(
            document.get("bibliography_export"), "CONFIG_INVALID", "bibliography_export must be a mapping"
        )
        if export.get("path") != "05_Literature/references.bib":
            fail("CONFIG_INVALID", "bibliography export path is not canonical")
        scope_alias = export.get("scope_library_alias")
        if scope_alias not in libraries:
            fail("CONFIG_INVALID", "bibliography scope library alias does not resolve")
        if export.get("automatic_mode") != "Paused":
            fail("CONFIG_INVALID", "bibliography automatic_mode must be Paused")

        security = _require_mapping(document.get("security"), "CONFIG_INVALID", "security must be a mapping")
        if security.get("credentials_stored_in_this_file") is not False:
            fail("CONFIG_INVALID", "credentials_stored_in_this_file must be false")

        return cls(
            schema_version="1.0",
            configuration_status=status,
            api_version=3,
            primary_transport="web_api",
            secondary_transport="local_api",
            libraries=libraries,
            citation_configuration_status=citation_status,
            bbt_compatibility_status=bbt_status,
            bibliography_scope_alias=scope_alias,
            offline_plan_allowed=True,
            external_execution_eligible=False,
        )

    @classmethod
    def load(cls, path: Path) -> "IntegrationConfig":
        return cls.from_mapping(_load_yaml_mapping(path, "CONFIG_INVALID"))


@dataclass(frozen=True)
class OperationRequest:
    operation_type: OperationType
    source_id: str
    library_alias: str
    payload: Mapping[str, Any]
    source_record_status: str = "active"
    source_create_eligible: bool = True
    expected_git_head: str | None = None
    expected_source_record_version: int | None = None
    existing_link_library_alias: str | None = None
    existing_link_item_key: str | None = None
    origin_packet_id: str | None = None
    operation_id: str | None = None
    task_id: str | None = None
    restart_id: str | None = None

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> "OperationRequest":
        try:
            operation_type = OperationType(document.get("operation_type"))
        except ValueError:
            fail("UNSUPPORTED_OPERATION", f"unsupported operation: {document.get('operation_type')!r}")
        source_id = document.get("source_id")
        if not isinstance(source_id, str) or SOURCE_ID_RE.fullmatch(source_id) is None:
            fail("SOURCE_ID_INVALID", "source_id must match SRC-NNNNNN")
        library_alias = document.get("library_alias")
        if not isinstance(library_alias, str) or not library_alias:
            fail("REQUEST_INVALID", "library_alias must be a non-empty string")
        payload = _require_mapping(document.get("payload"), "REQUEST_INVALID", "payload must be a mapping")
        normalize_operation_payload(payload)
        source_record_status = document.get("source_record_status", "active")
        if source_record_status != "active":
            fail("SOURCE_NOT_ELIGIBLE", "source record must be active")
        source_create_eligible = document.get("source_create_eligible", True)
        if not isinstance(source_create_eligible, bool):
            fail("REQUEST_INVALID", "source_create_eligible must be boolean")
        if operation_type == OperationType.ZOTERO_CREATE and not source_create_eligible:
            fail("SOURCE_NOT_ELIGIBLE", "source is not create-eligible")
        expected_head = document.get("expected_git_head")
        if expected_head is not None and (
            not isinstance(expected_head, str) or HEX40_RE.fullmatch(expected_head) is None
        ):
            fail("REQUEST_INVALID", "expected_git_head must be a 40-character lowercase SHA")
        record_version = document.get("expected_source_record_version")
        if record_version is not None and (
            isinstance(record_version, bool) or not isinstance(record_version, int) or record_version < 1
        ):
            fail("REQUEST_INVALID", "expected_source_record_version must be a positive integer")
        existing = document.get("existing_link")
        existing_alias = None
        existing_key = None
        if existing is not None:
            existing_map = _require_mapping(existing, "REQUEST_INVALID", "existing_link must be a mapping or null")
            existing_alias = existing_map.get("library_alias")
            existing_key = existing_map.get("item_key")
            if not isinstance(existing_alias, str) or not isinstance(existing_key, str):
                fail("REQUEST_INVALID", "existing_link requires library_alias and item_key")
        return cls(
            operation_type=operation_type,
            source_id=source_id,
            library_alias=library_alias,
            payload=payload,
            source_record_status=source_record_status,
            source_create_eligible=source_create_eligible,
            expected_git_head=expected_head,
            expected_source_record_version=record_version,
            existing_link_library_alias=existing_alias,
            existing_link_item_key=existing_key,
            origin_packet_id=document.get("origin_packet_id"),
            operation_id=document.get("operation_id"),
            task_id=document.get("task_id"),
            restart_id=document.get("restart_id"),
        )

    @classmethod
    def load(cls, path: Path) -> "OperationRequest":
        return cls.from_mapping(_load_yaml_mapping(path, "REQUEST_INVALID"))

    @property
    def payload_sha256(self) -> str:
        return normalized_payload_sha256(self.payload)

    @property
    def external_operation_identity(self) -> str:
        return external_operation_identity(
            self.operation_type,
            self.source_id,
            self.library_alias,
            self.payload_sha256,
        )


@dataclass(frozen=True)
class ExternalItem:
    item_key: str
    doi: str | None = None
    stable_identifiers: Mapping[str, str] = field(default_factory=dict)
    human_confirmed: bool = False
    fuzzy_match: bool = False
    collections: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    zotero_object_version: int | None = None
    version_space: str = "web_api"

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> "ExternalItem":
        item_key = document.get("item_key")
        if not isinstance(item_key, str) or ITEM_KEY_RE.fullmatch(item_key) is None:
            fail("REQUEST_INVALID", "fixture item_key is invalid")
        raw_ids = document.get("stable_identifiers", {})
        stable_ids = _require_mapping(raw_ids, "REQUEST_INVALID", "stable_identifiers must be a mapping")
        normalized_ids: dict[str, str] = {}
        for key, value in stable_ids.items():
            if not isinstance(key, str) or not isinstance(value, str):
                fail("REQUEST_INVALID", "stable identifiers must be string pairs")
            normalized_ids[key.casefold().strip()] = value.strip()
        version = document.get("zotero_object_version")
        if version is not None and (
            isinstance(version, bool) or not isinstance(version, int) or version < 0
        ):
            fail("REQUEST_INVALID", "zotero_object_version must be a non-negative integer")
        collections = document.get("collections", [])
        tags = document.get("tags", [])
        if not isinstance(collections, list) or not all(isinstance(x, str) for x in collections):
            fail("REQUEST_INVALID", "collections must be a string list")
        if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
            fail("REQUEST_INVALID", "tags must be a string list")
        return cls(
            item_key=item_key,
            doi=normalize_doi(document.get("doi")),
            stable_identifiers=normalized_ids,
            human_confirmed=document.get("human_confirmed") is True,
            fuzzy_match=document.get("fuzzy_match") is True,
            collections=tuple(collections),
            tags=tuple(tags),
            zotero_object_version=version,
            version_space=str(document.get("version_space", "web_api")),
        )


@dataclass(frozen=True)
class ExternalObservation:
    items: tuple[ExternalItem, ...]
    previous_attempt_uncertain: bool = False

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> "ExternalObservation":
        items = document.get("items", [])
        if not isinstance(items, list):
            fail("REQUEST_INVALID", "fixture items must be a list")
        return cls(
            items=tuple(
                ExternalItem.from_mapping(_require_mapping(item, "REQUEST_INVALID", "fixture item must be a mapping"))
                for item in items
            ),
            previous_attempt_uncertain=document.get("previous_attempt_uncertain") is True,
        )

    @classmethod
    def load(cls, path: Path) -> "ExternalObservation":
        return cls.from_mapping(_load_yaml_mapping(path, "REQUEST_INVALID"))


@dataclass(frozen=True)
class IdentityCandidate:
    item_key: str
    bases: tuple[ExactIdentityBasis, ...]


@dataclass(frozen=True)
class DuplicatePreflight:
    decision: DuplicateDecision
    exact_candidates: tuple[IdentityCandidate, ...] = ()
    fuzzy_item_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationPlan:
    schema_version: str
    phase: str
    operation_type: str
    source_id: str
    library_alias: str
    normalized_payload_sha256: str
    external_operation_identity: str
    ledger_state: str
    decision: str
    reason_code: str | None
    target_item_key: str | None
    zotero_mutation_planned: bool
    offline_plan_allowed: bool
    external_execution_eligible: bool
    network_used: bool
    write_token_required: bool = False
    write_token_identity: str | None = None
    server_generated_item_key_required: bool = False
    preallocated_item_key: str | None = None
    expected_zotero_object_version: int | None = None
    requires_full_preflight: bool = False


@dataclass(frozen=True)
class OperationResult:
    status: str
    reason_code: str | None = None
    item_key: str | None = None


@dataclass(frozen=True)
class LedgerEntry:
    external_operation_identity: str
    source_id: str
    library_alias: str
    operation_type: str
    normalized_payload_sha256: str
    state: LedgerState
    write_token_fingerprint: str | None = None
    item_key: str | None = None
    zotero_object_version: int | None = None
    zotero_library_version: int | None = None
    result_fingerprint: str | None = None
    git_reconciliation_status: str | None = None

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> "LedgerEntry":
        try:
            state = LedgerState(document.get("state"))
        except ValueError:
            fail("INVALID_LEDGER_TRANSITION", f"invalid persisted ledger state {document.get('state')!r}")
        return cls(
            external_operation_identity=str(document.get("external_operation_identity")),
            source_id=str(document.get("source_id")),
            library_alias=str(document.get("library_alias")),
            operation_type=str(document.get("operation_type")),
            normalized_payload_sha256=str(document.get("normalized_payload_sha256")),
            state=state,
            write_token_fingerprint=document.get("write_token_fingerprint"),
            item_key=document.get("item_key"),
            zotero_object_version=document.get("zotero_object_version"),
            zotero_library_version=document.get("zotero_library_version"),
            result_fingerprint=document.get("result_fingerprint"),
            git_reconciliation_status=document.get("git_reconciliation_status"),
        )

    def serializable(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value


@dataclass(frozen=True)
class GitReconciliationPayload:
    schema_version: str
    source_id: str
    external_operation_identity: str
    external_operation_type: str
    expected_git_head: str
    expected_source_record_version: int
    proposed_source_update: Mapping[str, Any]
    external_evidence: Mapping[str, Any]
    reconciliation_status: str

    def serializable(self) -> dict[str, Any]:
        return normalize_semantic_value(asdict(self))


class ExternalTransport(Protocol):
    def observe(self, request: OperationRequest) -> ExternalObservation:
        ...


class ForbiddenTransport:
    def observe(self, request: OperationRequest) -> ExternalObservation:
        del request
        fail("NETWORK_FORBIDDEN_IN_PHASE2", "real external state access is forbidden in Phase 2")


@dataclass(frozen=True)
class FixtureTransport:
    observation: ExternalObservation

    def observe(self, request: OperationRequest) -> ExternalObservation:
        del request
        return self.observation


def validate_ledger_transition(previous: LedgerState, next_state: LedgerState) -> None:
    if (previous, next_state) not in ALLOWED_LEDGER_TRANSITIONS:
        fail("INVALID_LEDGER_TRANSITION", f"{previous.value} -> {next_state.value} is forbidden")


class InMemoryOperationLedger:
    def __init__(self) -> None:
        self._entries: dict[str, LedgerEntry] = {}

    def get(self, external_operation_identity_value: str) -> LedgerEntry | None:
        return self._entries.get(external_operation_identity_value)

    def record(self, entry: LedgerEntry) -> OperationResult:
        previous = self._entries.get(entry.external_operation_identity)
        if previous is None:
            self._entries[entry.external_operation_identity] = entry
            return OperationResult("RECORDED", item_key=entry.item_key)
        immutable_previous = (
            previous.external_operation_identity,
            previous.source_id,
            previous.library_alias,
            previous.operation_type,
            previous.normalized_payload_sha256,
        )
        immutable_next = (
            entry.external_operation_identity,
            entry.source_id,
            entry.library_alias,
            entry.operation_type,
            entry.normalized_payload_sha256,
        )
        if immutable_previous != immutable_next:
            fail("OPERATION_IDENTITY_COLLISION", "ledger immutable identity fields changed")
        if previous.state == LedgerState.GIT_RECONCILED and entry.state == LedgerState.GIT_RECONCILED:
            return OperationResult("SUCCESS_NOOP", item_key=previous.item_key)
        validate_ledger_transition(previous.state, entry.state)
        self._entries[entry.external_operation_identity] = entry
        return OperationResult("RECORDED", item_key=entry.item_key)

    def serializable(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "entries": {
                identity: entry.serializable()
                for identity, entry in sorted(self._entries.items())
            },
        }


class TemporaryFileOperationLedger(InMemoryOperationLedger):
    """Ledger whose complete lifetime is confined to its own temporary directory."""

    def __init__(self) -> None:
        super().__init__()
        self._temporary = tempfile.TemporaryDirectory(prefix="zotero-phase2-ledger-")
        self.path = Path(self._temporary.name) / "operation-ledger.json"

    def record(self, entry: LedgerEntry) -> OperationResult:
        result = super().record(entry)
        self.path.write_text(
            json.dumps(self.serializable(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return result

    def reload(self) -> None:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        entries = _require_mapping(document.get("entries"), "REQUEST_INVALID", "temporary ledger entries invalid")
        self._entries = {
            identity: LedgerEntry.from_mapping(
                _require_mapping(entry, "REQUEST_INVALID", "temporary ledger entry invalid")
            )
            for identity, entry in entries.items()
        }

    def close(self) -> None:
        self._temporary.cleanup()

    def __enter__(self) -> "TemporaryFileOperationLedger":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()


def _request_identity_fields(request: OperationRequest) -> tuple[str | None, dict[str, str], str | None]:
    bibliographic = request.payload.get("bibliographic_identity", request.payload)
    if not isinstance(bibliographic, Mapping):
        fail("REQUEST_INVALID", "bibliographic_identity must be a mapping")
    doi = normalize_doi(bibliographic.get("doi"))
    raw_ids = bibliographic.get("stable_identifiers", bibliographic.get("other_ids", {}))
    stable_ids: dict[str, str] = {}
    if raw_ids is not None:
        raw_ids_map = _require_mapping(raw_ids, "REQUEST_INVALID", "stable identifiers must be a mapping")
        for key, value in raw_ids_map.items():
            if not isinstance(key, str) or not isinstance(value, str):
                fail("REQUEST_INVALID", "stable identifiers must be string pairs")
            stable_ids[key.casefold().strip()] = value.strip()
    known_key = (
        request.payload.get("target_item_key")
        or request.payload.get("known_item_key")
        or request.existing_link_item_key
    )
    if known_key is not None and not isinstance(known_key, str):
        fail("REQUEST_INVALID", "known item key must be a string")
    return doi, stable_ids, known_key


def classify_duplicates(request: OperationRequest, observation: ExternalObservation) -> DuplicatePreflight:
    request_doi, request_ids, known_key = _request_identity_fields(request)
    exact: list[IdentityCandidate] = []
    fuzzy: list[str] = []
    for item in observation.items:
        bases: list[ExactIdentityBasis] = []
        if request_doi is not None and item.doi == request_doi:
            bases.append(ExactIdentityBasis.EXACT_DOI)
        if any(item.stable_identifiers.get(key) == value for key, value in request_ids.items()):
            bases.append(ExactIdentityBasis.EXACT_STABLE_IDENTIFIER)
        if known_key is not None and item.item_key == known_key:
            bases.append(ExactIdentityBasis.KNOWN_ITEM_KEY)
        if item.human_confirmed:
            bases.append(ExactIdentityBasis.HUMAN_CONFIRMED)
        if bases:
            exact.append(IdentityCandidate(item.item_key, tuple(bases)))
        elif item.fuzzy_match:
            fuzzy.append(item.item_key)

    if len(exact) > 1:
        decision = DuplicateDecision.MULTIPLE_EXACT_MATCHES
    elif len(exact) == 1:
        candidate = exact[0]
        if request.existing_link_item_key is not None:
            same = (
                request.existing_link_library_alias == request.library_alias
                and request.existing_link_item_key == candidate.item_key
            )
            decision = (
                DuplicateDecision.ALREADY_LINKED_SAME
                if same
                else DuplicateDecision.ALREADY_LINKED_DIFFERENT
            )
        else:
            decision = DuplicateDecision.EXACT_SINGLE_MATCH
    elif request.existing_link_item_key is not None:
        decision = DuplicateDecision.ALREADY_LINKED_DIFFERENT
    elif fuzzy:
        decision = DuplicateDecision.FUZZY_ONLY
    else:
        decision = DuplicateDecision.NO_MATCH
    return DuplicatePreflight(decision, tuple(exact), tuple(fuzzy))


def _base_plan(
    request: OperationRequest,
    config: IntegrationConfig,
    decision: DecisionState,
    ledger_state: LedgerState,
    reason_code: str | None = None,
    target_item_key: str | None = None,
    zotero_mutation_planned: bool = False,
    **overrides: Any,
) -> OperationPlan:
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "phase": "PHASE2_OFFLINE",
        "operation_type": request.operation_type.value,
        "source_id": request.source_id,
        "library_alias": request.library_alias,
        "normalized_payload_sha256": request.payload_sha256,
        "external_operation_identity": request.external_operation_identity,
        "ledger_state": ledger_state.value,
        "decision": decision.value,
        "reason_code": reason_code,
        "target_item_key": target_item_key,
        "zotero_mutation_planned": zotero_mutation_planned,
        "offline_plan_allowed": config.offline_plan_allowed,
        "external_execution_eligible": False,
        "network_used": False,
    }
    values.update(overrides)
    return OperationPlan(**values)


def recover_lost_create(
    request: OperationRequest,
    config: IntegrationConfig,
    observation: ExternalObservation,
) -> OperationPlan:
    preflight = classify_duplicates(request, observation)
    if preflight.decision == DuplicateDecision.NO_MATCH:
        return _base_plan(
            request,
            config,
            DecisionState.SAFE_RETRY_CANDIDATE,
            LedgerState.FAILED_RETRYABLE,
            reason_code="SAFE_RETRY_CANDIDATE",
            requires_full_preflight=True,
        )
    if preflight.decision in {
        DuplicateDecision.EXACT_SINGLE_MATCH,
        DuplicateDecision.ALREADY_LINKED_SAME,
    }:
        target = preflight.exact_candidates[0].item_key
        return _base_plan(
            request,
            config,
            DecisionState.RECOVER_EXISTING_WRITE,
            LedgerState.EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT,
            reason_code="RECOVER_EXISTING_WRITE",
            target_item_key=target,
        )
    reason = (
        "MULTIPLE_EXACT_MATCHES"
        if preflight.decision == DuplicateDecision.MULTIPLE_EXACT_MATCHES
        else "NEEDS_REVIEW"
    )
    return _base_plan(
        request,
        config,
        DecisionState.NEEDS_REVIEW,
        LedgerState.NEEDS_REVIEW,
        reason_code=reason,
    )


def _find_target_item(request: OperationRequest, observation: ExternalObservation) -> ExternalItem | None:
    target_key = request.payload.get("target_item_key") or request.payload.get("known_item_key")
    if not isinstance(target_key, str):
        return None
    return next((item for item in observation.items if item.item_key == target_key), None)


def plan_operation(
    request: OperationRequest,
    config: IntegrationConfig,
    observation: ExternalObservation,
) -> OperationPlan:
    if request.library_alias not in config.libraries:
        fail("CONFIG_INVALID", f"library alias {request.library_alias!r} does not resolve")

    if request.operation_type == OperationType.ZOTERO_CREATE and observation.previous_attempt_uncertain:
        return recover_lost_create(request, config, observation)

    preflight = classify_duplicates(request, observation)
    if request.operation_type == OperationType.ZOTERO_CREATE:
        if preflight.decision == DuplicateDecision.NO_MATCH:
            token_identity = "ZWT-" + sha256_bytes(
                ("phase2-write-token:" + request.external_operation_identity).encode("ascii")
            )
            return _base_plan(
                request,
                config,
                DecisionState.CREATE,
                LedgerState.DRY_RUN_VALID,
                zotero_mutation_planned=True,
                write_token_required=True,
                write_token_identity=token_identity,
                server_generated_item_key_required=True,
                preallocated_item_key=None,
            )
        if preflight.decision == DuplicateDecision.ALREADY_LINKED_SAME:
            return _base_plan(
                request,
                config,
                DecisionState.SUCCESS_NOOP,
                LedgerState.GIT_RECONCILED,
                reason_code="ALREADY_LINKED_SAME",
                target_item_key=preflight.exact_candidates[0].item_key,
            )
        reason = (
            "MULTIPLE_EXACT_MATCHES"
            if preflight.decision == DuplicateDecision.MULTIPLE_EXACT_MATCHES
            else "FUZZY_MATCH_NOT_AUTHORIZED"
            if preflight.decision == DuplicateDecision.FUZZY_ONLY
            else "ALREADY_LINKED_DIFFERENT"
            if preflight.decision == DuplicateDecision.ALREADY_LINKED_DIFFERENT
            else "IDENTITY_AMBIGUOUS"
        )
        return _base_plan(
            request,
            config,
            DecisionState.NEEDS_REVIEW,
            LedgerState.NEEDS_REVIEW,
            reason_code=reason,
            target_item_key=(
                preflight.exact_candidates[0].item_key
                if len(preflight.exact_candidates) == 1
                else None
            ),
        )

    if request.operation_type == OperationType.ZOTERO_LINK_EXISTING:
        if preflight.decision == DuplicateDecision.ALREADY_LINKED_SAME:
            return _base_plan(
                request,
                config,
                DecisionState.SUCCESS_NOOP,
                LedgerState.GIT_RECONCILED,
                reason_code="ALREADY_LINKED_SAME",
                target_item_key=preflight.exact_candidates[0].item_key,
            )
        if preflight.decision == DuplicateDecision.EXACT_SINGLE_MATCH:
            return _base_plan(
                request,
                config,
                DecisionState.LINK_EXISTING,
                LedgerState.DRY_RUN_VALID,
                target_item_key=preflight.exact_candidates[0].item_key,
                zotero_mutation_planned=False,
            )
        reason_map = {
            DuplicateDecision.NO_MATCH: "NO_EXACT_TARGET",
            DuplicateDecision.FUZZY_ONLY: "FUZZY_MATCH_NOT_AUTHORIZED",
            DuplicateDecision.MULTIPLE_EXACT_MATCHES: "MULTIPLE_EXACT_MATCHES",
            DuplicateDecision.ALREADY_LINKED_DIFFERENT: "ALREADY_LINKED_DIFFERENT",
        }
        return _base_plan(
            request,
            config,
            DecisionState.NEEDS_REVIEW,
            LedgerState.NEEDS_REVIEW,
            reason_code=reason_map.get(preflight.decision, "NEEDS_REVIEW"),
        )

    target = _find_target_item(request, observation)
    if target is None:
        return _base_plan(
            request,
            config,
            DecisionState.NEEDS_REVIEW,
            LedgerState.NEEDS_REVIEW,
            reason_code="NO_EXACT_TARGET",
        )
    if request.existing_link_item_key is not None and (
        request.existing_link_library_alias != request.library_alias
        or request.existing_link_item_key != target.item_key
    ):
        return _base_plan(
            request,
            config,
            DecisionState.NEEDS_REVIEW,
            LedgerState.NEEDS_REVIEW,
            reason_code="ALREADY_LINKED_DIFFERENT",
        )

    value_key = "collection_key" if request.operation_type == OperationType.ADD_COLLECTION else "tag"
    value = request.payload.get(value_key)
    if not isinstance(value, str) or not value:
        fail("REQUEST_INVALID", f"{value_key} is required")
    present = value in (target.collections if request.operation_type == OperationType.ADD_COLLECTION else target.tags)
    if present:
        return _base_plan(
            request,
            config,
            DecisionState.SUCCESS_NOOP,
            LedgerState.GIT_RECONCILED,
            reason_code="ALREADY_PRESENT",
            target_item_key=target.item_key,
        )

    expected = request.payload.get("expected_zotero_object_version")
    version_space = request.payload.get("version_space", "web_api")
    if version_space != target.version_space:
        return _base_plan(
            request,
            config,
            DecisionState.NEEDS_REVIEW,
            LedgerState.NEEDS_REVIEW,
            reason_code="VERSION_SPACE_MISMATCH",
            target_item_key=target.item_key,
        )
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        fail("REQUEST_INVALID", "expected_zotero_object_version is required for object mutation")
    if target.zotero_object_version is None:
        fail("REQUEST_INVALID", "fixture target lacks zotero_object_version")
    if expected != target.zotero_object_version:
        return _base_plan(
            request,
            config,
            DecisionState.RETRY_ELIGIBLE,
            LedgerState.DRY_RUN_VALID,
            reason_code="STALE_ZOTERO_OBJECT",
            target_item_key=target.item_key,
            zotero_mutation_planned=True,
            expected_zotero_object_version=target.zotero_object_version,
            requires_full_preflight=True,
        )
    return _base_plan(
        request,
        config,
        DecisionState.MUTATE_EXISTING,
        LedgerState.DRY_RUN_VALID,
        target_item_key=target.item_key,
        zotero_mutation_planned=True,
        expected_zotero_object_version=expected,
    )


def build_git_reconciliation_payload(
    request: OperationRequest,
    plan: OperationPlan,
    result: OperationResult,
) -> GitReconciliationPayload:
    if request.operation_type not in {
        OperationType.ZOTERO_CREATE,
        OperationType.ZOTERO_LINK_EXISTING,
    }:
        fail("GIT_RECONCILIATION_PRECONDITION_FAILED", "only create/link can propose linkage")
    if result.status != "SUCCESS":
        fail("GIT_RECONCILIATION_PRECONDITION_FAILED", "successful external result is required")
    item_key = result.item_key
    if not isinstance(item_key, str) or ITEM_KEY_RE.fullmatch(item_key) is None:
        fail("GIT_RECONCILIATION_PRECONDITION_FAILED", "a valid server item key is required")
    if request.expected_git_head is None or request.expected_source_record_version is None:
        fail(
            "GIT_RECONCILIATION_PRECONDITION_FAILED",
            "expected Git HEAD and source record_version are required",
        )
    proposed = {
        "zotero": {
            "library_alias": request.library_alias,
            "item_key": item_key,
            "link_status": "linked",
        }
    }
    return GitReconciliationPayload(
        schema_version="1.0",
        source_id=request.source_id,
        external_operation_identity=plan.external_operation_identity,
        external_operation_type=request.operation_type.value,
        expected_git_head=request.expected_git_head,
        expected_source_record_version=request.expected_source_record_version,
        proposed_source_update=proposed,
        external_evidence={
            "item_key": item_key,
            "library_alias": request.library_alias,
            "basis": "offline_phase2_result",
        },
        reconciliation_status="PROPOSED_FOR_01A_REVIEW",
    )


def plan_document(
    request_path: Path,
    fixture_path: Path,
    config_path: Path,
) -> dict[str, Any]:
    config = IntegrationConfig.load(config_path)
    request = OperationRequest.load(request_path)
    observation = ExternalObservation.load(fixture_path)
    plan = plan_operation(request, config, FixtureTransport(observation).observe(request))
    result = asdict(plan)
    result["status"] = "PASS"
    result["mode"] = "plan"
    result["configuration_status"] = config.configuration_status
    return normalize_semantic_value(result)


def self_test() -> int:
    checks: list[bool] = []
    checks.append(len(LedgerState) == 9)
    checks.append(
        normalized_payload_sha256({"text": "Клементьев", "values": [2, 1]})
        == normalized_payload_sha256({"values": [2, 1], "text": "Клементьев"})
    )
    try:
        ForbiddenTransport().observe(
            OperationRequest(OperationType.ZOTERO_CREATE, "SRC-000001", "project-main", {})
        )
    except ExecutorFailure as exc:
        checks.append(exc.code == "NETWORK_FORBIDDEN_IN_PHASE2")
    else:
        checks.append(False)
    result = {
        "status": "PASS" if all(checks) else "FAIL",
        "mode": "self-test",
        "network_used": False,
        "checks_run": len(checks),
        "checks_passed": sum(checks),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if all(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test", help="run offline internal checks")
    plan_parser = subparsers.add_parser("plan", help="plan from local synthetic inputs")
    plan_parser.add_argument("--request", type=Path, required=True)
    plan_parser.add_argument("--fixture", type=Path, required=True)
    plan_parser.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "self-test":
        return self_test()
    try:
        result = plan_document(args.request, args.fixture, args.config)
    except ExecutorFailure as exc:
        result = {
            "status": "FAIL",
            "mode": "plan",
            "failure_code": exc.code,
            "network_used": False,
        }
        print(f"{exc.code}: {exc}", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
