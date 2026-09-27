from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import time
import unittest

from task_orchestrator.engine import Engine
from task_orchestrator.github import SourceUnavailable
from task_orchestrator.model import State
from task_orchestrator.reliability import Admission, M1bController, M1bStore
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


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.fx.cfg["autonomy"]["enabled"] = True
        self.fx.cfg["autonomy"]["max_batch_tasks"] = 16
        self.fx.cfg["llm"]["dispatch_enabled"] = True
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

    def test_result_is_accepted_exactly_once(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-RESULT-001"))
        row = self.store.get("INFRA-RESULT-001")
        state = M1bStore(self.store.conn, self.fx.cfg)
        lease = state.claim(row, "w", 100.0)
        result = {"task_id": "INFRA-RESULT-001", "status": "SUCCEEDED", "error": None}
        self.assertEqual(state.accept(lease["attempt_id"], result), "accepted")
        self.assertEqual(state.accept(lease["attempt_id"], result), "duplicate")
        changed = {**result, "status": "FAILED"}
        self.assertEqual(state.accept(lease["attempt_id"], changed), "conflict")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results").fetchone()[0], 1)

    def test_crash_after_result_before_ack_is_reconciled(self):
        self.engine.ingest(self.fx.task(task_id="INFRA-CRASH-001"))
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        lease = controller.state.claim(self.store.get("INFRA-CRASH-001"), "dead-worker", 100.0)
        result = {"task_id": "INFRA-CRASH-001", "status": "SUCCEEDED", "error": None}
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
        result = {"task_id": "INFRA-ACK-001", "status": "SUCCEEDED", "error": None}
        controller._write_spool(lease["attempt_id"], result)
        self.assertEqual(controller.state.accept(lease["attempt_id"], result), "accepted")
        fresh = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0)
        counts = fresh.ingest_spool()
        self.assertEqual(counts["duplicate"], 1)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results WHERE task_id='INFRA-ACK-001'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
