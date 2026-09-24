from __future__ import annotations

from dataclasses import replace
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import yaml

from task_orchestrator.engine import Engine
from task_orchestrator.config import load_config
from task_orchestrator.locking import LockBusy, ProcessLock
from task_orchestrator.model import State, TransitionError, ValidationError
from task_orchestrator.publishing import (
    AmbiguousDelivery, CommentPage, OutboxStatus, Publisher, RemoteComment,
    TransportResponse, enqueue_result_preview, load_result,
)
from task_orchestrator.store import Store
from task_orchestrator.visibility import (
    CURRENT_SCIENCE_LANE_FIXTURE, ExecutionLane, QuotaSnapshot, QuotaState,
    QuotaWindow, VisibilityState, project_board, quota_eligibility,
    science_lane_fixtures, validate_sidecar,
)

from .common import Fixture


def _hold_process_lock(path, ready, release):
    lock = ProcessLock(Path(path), 30)
    lock.acquire()
    ready.set()
    release.wait(10)
    lock.release()


class Transport:
    def __init__(self, response=None, error=None, page=None):
        self.response = response or TransportResponse(201, "comment-1")
        self.error = error
        self.page = page or CommentPage((), True)
        self.sends = 0

    def send_comment(self, target, body):
        self.sends += 1
        if self.error:
            raise self.error
        return self.response

    def list_comments(self, target):
        return self.page


class VisibilityPublishingTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture(mode="pilot")
        self.store = Store(self.fx.root / "state" / "db.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def sidecar(self, task_id="ORCH-M1-VIS-001", envelope_hash="a" * 64, **changes):
        value = dict(CURRENT_SCIENCE_LANE_FIXTURE)
        value.update({
            "task_id": task_id, "envelope_hash": envelope_hash,
            "current_observed_status": "AVAILABLE",
            "execution_lane": ExecutionLane.QUOTA_CONSUMING_UNATTENDED.value,
            "human_attention_class": "NONE", "unattended_safe": True,
            "away_eligible": True, "interactive_explicit": False,
            "chat_only": False, "handoff_delivered": False,
            "observation_source": "LOCAL_FIXTURE", "dispatch_claim": "NONE",
        })
        value.update(changes)
        return value

    def quota(self, five="AVAILABLE", weekly="AVAILABLE", observed="2026-09-24T00:00:00Z"):
        return QuotaSnapshot(
            QuotaWindow("five_hour", five, observed, "2026-09-24T05:00:00Z"),
            QuotaWindow("weekly", weekly, observed, "2026-09-30T00:00:00Z"),
            10_000_000,
        )

    def terminal_result(self, task_id="ORCH-M1-PUB-001"):
        task = self.fx.task(task_id)
        self.engine.ingest(task)
        self.engine.run_ready()
        return task, self.fx.root / "state" / "results" / f"{task_id}.yaml"

    def test_sidecar_is_separate_from_worker_queue_and_identity_is_strict(self):
        value = self.sidecar()
        self.assertEqual(self.store.put_sidecar(value), "created")
        self.assertEqual(self.store.put_sidecar(value), "duplicate")
        self.assertIsNone(self.store.get(value["task_id"]))
        with self.assertRaises(TransitionError):
            self.store.put_sidecar(self.sidecar(envelope_hash="b" * 64))

        task = self.fx.task("ORCH-M1-VIS-WORKER-001")
        self.engine.ingest(task)
        with self.assertRaises(TransitionError):
            self.store.put_sidecar(self.sidecar(
                task.task_id, envelope_hash="c" * 64,
            ))
        matching = self.sidecar(task.task_id, envelope_hash=task.envelope_hash)
        self.assertEqual(self.store.put_sidecar(matching), "created")

    def test_malformed_partial_oversized_and_override_sidecars_fail_closed(self):
        valid = self.sidecar()
        for bad in ({}, {**valid, "surprise": 1}, {key: value for key, value in valid.items() if key != "target_chat"}):
            with self.subTest(keys=sorted(bad)), self.assertRaises(ValidationError):
                validate_sidecar(bad)
        with self.assertRaises(ValidationError):
            validate_sidecar({**valid, "scientific_parent": "x" * 40_000})
        with self.assertRaises(ValidationError):
            validate_sidecar({**valid, "external_project_fields": {"state": "RUNNING"}})
        harmless = validate_sidecar({
            **valid, "external_project_fields": {"unknown_project_field": "human value"},
        })
        self.assertEqual(harmless["external_project_fields"]["unknown_project_field"],
                         "human value")
        self.assertIsNone(self.store.get(valid["task_id"]))

    def test_quota_windows_are_independent_and_reset_never_resumes_paused(self):
        unknown = QuotaSnapshot.unknown()
        eligible, reasons = quota_eligibility(
            lane=ExecutionLane.QUOTA_CONSUMING_UNATTENDED.value,
            unattended_safe=True, interactive_explicit=False, task_state="READY",
            quota=unknown, now_epoch=time.time(),
        )
        self.assertFalse(eligible)
        self.assertIn("FIVE_HOUR_QUOTA_UNKNOWN", reasons)
        eligible, reasons = quota_eligibility(
            lane=ExecutionLane.QUOTA_CONSUMING_INTERACTIVE.value,
            unattended_safe=False, interactive_explicit=True, task_state="READY",
            quota=unknown, now_epoch=time.time(),
        )
        self.assertTrue(eligible)
        self.assertTrue(any(reason.endswith("INTERACTIVE_OVERRIDE") for reason in reasons))
        stale = self.quota(observed="2020-01-01T00:00:00Z")
        eligible, reasons = quota_eligibility(
            lane=ExecutionLane.QUOTA_CONSUMING_UNATTENDED.value,
            unattended_safe=True, interactive_explicit=False, task_state="READY",
            quota=stale, now_epoch=1_797_000_000,
        )
        self.assertFalse(eligible)
        self.assertIn("FIVE_HOUR_QUOTA_STALE", reasons)
        exhausted = self.quota(five="EXHAUSTED")
        self.assertFalse(quota_eligibility(
            lane=ExecutionLane.QUOTA_CONSUMING_INTERACTIVE.value,
            unattended_safe=False, interactive_explicit=True, task_state="READY",
            quota=exhausted, now_epoch=1_797_000_000,
        )[0])
        passed_reset = QuotaSnapshot(
            QuotaWindow("five_hour", "AVAILABLE", "2026-09-24T00:00:00Z", "2020-01-01T00:00:00Z"),
            QuotaWindow("weekly", "AVAILABLE", "2026-09-24T00:00:00Z", "2020-01-01T00:00:00Z"),
            10_000_000,
        )
        self.assertFalse(quota_eligibility(
            lane=ExecutionLane.QUOTA_CONSUMING_INTERACTIVE.value,
            unattended_safe=True, interactive_explicit=True, task_state="PAUSED_QUOTA",
            quota=passed_reset, now_epoch=1_797_000_000,
        )[0])

    def test_local_deterministic_is_quota_independent(self):
        eligible, reasons = quota_eligibility(
            lane=ExecutionLane.LOCAL_DETERMINISTIC.value,
            unattended_safe=True, interactive_explicit=False, task_state="READY",
            quota=QuotaSnapshot.unknown(), now_epoch=time.time(),
        )
        self.assertTrue(eligible)
        self.assertEqual(reasons, [])

    def test_board_projects_available_not_dispatched_handoff_and_science_fixture(self):
        self.store.put_sidecar(self.sidecar())
        handoff = self.sidecar(
            "ORCH-M1-HANDOFF-001", execution_lane="HUMAN_CHAT_HANDOFF",
            human_attention_class="HANDOFF", unattended_safe=False,
            away_eligible=False, chat_only=True, handoff_delivered=False,
        )
        self.store.put_sidecar(handoff)
        fixtures = science_lane_fixtures()
        science = fixtures["current_review"]
        self.assertEqual(science["task_id"],
                         "STAGE03R-CS15-SYNTHETIC-HYPERSPACE-MVP-SCIENTIFIC-REVIEW-001")
        self.assertEqual(science["target_chat"], "03 - CEF Modelling & Fit Design")
        self.assertEqual(science["current_observed_status"],
                         "COMPLETED_RESULT_LEVEL_REVIEW")
        self.assertEqual(
            science["external_project_fields"]["terminal_verdict"],
            "IMPLEMENTATION_ARTIFACT_VERIFICATION_REQUIRED",
        )
        self.assertEqual(
            science["external_project_fields"]["canonicalization"],
            "DEFERRED_PENDING_ARTIFACT_LEVEL_VERIFICATION",
        )
        self.store.put_sidecar(science)
        queued = fixtures["next_science_support_task"]
        self.store.put_sidecar(queued)
        self.assertEqual(
            queued["task_id"],
            "STAGE03R-CS15-SYNTHETIC-MVP-ARTIFACT-REVIEW-PACKAGE-001",
        )
        self.assertEqual(queued["current_observed_status"], "WAITING_EXECUTION_LANE")
        self.assertEqual(queued["target_chat"], "WKB-R3")
        continuation = fixtures["continuation"]
        self.assertEqual(continuation, {
            "target_chat": "03 - CEF Modelling & Fit Design",
            "purpose": "artifact-level continuation of the existing CS15 scientific review",
            "state": "WAITING_DEPENDENCY",
            "dependency": "CS15 exact artifact review package",
            "dispatch_claim": "NONE",
        })
        board = project_board(self.store, self.quota(), now_epoch=1_797_000_000)
        by_id = {item["task_id"]: item for item in board["queue"]}
        self.assertEqual(by_id["ORCH-M1-VIS-001"]["visibility_state"],
                         VisibilityState.TASK_AVAILABLE_BUT_NOT_DISPATCHED.value)
        self.assertEqual(by_id["ORCH-M1-HANDOFF-001"]["visibility_state"],
                         VisibilityState.CHAT_HANDOFF_REQUIRED.value)
        self.assertEqual(
            by_id[science["task_id"]]["visibility_state"],
            "COMPLETED_RESULT_LEVEL_REVIEW",
        )
        self.assertEqual(
            by_id[queued["task_id"]]["visibility_state"],
            VisibilityState.TASK_AVAILABLE_BUT_NOT_DISPATCHED.value,
        )
        self.assertIn(
            "WKB-R3 currently occupied by active Orch M1 implementation",
            by_id[queued["task_id"]]["WHY_NOT_RUNNING"],
        )
        self.assertIsNone(self.store.get(queued["task_id"]))
        self.assertEqual(board["worker_starts"], 0)
        self.assertEqual(board["llm_calls"], 0)
        self.assertEqual(board["github_mutations"], 0)

    def test_shadow_preview_has_zero_execution_or_mutation(self):
        self.fx.cfg["mode"] = "shadow"
        task = self.fx.task("ORCH-M1-SHADOW-001")
        self.engine.ingest(task)
        with mock.patch("task_orchestrator.engine.workers.run") as worker:
            self.assertEqual(self.engine.run_ready(), [])
        worker.assert_not_called()
        self.assertEqual(self.store.get(task.task_id)["attempt"], 0)

    def test_preview_is_safe_and_idempotent_across_restart(self):
        task, result_path = self.terminal_result()
        result = yaml.safe_load(result_path.read_text())
        result["error"] = "notify @all\x00 safely ``` <script>"
        result_path.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
        first = enqueue_result_preview(
            self.store, repository="oregu93/cef-dy", target="issue:1",
            result_path=result_path, preview_only=True,
        )
        self.assertEqual(first["status"], "PREVIEW")
        self.assertIn("@\u200ball", first["preview"])
        self.assertNotIn("\x00", first["preview"])
        self.assertNotIn("<script>", first["preview"])
        self.assertEqual(first["preview"].count("```"), 2)
        self.assertEqual(enqueue_result_preview(
            self.store, repository="oregu93/cef-dy", target="issue:1",
            result_path=result_path, preview_only=True,
        )["outcome"], "duplicate")
        publication_id = first["publication_id"]
        self.store.close()
        self.store = Store(self.fx.root / "state" / "db.sqlite3")
        self.assertEqual(self.store.publication(publication_id)["result_sha256"],
                         first["result_sha256"])

    def test_same_identity_different_result_sha_is_conflict(self):
        _task, result_path = self.terminal_result("ORCH-M1-PUB-CONFLICT")
        enqueue_result_preview(self.store, repository="oregu93/cef-dy",
                               target="issue:2", result_path=result_path)
        result = yaml.safe_load(result_path.read_text())
        result["checks"].append({"changed": True})
        result_path.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
        with self.assertRaises(TransitionError):
            enqueue_result_preview(self.store, repository="oregu93/cef-dy",
                                   target="issue:2", result_path=result_path)

    def test_live_publishing_config_and_unsafe_targets_fail_closed(self):
        config = self.fx.root / "publisher.yaml"
        config.write_text("publishing:\n  enabled: true\n  preview_only: false\n",
                          encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_config(config)
        _task, result_path = self.terminal_result("ORCH-M1-PUB-TARGET")
        with self.assertRaises(ValidationError):
            enqueue_result_preview(self.store, repository="oregu93/cef-dy",
                                   target="https://example.invalid", result_path=result_path)

    def test_missing_corrupt_mismatched_result_and_missing_event_fail_closed(self):
        with self.assertRaises(ValidationError):
            load_result(self.fx.root / "missing.yaml")
        bad = self.fx.root / "bad.yaml"
        bad.write_text(": malformed", encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_result(bad)
        task, result_path = self.terminal_result("ORCH-M1-PUB-MISMATCH")
        result = yaml.safe_load(result_path.read_text())
        result["task_id"] = "OTHER-TASK"
        result_path.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
        with self.assertRaises(ValidationError):
            enqueue_result_preview(self.store, repository="oregu93/cef-dy",
                                   target="issue:3", result_path=result_path)

    def _pending(self, task_id="ORCH-M1-PUB-SEND"):
        _task, result_path = self.terminal_result(task_id)
        return enqueue_result_preview(self.store, repository="oregu93/cef-dy",
                                      target="issue:9", result_path=result_path,
                                      preview_only=False)

    def publisher(self, transport, **changes):
        options = dict(lock_path=self.fx.root / "state" / "publisher.lock",
                       lock_stale_after_seconds=10, enabled=True,
                       preview_only=False, trusted_authors=("trusted-bot",))
        options.update(changes)
        return Publisher(self.store, transport, **options)

    def test_ambiguous_send_becomes_unknown_and_is_never_blindly_retried(self):
        pending = self._pending()
        transport = Transport(error=AmbiguousDelivery("disconnect after acceptance"))
        publisher = self.publisher(transport)
        self.assertEqual(publisher.publish(pending["publication_id"])["status"], "UNKNOWN")
        self.assertEqual(publisher.publish(pending["publication_id"])["network_writes"], 0)
        self.assertEqual(transport.sends, 1)

    def test_reconciliation_requires_complete_pagination_trusted_unique_marker(self):
        pending = self._pending("ORCH-M1-PUB-RECON")
        publication_id = pending["publication_id"]
        self.store.update_publication(publication_id, "UNKNOWN")
        marker = self.store.publication(publication_id)["marker"]
        incomplete = self.publisher(Transport(page=CommentPage((), False)))
        self.assertEqual(incomplete.reconcile(publication_id)["status"], "UNKNOWN")
        forged = self.publisher(Transport(page=CommentPage(
            (RemoteComment(marker, None, "x"),), True)))
        self.assertEqual(forged.reconcile(publication_id)["status"], "CONFLICT")

        other = self._pending("ORCH-M1-PUB-RECON-OK")
        marker = self.store.publication(other["publication_id"])["marker"]
        trusted_body = self.store.publication(other["publication_id"])["preview"]
        trusted = self.publisher(Transport(page=CommentPage(
            (RemoteComment(trusted_body, "trusted-bot", "ok"),), True)))
        self.assertEqual(trusted.reconcile(other["publication_id"])["status"], "PUBLISHED")
        trusted.transport.page = CommentPage((
            RemoteComment(trusted_body, "trusted-bot", "a"),
            RemoteComment(trusted_body, "trusted-bot", "b"),
        ), True)
        self.assertEqual(trusted.reconcile(other["publication_id"])["status"], "CONFLICT")
        trusted.transport.page = CommentPage((
            RemoteComment(trusted_body + marker, "trusted-bot", "edited"),
        ), True)
        self.assertEqual(trusted.reconcile(other["publication_id"])["status"], "CONFLICT")
        trusted.transport.page = CommentPage((), True)
        self.assertEqual(trusted.audit_published(other["publication_id"])["status"], "UNKNOWN")

    def test_http_failures_backoff_and_uncertain_server_response(self):
        cases = [(401, "FAILED"), (403, "FAILED"), (429, "PENDING"), (500, "UNKNOWN")]
        for index, (code, expected) in enumerate(cases):
            with self.subTest(code=code):
                pending = self._pending(f"ORCH-M1-PUB-HTTP-{index}")
                response = TransportResponse(code, retry_after_seconds=17)
                result = self.publisher(Transport(response=response)).publish(
                    pending["publication_id"], now_epoch=100.0)
                self.assertEqual(result["status"], expected)
                if code == 429:
                    self.assertEqual(self.store.publication(pending["publication_id"])["backoff_until"], 117.0)

    def test_restart_marks_interrupted_send_unknown(self):
        pending = self._pending("ORCH-M1-PUB-RESTART")
        self.store.claim_publication(pending["publication_id"], now_epoch=time.time())
        self.assertEqual(self.store.recover_uncertain_publications(), 1)
        self.assertEqual(self.store.publication(pending["publication_id"])["status"], "UNKNOWN")

    def test_sqlite_transaction_fault_rolls_back_outbox(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.store.conn.execute(
                    "INSERT INTO publication_outbox(publication_id,repository,task_id,envelope_hash,result_sha256,target,marker,preview,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    ("x", "o/r", "TASK-001", "a" * 64, "b" * 64, "issue:1",
                     "marker", "preview", "PENDING", "now", "now"),
                )
                raise RuntimeError("injected")
        self.assertIsNone(self.store.publication("x"))

    def test_publisher_lock_prevents_two_effective_senders_and_stale_lock_recovers(self):
        pending = self._pending("ORCH-M1-PUB-LOCK")
        transport = Transport()
        publisher = self.publisher(transport)
        context = multiprocessing.get_context("fork")
        ready = context.Event()
        release = context.Event()
        holder = context.Process(
            target=_hold_process_lock,
            args=(str(publisher.lock_path), ready, release),
        )
        holder.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaises(LockBusy):
                publisher.publish(pending["publication_id"])
        finally:
            release.set()
            holder.join(5)
        self.assertEqual(holder.exitcode, 0)
        self.assertEqual(transport.sends, 0)
        publisher.lock_path.write_text(json.dumps(
            {"pid": 99999999, "host": "x", "created": time.time() - 100}), encoding="utf-8")
        publisher.lock_stale_after_seconds = 1
        self.assertEqual(publisher.publish(pending["publication_id"])["status"], "PUBLISHED")
        self.assertEqual(transport.sends, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
