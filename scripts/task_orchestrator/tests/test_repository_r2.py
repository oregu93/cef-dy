from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
from unittest import mock

import yaml
import kb_validate

from task_orchestrator.authoring import (
    R2_ISSUE8_ACCEPTED_RESULT_SHA256,
    R2_ISSUE8_AUTHORITY_ID,
    R2_ISSUE8_AUTHORITY_SHA256,
    R2_ISSUE8_DEBT_ID,
    R2_ISSUE8_TASK_CANONICAL_HEAD,
    R2_ISSUE8_TASK_ID,
    preflight_authoring,
    reconcile_repository_r2_issue8,
    task_status_projection,
)
from task_orchestrator.current_state import load_repository_authority
from task_orchestrator.dashboard import snapshot
from task_orchestrator.model import ValidationError
from task_orchestrator.reliability import M1bStore
from task_orchestrator.schema import validate_task
from task_orchestrator.store import Store

from .common import Fixture


class RepositoryR2Tests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    @property
    def ledger_path(self) -> Path:
        return self.fx.root / "00_Project" / "MATERIALIZATION_DEBT_LEDGER.yaml"

    def debt_item(
        self, identity: str, *, state: str = "PENDING_MATERIALIZATION",
        roles=None, paths=None, task_ids=None, decision_changing=True,
        result_sha256: str = "b" * 64,
    ):
        return {
            "identity": identity,
            "state": state,
            "reason": None,
            "source": {
                "kind": "test_authority",
                "identity": f"test:{identity}",
                "result_sha256": result_sha256,
            },
            "evidence_paths": ["safe.txt"],
            "affected_roles": roles or [],
            "affected_paths": paths or [],
            "affected_task_ids": task_ids or [],
            "decision_changing": decision_changing,
            "target_batch": "TEST",
            "materialization_commit": None,
        }

    def set_debt(self, *items):
        value = yaml.safe_load(self.ledger_path.read_text(encoding="utf-8"))
        value["items"] = sorted(deepcopy(items), key=lambda item: item["identity"])
        value["inventory_ids"] = [item["identity"] for item in value["items"]]
        self.ledger_path.write_text(
            yaml.safe_dump(value, sort_keys=False), encoding="utf-8",
        )

    def task_data(self, task_id="INFRA-R2-TEST-001"):
        return {
            "schema_version": 1,
            "task_id": task_id,
            "role": "07_INFRASTRUCTURE",
            "canonical_head": self.fx.head,
            "task_type": "deterministic",
            "action": "head_check",
            "dependencies": [],
            "inputs": {
                "resource_requirement": "DETERMINISTIC_REQUIRED",
                "allowed_lanes": ["LOCAL_DETERMINISTIC"],
            },
            "allowed_paths": ["scripts/task_orchestrator"],
            "expected_artifacts": [],
            "timeout_seconds": 60,
            "stop_condition": "Stop after exact validation.",
        }

    def request(self, *, include_debt=None):
        task = self.task_data()
        parsed = validate_task(task, labels=("orchestrator:task",))
        changes = [{
            "identity": "DECISION-TEST-NON-STATE-CHANGING",
            "result_sha256": "a" * 64,
            "materialization_state": "NOT_STATE_CHANGING",
            "materialization_commit": None,
            "reason": None,
        }]
        context = None
        if include_debt:
            changes.append({
                "identity": include_debt["identity"],
                "result_sha256": include_debt["source"]["result_sha256"],
                "materialization_state": "PENDING_MATERIALIZATION",
                "materialization_commit": None,
                "reason": None,
            })
            context = {
                "bundle_id": "TEST-EXACT-DELTA",
                "sha256": "c" * 64,
                "pending_materialization_ids": [include_debt["identity"]],
                "review_id": "TEST-REVIEW",
                "review_result_sha256": "d" * 64,
                "mandatory_later_materialization": True,
            }
        return {
            "schema_version": 1,
            "operation_type": "NEW_ISSUE",
            "author_role": "00_PROJECT_CONTROL",
            "canonical_head": self.fx.head,
            "issue": {"number": None, "state": "open", "labels": ["orchestrator:task"]},
            "task": task,
            "existing_binding": None,
            "required_repository_paths": ["scripts/task_orchestrator/authoring.py"],
            "dependency_bindings": [],
            "review_binding": None,
            "accepted_state_changes": changes,
            "context_delta_bundle": context,
            "lifecycle": {
                "disposition": "CURRENT", "target_task_id": parsed.task_id,
                "target_envelope_hash": parsed.envelope_hash,
                "successor_task_id": None, "reason": None,
            },
            "project_status": {
                "project_progress": "IN_PROGRESS", "human_action_required": False,
                "semantic_state": "AUTHORIZED", "design_state": "REVIEWED",
                "implementation_state": "NOT_STARTED",
                "deployment_state": "NOT_AUTHORIZED",
                "canonicalization_state": "PENDING_MATERIALIZATION",
            },
            "execution_context": "SEPARATE_BOUNDED_WORK",
            "persistent_chat_role": "00_PROJECT_CONTROL",
            "chatgpt_scheduler_requested": False,
        }

    def test_stale_assessed_head_fails_closed(self):
        with self.assertRaisesRegex(ValidationError, "assessed_head drift"):
            load_repository_authority(
                self.fx.root, expected_canonical_head="f" * 40,
            )

    def test_strict_validator_detects_authority_freshness_drift(self):
        metadata = self.fx.root / "00_Project" / "PROJECT_METADATA.yaml"
        manifest = self.fx.root / "PROJECT_MANIFEST.yaml"
        metadata.write_text(yaml.safe_dump({
            "canonical_state_freshness": {
                "assessed_head": self.fx.head,
                "record_path": "00_Project/CANONICAL_STATE_FRESHNESS.yaml",
                "debt_ledger_path": "00_Project/MATERIALIZATION_DEBT_LEDGER.yaml",
            },
        }), encoding="utf-8")
        manifest.write_text(yaml.safe_dump({
            "canonical_repository": {"assessed_head": self.fx.head},
            "authoritative": {
                "canonical_state_freshness": "00_Project/CANONICAL_STATE_FRESHNESS.yaml",
                "materialization_debt_ledger": "00_Project/MATERIALIZATION_DEBT_LEDGER.yaml",
            },
        }), encoding="utf-8")
        path = self.fx.root / "00_Project" / "CANONICAL_STATE_FRESHNESS.yaml"
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        value["assessed_head"] = "f" * 40
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
        issues = []
        with mock.patch.multiple(
            kb_validate, ROOT=self.fx.root, META=metadata, MANIFEST=manifest,
        ):
            kb_validate.canonical_authority_checks(issues)
        self.assertTrue(any(
            item["level"] == "error" and (
                "CANONICAL_STATE_FRESHNESS" in item["file"]
                or "freshness" in item["message"]
            )
            for item in issues
        ))

    def test_omitted_known_relevant_debt_fails_admission(self):
        relevant = self.debt_item(
            "INFRA-RELEVANT-DEBT-001",
            roles=["07_INFRASTRUCTURE"],
            paths=["scripts/task_orchestrator"],
        )
        self.set_debt(relevant)
        with self.assertRaisesRegex(ValidationError, "known relevant repository debt omitted"):
            preflight_authoring(
                self.request(), self.fx.cfg, observed_canonical_head=self.fx.head,
            )

    def test_exact_delta_accepts_relevant_debt_and_unrelated_debt_does_not_block(self):
        relevant = self.debt_item(
            "INFRA-RELEVANT-DEBT-001",
            roles=["07_INFRASTRUCTURE"], paths=["scripts/task_orchestrator"],
        )
        unrelated = self.debt_item(
            "LITERATURE-UNRELATED-DEBT-001",
            state="UNRESOLVED_SOURCE_RECOVERY",
            roles=["01_LITERATURE_PHYSICS"], paths=["05_Literature"],
        )
        self.set_debt(relevant, unrelated)
        receipt = preflight_authoring(
            self.request(include_debt=relevant), self.fx.cfg,
            observed_canonical_head=self.fx.head,
        )
        self.assertEqual(receipt["status"], "PREFLIGHT_PASS")
        self.assertEqual(receipt["repository_relevant_debt_ids"], [relevant["identity"]])

    def test_issue8_reconciliation_is_idempotent_and_preserves_failed_history(self):
        self.set_debt(self.debt_item(
            R2_ISSUE8_DEBT_ID,
            roles=["00_PROJECT_CONTROL", "07_INFRASTRUCTURE"],
            task_ids=[R2_ISSUE8_TASK_ID],
            result_sha256=R2_ISSUE8_AUTHORITY_SHA256,
        ))
        authority_source = (
            Path(__file__).resolve().parents[3]
            / "00_Project" / "R2_ISSUE8_LIFECYCLE_AUTHORITY.yaml"
        )
        authority_target = (
            self.fx.root / "00_Project" / "R2_ISSUE8_LIFECYCLE_AUTHORITY.yaml"
        )
        authority_target.write_text(
            authority_source.read_text(encoding="utf-8"), encoding="utf-8",
        )
        store = Store(self.fx.root / "state" / "state.sqlite3")
        try:
            M1bStore(store.conn, self.fx.cfg)
            task = self.fx.task(
                R2_ISSUE8_TASK_ID,
                source_issue=8,
                canonical_head=R2_ISSUE8_TASK_CANONICAL_HEAD,
                role="07_RESEARCH_SOFTWARE_INFRASTRUCTURE",
                task_type="llm_worker",
                action="semantic_helper",
                inputs={
                    "resource_requirement": "LOCAL_SEMANTIC_OK",
                    "allowed_lanes": ["LOCAL_OSS_MODEL", "NON_WORK_AI", "WORK_CODEX"],
                },
                labels=("orchestrator:task", "orchestrator:llm-approved"),
            )
            store.ingest(task)
            store.conn.execute(
                "UPDATE tasks SET state='FAILED',reason='historical protocol defect' WHERE task_id=?",
                (task.task_id,),
            )
            store.conn.execute(
                "INSERT INTO accepted_results(task_id,attempt_id,result_sha256,result_json,accepted_at) "
                "VALUES(?,?,?,?,?)",
                (task.task_id, "attempt-1", R2_ISSUE8_ACCEPTED_RESULT_SHA256,
                 '{"status":"FAILED"}', "2026-10-01T00:00:00Z"),
            )
            with mock.patch(
                "task_orchestrator.authoring.R2_ISSUE8_ENVELOPE_SHA256",
                task.envelope_hash,
            ):
                artifact = yaml.safe_load(authority_target.read_text(encoding="utf-8"))
                artifact["target"]["envelope_sha256"] = task.envelope_hash
                authority_target.write_text(
                    yaml.safe_dump(artifact, sort_keys=False), encoding="utf-8",
                )
                first = reconcile_repository_r2_issue8(
                    store, self.fx.cfg, observed_canonical_head=self.fx.head,
                    authority_id=R2_ISSUE8_AUTHORITY_ID,
                    authority_result_sha256=R2_ISSUE8_AUTHORITY_SHA256,
                )
                second = reconcile_repository_r2_issue8(
                    store, self.fx.cfg, observed_canonical_head=self.fx.head,
                    authority_id=R2_ISSUE8_AUTHORITY_ID,
                    authority_result_sha256=R2_ISSUE8_AUTHORITY_SHA256,
                )
            self.assertEqual((first["status"], second["status"]), ("created", "duplicate"))
            row = store.get(task.task_id)
            self.assertEqual(row["state"], "FAILED")
            projection = task_status_projection(
                task_id=task.task_id, envelope_hash=task.envelope_hash,
                fsm_state=row["state"], receipt=store.latest_authoring_receipt(task.task_id),
            )
            self.assertTrue(projection["historical_non_actionable"])
            self.assertFalse(projection["human_action_required"])
            self.assertEqual(projection["semantic_state"], "SUPERSEDED_DIAGNOSTIC")
        finally:
            store.close()

    def test_current_facades_bind_the_same_exact_head_and_boundaries(self):
        root = Path(__file__).resolve().parents[3]
        head = "45fcf89f5a2571d534da6cf3f70018d3de620d7e"
        for relative in (
            "README.md", "00_Project/PROJECT_STATE.md",
            "00_Project/PROJECT_CONTROL.md", "00_Project/PROJECT_METADATA.yaml",
            "00_Project/CANONICAL_STATE_FRESHNESS.yaml", "PROJECT_MANIFEST.yaml",
        ):
            self.assertIn(head, (root / relative).read_text(encoding="utf-8"))
        combined = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in ("README.md", "00_Project/PROJECT_STATE.md", "00_Project/PROJECT_CONTROL.md")
        )
        for boundary in (
            "LEVEL_2", "LEVEL_3", "Stage03D", "exchange", "holdout", "18.247",
        ):
            self.assertIn(boundary, combined)

    def test_dashboard_epistemic_freshness_prevents_hidden_green(self):
        store = Store(self.fx.root / "state" / "state.sqlite3")
        try:
            M1bStore(store.conn, self.fx.cfg)
            fresh = snapshot(self.fx.cfg)
            self.assertEqual(fresh["canonical_state_freshness"]["state"], "FRESH")
            self.assertEqual(
                fresh["dashboard"]["components"]["canonical_state"]["state"],
                "HEALTHY",
            )
            path = self.fx.root / "00_Project" / "CANONICAL_STATE_FRESHNESS.yaml"
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            value["assessed_head"] = "f" * 40
            path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
            stale = snapshot(self.fx.cfg)
            self.assertEqual(stale["canonical_state_freshness"]["state"], "STALE")
            self.assertEqual(
                stale["dashboard"]["components"]["canonical_state"]["state"],
                "STALE",
            )
            self.assertNotEqual(stale["dashboard"]["health"], "HEALTHY")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
