#!/usr/bin/env python3
"""Synthetic offline tests for the Phase-2 Zotero integration executor."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import yaml

import zotero_executor as executor


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "05_Literature" / "ZOTERO_INTEGRATION_CONFIG.yaml"

PROTECTED_PATHS = (
    "03_Protocols/LIT_ZOTERO_INTEGRATION_SPEC_V1_0.md",
    "03_Protocols/LITERATURE_PACKET_MATERIALIZER_SPEC_V1_0.md",
    "03_Protocols/LITERATURE_KNOWLEDGE_SCHEMA_V1_0.md",
    "05_Literature/ZOTERO_INTEGRATION_CONFIG.yaml",
    "05_Literature/SOURCE_REGISTRY.yaml",
    "05_Literature/MATERIALIZATION_LOG.yaml",
    "scripts/literature/materialize_packet.py",
    "scripts/literature/literature_validate.py",
    "00_Project/PROJECT_METADATA.yaml",
    "00_Project/PROJECT_STATE.md",
    "00_Project/PROJECT_CONTROL.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_config_document() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def request_document(operation_type: str = "ZOTERO_CREATE", **updates: object) -> dict:
    document = {
        "schema_version": "1.0",
        "operation_type": operation_type,
        "source_id": "SRC-000001",
        "library_alias": "project-main",
        "payload": {
            "bibliographic_identity": {
                "doi": "10.1000/example",
                "stable_identifiers": {"report_identifier": "R-1"},
            }
        },
        "expected_git_head": "1" * 40,
        "expected_source_record_version": 1,
    }
    document.update(updates)
    return document


def request(operation_type: str = "ZOTERO_CREATE", **updates: object) -> executor.OperationRequest:
    return executor.OperationRequest.from_mapping(request_document(operation_type, **updates))


def observation(*items: dict, uncertain: bool = False) -> executor.ExternalObservation:
    return executor.ExternalObservation.from_mapping(
        {"items": list(items), "previous_attempt_uncertain": uncertain}
    )


def item(
    key: str = "ITEMA",
    doi: str | None = None,
    stable_identifiers: dict | None = None,
    **updates: object,
) -> dict:
    value = {
        "item_key": key,
        "doi": doi,
        "stable_identifiers": stable_identifiers or {},
        "collections": [],
        "tags": [],
        "zotero_object_version": 7,
        "version_space": "web_api",
    }
    value.update(updates)
    return value


class ConfigTests(unittest.TestCase):
    def test_canonical_unconfigured_config_is_valid(self) -> None:
        config = executor.IntegrationConfig.load(CONFIG_PATH)
        self.assertEqual(config.configuration_status, "unconfigured")
        self.assertTrue(config.offline_plan_allowed)
        self.assertFalse(config.external_execution_eligible)

    def test_malformed_config_fails_closed(self) -> None:
        document = canonical_config_document()
        document["schema_version"] = "9.9"
        with self.assertRaisesRegex(executor.ExecutorFailure, "schema_version") as caught:
            executor.IntegrationConfig.from_mapping(document)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_configured_library_requires_valid_identity(self) -> None:
        document = canonical_config_document()
        document["configuration_status"] = "configured"
        document["libraries"]["project-main"]["type"] = "group"
        document["libraries"]["project-main"]["library_id"] = "12345"
        parsed = executor.IntegrationConfig.from_mapping(document)
        self.assertEqual(parsed.configuration_status, "configured")
        document["libraries"]["project-main"]["library_id"] = None
        with self.assertRaises(executor.ExecutorFailure) as caught:
            executor.IntegrationConfig.from_mapping(document)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_secret_like_keys_are_rejected(self) -> None:
        for key in (
            "api_key",
            "apikey",
            "token",
            "access_token",
            "authorization",
            "password",
            "secret",
            "client_secret",
            "local_api_key",
        ):
            with self.subTest(key=key):
                document = canonical_config_document()
                document["runtime"] = {key: "forbidden-value"}
                with self.assertRaises(executor.ExecutorFailure) as caught:
                    executor.IntegrationConfig.from_mapping(document)
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_verified_citation_config_requires_formula_and_scope(self) -> None:
        document = canonical_config_document()
        document["citation_keys"]["configuration_status"] = "verified"
        with self.assertRaises(executor.ExecutorFailure):
            executor.IntegrationConfig.from_mapping(document)
        document["citation_keys"]["formula"] = "authYear"
        document["citation_keys"]["uniqueness_scope"] = "project-main"
        executor.IntegrationConfig.from_mapping(document)

    def test_bibliography_scope_must_resolve(self) -> None:
        document = canonical_config_document()
        document["bibliography_export"]["scope_library_alias"] = "missing"
        with self.assertRaises(executor.ExecutorFailure) as caught:
            executor.IntegrationConfig.from_mapping(document)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_kb_validator_rejects_secret_like_committed_config_key(self) -> None:
        module_path = ROOT / "scripts/kb_validate.py"
        specification = importlib.util.spec_from_file_location(
            "phase2_kb_validate", module_path
        )
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        document = canonical_config_document()
        document["runtime"] = {"access_token": "forbidden-value"}
        with tempfile.TemporaryDirectory(prefix="zotero-config-validator-") as temporary:
            path = Path(temporary) / "config.yaml"
            path.write_text(
                yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
            )
            issues: list[dict] = []
            with mock.patch.object(module, "ZOTERO_CONFIG", path):
                module.zotero_config_checks(issues)
        self.assertTrue(
            any("secret-like key" in issue["message"] for issue in issues)
        )


class NormalizationAndIdentityTests(unittest.TestCase):
    def test_mapping_order_is_canonical(self) -> None:
        left = {"b": 2, "a": {"я": True, "x": None}}
        right = {"a": {"x": None, "я": True}, "b": 2}
        self.assertEqual(
            executor.normalized_payload_sha256(left),
            executor.normalized_payload_sha256(right),
        )

    def test_list_order_is_preserved(self) -> None:
        self.assertNotEqual(
            executor.normalized_payload_sha256({"x": [1, 2]}),
            executor.normalized_payload_sha256({"x": [2, 1]}),
        )

    def test_unicode_is_preserved_without_transliteration(self) -> None:
        raw = executor.canonical_json_bytes({"author": "Клементьев"})
        self.assertIn("Клементьев", raw.decode("utf-8"))

    def test_unsupported_scalar_type_is_rejected(self) -> None:
        with self.assertRaises(executor.ExecutorFailure) as caught:
            executor.normalize_semantic_value({"bad": {1, 2}})
        self.assertEqual(caught.exception.code, "REQUEST_INVALID")

    def test_nonfinite_float_is_rejected(self) -> None:
        with self.assertRaises(executor.ExecutorFailure):
            executor.normalize_semantic_value({"bad": float("nan")})

    def test_doi_normalization(self) -> None:
        expected = "10.21468/scipostphyscore.5.1.018"
        for value in (
            " 10.21468/SciPostPhysCore.5.1.018 ",
            "doi:10.21468/SciPostPhysCore.5.1.018",
            "https://doi.org/10.21468/SciPostPhysCore.5.1.018",
            "http://dx.doi.org/10.21468/SciPostPhysCore.5.1.018",
        ):
            with self.subTest(value=value):
                self.assertEqual(executor.normalize_doi(value), expected)

    def test_provenance_wrappers_do_not_change_identity(self) -> None:
        first = request(origin_packet_id="MP-A", operation_id="OP-1", task_id="T-1", restart_id="R-1")
        second = request(origin_packet_id="MP-B", operation_id="OP-9", task_id="T-2", restart_id="R-8")
        self.assertEqual(first.external_operation_identity, second.external_operation_identity)

    def test_semantic_payload_change_changes_identity(self) -> None:
        left = request()
        changed = request_document()
        changed["payload"]["bibliographic_identity"]["doi"] = "10.1000/changed"
        right = executor.OperationRequest.from_mapping(changed)
        self.assertNotEqual(left.external_operation_identity, right.external_operation_identity)

    def test_doi_url_and_case_variants_have_same_semantic_identity(self) -> None:
        plain = request()
        variant_document = request_document()
        variant_document["payload"]["bibliographic_identity"]["doi"] = (
            " HTTPS://DOI.ORG/10.1000/EXAMPLE "
        )
        variant = executor.OperationRequest.from_mapping(variant_document)
        self.assertEqual(plain.external_operation_identity, variant.external_operation_identity)

    def test_source_library_and_operation_type_differentiate_identity(self) -> None:
        base = request()
        other_source = request(source_id="SRC-000002")
        other_library = request(library_alias="secondary")
        other_type = request("ZOTERO_LINK_EXISTING")
        identities = {
            base.external_operation_identity,
            other_source.external_operation_identity,
            other_library.external_operation_identity,
            other_type.external_operation_identity,
        }
        self.assertEqual(len(identities), 4)

    def test_identity_uses_full_sha256(self) -> None:
        identity = request().external_operation_identity
        self.assertRegex(identity, r"^ZOP-[0-9a-f]{64}$")

    def test_inactive_or_ineligible_source_fails_closed(self) -> None:
        for update in (
            {"source_record_status": "merged"},
            {"source_create_eligible": False},
        ):
            with self.subTest(update=update):
                with self.assertRaises(executor.ExecutorFailure) as caught:
                    request(**update)
                self.assertEqual(caught.exception.code, "SOURCE_NOT_ELIGIBLE")


class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = executor.IntegrationConfig.load(CONFIG_PATH)

    def test_create_no_match_is_normal_plan_without_item_preallocation(self) -> None:
        req = request()
        plan = executor.plan_operation(req, self.config, observation())
        self.assertEqual(plan.decision, "CREATE")
        self.assertEqual(plan.ledger_state, "DRY_RUN_VALID")
        self.assertTrue(plan.write_token_required)
        self.assertNotEqual(plan.write_token_identity, plan.external_operation_identity)
        self.assertTrue(plan.server_generated_item_key_required)
        self.assertIsNone(plan.preallocated_item_key)
        self.assertFalse(plan.external_execution_eligible)

    def test_create_exact_doi_requires_review(self) -> None:
        plan = executor.plan_operation(
            request(), self.config, observation(item(doi="10.1000/example"))
        )
        self.assertEqual(plan.decision, "NEEDS_REVIEW")
        self.assertEqual(plan.reason_code, "IDENTITY_AMBIGUOUS")

    def test_create_exact_stable_id_requires_review(self) -> None:
        plan = executor.plan_operation(
            request(),
            self.config,
            observation(item(stable_identifiers={"report_identifier": "R-1"})),
        )
        self.assertEqual(plan.decision, "NEEDS_REVIEW")

    def test_create_fuzzy_only_requires_review(self) -> None:
        plan = executor.plan_operation(
            request(), self.config, observation(item(fuzzy_match=True))
        )
        self.assertEqual(plan.reason_code, "FUZZY_MATCH_NOT_AUTHORIZED")

    def test_create_multiple_exact_matches_requires_review(self) -> None:
        plan = executor.plan_operation(
            request(),
            self.config,
            observation(
                item("ITEMA", doi="10.1000/example"),
                item("ITEMB", doi="10.1000/example"),
            ),
        )
        self.assertEqual(plan.reason_code, "MULTIPLE_EXACT_MATCHES")

    def test_create_already_linked_same_is_noop(self) -> None:
        req = request(existing_link={"library_alias": "project-main", "item_key": "ITEMA"})
        plan = executor.plan_operation(
            req, self.config, observation(item("ITEMA", doi="10.1000/example"))
        )
        self.assertEqual(plan.decision, "SUCCESS_NOOP")
        self.assertEqual(plan.reason_code, "ALREADY_LINKED_SAME")

    def test_create_conflicting_existing_link_requires_review(self) -> None:
        req = request(existing_link={"library_alias": "project-main", "item_key": "OTHER"})
        plan = executor.plan_operation(
            req, self.config, observation(item("ITEMA", doi="10.1000/example"))
        )
        self.assertEqual(plan.reason_code, "ALREADY_LINKED_DIFFERENT")

    def test_link_existing_exact_is_pure_link(self) -> None:
        plan = executor.plan_operation(
            request("ZOTERO_LINK_EXISTING"),
            self.config,
            observation(item(doi="10.1000/example")),
        )
        self.assertEqual(plan.decision, "LINK_EXISTING")
        self.assertFalse(plan.zotero_mutation_planned)

    def test_known_existing_item_key_is_an_exact_identity_basis(self) -> None:
        req = request(
            "ZOTERO_LINK_EXISTING",
            payload={"known_item_key": "ITEMA"},
        )
        plan = executor.plan_operation(req, self.config, observation(item("ITEMA")))
        self.assertEqual(plan.decision, "LINK_EXISTING")

    def test_link_existing_no_exact_target_fails_closed(self) -> None:
        plan = executor.plan_operation(
            request("ZOTERO_LINK_EXISTING"), self.config, observation()
        )
        self.assertEqual(plan.decision, "NEEDS_REVIEW")
        self.assertEqual(plan.reason_code, "NO_EXACT_TARGET")

    def test_link_existing_fuzzy_target_is_not_authorized(self) -> None:
        plan = executor.plan_operation(
            request("ZOTERO_LINK_EXISTING"),
            self.config,
            observation(item(fuzzy_match=True)),
        )
        self.assertEqual(plan.reason_code, "FUZZY_MATCH_NOT_AUTHORIZED")

    def mutation_request(self, operation: str, **payload_updates: object) -> executor.OperationRequest:
        payload = {
            "target_item_key": "ITEMA",
            "expected_zotero_object_version": 7,
            "version_space": "web_api",
        }
        payload["collection_key" if operation == "ADD_COLLECTION" else "tag"] = "VALUE"
        payload.update(payload_updates)
        return request(operation, payload=payload)

    def test_add_collection_already_present_is_noop(self) -> None:
        plan = executor.plan_operation(
            self.mutation_request("ADD_COLLECTION"),
            self.config,
            observation(item(collections=["VALUE"])),
        )
        self.assertEqual(plan.decision, "SUCCESS_NOOP")

    def test_add_collection_requires_matching_object_version(self) -> None:
        plan = executor.plan_operation(
            self.mutation_request("ADD_COLLECTION"),
            self.config,
            observation(item()),
        )
        self.assertEqual(plan.decision, "MUTATE_EXISTING")
        self.assertEqual(plan.expected_zotero_object_version, 7)

    def test_stale_collection_mutation_is_replanned_not_blind(self) -> None:
        plan = executor.plan_operation(
            self.mutation_request("ADD_COLLECTION", expected_zotero_object_version=6),
            self.config,
            observation(item()),
        )
        self.assertEqual(plan.decision, "RETRY_ELIGIBLE")
        self.assertEqual(plan.reason_code, "STALE_ZOTERO_OBJECT")
        self.assertEqual(plan.expected_zotero_object_version, 7)
        self.assertTrue(plan.requires_full_preflight)

    def test_version_spaces_are_never_compared(self) -> None:
        plan = executor.plan_operation(
            self.mutation_request("ADD_COLLECTION", version_space="local_api"),
            self.config,
            observation(item(version_space="web_api")),
        )
        self.assertEqual(plan.reason_code, "VERSION_SPACE_MISMATCH")

    def test_add_tag_idempotency(self) -> None:
        present = executor.plan_operation(
            self.mutation_request("ADD_TAG"),
            self.config,
            observation(item(tags=["VALUE"])),
        )
        absent = executor.plan_operation(
            self.mutation_request("ADD_TAG"), self.config, observation(item())
        )
        self.assertEqual(present.decision, "SUCCESS_NOOP")
        self.assertEqual(absent.decision, "MUTATE_EXISTING")

    def test_lost_response_zero_exact_is_safe_retry_candidate(self) -> None:
        plan = executor.plan_operation(request(), self.config, observation(uncertain=True))
        self.assertEqual(plan.decision, "SAFE_RETRY_CANDIDATE")
        self.assertTrue(plan.requires_full_preflight)
        self.assertFalse(plan.zotero_mutation_planned)

    def test_lost_response_one_exact_recovers_existing_write(self) -> None:
        plan = executor.plan_operation(
            request(),
            self.config,
            observation(item(doi="10.1000/example"), uncertain=True),
        )
        self.assertEqual(plan.decision, "RECOVER_EXISTING_WRITE")
        self.assertEqual(plan.ledger_state, "EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT")

    def test_lost_response_ambiguous_never_blind_reposts(self) -> None:
        for observed in (
            observation(item(fuzzy_match=True), uncertain=True),
            observation(
                item("ITEMA", doi="10.1000/example"),
                item("ITEMB", doi="10.1000/example"),
                uncertain=True,
            ),
        ):
            with self.subTest(items=len(observed.items)):
                plan = executor.plan_operation(request(), self.config, observed)
                self.assertEqual(plan.decision, "NEEDS_REVIEW")
                self.assertFalse(plan.zotero_mutation_planned)


class LedgerTests(unittest.TestCase):
    def entry(self, state: executor.LedgerState, **updates: object) -> executor.LedgerEntry:
        values = {
            "external_operation_identity": "ZOP-" + "a" * 64,
            "source_id": "SRC-000001",
            "library_alias": "project-main",
            "operation_type": "ZOTERO_CREATE",
            "normalized_payload_sha256": "b" * 64,
            "state": state,
        }
        values.update(updates)
        return executor.LedgerEntry(**values)

    def test_frozen_ledger_state_set_is_exactly_nine(self) -> None:
        expected = {
            "PENDING",
            "DRY_RUN_VALID",
            "EXTERNAL_WRITE_ATTEMPTED",
            "EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT",
            "GIT_RECONCILIATION_PREPARED",
            "GIT_RECONCILED",
            "FAILED_RETRYABLE",
            "FAILED_TERMINAL",
            "NEEDS_REVIEW",
        }
        self.assertEqual({state.value for state in executor.LedgerState}, expected)
        self.assertEqual(len(executor.LedgerState), 9)

    def test_complete_nine_by_nine_transition_matrix(self) -> None:
        for previous in executor.LedgerState:
            for next_state in executor.LedgerState:
                allowed = (previous, next_state) in executor.ALLOWED_LEDGER_TRANSITIONS
                with self.subTest(previous=previous.value, next_state=next_state.value):
                    if allowed:
                        executor.validate_ledger_transition(previous, next_state)
                    else:
                        with self.assertRaises(executor.ExecutorFailure) as caught:
                            executor.validate_ledger_transition(previous, next_state)
                        self.assertEqual(caught.exception.code, "INVALID_LEDGER_TRANSITION")

    def test_transient_state_cannot_deserialize_as_ledger_state(self) -> None:
        for transient in ("PREFLIGHT_VALID", "EXACT_SINGLE_MATCH", "STALE_OBJECT"):
            with self.subTest(transient=transient):
                document = self.entry(executor.LedgerState.PENDING).serializable()
                document["state"] = transient
                with self.assertRaises(executor.ExecutorFailure):
                    executor.LedgerEntry.from_mapping(document)

    def test_reconciled_replay_is_success_noop(self) -> None:
        ledger = executor.InMemoryOperationLedger()
        entry = self.entry(executor.LedgerState.GIT_RECONCILED, item_key="ITEMA")
        ledger.record(entry)
        result = ledger.record(entry)
        self.assertEqual(result.status, "SUCCESS_NOOP")

    def test_identity_collision_is_rejected(self) -> None:
        ledger = executor.InMemoryOperationLedger()
        ledger.record(self.entry(executor.LedgerState.PENDING))
        with self.assertRaises(executor.ExecutorFailure) as caught:
            ledger.record(
                self.entry(
                    executor.LedgerState.DRY_RUN_VALID,
                    normalized_payload_sha256="c" * 64,
                )
            )
        self.assertEqual(caught.exception.code, "OPERATION_IDENTITY_COLLISION")

    def test_temporary_ledger_round_trip_and_cleanup(self) -> None:
        with executor.TemporaryFileOperationLedger() as ledger:
            ledger.record(self.entry(executor.LedgerState.PENDING))
            ledger.record(self.entry(executor.LedgerState.DRY_RUN_VALID))
            path = ledger.path
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("credential", text)
            ledger.reload()
            self.assertEqual(
                ledger.get("ZOP-" + "a" * 64).state,
                executor.LedgerState.DRY_RUN_VALID,
            )
        self.assertFalse(path.exists())


class ReconciliationAndBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = executor.IntegrationConfig.load(CONFIG_PATH)
        cls.protected_before = {
            relative: digest(ROOT / relative) for relative in PROTECTED_PATHS
        }

    def test_git_reconciliation_payload_is_narrow_and_has_no_citation_key(self) -> None:
        req = request()
        plan = executor.plan_operation(req, self.config, observation())
        payload = executor.build_git_reconciliation_payload(
            req,
            plan,
            executor.OperationResult("SUCCESS", item_key="SERVERKEY"),
        )
        serialized = payload.serializable()
        self.assertEqual(
            serialized["proposed_source_update"]["zotero"]["item_key"],
            "SERVERKEY",
        )
        self.assertNotIn("citation_key", json.dumps(serialized))
        self.assertEqual(serialized["reconciliation_status"], "PROPOSED_FOR_01A_REVIEW")

    def test_git_reconciliation_requires_git_and_record_preconditions(self) -> None:
        doc = request_document()
        doc.pop("expected_git_head")
        req = executor.OperationRequest.from_mapping(doc)
        plan = executor.plan_operation(req, self.config, observation())
        with self.assertRaises(executor.ExecutorFailure) as caught:
            executor.build_git_reconciliation_payload(
                req,
                plan,
                executor.OperationResult("SUCCESS", item_key="SERVERKEY"),
            )
        self.assertEqual(caught.exception.code, "GIT_RECONCILIATION_PRECONDITION_FAILED")

    def test_git_reconciliation_rejects_unsuccessful_result(self) -> None:
        req = request()
        plan = executor.plan_operation(req, self.config, observation())
        with self.assertRaises(executor.ExecutorFailure) as caught:
            executor.build_git_reconciliation_payload(
                req,
                plan,
                executor.OperationResult("FAILED_RETRYABLE", item_key="SERVERKEY"),
            )
        self.assertEqual(caught.exception.code, "GIT_RECONCILIATION_PRECONDITION_FAILED")

    def test_forbidden_transport_fails_with_frozen_code(self) -> None:
        with self.assertRaises(executor.ExecutorFailure) as caught:
            executor.ForbiddenTransport().observe(request())
        self.assertEqual(caught.exception.code, "NETWORK_FORBIDDEN_IN_PHASE2")

    def test_fixture_transport_uses_only_in_memory_observation(self) -> None:
        observed = observation(item(doi="10.1000/example"))
        self.assertIs(executor.FixtureTransport(observed).observe(request()), observed)

    def test_production_source_has_no_real_network_or_credential_path(self) -> None:
        source = (ROOT / "scripts/literature/zotero_executor.py").read_text(encoding="utf-8")
        forbidden = (
            "import requests",
            "import httpx",
            "import urllib.request",
            "import pyzotero",
            "import socket",
            "os.environ",
            "keyring",
            "localhost:",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_self_test_emits_single_machine_readable_object(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            return_code = executor.main(["self-test"])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(return_code, 0)
        self.assertEqual(len(lines), 1)
        result = json.loads(lines[0])
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["network_used"])

    def test_plan_cli_accepts_unconfigured_config_and_emits_one_json_object(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zotero-phase2-cli-") as temporary:
            root = Path(temporary)
            request_path = root / "request.yaml"
            fixture_path = root / "fixture.yaml"
            request_path.write_text(
                yaml.safe_dump(request_document(), sort_keys=False), encoding="utf-8"
            )
            fixture_path.write_text("items: []\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return_code = executor.main(
                    [
                        "plan",
                        "--request",
                        str(request_path),
                        "--fixture",
                        str(fixture_path),
                        "--config",
                        str(CONFIG_PATH),
                    ]
                )
        self.assertEqual(return_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        result = json.loads(lines[0])
        self.assertEqual(result["configuration_status"], "unconfigured")
        self.assertEqual(result["decision"], "CREATE")

    def test_no_arguments_prints_usage_to_stderr_and_exits_two(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                executor.main([])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("usage:", stderr.getvalue())

    def test_canonical_repository_state_is_unchanged(self) -> None:
        protected_after = {
            relative: digest(ROOT / relative) for relative in PROTECTED_PATHS
        }
        self.assertEqual(self.protected_before, protected_after)
        self.assertFalse((ROOT / "05_Literature/ZOTERO_OPERATION_LOG.yaml").exists())
        self.assertFalse((ROOT / "05_Literature/references.bib").exists())


def network_forbidden(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("network access attempted by Phase-2 synthetic tests")


if __name__ == "__main__":
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.casefold()
        not in {
            "zotero_api_key",
            "zotero_token",
            "zotero_access_token",
        }
    }
    with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
        "socket.socket", side_effect=network_forbidden
    ), mock.patch(
        "socket.create_connection", side_effect=network_forbidden
    ), mock.patch(
        "urllib.request.urlopen", side_effect=network_forbidden
    ):
        unittest.main(verbosity=2)
