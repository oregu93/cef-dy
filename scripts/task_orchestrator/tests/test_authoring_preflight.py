from __future__ import annotations

from copy import deepcopy
import unittest

from task_orchestrator.authoring import (
    interface_manifest, preflight_authoring, validate_preflight_receipt,
)
from task_orchestrator.model import ValidationError
from task_orchestrator.schema import ACTIONS, validate_task
from task_orchestrator.store import Store

from .common import Fixture


class AuthoringPreflightTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def task_data(self, task_id: str = "INFRA-AUTHOR-001", **overrides):
        value = {
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
            "allowed_paths": ["scripts"],
            "expected_artifacts": [],
            "timeout_seconds": 60,
            "stop_condition": "Stop after bounded validation.",
        }
        value.update(overrides)
        return value

    def request(self, *, operation="NEW_ISSUE", task=None, issue_number=None,
                existing=None, materialization_state="NOT_STATE_CHANGING"):
        task = task or self.task_data()
        parsed = validate_task(task, source_issue=issue_number,
                               labels=("orchestrator:task",))
        lifecycle_target = existing if operation in {"SUPERSEDE", "CLOSE"} else {
            "task_id": parsed.task_id, "envelope_hash": parsed.envelope_hash,
        }
        disposition = "CURRENT"
        successor = None
        reason = None
        if operation == "SUPERSEDE":
            disposition, successor, reason = "SUPERSEDED", parsed.task_id, "Replaced by reviewed successor."
        if operation == "CLOSE":
            disposition, reason = "CLOSED_HISTORICAL", "Accepted historical closure."
        return {
            "schema_version": 1,
            "operation_type": operation,
            "author_role": "00_PROJECT_CONTROL",
            "canonical_head": self.fx.head,
            "issue": {
                "number": issue_number,
                "state": "closed" if operation == "CLOSE" else "open",
                "labels": ["orchestrator:task"],
            },
            "task": task,
            "existing_binding": existing,
            "required_repository_paths": ["scripts/README.md"],
            "dependency_bindings": [],
            "review_binding": None,
            "accepted_state_changes": [{
                "identity": "DECISION-TEST-001",
                "result_sha256": "a" * 64,
                "materialization_state": materialization_state,
                "materialization_commit": self.fx.head if materialization_state == "MATERIALIZED" else None,
                "reason": "Explicit bounded deferral." if materialization_state == "EXPLICITLY_DEFERRED_WITH_REASON" else None,
            }],
            "context_delta_bundle": None,
            "lifecycle": {
                "disposition": disposition,
                "target_task_id": lifecycle_target["task_id"],
                "target_envelope_hash": lifecycle_target["envelope_hash"],
                "successor_task_id": successor,
                "reason": reason,
            },
            "project_status": {
                "project_progress": "IN_PROGRESS",
                "human_action_required": False,
                "semantic_state": "ACCEPTED",
                "design_state": "REVIEWED",
                "implementation_state": "AUTHORIZED",
                "deployment_state": "NOT_AUTHORIZED",
                "canonicalization_state": materialization_state,
            },
            "execution_context": "SEPARATE_BOUNDED_WORK",
            "persistent_chat_role": "00_PROJECT_CONTROL",
            "chatgpt_scheduler_requested": False,
        }

    def run_preflight(self, request):
        return preflight_authoring(
            request, self.fx.cfg, observed_canonical_head=self.fx.head,
        )

    def test_manifest_is_derived_from_executable_contract(self):
        manifest = interface_manifest()
        self.assertEqual(manifest["actions"], sorted(ACTIONS))
        self.assertEqual(manifest["resource_suitability"]["DETERMINISTIC_REQUIRED"],
                         ["LOCAL_DETERMINISTIC"])
        self.assertEqual(manifest["persistent_project_control_mode"], "NON_WORK")
        self.assertFalse(manifest["chatgpt_scheduler_authorized"])

    def test_valid_new_issue_returns_deterministic_authorizing_receipt(self):
        request = self.request(materialization_state="MATERIALIZED")
        first = self.run_preflight(request)
        second = self.run_preflight(request)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PREFLIGHT_PASS")
        self.assertEqual(first["state_freshness"], "FRESH")
        self.assertEqual(validate_preflight_receipt(first), first)

    def test_malformed_task_envelope_is_rejected_before_issue_authoring(self):
        request = self.request()
        request["task"]["unexpected"] = True
        with self.assertRaisesRegex(ValidationError, "unknown task fields"):
            self.run_preflight(request)

    def test_canonical_head_drift_is_rejected(self):
        request = self.request()
        with self.assertRaisesRegex(ValidationError, "canonical HEAD drift"):
            preflight_authoring(request, self.fx.cfg, observed_canonical_head="f" * 40)

    def test_existing_issue_task_identity_is_immutable(self):
        old = validate_task(self.task_data("INFRA-OLD-001"))
        existing = {"source_issue": 12, "task_id": old.task_id,
                    "envelope_hash": old.envelope_hash}
        request = self.request(operation="UPDATE_EXISTING", issue_number=12,
                               existing=existing)
        with self.assertRaisesRegex(ValidationError, "cannot be rebound"):
            self.run_preflight(request)

    def test_rerun_and_supersession_require_explicit_original_binding(self):
        old = validate_task(self.task_data("INFRA-OLD-002"))
        existing = {"source_issue": 13, "task_id": old.task_id,
                    "envelope_hash": old.envelope_hash}
        rerun_task = self.task_data("INFRA-RERUN-002", inputs={
            "resource_requirement": "DETERMINISTIC_REQUIRED",
            "allowed_lanes": ["LOCAL_DETERMINISTIC"], "rerun_of": old.task_id,
        })
        receipt = self.run_preflight(self.request(
            operation="RERUN", task=rerun_task, existing=existing,
        ))
        self.assertEqual(receipt["status"], "PREFLIGHT_PASS")
        bad = self.request(operation="SUPERSEDE", task=self.task_data("INFRA-NEW-002"),
                           existing=existing)
        with self.assertRaisesRegex(ValidationError, "supersedes_task_id"):
            self.run_preflight(bad)

    def test_labels_resource_lane_and_scope_are_checked(self):
        request = self.request()
        request["issue"]["labels"] = []
        with self.assertRaisesRegex(ValidationError, "task label"):
            self.run_preflight(request)
        request = self.request()
        request["task"]["inputs"]["allowed_lanes"] = ["HUMAN_DECISION"]
        with self.assertRaises(ValidationError):
            self.run_preflight(request)
        request = self.request()
        request["required_repository_paths"] = ["00_Project/PROJECT_STATE.md"]
        with self.assertRaisesRegex(ValidationError, "outside"):
            self.run_preflight(request)

    def test_dependency_material_is_exactly_bound(self):
        task = self.task_data(
            "INFRA-DEPENDENT-001", task_type="llm_worker", action="semantic_helper",
            dependencies=["INFRA-PARENT-001"],
            inputs={
                "resource_requirement": "WORK_REQUIRED",
                "allowed_lanes": ["WORK_CODEX"],
                "bind_dependency_results": True,
            },
        )
        request = self.request(task=task)
        request["issue"]["labels"].append("orchestrator:llm-approved")
        request["dependency_bindings"] = [{
            "task_id": "INFRA-PARENT-001", "result_sha256": "b" * 64,
            "canonical_head": self.fx.head, "status": "SUCCEEDED",
        }]
        self.assertEqual(self.run_preflight(request)["status"], "PREFLIGHT_PASS")
        request["dependency_bindings"] = []
        with self.assertRaisesRegex(ValidationError, "exactly cover"):
            self.run_preflight(request)

    def test_independent_review_requires_exact_parent_role_and_material(self):
        task = self.task_data(
            "INFRA-REVIEW-001", task_type="llm_worker", action="semantic_helper",
            inputs={
                "resource_requirement": "WORK_REQUIRED", "allowed_lanes": ["WORK_CODEX"],
                "independent_review": True, "review_of": "INFRA-PARENT-002",
                "accepted_result_sha256": "c" * 64,
                "review_material_sha256": "d" * 64,
            },
        )
        request = self.request(task=task)
        request["issue"]["labels"].append("orchestrator:llm-approved")
        request["review_binding"] = {
            "parent_task_id": "INFRA-PARENT-002", "review_task_id": "INFRA-REVIEW-001",
            "review_role": "07_RESEARCH_SOFTWARE_INFRASTRUCTURE",
            "accepted_result_sha256": "c" * 64, "review_material_sha256": "d" * 64,
        }
        self.assertEqual(self.run_preflight(request)["status"], "PREFLIGHT_PASS")
        request["review_binding"]["review_task_id"] = "INFRA-ALT-REVIEW-001"
        with self.assertRaisesRegex(ValidationError, "exact review TASK"):
            self.run_preflight(request)

    def test_pending_materialization_stops_unbound_dependent_authoring(self):
        request = self.request(materialization_state="PENDING_MATERIALIZATION")
        receipt = self.run_preflight(request)
        self.assertEqual(receipt["status"], "STATE_SYNC_REQUIRED")
        self.assertEqual(receipt["state_freshness"], "STATE_SYNC_REQUIRED")
        with self.assertRaisesRegex(ValidationError, "not authorizing"):
            validate_preflight_receipt(receipt)

    def test_exact_context_delta_binds_pending_materialization(self):
        request = self.request(materialization_state="PENDING_MATERIALIZATION")
        request["context_delta_bundle"] = {
            "bundle_id": "CONTEXT-DELTA-001", "sha256": "e" * 64,
            "pending_materialization_ids": ["DECISION-TEST-001"],
            "review_id": "REVIEW-001", "review_result_sha256": "f" * 64,
            "mandatory_later_materialization": True,
        }
        receipt = self.run_preflight(request)
        self.assertEqual(receipt["status"], "PREFLIGHT_PASS")
        self.assertEqual(receipt["state_freshness"], "CONTEXT_DELTA_BOUND")

    def test_all_four_materialization_states_are_exact(self):
        for state in (
            "MATERIALIZED", "PENDING_MATERIALIZATION",
            "EXPLICITLY_DEFERRED_WITH_REASON", "NOT_STATE_CHANGING",
        ):
            with self.subTest(state=state):
                receipt = self.run_preflight(self.request(materialization_state=state))
                self.assertEqual(receipt["accepted_state_changes"][0]["materialization_state"], state)
        request = self.request(materialization_state="EXPLICITLY_DEFERRED_WITH_REASON")
        request["accepted_state_changes"][0]["reason"] = None
        with self.assertRaises(ValidationError):
            self.run_preflight(request)

    def test_project_progress_and_human_action_are_independent_dimensions(self):
        request = self.request()
        request["project_status"]["project_progress"] = "COMPLETED"
        request["project_status"]["human_action_required"] = True
        receipt = self.run_preflight(request)
        self.assertEqual(receipt["project_progress"], "COMPLETED")
        self.assertTrue(receipt["human_action_required"])

    def test_persistent_project_control_cannot_become_work_or_scheduler(self):
        request = self.request()
        request["execution_context"] = "PERSISTENT_NON_WORK"
        with self.assertRaisesRegex(ValidationError, "NON-WORK"):
            self.run_preflight(request)
        request = self.request()
        request["chatgpt_scheduler_requested"] = True
        with self.assertRaisesRegex(ValidationError, "scheduler"):
            self.run_preflight(request)

    def test_receipt_tampering_is_rejected(self):
        receipt = self.run_preflight(self.request())
        receipt["human_action_required"] = True
        with self.assertRaisesRegex(ValidationError, "identity mismatch"):
            validate_preflight_receipt(receipt)

    def test_store_accepts_only_bound_receipt_and_preserves_history(self):
        task_data = self.task_data("INFRA-HISTORY-001")
        task = validate_task(task_data, source_issue=21, labels=("orchestrator:task",))
        existing = {"source_issue": 21, "task_id": task.task_id,
                    "envelope_hash": task.envelope_hash}
        request = self.request(operation="CLOSE", task=task_data, issue_number=21,
                               existing=existing)
        receipt = self.run_preflight(request)
        store = Store(self.fx.root / "authoring.sqlite3")
        try:
            store.ingest(task)
            store.conn.execute("UPDATE tasks SET state='FAILED' WHERE task_id=?", (task.task_id,))
            self.assertEqual(store.put_authoring_receipt(receipt), "created")
            self.assertEqual(store.put_authoring_receipt(receipt), "duplicate")
            self.assertEqual(store.lifecycle_disposition(task.task_id), "CLOSED_HISTORICAL")
            self.assertEqual(store.conn.execute(
                "SELECT count(*) FROM authoring_receipts"
            ).fetchone()[0], 1)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
