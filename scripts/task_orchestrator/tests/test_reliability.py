from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest import mock

from task_orchestrator.authoring import preflight_authoring
from task_orchestrator.engine import Engine
from task_orchestrator.github import Issue, SourceUnavailable
from task_orchestrator.model import State
from task_orchestrator.reliability import (
    Admission, M1bController, M1bStore, SubprocessAITransport,
)
from task_orchestrator.publishing import CommentPage, TransportResponse
from task_orchestrator.store import Store

from .common import Fixture


class FakeAI:
    def __init__(self, probes=(), executions=()):
        self.probes = list(probes)
        self.executions = list(executions)
        self.probe_calls = 0
        self.execute_calls = 0

    def probe(self):
        self.probe_calls += 1
        return self.probes.pop(0) if self.probes else Admission("ACCEPTED", {"text": "ADMISSION_OK"})

    def execute(self, task, attempt):
        self.execute_calls += 1
        return self.executions.pop(0) if self.executions else Admission(
            "ACCEPTED", {"status": "SUCCEEDED", "summary": "completed",
                         "checks": [], "artifacts": [], "error": None}
        )


class OutageSource:
    def fetch(self, etag):
        raise SourceUnavailable("synthetic network outage")


class StaticSource:
    def __init__(self, issues):
        self.issues = issues

    def fetch(self, etag):
        return self.issues, '"etag"', False


class FakePublication:
    def __init__(self, responses=()):
        self.sends = 0
        self.bodies = []
        self.responses = list(responses)

    def send_comment(self, target, body):
        self.sends += 1
        self.bodies.append(body)
        return self.responses.pop(0) if self.responses else TransportResponse(201, remote_id="comment-1")

    def list_comments(self, target):
        return CommentPage((), True)


def ai_issue_body(head, task_id):
    return f"""task
```yaml
schema_version: 1
task_id: {task_id}
role: 07_INFRASTRUCTURE
canonical_head: {head}
task_type: llm_worker
action: semantic_helper
timeout_seconds: 10
stop_condition: stop
```
"""


def ordinary_issue_body(head, task_id):
    return f"""task
```yaml
schema_version: 1
task_id: {task_id}
role: 07_INFRASTRUCTURE
canonical_head: {head}
task_type: deterministic
action: head_check
timeout_seconds: 10
stop_condition: stop
```
"""


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.fx.cfg["autonomy"]["enabled"] = True
        self.fx.cfg["autonomy"]["plan_only"] = False
        self.fx.cfg["autonomy"]["max_batch_tasks"] = 16
        self.fx.cfg["llm"]["dispatch_enabled"] = True
        self.fx.cfg["llm"]["detached_workers"] = False
        self.fx.cfg["llm"]["require_local_approval"] = False
        self.fx.cfg["llm"]["quota_probe_guard_seconds"] = 0
        self.fx.cfg["llm"]["quota_probe_backoff_seconds"] = [1, 2, 3]
        self.store = Store(self.fx.root / "state" / "state.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def ai_task(self, task_id="AI-TEST-001", **kwargs):
        return self.fx.task(
            task_id=task_id, task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:task", "orchestrator:llm-approved"), **kwargs,
        )

    def result(self, task_id, attempt=1, status="SUCCEEDED", retryable=False, error=None):
        return {
            "schema_version": 1, "task_id": task_id, "attempt": attempt,
            "status": status, "canonical_head": self.fx.head, "worker": "test",
            "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:01Z",
            "checks": [], "artifacts": [], "error": error, "retryable": retryable,
        }

    def recovery_proof(self):
        row = self.store.conn.execute(
            "SELECT state_json FROM controller_state "
            "WHERE task_id='ORCH-M1B-RELIABILITY-REBUILD-001'"
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def mark_recovery_proven(self, now=0.0):
        M1bStore(self.store.conn, self.fx.cfg).checkpoint(
            RECOVERY_PROOF_STATE="PROVEN",
            RECOVERY_FIRST_HEALTHY_AT=now,
            RECOVERY_LAST_HEALTHY_AT=now,
            RECOVERY_PROOF_REASON="pre-existing healthy live controller fixture",
        )

    def create_preview_backlog(self, task_id="RECOVERY-PREVIEW-001"):
        task = self.fx.task(task_id=task_id, source_issue=55)
        self.assertEqual(self.engine.ingest(task), "created")
        controller = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
            clock=lambda: 1000.0,
        )
        controller.cycle(StaticSource([]))
        accepted = self.store.conn.execute(
            "SELECT result_sha256 FROM accepted_results WHERE task_id=?", (task_id,),
        ).fetchone()
        self.assertIsNotNone(accepted)
        self.assertEqual(self.store.conn.execute(
            "SELECT status FROM publication_outbox WHERE task_id=? "
            "AND marker LIKE '<!-- cef-dy-orch-result:v1 %'", (task_id,),
        ).fetchone()[0], "PREVIEW")
        return task, accepted["result_sha256"]

    def apply_historical_disposition(self, task, disposition="CLOSED_HISTORICAL"):
        receipt = preflight_authoring({
            "schema_version": 1,
            "operation_type": "CLOSE",
            "author_role": "00_PROJECT_CONTROL",
            "canonical_head": self.fx.head,
            "issue": {"number": task.source_issue, "state": "closed",
                      "labels": list(task.labels)},
            "task": task.envelope_dict(),
            "existing_binding": {"source_issue": task.source_issue,
                                 "task_id": task.task_id,
                                 "envelope_hash": task.envelope_hash},
            "required_repository_paths": [],
            "dependency_bindings": [],
            "review_binding": None,
            "accepted_state_changes": [{
                "identity": "ATTENTION-DISPOSITION-" + task.task_id,
                "result_sha256": "a" * 64,
                "materialization_state": "NOT_STATE_CHANGING",
                "materialization_commit": None,
                "reason": None,
            }],
            "context_delta_bundle": None,
            "lifecycle": {
                "disposition": disposition,
                "target_task_id": task.task_id,
                "target_envelope_hash": task.envelope_hash,
                "successor_task_id": None,
                "reason": "Project Control accepted this task as historical.",
            },
            "project_status": {
                "project_progress": "COMPLETED",
                "human_action_required": False,
                "semantic_state": "ACCEPTED",
                "design_state": "REVIEWED",
                "implementation_state": "COMPLETED",
                "deployment_state": "NOT_AUTHORIZED",
                "canonicalization_state": "NOT_STATE_CHANGING",
            },
            "execution_context": "SEPARATE_BOUNDED_WORK",
            "persistent_chat_role": "00_PROJECT_CONTROL",
            "chatgpt_scheduler_requested": False,
        }, self.fx.cfg, observed_canonical_head=self.fx.head)
        self.assertEqual(self.store.put_authoring_receipt(receipt), "created")
        return receipt

    def test_quota_wait_does_not_consume_retry_and_local_work_continues(self):
        self.assertEqual(self.engine.ingest(self.ai_task()), "created")
        self.assertEqual(self.engine.ingest(self.fx.task(task_id="INFRA-LOCAL-001")), "created")
        fake = FakeAI(executions=[Admission("QUOTA_REFUSED", reason="usage limit", reset_at=110.0)])
        result = M1bController(self.fx.cfg, self.store, fake, clock=lambda: 100.0).cycle()
        self.assertEqual(self.store.get("AI-TEST-001")["state"], State.QUOTA_WAIT.value)
        self.assertEqual(self.store.get("AI-TEST-001")["attempt"], 0)
        self.assertEqual(self.store.get("INFRA-LOCAL-001")["state"], State.SUCCEEDED.value)
        self.assertEqual(result["status"]["AI_LANE"], "QUOTA_WAIT")
        self.assertEqual(result["status"]["AI_REFUSAL_COUNT"], 1)

    def test_automatic_post_reset_probe_and_resume(self):
        self.engine.ingest(self.ai_task())
        first = FakeAI(executions=[Admission("QUOTA_REFUSED", reason="quota", reset_at=101.0)])
        M1bController(self.fx.cfg, self.store, first, clock=lambda: 100.0).cycle()
        second = FakeAI(
            probes=[Admission("ACCEPTED", {"text": "ADMISSION_OK"})],
            executions=[Admission("ACCEPTED", {"status": "SUCCEEDED", "summary": "completed",
                                                "checks": [], "artifacts": [], "error": None})],
        )
        result = M1bController(self.fx.cfg, self.store, second, clock=lambda: 102.0).cycle()
        self.assertEqual(second.probe_calls, 1)
        self.assertEqual(second.execute_calls, 1)
        self.assertEqual(self.store.get("AI-TEST-001")["state"], State.SUCCEEDED.value)
        self.assertEqual(result["status"]["AI_LANE"], "AVAILABLE")

    def test_repeated_quota_refusal_never_blocks_controller(self):
        self.engine.ingest(self.ai_task())
        now = 100.0
        controller = M1bController(
            self.fx.cfg, self.store,
            FakeAI(probes=[Admission("QUOTA_REFUSED", reason="quota") for _ in range(12)],
                   executions=[Admission("QUOTA_REFUSED", reason="quota")]),
            clock=lambda: now,
        )
        controller.cycle()
        for _ in range(12):
            now += 10
            output = controller.cycle()
            self.assertEqual(output["status"]["ORCHESTRATOR_M1B_STATE"], "OPERATIONAL")
            self.assertEqual(self.store.get("AI-TEST-001")["attempt"], 0)
        self.assertEqual(self.store.get("AI-TEST-001")["state"], State.QUOTA_WAIT.value)

    def test_eight_way_claim_race_has_one_winner(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-RACE-001"))
        db = self.fx.root / "state" / "state.sqlite3"

        def claim(index):
            local = Store(db)
            try:
                row = local.get("INFRA-RACE-001")
                return M1bStore(local.conn, self.fx.cfg).claim(row, f"w{index}", 100.0)
            finally:
                local.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(claim, range(8)))
        winners = [claim for claim in claims if claim is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM worker_leases").fetchone()[0], 1)

    def test_global_ai_slot_allows_only_one_lease_across_tasks_and_cycles(self):
        for task_id in ("AI-SLOT-001", "AI-SLOT-002"):
            self.engine.ingest(self.ai_task(task_id))
        self.fx.cfg["llm"]["detached_workers"] = True
        self.fx.cfg["_config_path"] = str(self.fx.root / "config.yaml")
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        controller = M1bController(self.fx.cfg, self.store, FakeAI())
        with mock.patch("task_orchestrator.reliability.subprocess.run", return_value=completed):
            first = controller.cycle(StaticSource([]))
            second = controller.cycle(StaticSource([]))
        launched = [item for item in first["dispatched"] + second["dispatched"]
                    if item["outcome"] == "launched"]
        self.assertEqual(len(launched), 1)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM worker_leases w JOIN dispatch_attempts d "
            "ON d.attempt_id=w.attempt_id WHERE d.lane='AI_BOUNDED_SPECIALIST'"
        ).fetchone()[0], 1)

    def test_concurrent_claims_for_distinct_ai_tasks_share_one_global_slot(self):
        for task_id in ("AI-SLOT-RACE-001", "AI-SLOT-RACE-002"):
            self.engine.ingest(self.ai_task(task_id))
        database = self.fx.root / "state" / "state.sqlite3"

        def claim(task_id):
            local = Store(database)
            try:
                return M1bStore(local.conn, self.fx.cfg).claim(local.get(task_id), task_id, 100.0)
            finally:
                local.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(claim, ["AI-SLOT-RACE-001", "AI-SLOT-RACE-002"] * 4))
        self.assertEqual(sum(item is not None for item in claims), 1)

    def test_result_is_accepted_exactly_once(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-RESULT-001"))
        row = self.store.get("INFRA-RESULT-001")
        state = M1bStore(self.store.conn, self.fx.cfg)
        lease = state.claim(row, "w", 100.0)
        result = self.result("INFRA-RESULT-001")
        self.assertEqual(state.accept(lease["attempt_id"], result), "accepted")
        self.assertEqual(state.accept(lease["attempt_id"], result), "duplicate")
        changed = {**result, "status": "FAILED"}
        self.assertEqual(state.accept(lease["attempt_id"], changed), "conflict")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 1)

    def test_crash_after_result_before_ack_is_reconciled(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-CRASH-001"))
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        lease = controller.state.claim(self.store.get("INFRA-CRASH-001"), "dead-worker", 100.0)
        result = self.result("INFRA-CRASH-001")
        controller._write_spool(lease["attempt_id"], result)
        fresh = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0)
        counts = fresh.ingest_spool()
        self.assertEqual(counts["accepted"], 1)
        self.assertEqual(self.store.get("INFRA-CRASH-001")["state"], State.SUCCEEDED.value)

    def test_expired_lease_is_recovered(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-LEASE-001"))
        state = M1bStore(self.store.conn, self.fx.cfg)
        state.claim(self.store.get("INFRA-LEASE-001"), "dead", 100.0)
        self.assertEqual(state.recover_expired(2000.0), 1)
        self.assertEqual(self.store.get("INFRA-LEASE-001")["state"], State.READY.value)

    def test_waiting_user_does_not_stall_ready_work(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-WAIT-001"))
        self.store.transition("INFRA-WAIT-001", State.WAITING_USER, "human decision", force_recovery=True)
        self.engine.ingest(self.fx.task(task_id="INFRA-GO-001"))
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.assertEqual(self.store.get("INFRA-WAIT-001")["state"], State.WAITING_USER.value)
        self.assertEqual(self.store.get("INFRA-GO-001")["state"], State.SUCCEEDED.value)

    def test_waiting_user_attention_is_durable_exactly_once_and_nonblocking(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        self.engine.ingest(self.fx.task(
            task_id="INFRA-ATTENTION-001", task_type="llm_worker",
            action="semantic_helper", source_issue=14,
            labels=("orchestrator:task",),
        ))
        self.engine.ingest(self.fx.task(task_id="INFRA-ATTENTION-GO-001", source_issue=None))
        transport = FakePublication()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport)
        controller.cycle(StaticSource([]))
        controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 1)
        self.assertEqual(self.store.get("INFRA-ATTENTION-GO-001")["state"], State.SUCCEEDED.value)
        body = transport.bodies[0]
        for field in ("ATTENTION_REQUIRED: true", "DECISION_CLASS:", "WHY_NOW:",
                      "SMALLEST_DECISION_REQUIRED:", "OPTIONS:",
                      "SAFE_DEFAULT_IF_NO_RESPONSE:", "OTHER_WORK_CONTINUES: true"):
            self.assertIn(field, body)
        rows = list(self.store.conn.execute(
            "SELECT * FROM publication_outbox WHERE task_id='INFRA-ATTENTION-001'"
        ))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PUBLISHED")
        self.store.transition("INFRA-ATTENTION-001", State.BLOCKED,
                              "decision remained unresolved")
        controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 2)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM publication_outbox WHERE task_id='INFRA-ATTENTION-001'"
        ).fetchone()[0], 2)

    def test_shadow_attention_projection_has_zero_network_writes(self):
        self.fx.cfg["mode"] = "shadow"
        self.fx.cfg["autonomy"]["enabled"] = False
        self.engine.ingest(self.fx.task(
            task_id="INFRA-SHADOW-ATTN-001", task_type="llm_worker",
            action="semantic_helper", source_issue=15,
            labels=("orchestrator:task",),
        ))
        transport = FakePublication()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport)
        controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 0)
        row = self.store.conn.execute(
            "SELECT * FROM publication_outbox WHERE task_id='INFRA-SHADOW-ATTN-001'"
        ).fetchone()
        self.assertEqual(row["status"], "PREVIEW")
        self.fx.cfg["mode"] = "pilot"
        self.fx.cfg["autonomy"]["enabled"] = True
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        M1bController(self.fx.cfg, self.store, FakeAI(),
                      publication_transport=transport).cycle(StaticSource([]))
        self.assertEqual(transport.sends, 1)
        row = self.store.conn.execute(
            "SELECT * FROM publication_outbox WHERE task_id='INFRA-SHADOW-ATTN-001'"
        ).fetchone()
        self.assertEqual(row["status"], "PUBLISHED")

    def test_unpublished_attention_is_superseded_after_resolution(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        task = self.fx.task(
            task_id="INFRA-STALE-ATTN-001", task_type="llm_worker",
            action="semantic_helper", source_issue=16, labels=("orchestrator:task",),
        )
        self.engine.ingest(task)
        transport = FakePublication((TransportResponse(429, retry_after_seconds=60),))
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport, clock=lambda: 100.0)
        controller.cycle(StaticSource([]))
        approved = self.fx.task(
            task_id=task.task_id, task_type="llm_worker", action="semantic_helper",
            source_issue=16, labels=("orchestrator:task", "orchestrator:llm-approved"),
        )
        self.assertEqual(self.store.ingest(approved), "metadata_updated")
        clock = [200.0]
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport, clock=lambda: clock[0])
        controller.cycle(StaticSource([]))
        clock[0] += int(self.fx.cfg["poll_interval_seconds"])
        controller.cycle(StaticSource([]))
        attention = self.store.conn.execute(
            "SELECT status FROM publication_outbox WHERE marker LIKE "
            "'<!-- cef-dy-orch-attention:v1 %' AND task_id=?", (task.task_id,)
        ).fetchone()
        self.assertEqual(attention["status"], "SUPERSEDED")
        self.assertEqual(sum("ATTENTION_REQUIRED: true" in body for body in transport.bodies), 1)
        self.assertEqual(transport.sends, 2)

    def test_published_attention_gets_exactly_one_resolution_update(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        task = self.fx.task(
            task_id="INFRA-RESOLVE-ATTN-001", task_type="llm_worker",
            action="semantic_helper", source_issue=17, labels=("orchestrator:task",),
        )
        self.engine.ingest(task)
        transport = FakePublication()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport)
        controller.cycle(StaticSource([]))
        approved = self.fx.task(
            task_id=task.task_id, task_type="llm_worker", action="semantic_helper",
            source_issue=17, labels=("orchestrator:task", "orchestrator:llm-approved"),
        )
        self.assertEqual(self.store.ingest(approved), "metadata_updated")
        self.fx.cfg["llm"]["detached_workers"] = True
        self.fx.cfg["_config_path"] = str(self.fx.root / "config.yaml")
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("task_orchestrator.reliability.subprocess.run", return_value=completed):
            controller.cycle(StaticSource([]))
        self.assertEqual(self.store.get(task.task_id)["state"], State.RUNNING.value)
        self.assertEqual(sum("ATTENTION_REQUIRED: false" in body for body in transport.bodies), 1)
        attempt_id = self.store.conn.execute(
            "SELECT attempt_id FROM worker_leases WHERE task_id=?", (task.task_id,)
        ).fetchone()[0]
        self.fx.cfg["llm"]["detached_workers"] = False
        controller.run_leased_ai(task.task_id, attempt_id)
        controller.cycle(StaticSource([]))
        controller.cycle(StaticSource([]))
        self.assertEqual(sum("ATTENTION_REQUIRED: false" in body for body in transport.bodies), 1)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM publication_outbox WHERE marker LIKE "
            "'<!-- cef-dy-orch-attention-resolution:v1 %' AND task_id=?", (task.task_id,)
        ).fetchone()[0], 1)

    def test_historical_overlay_resolves_published_nonterminal_attention(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        task = self.fx.task(task_id="INFRA-HISTORICAL-ATTN-001", source_issue=41)
        self.engine.ingest(task)
        self.store.transition(
            task.task_id, State.WAITING_USER, "historical unresolved prompt",
            force_recovery=True,
        )
        transport = FakePublication()
        controller = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=transport,
        )
        controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 1)
        self.assertIn("ATTENTION_REQUIRED: true", transport.bodies[0])

        events_before = [dict(row) for row in self.store.conn.execute(
            "SELECT * FROM events WHERE task_id=? ORDER BY event_id", (task.task_id,),
        )]
        self.apply_historical_disposition(task)
        self.assertEqual(self.store.get(task.task_id)["state"], State.WAITING_USER.value)
        self.assertEqual([dict(row) for row in self.store.conn.execute(
            "SELECT * FROM events WHERE task_id=? ORDER BY event_id", (task.task_id,),
        )], events_before)

        controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 2)
        self.assertIn("ATTENTION_REQUIRED: false", transport.bodies[1])
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM publication_outbox WHERE marker LIKE "
            "'<!-- cef-dy-orch-attention-resolution:v1 %' AND task_id=?", (task.task_id,)
        ).fetchone()[0], 1)

    def test_two_attention_episodes_each_get_exactly_one_resolution(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        self.fx.cfg["llm"]["detached_workers"] = True
        self.fx.cfg["_config_path"] = str(self.fx.root / "config.yaml")
        task = self.fx.task(
            task_id="INFRA-TWO-ATTN-001", task_type="llm_worker",
            action="semantic_helper", source_issue=18, labels=("orchestrator:task",),
        )
        self.engine.ingest(task)
        transport = FakePublication()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport)
        controller.cycle(StaticSource([]))
        approved = self.fx.task(
            task_id=task.task_id, task_type="llm_worker", action="semantic_helper",
            source_issue=18, labels=("orchestrator:task", "orchestrator:llm-approved"),
        )
        self.assertEqual(self.store.ingest(approved), "metadata_updated")
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("task_orchestrator.reliability.subprocess.run", return_value=completed):
            controller.cycle(StaticSource([]))
        self.assertEqual(self.store.ingest(task), "metadata_updated")
        self.store.transition(task.task_id, State.WAITING_USER,
                              "approval revoked again", force_recovery=True)
        controller.state.cancel_invalid_leases()
        controller.cycle(StaticSource([]))
        self.assertEqual(self.store.ingest(approved), "metadata_updated")
        with mock.patch("task_orchestrator.reliability.subprocess.run", return_value=completed):
            controller.cycle(StaticSource([]))
        controller.cycle(StaticSource([]))
        self.assertEqual(sum("ATTENTION_REQUIRED: true" in body for body in transport.bodies), 2)
        self.assertEqual(sum("ATTENTION_REQUIRED: false" in body for body in transport.bodies), 2)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM publication_outbox WHERE marker LIKE "
            "'<!-- cef-dy-orch-attention-resolution:v1 %' AND task_id=?", (task.task_id,)
        ).fetchone()[0], 2)

    def test_attention_without_source_issue_uses_configured_durable_issue(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["github"]["attention_issue"] = 4
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        self.engine.ingest(self.fx.task(
            task_id="INFRA-FALLBACK-ATTN-001", task_type="llm_worker",
            action="semantic_helper", source_issue=None, labels=("orchestrator:task",),
        ))
        transport = FakePublication()
        M1bController(self.fx.cfg, self.store, FakeAI(),
                      publication_transport=transport).cycle(StaticSource([]))
        row = self.store.conn.execute(
            "SELECT target,status FROM publication_outbox WHERE task_id='INFRA-FALLBACK-ATTN-001'"
        ).fetchone()
        self.assertEqual((row["target"], row["status"]), ("issue:4", "PUBLISHED"))

    def test_hundred_task_load_has_no_double_execution_or_starvation(self):
        self.fx.cfg["autonomy"]["max_batch_tasks"] = 16
        for index in range(100):
            self.engine.ingest(self.fx.task(task_id=f"INFRA-LOAD-{index:03d}"))
        controller = M1bController(self.fx.cfg, self.store, FakeAI())
        for _ in range(7):
            controller.cycle()
        self.assertEqual(len(self.store.list_state(State.SUCCEEDED)), 100)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 100)
        self.assertEqual(self.store.conn.execute("SELECT count(DISTINCT task_id) FROM accepted_results").fetchone()[0], 100)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM worker_leases").fetchone()[0], 0)

    def test_github_outage_does_not_stop_local_lane(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        self.engine.ingest(self.fx.task(task_id="INFRA-OFFLINE-001"))
        result = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
        ).cycle(OutageSource())
        self.assertEqual(result["poll"]["status"], "outage")
        self.assertEqual(self.store.get("INFRA-OFFLINE-001")["state"], State.SUCCEEDED.value)

    def test_current_preview_only_autonomy_scenario_pauses_claims(self):
        task = self.fx.task(task_id="OPAQUE-CURRENT-SCENARIO-001")
        self.engine.ingest(task)
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        fake = FakeAI()
        result = M1bController(self.fx.cfg, self.store, fake).cycle(StaticSource([]))
        self.assertEqual(result["admission_visibility"], "ADMISSION_PAUSED_OPAQUE_STATE")
        self.assertEqual(self.store.get(task.task_id)["state"], State.READY.value)
        self.assertEqual(result["dispatched"], [])
        self.assertEqual(fake.execute_calls, 0)

    def test_paused_issue_flood_is_not_persisted_and_reopens_cleanly(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        issues = [
            Issue(
                1000 + index, "task",
                ordinary_issue_body(self.fx.head, f"PAUSED-FLOOD-{index:03d}"),
                ("orchestrator:task",), f"t{index}",
            )
            for index in range(100)
        ]
        first = self.engine.poll(StaticSource(issues))
        self.assertEqual(first["deferred"], 100)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)
        self.assertIsNone(self.store.source("github")["etag"])
        second = self.engine.poll(StaticSource(issues))
        self.assertEqual(second["deferred"], 100)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)

        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        self.mark_recovery_proven()
        reopened = self.engine.poll(StaticSource(issues))
        self.assertEqual(reopened["accepted"], 100)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM tasks").fetchone()[0], 100)
        self.assertIsNotNone(self.store.get("PAUSED-FLOOD-000"))

    def test_pre_admission_recovery_barrier_orders_preview_reconciliation_before_reopen(self):
        accepted_task, accepted_hash = self.create_preview_backlog()
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        issue = Issue(
            1200, "task", ordinary_issue_body(self.fx.head, "DEFERRED-AFTER-MAINT-001"),
            ("orchestrator:task",), "maintenance-etag",
        )
        clock = [2000.0]
        transport = FakePublication()
        controller = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=transport,
            clock=lambda: clock[0],
        )

        maintenance = controller.cycle(StaticSource([issue]))
        self.assertEqual(maintenance["poll"]["deferred"], 1)
        self.assertIsNone(self.store.get("DEFERRED-AFTER-MAINT-001"))
        self.assertEqual(self.recovery_proof()["RECOVERY_PROOF_STATE"], "NOT_PROVEN")

        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        first = controller.cycle(StaticSource([issue]))
        self.assertEqual(first["poll"]["deferred"], 1)
        self.assertEqual(first["dispatched"], [])
        self.assertFalse(first["ordinary_admission_open"])
        self.assertEqual(first["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION")
        self.assertEqual(self.store.conn.execute(
            "SELECT status FROM publication_outbox WHERE task_id=? "
            "AND marker LIKE '<!-- cef-dy-orch-result:v1 %'", (accepted_task.task_id,),
        ).fetchone()[0], "PUBLISHED")
        self.assertIsNone(self.store.get("DEFERRED-AFTER-MAINT-001"))

        clock[0] += int(self.fx.cfg["poll_interval_seconds"]) - 1
        too_soon = controller.cycle(StaticSource([issue]))
        self.assertEqual(too_soon["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION")
        self.assertEqual(too_soon["poll"]["deferred"], 1)
        self.assertEqual(too_soon["dispatched"], [])

        clock[0] += 1
        reopened = controller.cycle(StaticSource([issue]))
        self.assertEqual(reopened["recovery_proof"]["state"], "PROVEN")
        self.assertTrue(reopened["ordinary_admission_open"])
        self.assertEqual(reopened["poll"]["accepted"], 1)
        self.assertEqual(len(reopened["dispatched"]), 1)
        self.assertEqual(
            self.store.get("DEFERRED-AFTER-MAINT-001")["state"], State.SUCCEEDED.value,
        )
        self.assertEqual(self.store.conn.execute(
            "SELECT result_sha256 FROM accepted_results WHERE task_id=?",
            (accepted_task.task_id,),
        ).fetchone()[0], accepted_hash)

    def test_recovery_proof_resets_on_opaque_failed_and_missing_projection(self):
        accepted_task, accepted_hash = self.create_preview_backlog("RECOVERY-RESET-SOURCE-001")
        held = self.fx.task(task_id="RECOVERY-HELD-READY-001")
        self.assertEqual(self.engine.ingest(held), "created")
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        clock = [3000.0]
        fake_ai = FakeAI()
        controller = M1bController(
            self.fx.cfg, self.store, fake_ai, publication_transport=FakePublication(),
            clock=lambda: clock[0],
        )
        first = controller.cycle(StaticSource([]))
        self.assertEqual(first["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION")

        publication_id = self.store.conn.execute(
            "SELECT publication_id FROM publication_outbox WHERE task_id=? "
            "AND marker LIKE '<!-- cef-dy-orch-result:v1 %'", (accepted_task.task_id,),
        ).fetchone()[0]

        for status in ("UNKNOWN", "CONFLICT", "FAILED"):
            with self.subTest(status=status):
                if self.recovery_proof()["RECOVERY_PROOF_STATE"] == "NOT_PROVEN":
                    self.store.update_publication(publication_id, "PUBLISHED")
                    clock[0] += 1
                    observed = controller.cycle(StaticSource([]))
                    self.assertEqual(
                        observed["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION",
                    )
                self.store.update_publication(
                    publication_id, status,
                    backoff_until=clock[0] + 1000 if status == "UNKNOWN" else 0,
                )
                clock[0] += int(self.fx.cfg["poll_interval_seconds"])
                blocked = controller.cycle(StaticSource([]))
                self.assertEqual(blocked["recovery_proof"]["state"], "NOT_PROVEN")
                self.assertFalse(blocked["ordinary_admission_open"])
                self.assertEqual(blocked["dispatched"], [])
                self.assertEqual(self.store.get(held.task_id)["state"], State.READY.value)

        self.store.update_publication(publication_id, "PUBLISHED")
        clock[0] += 1
        observed = controller.cycle(StaticSource([]))
        self.assertEqual(observed["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION")
        self.store.conn.execute(
            "DELETE FROM publication_outbox WHERE publication_id=?", (publication_id,),
        )
        (self.fx.root / "state" / "results" / f"{accepted_task.task_id}.yaml").unlink()
        clock[0] += int(self.fx.cfg["poll_interval_seconds"])
        missing = controller.cycle(StaticSource([]))
        self.assertEqual(missing["recovery_proof"]["state"], "NOT_PROVEN")
        self.assertEqual(missing["dispatched"], [])
        self.assertEqual(self.store.conn.execute(
            "SELECT result_sha256 FROM accepted_results WHERE task_id=?",
            (accepted_task.task_id,),
        ).fetchone()[0], accepted_hash)
        self.assertEqual(fake_ai.execute_calls, 0)

    def test_recovery_proof_is_durable_and_restart_revalidates_before_admission(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        clock = [4000.0]
        first = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
            clock=lambda: clock[0],
        ).cycle(StaticSource([]))
        self.assertEqual(first["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION")

        clock[0] += int(self.fx.cfg["poll_interval_seconds"]) - 1
        restarted_one = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
            clock=lambda: clock[0],
        ).cycle(StaticSource([]))
        self.assertEqual(
            restarted_one["recovery_proof"]["state"], "ONE_HEALTHY_OBSERVATION",
        )

        clock[0] += 1
        restarted_proven = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
            clock=lambda: clock[0],
        ).cycle(StaticSource([]))
        self.assertEqual(restarted_proven["recovery_proof"]["state"], "PROVEN")
        self.assertTrue(restarted_proven["ordinary_admission_open"])

        held = self.fx.task(task_id="RESTART-OPAQUE-HELD-001")
        self.assertEqual(self.engine.ingest(held), "created")
        row = self.store.get(held.task_id)
        self.store.enqueue_publication(
            publication_id="restart-opaque", repository="org/repo",
            task_id=held.task_id, envelope_hash=row["envelope_hash"],
            result_sha256="a" * 64, target="issue:1",
            marker="<!-- recovery-test -->", preview="opaque", status="CONFLICT",
        )
        clock[0] += 1
        restarted_unhealthy = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
            clock=lambda: clock[0],
        ).cycle(StaticSource([]))
        self.assertEqual(restarted_unhealthy["recovery_proof"]["state"], "NOT_PROVEN")
        self.assertFalse(restarted_unhealthy["ordinary_admission_open"])
        self.assertEqual(restarted_unhealthy["dispatched"], [])
        self.assertEqual(self.store.get(held.task_id)["state"], State.READY.value)

        clock[0] += int(self.fx.cfg["poll_interval_seconds"])
        restarted_not_proven = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=FakePublication(),
            clock=lambda: clock[0],
        ).cycle(StaticSource([]))
        self.assertEqual(restarted_not_proven["recovery_proof"]["state"], "NOT_PROVEN")
        self.assertEqual(restarted_not_proven["dispatched"], [])

    def test_restart_reconstructs_paused_visibility_from_durable_results(self):
        for task_id in ("UNPROJECTED-ONE-001", "UNPROJECTED-TWO-001"):
            self.engine.ingest(self.fx.task(task_id=task_id, source_issue=101))
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        accepted_before = [tuple(row) for row in self.store.conn.execute(
            "SELECT task_id,result_sha256,result_json FROM accepted_results ORDER BY task_id"
        )]
        self.store.conn.execute(
            "UPDATE publication_outbox SET status='PENDING' WHERE status='PREVIEW'"
        )
        self.fx.cfg["autonomy"]["max_batch_tasks"] = 1
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        first = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: time.time())
        self.assertEqual(
            first.engine.visibility_health().state.value,
            "ADMISSION_PAUSED_OPAQUE_STATE",
        )
        restarted = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: time.time())
        self.assertEqual(
            restarted.engine.visibility_health().state.value,
            "ADMISSION_PAUSED_OPAQUE_STATE",
        )
        accepted_after = [tuple(row) for row in self.store.conn.execute(
            "SELECT task_id,result_sha256,result_json FROM accepted_results ORDER BY task_id"
        )]
        self.assertEqual(accepted_after, accepted_before)

    def test_historical_accepted_result_with_preview_does_not_trip_breaker(self):
        task = self.fx.task(task_id="HISTORICAL-PREVIEW-001", source_issue=55)
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.assertIsNotNone(self.store.conn.execute(
            "SELECT 1 FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone())
        self.assertEqual(self.store.conn.execute(
            "SELECT status FROM publication_outbox WHERE task_id=?", (task.task_id,)
        ).fetchone()[0], "PREVIEW")
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        self.assertEqual(
            self.engine.visibility_health().state.value,
            "AUTONOMY_VISIBILITY_OK",
        )

    def test_live_missing_and_outbox_states_drive_visibility(self):
        task = self.fx.task(task_id="LIVE-OBLIGATION-001", source_issue=56)
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        self.store.conn.execute(
            "DELETE FROM publication_outbox WHERE task_id=?", (task.task_id,)
        )
        self.assertEqual(
            self.engine.visibility_health().state.value,
            "AUTONOMY_VISIBILITY_DEGRADED",
        )
        accepted = self.store.conn.execute(
            "SELECT result_sha256 FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone()
        row = self.store.get(task.task_id)
        self.store.enqueue_publication(
            publication_id="live-obligation", repository="org/repo",
            task_id=task.task_id, envelope_hash=row["envelope_hash"],
            result_sha256=accepted["result_sha256"], target="issue:56",
            marker="<!-- cef-dy-orch-result:v1 live -->", preview="live",
            status="PENDING",
        )
        self.assertEqual(
            self.engine.visibility_health().state.value,
            "AUTONOMY_VISIBILITY_DEGRADED",
        )
        for status in ("UNKNOWN", "CONFLICT"):
            with self.subTest(status=status):
                self.store.conn.execute(
                    "UPDATE publication_outbox SET status=? WHERE task_id=?",
                    (status, task.task_id),
                )
                self.assertEqual(
                    self.engine.visibility_health().state.value,
                    "ADMISSION_PAUSED_OPAQUE_STATE",
                )

    def test_identity_bound_mandatory_review_is_admitted_while_paused(self):
        parent = self.fx.task(task_id="PAUSED-REVIEW-PARENT-001")
        self.engine.ingest(parent)
        controller = M1bController(self.fx.cfg, self.store, FakeAI())
        controller.cycle()
        material = controller.router._build_review_material(parent)
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        review = self.fx.task(
            task_id="PAUSED-REVIEW-PARENT-001-REVIEW-001",
            task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:task", "orchestrator:llm-approved"),
            source_issue=None,
            inputs={
                "independent_review": True,
                "review_of": parent.task_id,
                "review_material": material,
            },
        )
        self.store.conn.execute(
            "INSERT INTO review_requirements VALUES(?,?,?,?,?,?,?)",
            (parent.task_id, review.task_id, "07", "RESERVED",
             "test exact reservation", "2026-01-01T00:00:00Z",
             "2026-01-01T00:00:00Z"),
        )
        self.assertEqual(self.engine.ingest(review), "created")
        self.assertNotEqual(self.store.get(review.task_id)["state"], State.VALIDATED.value)

    def test_publication_failure_does_not_restart_accepted_worker(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        task = self.fx.task(task_id="PUBLICATION-FAIL-NO-RERUN-001", source_issue=77)
        self.engine.ingest(task)
        transport = FakePublication((TransportResponse(500),))
        controller = M1bController(
            self.fx.cfg, self.store, FakeAI(), publication_transport=transport,
        )
        first = controller.cycle(StaticSource([]))
        attempts = self.store.get(task.task_id)["attempt"]
        second = controller.cycle(StaticSource([]))
        self.assertEqual(self.store.get(task.task_id)["state"], State.SUCCEEDED.value)
        self.assertEqual(self.store.get(task.task_id)["attempt"], attempts)
        self.assertEqual(first["dispatched"][0]["task_id"], task.task_id)
        self.assertEqual(second["dispatched"], [])

    def test_expired_ordinary_attempt_is_not_retried_while_visibility_paused(self):
        task = self.fx.task(task_id="OPAQUE-RETRY-001")
        self.engine.ingest(task)
        state = M1bStore(self.store.conn, self.fx.cfg)
        lease = state.claim(self.store.get(task.task_id), "dead", 100.0)
        self.assertIsNotNone(lease)
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        result = M1bController(
            self.fx.cfg, self.store, FakeAI(), clock=lambda: 2000.0,
        ).cycle(StaticSource([]))
        self.assertEqual(result["admission_visibility"], "ADMISSION_PAUSED_OPAQUE_STATE")
        self.assertEqual(self.store.get(task.task_id)["state"], State.FAILED_RETRYABLE.value)
        self.assertEqual(result["dispatched"], [])

    def test_result_after_database_accept_before_ack_is_deduplicated(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-ACK-001"))
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        lease = controller.state.claim(self.store.get("INFRA-ACK-001"), "worker", 100.0)
        result = self.result("INFRA-ACK-001")
        controller._write_spool(lease["attempt_id"], result)
        self.assertEqual(controller.state.accept(lease["attempt_id"], result), "accepted")
        fresh = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0)
        counts = fresh.ingest_spool()
        self.assertEqual(counts["duplicate"], 1)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results WHERE task_id='INFRA-ACK-001'").fetchone()[0], 1)

    def test_shadow_and_disabled_modes_never_dispatch(self):
        self.fx.cfg["mode"] = "shadow"
        self.fx.cfg["autonomy"]["enabled"] = False
        self.store.ingest(self.fx.task(task_id="INFRA-SHADOW-001"))
        self.store.transition("INFRA-SHADOW-001", State.VALIDATED, "test")
        self.store.transition("INFRA-SHADOW-001", State.READY, "test")
        output = M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.assertEqual(self.store.get("INFRA-SHADOW-001")["state"], State.READY.value)
        self.assertEqual(output["status"]["ORCHESTRATOR_M1B_STATE"], "SHADOW")

    def test_retryable_attempt_does_not_occupy_final_result_identity(self):
        self.engine.ingest(self.ai_task("AI-RETRY-001"))
        fake = FakeAI(executions=[
            Admission("FAILED_RETRYABLE", reason="transient"),
            Admission("ACCEPTED", {"status": "SUCCEEDED", "summary": "completed",
                                   "checks": [], "artifacts": [], "error": None}),
        ])
        controller = M1bController(self.fx.cfg, self.store, fake)
        controller.cycle()
        self.assertEqual(self.store.get("AI-RETRY-001")["state"], State.FAILED_RETRYABLE.value)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 0)
        controller.cycle()
        self.assertEqual(self.store.get("AI-RETRY-001")["state"], State.SUCCEEDED.value)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 1)

    def test_malformed_spool_is_quarantined_not_accepted(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-BADRESULT-001"))
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        lease = controller.state.claim(self.store.get("INFRA-BADRESULT-001"), "worker", 100.0)
        controller._write_spool(lease["attempt_id"], {"task_id": "INFRA-BADRESULT-001", "status": "SUCCEEDED"})
        counts = controller.ingest_spool()
        self.assertEqual(counts["malformed"], 1)
        self.assertEqual(counts["result_schema_rejected"], 1)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 0)
        row = self.store.get("INFRA-BADRESULT-001")
        self.assertEqual((row["state"], row["attempt"]), (State.FAILED_RETRYABLE.value, 1))
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM worker_leases").fetchone()[0], 0)
        dispatch = self.store.conn.execute(
            "SELECT outcome,finished_at FROM dispatch_attempts WHERE attempt_id=?", (lease["attempt_id"],)
        ).fetchone()
        self.assertEqual(dispatch["outcome"], "RESULT_SCHEMA_REJECTED")
        self.assertIsNotNone(dispatch["finished_at"])
        self.assertEqual(len(list(controller.spool.glob("*.malformed"))), 1)

    def test_semantic_producer_contract_rejects_wrong_container_types(self):
        task = self.ai_task("AI-TYPED-PRODUCER-001")
        transport = SubprocessAITransport(self.fx.cfg)
        invalid = {
            "status": "PASS", "summary": "bad checks", "checks": {"scope": "PASS"},
            "artifacts": [], "error": None,
        }
        with mock.patch.object(transport, "_run", return_value=Admission("ACCEPTED", {"text": json.dumps(invalid)})) as run:
            outcome = transport.execute(task, 1)
        self.assertEqual(outcome.status, "RESULT_SCHEMA_REJECTED")
        self.assertIn("checks must be a list", outcome.reason)
        self.assertIn("checks (list)", run.call_args.args[0])

        invalid["checks"] = []
        invalid["artifacts"] = "not-a-list"
        with mock.patch.object(transport, "_run", return_value=Admission("ACCEPTED", {"text": json.dumps(invalid)})):
            outcome = transport.execute(task, 1)
        self.assertEqual(outcome.status, "RESULT_SCHEMA_REJECTED")
        self.assertIn("artifacts must be a list", outcome.reason)

    def test_semantic_producer_contract_accepts_typed_lists(self):
        task = self.ai_task("AI-TYPED-PRODUCER-OK-001")
        payload = {
            "status": "PASS", "summary": "typed", "checks": [{"name": "scope"}],
            "artifacts": ["report.txt"], "error": None,
        }
        transport = SubprocessAITransport(self.fx.cfg)
        with mock.patch.object(transport, "_run", return_value=Admission("ACCEPTED", {"text": json.dumps(payload)})):
            outcome = transport.execute(task, 1)
        self.assertEqual(outcome, Admission("ACCEPTED", payload))

    def test_repeated_invalid_semantic_results_reach_retry_limit(self):
        task = self.ai_task("AI-SCHEMA-RETRY-LIMIT-001")
        self.engine.ingest(task)
        invalid = Admission("ACCEPTED", {
            "status": "PASS", "summary": "invalid", "checks": {"scope": "PASS"},
            "artifacts": [], "error": None,
        })
        controller = M1bController(
            self.fx.cfg, self.store, FakeAI(executions=[invalid, invalid, invalid])
        )
        for _ in range(3):
            controller.cycle()
        self.assertEqual(self.store.get(task.task_id)["attempt"], 3)
        controller.cycle()
        self.assertEqual(self.store.get(task.task_id)["state"], State.BLOCKED.value)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM dispatch_attempts WHERE task_id=? AND finished_at IS NOT NULL",
            (task.task_id,),
        ).fetchone()[0], 3)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM dispatch_attempts WHERE task_id=? AND outcome='RESULT_SCHEMA_REJECTED'",
            (task.task_id,),
        ).fetchone()[0], 3)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM worker_leases").fetchone()[0], 0)

    def test_rejected_spool_recovery_is_idempotent_and_observable(self):
        task = self.ai_task("AI-DETACHED-SCHEMA-001")
        self.engine.ingest(task)
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        lease = controller.state.claim(self.store.get(task.task_id), "detached", 100.0)
        malformed = self.result(task.task_id)
        malformed["checks"] = {"wrong": "container"}
        controller._write_spool(lease["attempt_id"], malformed)
        first = controller.ingest_spool()
        forensic = next(controller.spool.glob("*.malformed"))
        forensic.rename(forensic.with_suffix(".yaml"))  # simulate restart before quarantine rename
        second = M1bController(self.fx.cfg, self.store, FakeAI()).ingest_spool()
        self.assertEqual(first["result_schema_rejected"], 1)
        self.assertEqual(second["duplicate_schema_rejected"], 1)
        self.assertEqual(self.store.get(task.task_id)["attempt"], 1)
        self.assertEqual(len(list(controller.spool.glob("*.malformed"))), 1)
        status = controller.state.status()
        self.assertEqual(status["ACTIVE_WORKER_LEASES"], [])
        self.assertEqual(status["RESULT_SCHEMA_REJECTED_ATTEMPTS"][0]["task_id"], task.task_id)
        self.assertEqual(status["RECOVERY_REQUIRED"], [])

        orphan = self.fx.task(task_id="INFRA-ORPHANED-RUNNING-001")
        self.engine.ingest(orphan)
        self.store.conn.execute(
            "UPDATE tasks SET state=?,reason=? WHERE task_id=?",
            (State.RUNNING.value, "synthetic interrupted recovery", orphan.task_id),
        )
        status = controller.state.status()
        self.assertEqual(status["ACTIVE_WORKER_LEASES"], [])
        self.assertEqual(status["RECOVERY_REQUIRED"][0]["task_id"], orphan.task_id)

    def test_result_attempt_must_match_durable_dispatch(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-ATTEMPT-001"))
        state = M1bStore(self.store.conn, self.fx.cfg)
        lease = state.claim(self.store.get("INFRA-ATTEMPT-001"), "worker", 100.0)
        with self.assertRaises(ValueError):
            state.accept(lease["attempt_id"], self.result("INFRA-ATTEMPT-001", attempt=999))
        self.assertEqual(self.store.get("INFRA-ATTEMPT-001")["state"], State.RUNNING.value)

    def test_shadow_mode_never_performs_live_publication(self):
        self.fx.cfg["mode"] = "pilot"
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        self.engine.ingest(self.fx.task(task_id="INFRA-SHADOW-PUB-001", source_issue=10))
        transport = FakePublication()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), publication_transport=transport)
        controller.cycle(StaticSource([]))
        self.fx.cfg["mode"] = "shadow"
        self.fx.cfg["autonomy"]["enabled"] = False
        self.store.update_publication(
            self.store.conn.execute("SELECT publication_id FROM publication_outbox").fetchone()[0],
            "PENDING",
        )
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), publication_transport=transport)
        controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 1)

    def test_sigterm_and_sigkill_worker_processes_recover_from_durable_lease(self):
        package_root = Path(__file__).resolve().parents[2]
        database = self.fx.root / "state" / "state.sqlite3"
        child_code = r"""
from copy import deepcopy
from pathlib import Path
import sys,time
from task_orchestrator.config import DEFAULTS
from task_orchestrator.reliability import M1bStore
from task_orchestrator.store import Store
cfg=deepcopy(DEFAULTS)
cfg['repository_root']=sys.argv[2]
cfg['state_dir']=sys.argv[3]
store=Store(Path(sys.argv[1]))
row=store.get(sys.argv[4])
M1bStore(store.conn,cfg).claim(row,'crash-child',0.0)
print('CLAIMED',flush=True)
time.sleep(60)
"""
        for index, sig in enumerate((signal.SIGTERM, signal.SIGKILL)):
            task_id = f"INFRA-SIGNAL-{index}"
            self.engine.ingest(self.fx.task(task_id=task_id))
            env = dict(os.environ)
            env["PYTHONPATH"] = str(package_root)
            child = subprocess.Popen(
                [sys.executable, "-c", child_code, str(database), str(self.fx.root),
                 str(self.fx.root / "state"), task_id],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            )
            self.assertEqual(child.stdout.readline().strip(), "CLAIMED")
            child.send_signal(sig)
            child.communicate(timeout=10)
            self.assertEqual(self.store.get(task_id)["state"], State.RUNNING.value)
            self.assertEqual(M1bStore(self.store.conn, self.fx.cfg).recover_expired(5000.0), 1)
            self.assertEqual(self.store.get(task_id)["state"], State.READY.value)

    def test_revoked_approval_is_not_restored_by_quota_probe(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"].update(enabled=True, preview_only=False)
        self.mark_recovery_proven()
        task = self.ai_task("AI-REVOKE-001")
        self.engine.ingest(task)
        first = FakeAI(executions=[Admission("QUOTA_REFUSED", reason="quota", reset_at=101.0)])
        M1bController(self.fx.cfg, self.store, first, clock=lambda: 100.0).cycle(StaticSource([]))
        issue = Issue(1, "task", ai_issue_body(self.fx.head, task.task_id),
                      ("orchestrator:task",), "t2")
        second = FakeAI(probes=[Admission("ACCEPTED", {"text": "ADMISSION_OK"})])
        M1bController(self.fx.cfg, self.store, second, clock=lambda: 102.0).cycle(StaticSource([issue]))
        self.assertEqual(self.store.get(task.task_id)["state"], State.WAITING_USER.value)
        self.assertEqual(second.execute_calls, 0)

    def test_revoked_running_worker_late_result_is_rejected(self):
        task = self.ai_task("AI-RUNNING-REVOKE-001")
        self.engine.ingest(task)
        state = M1bStore(self.store.conn, self.fx.cfg)
        lease = state.claim(self.store.get(task.task_id), "detached", 100.0)
        revoked = self.fx.task(
            task_id=task.task_id, task_type="llm_worker", action="semantic_helper",
            source_issue=1, labels=("orchestrator:task",),
        )
        self.assertEqual(self.store.ingest(revoked), "metadata_updated")
        self.store.transition(task.task_id, State.WAITING_USER, "approval revoked", force_recovery=True)
        outcome = state.accept(lease["attempt_id"], self.result(task.task_id))
        self.assertEqual(outcome, "revoked")
        self.assertEqual(self.store.get(task.task_id)["state"], State.WAITING_USER.value)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 0)

    def test_revoked_running_worker_late_quota_signal_is_rejected(self):
        task = self.ai_task("AI-RUNNING-QUOTA-REVOKE-001")
        self.engine.ingest(task)
        state = M1bStore(self.store.conn, self.fx.cfg)
        lease = state.claim(self.store.get(task.task_id), "detached", 100.0)
        self.store.transition(task.task_id, State.WAITING_USER, "approval revoked", force_recovery=True)
        state.cancel_invalid_leases()
        outcome = state.quota_refused(task.task_id, lease["attempt_id"], "quota", 101.0, 100.0)
        self.assertEqual(outcome, "revoked")
        self.assertEqual(self.store.get(task.task_id)["state"], State.WAITING_USER.value)
        self.assertEqual(state.lane()["state"], "AVAILABLE")

    def test_cycle_projects_terminal_result_exactly_once(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
        self.mark_recovery_proven()
        self.engine.ingest(self.fx.task(task_id="INFRA-PROJECT-001", source_issue=9))
        transport = FakePublication()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport)
        first = controller.cycle(StaticSource([]))
        second = controller.cycle(StaticSource([]))
        self.assertEqual(transport.sends, 1)
        row = self.store.conn.execute("SELECT * FROM publication_outbox").fetchone()
        self.assertEqual(row["status"], "PUBLISHED")
        self.assertTrue(first["publications"])
        self.assertFalse([item for item in second["publications"] if item.get("network_writes")])

    def test_detached_ai_launch_returns_without_running_worker_inline(self):
        self.fx.cfg["llm"]["detached_workers"] = True
        self.fx.cfg["_config_path"] = str(self.fx.root / "config.yaml")
        self.engine.ingest(self.ai_task("AI-DETACHED-001"))
        fake = FakeAI()
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("task_orchestrator.reliability.subprocess.run", return_value=completed) as run:
            result = M1bController(self.fx.cfg, self.store, fake).cycle()
        self.assertEqual(result["dispatched"][0]["outcome"], "launched")
        self.assertEqual(fake.execute_calls, 0)
        self.assertEqual(self.store.get("AI-DETACHED-001")["state"], State.RUNNING.value)
        self.assertEqual(run.call_args.args[0][0:2], ["systemd-run", "--user"])

        self.fx.cfg["llm"]["detached_workers"] = False
        worker = M1bController(self.fx.cfg, self.store, fake)
        attempt_id = self.store.conn.execute(
            "SELECT attempt_id FROM worker_leases WHERE task_id='AI-DETACHED-001'"
        ).fetchone()[0]
        worker.run_leased_ai("AI-DETACHED-001", attempt_id)
        self.assertEqual(self.store.get("AI-DETACHED-001")["state"], State.SUCCEEDED.value)


if __name__ == "__main__":
    unittest.main()
