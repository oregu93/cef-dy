from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest import mock

from task_orchestrator.engine import Engine
from task_orchestrator.github import Issue, SourceUnavailable
from task_orchestrator.model import State
from task_orchestrator.reliability import Admission, M1bController, M1bStore
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
            "ACCEPTED", {"status": "SUCCEEDED", "checks": [], "artifacts": [], "error": None}
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
            executions=[Admission("ACCEPTED", {"status": "SUCCEEDED", "checks": [], "artifacts": [], "error": None})],
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
        controller = M1bController(self.fx.cfg, self.store, FakeAI(),
                                   publication_transport=transport, clock=lambda: 200.0)
        controller.cycle(StaticSource([]))
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

    def test_two_attention_episodes_each_get_exactly_one_resolution(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["publishing"] = {"enabled": True, "preview_only": False,
                                      "trusted_authors": ["trusted-bot"]}
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
        self.engine.ingest(self.fx.task(task_id="INFRA-OFFLINE-001"))
        result = M1bController(self.fx.cfg, self.store, FakeAI()).cycle(OutageSource())
        self.assertEqual(result["poll"]["status"], "outage")
        self.assertEqual(self.store.get("INFRA-OFFLINE-001")["state"], State.SUCCEEDED.value)

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
            Admission("ACCEPTED", {"status": "SUCCEEDED", "checks": [], "artifacts": [], "error": None}),
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
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 0)

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
