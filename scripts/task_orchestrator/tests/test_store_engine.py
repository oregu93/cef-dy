from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import time
import unittest
from unittest import mock

from task_orchestrator.engine import Engine
from task_orchestrator.model import State, TransitionError, WorkerResult, utc_now
from task_orchestrator.store import Store

from .common import Fixture


class StoreEngineTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.store = Store(self.fx.root / "state" / "db.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)

    def tearDown(self):
        self.store.close(); self.fx.close()

    def test_duplicate_delivery_and_identity_conflict(self):
        task = self.fx.task()
        self.assertEqual(self.engine.ingest(task), "created")
        self.assertEqual(self.engine.ingest(task), "duplicate")
        self.assertEqual(self.store.event_count(task.task_id, "DUPLICATE_DELIVERY"), 1)
        with self.assertRaises(TransitionError): self.engine.ingest(self.fx.task(stop_condition="different"))

    def test_state_transition_and_run(self):
        task = self.fx.task()
        self.engine.ingest(task)
        self.assertEqual(self.store.get(task.task_id)["state"], "READY")
        results = self.engine.run_ready()
        self.assertEqual(results[0]["status"], "SUCCEEDED")
        self.assertEqual(self.store.get(task.task_id)["state"], "SUCCEEDED")
        self.assertTrue((self.fx.root / "state" / "results" / f"{task.task_id}.yaml").is_file())

    def test_dry_run_never_executes(self):
        self.fx.cfg["mode"] = "shadow"
        task = self.fx.task()
        self.engine.ingest(task)
        self.assertEqual(self.engine.run_ready(), [])
        self.assertEqual(self.store.get(task.task_id)["state"], "READY")

    def test_dependencies_and_failure_propagation(self):
        dep = self.fx.task("INFRA-DEP-001")
        child = self.fx.task("INFRA-CHILD-001", dependencies=(dep.task_id,))
        self.engine.ingest(child)
        self.assertEqual(self.store.get(child.task_id)["state"], "WAITING_DEPENDENCY")
        self.engine.ingest(dep); self.engine.run_ready(); self.engine.reevaluate_waiting()
        self.assertEqual(self.store.get(child.task_id)["state"], "READY")

    def test_dependency_cycle_blocks(self):
        a = self.fx.task("INFRA-CYCLE-A", dependencies=("INFRA-CYCLE-B",))
        b = self.fx.task("INFRA-CYCLE-B", dependencies=("INFRA-CYCLE-A",))
        self.engine.ingest(a); self.engine.ingest(b)
        cycles = self.engine.detect_cycles()
        self.assertTrue(cycles)
        self.assertEqual(self.store.get(a.task_id)["state"], "BLOCKED")
        self.assertEqual(self.store.get(b.task_id)["state"], "BLOCKED")

    def test_manual_llm_gate_and_quota_enters_recoverable_lane(self):
        task = self.fx.task("INFRA-LLM-001", task_type="llm_semantic", action="semantic_helper", labels=("orchestrator:task", "orchestrator:llm-approved"))
        self.engine.ingest(task)
        self.store.approve(task.task_id)
        self.engine.reevaluate_waiting()
        self.assertEqual(self.store.get(task.task_id)["state"], "WAITING_APPROVAL")
        self.fx.cfg["llm"]["dispatch_enabled"] = True
        self.engine.reevaluate_waiting()
        self.assertEqual(self.store.get(task.task_id)["state"], "READY")
        self.engine.pause_quota(task.task_id)
        self.assertEqual(self.store.get(task.task_id)["state"], "QUOTA_WAIT")
        self.engine.reevaluate_waiting()
        self.assertEqual(self.store.get(task.task_id)["state"], "QUOTA_WAIT")

    def test_orphan_recovery_deterministic_and_llm(self):
        det = self.fx.task("INFRA-ORPHAN-D")
        llm = self.fx.task("INFRA-ORPHAN-L", task_type="llm_semantic", action="semantic_helper")
        for task in (det, llm):
            self.store.ingest(task)
            self.store.transition(task.task_id, State.VALIDATED, "test")
            self.store.transition(task.task_id, State.READY, "test")
            self.store.transition(task.task_id, State.RUNNING, "test")
            old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
            self.store.conn.execute("UPDATE tasks SET updated_at=? WHERE task_id=?", (old, task.task_id))
        self.assertEqual(self.engine.recover_orphans(), 2)
        self.assertEqual(self.store.get(det.task_id)["state"], "READY")
        self.assertEqual(self.store.get(llm.task_id)["state"], "WAITING_APPROVAL")

    def test_worker_crash_becomes_failed(self):
        task = self.fx.task()
        self.engine.ingest(task)
        with mock.patch("task_orchestrator.engine.workers.run", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError): self.engine.run_ready()
        self.assertEqual(self.store.get(task.task_id)["state"], "RUNNING")
        self.store.conn.execute("UPDATE tasks SET updated_at=? WHERE task_id=?", ("2000-01-01T00:00:00Z", task.task_id))
        self.engine.recover_orphans()
        self.assertEqual(self.store.get(task.task_id)["state"], "READY")

    def test_invalid_transition(self):
        task = self.fx.task(); self.engine.ingest(task)
        with self.assertRaises(TransitionError): self.store.transition(task.task_id, State.RECEIVED, "backwards")

    def test_restart_reopens_database(self):
        task = self.fx.task(); self.engine.ingest(task)
        self.store.close()
        self.store = Store(self.fx.root / "state" / "db.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)
        self.assertEqual(self.store.get(task.task_id)["state"], "READY")
        self.store.integrity_check()


if __name__ == "__main__": unittest.main()
