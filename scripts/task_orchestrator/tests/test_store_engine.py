from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import sqlite3
import time
import unittest
from unittest import mock

import yaml

from orchestrate_tasks import main as cli_main
from task_orchestrator.engine import Engine
from task_orchestrator.github import Issue
from task_orchestrator.model import State, TransitionError, WorkerResult, utc_now
from task_orchestrator.reliability import M1bStore
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

    def test_preview_only_autonomy_holds_new_ordinary_before_ready(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["autonomy"].update(enabled=True, plan_only=False)
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        task = self.fx.task("OPAQUE-ORDINARY-001")
        self.assertEqual(self.engine.ingest(task), "admission_paused")
        self.assertIsNone(self.store.get(task.task_id))
        self.assertEqual(self.engine.run_ready(), [])

    def test_paused_new_ordinary_policy_failure_is_not_persisted(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["autonomy"].update(enabled=True, plan_only=False)
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        task = self.fx.task(
            "OPAQUE-INVALID-ORDINARY-001", action="test_command",
            inputs={"command_id": "not-allowlisted"},
        )
        self.assertEqual(self.engine.ingest(task), "admission_paused")
        self.assertIsNone(self.store.get(task.task_id))

    def test_forged_diagnostic_recovery_and_free_text_do_not_bypass(self):
        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["autonomy"].update(enabled=True, plan_only=False)
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        diagnostic = self.fx.task(
            "OPAQUE-DIAGNOSTIC-001",
            inputs={"admission_control": {"class": "DIAGNOSTIC", "authorized": True}},
        )
        recovery = self.fx.task(
            "OPAQUE-RECOVERY-001",
            inputs={"admission_control": {"class": "RECOVERY", "authorized": True}},
        )
        free_text = self.fx.task(
            "OPAQUE-FREE-TEXT-001", action="diagnostic repair",
            inputs={"description": "diagnostic repair"},
        )
        self.assertEqual(self.engine.ingest(diagnostic), "admission_blocked")
        self.assertEqual(self.engine.ingest(recovery), "admission_blocked")
        self.assertEqual(self.engine.ingest(free_text), "admission_paused")
        self.assertEqual(self.store.get(diagnostic.task_id)["state"], State.BLOCKED.value)
        self.assertEqual(self.store.get(recovery.task_id)["state"], State.BLOCKED.value)
        self.assertIsNone(self.store.get(free_text.task_id))

    def test_unresolved_original_identity_blocks_replacement_amplification(self):
        M1bStore(self.store.conn, self.fx.cfg)
        original = self.fx.task("ORIGINAL-UNRESOLVED-001")
        self.engine.ingest(original)
        replacement = self.fx.task(
            "ORIGINAL-REPLACEMENT-001",
            inputs={"replacement_for": original.task_id},
        )
        self.assertEqual(self.engine.ingest(replacement), "admission_paused")
        self.assertIsNone(self.store.get(replacement.task_id))

    def test_paused_gate_blocks_validated_dependency_and_approval_promotions(self):
        validated = self.fx.task("PAUSED-VALIDATED-001")
        self.store.ingest(validated)
        self.store.transition(validated.task_id, State.VALIDATED, "test fixture")

        dependency = self.fx.task("PAUSED-DEPENDENCY-001")
        child = self.fx.task(
            "PAUSED-DEPENDENCY-CHILD-001", dependencies=(dependency.task_id,),
        )
        self.engine.ingest(child)
        self.engine.ingest(dependency)
        self.engine.run_ready()

        approval = self.fx.task(
            "PAUSED-APPROVAL-001", task_type="llm_semantic",
            action="semantic_helper",
            labels=("orchestrator:task", "orchestrator:llm-approved"),
        )
        self.engine.ingest(approval)
        self.store.approve(approval.task_id)

        self.fx.cfg["github"]["enabled"] = True
        self.fx.cfg["autonomy"].update(enabled=True, plan_only=False)
        self.fx.cfg["publishing"].update(enabled=False, preview_only=True)
        self.fx.cfg["llm"]["dispatch_enabled"] = True
        self.engine.reevaluate_waiting()

        self.assertEqual(self.store.get(validated.task_id)["state"], State.VALIDATED.value)
        self.assertEqual(self.store.get(child.task_id)["state"], State.WAITING_DEPENDENCY.value)
        self.assertEqual(self.store.get(approval.task_id)["state"], State.WAITING_APPROVAL.value)

    @staticmethod
    def _live_cfg(fixture):
        fixture.cfg["mode"] = "pilot"
        fixture.cfg["github"]["enabled"] = True
        fixture.cfg["autonomy"].update(enabled=True, plan_only=False)
        fixture.cfg["publishing"].update(
            enabled=True, preview_only=False, trusted_authors=["trusted-bot"],
        )

    def test_direct_engine_reconstructs_incomplete_proof_and_fails_closed(self):
        for proof_state in ("NOT_PROVEN", "ONE_HEALTHY_OBSERVATION"):
            with self.subTest(proof_state=proof_state):
                fx = Fixture()
                store = Store(fx.root / "state" / "state.sqlite3")
                try:
                    self._live_cfg(fx)
                    M1bStore(store.conn, fx.cfg).checkpoint(
                        RECOVERY_PROOF_STATE=proof_state,
                        RECOVERY_FIRST_HEALTHY_AT=100.0,
                        RECOVERY_LAST_HEALTHY_AT=100.0,
                    )
                    first = Engine(fx.cfg, store)
                    second = Engine(fx.cfg, store)
                    for engine, suffix in ((first, "A"), (second, "B")):
                        task = fx.task(f"DIRECT-{proof_state}-{suffix}")
                        self.assertEqual(engine.ingest(task), "admission_paused")
                        self.assertIsNone(store.get(task.task_id))
                finally:
                    store.close()
                    fx.close()

    def test_direct_engine_missing_or_malformed_proof_fails_closed(self):
        for stored_state in (None, {}, {"RECOVERY_PROOF_STATE": "BROKEN"}, "not-json"):
            with self.subTest(stored_state=stored_state):
                fx = Fixture()
                store = Store(fx.root / "state" / "state.sqlite3")
                try:
                    self._live_cfg(fx)
                    M1bStore(store.conn, fx.cfg)
                    if stored_state is not None:
                        state_json = (
                            stored_state if isinstance(stored_state, str)
                            else json.dumps(stored_state)
                        )
                        store.conn.execute(
                            "INSERT INTO controller_state VALUES(?,?,?)",
                            ("ORCH-M1B-RELIABILITY-REBUILD-001", state_json, utc_now()),
                        )
                    engine = Engine(fx.cfg, store)
                    task = fx.task("DIRECT-MALFORMED-PROOF-001")
                    self.assertEqual(engine.ingest(task), "admission_paused")
                    self.assertIsNone(store.get(task.task_id))
                finally:
                    store.close()
                    fx.close()

    def test_direct_engine_proven_requires_current_healthy_visibility(self):
        for publication_state in (None, "UNKNOWN", "CONFLICT", "FAILED", "SENDING"):
            with self.subTest(publication_state=publication_state):
                fx = Fixture()
                store = Store(fx.root / "state" / "state.sqlite3")
                try:
                    task = fx.task("DURABLE-RESULT-001", source_issue=77)
                    store.ingest(task)
                    store.transition(task.task_id, State.VALIDATED, "fixture")
                    store.transition(task.task_id, State.READY, "fixture")
                    store.transition(task.task_id, State.RUNNING, "fixture")
                    store.transition(task.task_id, State.SUCCEEDED, "fixture")
                    M1bStore(store.conn, fx.cfg)
                    result_json = json.dumps({"task_id": task.task_id}, sort_keys=True)
                    store.conn.execute(
                        "INSERT INTO accepted_results VALUES(?,?,?,?,?)",
                        (task.task_id, "attempt-1", "a" * 64, result_json, utc_now()),
                    )
                    if publication_state is not None:
                        store.enqueue_publication(
                            publication_id="durable-result-publication",
                            repository="org/repo", task_id=task.task_id,
                            envelope_hash=store.get(task.task_id)["envelope_hash"],
                            result_sha256="a" * 64, target="issue:77",
                            marker="<!-- cef-dy-orch-result:v1 fixture -->",
                            preview="fixture", status=publication_state,
                        )
                    M1bStore(store.conn, fx.cfg).checkpoint(
                        RECOVERY_PROOF_STATE="PROVEN",
                        RECOVERY_FIRST_HEALTHY_AT=100.0,
                        RECOVERY_LAST_HEALTHY_AT=200.0,
                    )
                    self._live_cfg(fx)
                    engine = Engine(fx.cfg, store)
                    ordinary = fx.task("DIRECT-PROVEN-OPAQUE-001")
                    self.assertEqual(engine.ingest(ordinary), "admission_paused")
                    self.assertIsNone(store.get(ordinary.task_id))
                finally:
                    store.close()
                    fx.close()

    def test_direct_engine_proven_and_currently_healthy_allows_ordinary(self):
        fx = Fixture()
        store = Store(fx.root / "state" / "state.sqlite3")
        try:
            self._live_cfg(fx)
            M1bStore(store.conn, fx.cfg).checkpoint(
                RECOVERY_PROOF_STATE="PROVEN",
                RECOVERY_FIRST_HEALTHY_AT=100.0,
                RECOVERY_LAST_HEALTHY_AT=200.0,
            )
            engine = Engine(fx.cfg, store)
            task = fx.task("DIRECT-PROVEN-HEALTHY-001")
            self.assertEqual(engine.ingest(task), "created")
            self.assertEqual(store.get(task.task_id)["state"], State.READY.value)
            self.assertEqual(engine.run_ready()[0]["status"], "SUCCEEDED")
        finally:
            store.close()
            fx.close()

    def test_cli_surfaces_cannot_bypass_or_advance_incomplete_proof(self):
        for proof_state in ("NOT_PROVEN", "ONE_HEALTHY_OBSERVATION"):
            with self.subTest(proof_state=proof_state):
                fx = Fixture()
                store = Store(fx.root / "state" / "state.sqlite3")
                try:
                    self._live_cfg(fx)
                    m1b = M1bStore(store.conn, fx.cfg)
                    m1b.checkpoint(
                        RECOVERY_PROOF_STATE=proof_state,
                        RECOVERY_FIRST_HEALTHY_AT=100.0,
                        RECOVERY_LAST_HEALTHY_AT=100.0,
                    )
                    ready = fx.task(f"CLI-READY-{proof_state}")
                    waiting = fx.task(
                        f"CLI-APPROVAL-{proof_state}", task_type="llm_semantic",
                        action="semantic_helper",
                        labels=("orchestrator:task", "orchestrator:llm-approved"),
                    )
                    orphan = fx.task(f"CLI-ORPHAN-{proof_state}")
                    for task, target in (
                        (ready, State.READY),
                        (waiting, State.WAITING_APPROVAL),
                        (orphan, State.RUNNING),
                    ):
                        store.ingest(task)
                        store.transition(task.task_id, State.VALIDATED, "fixture")
                        if target is State.RUNNING:
                            store.transition(task.task_id, State.READY, "fixture")
                        store.transition(task.task_id, target, "fixture")
                    store.conn.execute(
                        "UPDATE tasks SET updated_at='2000-01-01T00:00:00Z' "
                        "WHERE task_id=?", (orphan.task_id,),
                    )
                finally:
                    store.close()

                config = fx.root / "orchestrator.yaml"
                config.write_text(yaml.safe_dump(fx.cfg, sort_keys=False), encoding="utf-8")
                ingest_task = fx.task(f"CLI-INGEST-{proof_state}")
                ingest_path = fx.root / "ingest.yaml"
                ingest_payload = {
                    key: value for key, value in ingest_task.canonical_dict().items()
                    if key not in {"source_issue", "labels"}
                }
                ingest_path.write_text(
                    yaml.safe_dump(ingest_payload, sort_keys=False),
                    encoding="utf-8",
                )
                poll_task_id = f"CLI-POLL-{proof_state}"
                poll_payload = {
                    key: value for key, value in fx.task(poll_task_id).canonical_dict().items()
                    if key not in {"source_issue", "labels"}
                }
                issue_body = "task\n```yaml\n" + yaml.safe_dump(
                    poll_payload, sort_keys=False,
                ) + "```\n"
                issue = Issue(
                    9901, "task", issue_body, ("orchestrator:task",), "etag",
                )

                commands = (
                    ("ingest", ["ingest", str(ingest_path)]),
                    ("run-ready", ["run-ready"]),
                    ("approve", ["approve", waiting.task_id]),
                    ("recover", ["recover"]),
                )
                for _name, command in commands:
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(
                            cli_main(["--config", str(config), *command]), 0,
                        )
                with mock.patch(
                    "task_orchestrator.engine.GitHubIssueSource",
                    return_value=mock.Mock(
                        fetch=mock.Mock(return_value=([issue], '"etag"', False)),
                    ),
                ), redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        cli_main(["--config", str(config), "poll-once"]), 0,
                    )

                verify = Store(fx.root / "state" / "state.sqlite3")
                try:
                    self.assertIsNone(verify.get(ingest_task.task_id))
                    self.assertIsNone(verify.get(poll_task_id))
                    self.assertEqual(verify.get(ready.task_id)["state"], State.READY.value)
                    self.assertEqual(
                        verify.get(waiting.task_id)["state"], State.WAITING_APPROVAL.value,
                    )
                    self.assertEqual(
                        verify.get(orphan.task_id)["state"], State.FAILED_RETRYABLE.value,
                    )
                    self.assertEqual(
                        M1bStore(verify.conn, fx.cfg).recovery_proof()["state"],
                        proof_state,
                    )
                    self.assertEqual(verify.get(ready.task_id)["attempt"], 0)
                finally:
                    verify.close()
                    fx.close()


if __name__ == "__main__": unittest.main()
