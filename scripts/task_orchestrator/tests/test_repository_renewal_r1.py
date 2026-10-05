from __future__ import annotations

from copy import deepcopy
import unittest

from task_orchestrator.authoring import (
    R1_HISTORICAL_DISPOSITIONS,
    historical_disposition_receipt,
    preflight_authoring,
    task_status_projection,
)
from task_orchestrator.dashboard import snapshot
from task_orchestrator.model import ValidationError
from task_orchestrator.reliability import M1bStore
from task_orchestrator.store import Store
from task_orchestrator.telegram import TelegramGateway, TelegramSecrets

from .common import Fixture


class _NoNetworkTransport:
    def get_updates(self, *, offset, timeout_seconds):
        return []

    def send_message(self, *, text, reply_markup=None):
        raise AssertionError("R1 projection tests must not send Telegram messages")


class RepositoryRenewalR1Tests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.store = Store(self.fx.root / "state" / "state.sqlite3")
        self.control = M1bStore(self.store.conn, self.fx.cfg)
        self.control.checkpoint(
            CURRENT_PHASE="READY", CANONICAL_HEAD=self.fx.head,
            AI_LANE_STATE="AVAILABLE",
        )
        self.gateway = TelegramGateway(
            self.fx.cfg, self.store.conn, _NoNetworkTransport(),
            TelegramSecrets("test-placeholder-not-a-real-token", 1, 2),
        )

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def _receipt(
        self, task, disposition, *, project_progress="COMPLETED",
        semantic_state="HISTORICAL_COMPLETE", implementation_state="COMPLETED",
        deployment_state="DEPLOYED", canonicalization_state="MATERIALIZED",
    ):
        operation = "UPDATE_EXISTING" if disposition == "CURRENT" else "CLOSE"
        request = {
            "schema_version": 1, "operation_type": operation,
            "author_role": "00_PROJECT_CONTROL", "canonical_head": self.fx.head,
            "issue": {"number": task.source_issue,
                      "state": "open" if operation == "UPDATE_EXISTING" else "closed",
                      "labels": ["orchestrator:task"]},
            "task": task.envelope_dict(),
            "existing_binding": {
                "source_issue": task.source_issue, "task_id": task.task_id,
                "envelope_hash": task.envelope_hash,
            },
            "required_repository_paths": [], "dependency_bindings": [],
            "review_binding": None,
            "accepted_state_changes": [{
                "identity": "ISSUE-52-COMMENT-5994972384",
                "result_sha256": "a" * 64,
                "materialization_state": "NOT_STATE_CHANGING",
                "materialization_commit": None, "reason": None,
            }],
            "context_delta_bundle": None,
            "lifecycle": {
                "disposition": disposition, "target_task_id": task.task_id,
                "target_envelope_hash": task.envelope_hash,
                "successor_task_id": None,
                "reason": None if disposition == "CURRENT" else
                          "Project Control accepted this exact historical disposition.",
            },
            "project_status": {
                "project_progress": project_progress, "human_action_required": False,
                "semantic_state": semantic_state,
                "design_state": "REVIEWED", "implementation_state": implementation_state,
                "deployment_state": deployment_state,
                "canonicalization_state": canonicalization_state,
            },
            "execution_context": "SEPARATE_BOUNDED_WORK",
            "persistent_chat_role": "00_PROJECT_CONTROL",
            "chatgpt_scheduler_requested": False,
        }
        return preflight_authoring(
            request, self.fx.cfg, observed_canonical_head=self.fx.head,
        )

    def _stranded(self, task_id, state, disposition):
        task = self.fx.task(task_id, source_issue=1 if task_id == "INFRA-SHADOW-001" else 27)
        self.store.ingest(task)
        self.store.conn.execute(
            "UPDATE tasks SET state=?,reason='old operational handoff' WHERE task_id=?",
            (state, task_id),
        )
        self.store.put_authoring_receipt(self._receipt(task, disposition))
        return task

    def test_reviewed_reconciliation_targets_are_exact_and_not_task_id_shortcuts(self):
        self.assertEqual(set(R1_HISTORICAL_DISPOSITIONS), {
            "INFRA-SHADOW-001",
            "INFRA-CONVERGENCE-DASHBOARD-V2-PRODUCTION-DEPLOYMENT-001",
        })
        self.assertEqual(
            R1_HISTORICAL_DISPOSITIONS["INFRA-SHADOW-001"]["envelope_hash"],
            "e30e68e772a43fb1a2f5f39bce7d787866f81905962be41694591361476647d6",
        )
        self.assertEqual(
            R1_HISTORICAL_DISPOSITIONS[
                "INFRA-CONVERGENCE-DASHBOARD-V2-PRODUCTION-DEPLOYMENT-001"
            ]["envelope_hash"],
            "d099ee9c8aeb551f22371e4c474675102661bd36a64ebbe06b1e9178de707c02",
        )
        forged = task_status_projection(
            task_id="INFRA-SHADOW-001", envelope_hash="f" * 64,
            fsm_state="WAITING_APPROVAL",
        )
        self.assertTrue(forged["human_action_required"])
        self.assertFalse(forged["historical_non_actionable"])

    def test_historical_receipt_allows_only_exact_immutable_task_binding(self):
        old = self.fx.task(
            "IMMUTABLE-HISTORICAL-001", canonical_head="1" * 40, source_issue=88,
        )
        spec = {
            "source_issue": 88, "envelope_hash": old.envelope_hash,
            "disposition": "CLOSED_HISTORICAL", "reason": "Reviewed closure.",
            "semantic_state": "COMPLETE", "design_state": "REVIEWED",
            "implementation_state": "COMPLETED", "deployment_state": "NOT_APPLICABLE",
            "canonicalization_state": "NOT_STATE_CHANGING",
        }
        receipt = historical_disposition_receipt(
            old, self.fx.cfg, observed_canonical_head=self.fx.head,
            authority_id="ISSUE-52-COMMENT-5994972384",
            authority_result_sha256="a" * 64, specification=spec,
        )
        self.assertEqual(receipt["canonical_head"], self.fx.head)
        self.assertEqual(receipt["envelope_hash"], old.envelope_hash)
        bad = deepcopy(spec)
        bad["envelope_hash"] = "f" * 64
        with self.assertRaisesRegex(ValidationError, "envelope mismatch"):
            historical_disposition_receipt(
                old, self.fx.cfg, observed_canonical_head=self.fx.head,
                authority_id="ISSUE-52-COMMENT-5994972384",
                authority_result_sha256="a" * 64, specification=bad,
            )

    def test_two_known_false_attention_cases_are_consistent_across_surfaces(self):
        shadow = self._stranded(
            "INFRA-SHADOW-001", "WAITING_APPROVAL", "CLOSED_HISTORICAL",
        )
        deployment = self._stranded(
            "INFRA-CONVERGENCE-DASHBOARD-V2-PRODUCTION-DEPLOYMENT-001",
            "WAITING_USER", "RETIRED",
        )
        before = {
            task.task_id: self.store.get(task.task_id)["state"]
            for task in (shadow, deployment)
        }
        data = snapshot(self.fx.cfg)
        dashboard_attention = {item["task_id"] for item in data["attention"]}
        telegram_attention = {item["task_id"] for item in self.gateway._current_attention_rows()}
        self.assertEqual(dashboard_attention, telegram_attention)
        self.assertTrue({shadow.task_id, deployment.task_id}.isdisjoint(dashboard_attention))
        self.assertIn("Needs attention: 0", self.gateway._status())
        self.assertEqual(self.gateway._attention(), "No current user-attention items.")
        self.assertEqual(
            before,
            {task.task_id: self.store.get(task.task_id)["state"]
             for task in (shadow, deployment)},
        )

    def test_current_actionable_task_remains_human_readable(self):
        task = self.fx.task("CURRENT-QUESTION-001", source_issue=99)
        self.store.ingest(task)
        self.store.conn.execute(
            "UPDATE tasks SET state='WAITING_USER',reason='Choose the reviewed option' "
            "WHERE task_id=?", (task.task_id,),
        )
        self.assertIn(task.task_id, {item["task_id"] for item in snapshot(self.fx.cfg)["attention"]})
        self.assertIn("Needs attention: 1", self.gateway._status())
        attention = self.gateway._attention()
        self.assertTrue(attention.startswith("Action required\n"))
        self.assertIn("task: CURRENT-QUESTION-001 · state: WAITING_USER", attention)

    def test_semantic_completion_is_not_collapsed_into_execution_completion(self):
        task = self.fx.task("SEMANTIC-FACETS-001", source_issue=100)
        self.store.ingest(task)
        self.store.conn.execute(
            "UPDATE tasks SET state='SUCCEEDED' WHERE task_id=?", (task.task_id,),
        )
        self.store.put_authoring_receipt(self._receipt(
            task, "CURRENT", project_progress="IN_PROGRESS",
            implementation_state="PENDING", deployment_state="NOT_AUTHORIZED",
            canonicalization_state="PENDING_MATERIALIZATION",
        ))
        message = self.gateway._task(task.task_id)
        self.assertIn("Execution: Succeeded", message)
        self.assertIn("Semantic verdict: HISTORICAL_COMPLETE", message)
        self.assertIn("Implementation: PENDING", message)
        self.assertIn("Deployment: NOT_AUTHORIZED", message)


if __name__ == "__main__":
    unittest.main()
