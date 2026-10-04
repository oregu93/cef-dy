from __future__ import annotations

from copy import deepcopy
import json
import os
import sqlite3
import unittest
from unittest import mock

from task_orchestrator.config import DEFAULTS, load_config
from task_orchestrator.authoring import preflight_authoring
from task_orchestrator.dashboard import snapshot
from task_orchestrator.engine import Engine
from task_orchestrator.model import State
from task_orchestrator.reliability import M1bStore
from task_orchestrator.store import Store
from task_orchestrator.telegram import (
    SendOutcomeUnknown, TelegramBotAPI, TelegramGateway, TelegramSecrets, TelegramStore,
)

from .common import Fixture


class FakeTransport:
    def __init__(self):
        self.updates = []
        self.sent = []
        self.failure = None

    def get_updates(self, *, offset, timeout_seconds):
        if self.failure:
            raise self.failure
        return [item for item in self.updates if item["update_id"] >= offset]

    def send_message(self, *, text, reply_markup=None):
        if self.failure:
            raise self.failure
        self.sent.append((text, reply_markup))
        return str(100 + len(self.sent))


class TelegramGatewayTests(unittest.TestCase):
    USER = 10101
    CHAT = 20202

    def setUp(self):
        self.fx = Fixture()
        self.fx.cfg["telegram"].update(enabled=True, loop_delay_seconds=1)
        self.store = Store(self.fx.root / "state" / "state.sqlite3")
        self.control = M1bStore(self.store.conn, self.fx.cfg)
        self.control.checkpoint(
            CURRENT_PHASE="READY", CANONICAL_HEAD=self.fx.head,
            RECOVERY_PROOF_STATE="PROVEN",
            AUTONOMY_VISIBILITY_STATE="AUTONOMY_VISIBILITY_OK",
            HARD_BLOCKERS=[],
        )
        self.transport = FakeTransport()
        self.secrets = TelegramSecrets("test-placeholder-not-a-real-token", self.USER, self.CHAT)
        self.now = 1_800_000_000.0
        self.gateway = TelegramGateway(
            self.fx.cfg, self.store.conn, self.transport, self.secrets,
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def update(self, update_id, text, *, user=None, chat=None, forwarded=False):
        message = {
            "message_id": update_id,
            "from": {"id": self.USER if user is None else user},
            "chat": {"id": self.CHAT if chat is None else chat, "type": "private"},
            "text": text,
        }
        if forwarded:
            message["forward_date"] = 1
        return {"update_id": update_id, "message": message}

    def callback(self, update_id, data):
        return {
            "update_id": update_id,
            "callback_query": {
                "id": str(update_id), "from": {"id": self.USER}, "data": data,
                "message": {"message_id": 1, "chat": {"id": self.CHAT, "type": "private"}},
            },
        }

    def drain(self, limit=20):
        outcomes = []
        for _ in range(limit):
            value = self.gateway.deliver_once()
            outcomes.append(value)
            if value in {"idle", "muted"}:
                break
        return outcomes

    def test_exact_private_allowlist_precedes_command_interpretation(self):
        self.assertEqual(self.gateway.process_update(self.update(1, "/safe", user=999)), "unauthorized")
        self.assertEqual(self.gateway.process_update(self.update(2, "/safe", chat=999)), "unauthorized")
        self.assertEqual(self.gateway.process_update(self.update(3, "/safe", forwarded=True)), "unauthorized")
        self.assertEqual(self.gateway.store.state()["control_mode"], "NORMAL")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM telegram_confirmations").fetchone()[0], 0)

    def test_update_id_idempotency_and_conflict_quarantine(self):
        update = self.update(10, "/status")
        self.assertEqual(self.gateway.process_update(update), "processed")
        self.assertEqual(self.gateway.process_update(update), "duplicate")
        conflict = self.update(10, "/health")
        self.assertEqual(self.gateway.process_update(conflict), "conflict")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM telegram_updates").fetchone()[0], 1)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM telegram_events WHERE event_type='UPDATE_ID_CONFLICT'"
        ).fetchone()[0], 1)

    def test_interrupted_received_update_is_resumed_after_restart(self):
        update = self.update(11, "/last")
        payload_hash = __import__("hashlib").sha256(
            json.dumps(update, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(self.gateway.store.record_update(11, payload_hash), "created")
        restarted = TelegramGateway(
            self.fx.cfg, self.store.conn, self.transport, self.secrets,
            clock=lambda: self.now,
        )
        self.assertEqual(restarted.process_update(update), "processed")
        self.assertEqual(restarted.store.state()["update_offset"], 12)

    def test_notification_policy_suppresses_routine_and_deduplicates(self):
        body = {"reason_code": "WAIT", "safe_context": "Need input"}
        self.assertEqual(self.gateway.store.enqueue_projection(
            attention_id="a-1", source_event_id="event-1", task_id="T-1",
            kind="ROUTINE_PROGRESS", body=body,
        ), "suppressed")
        self.assertEqual(self.gateway.store.enqueue_projection(
            attention_id="a-1", source_event_id="event-1", task_id="T-1",
            kind="HUMAN_ACTION_REQUIRED", body=body,
        ), "enqueued")
        self.assertEqual(self.gateway.store.enqueue_projection(
            attention_id="a-1", source_event_id="event-1", task_id="T-1",
            kind="HUMAN_ACTION_REQUIRED", body=body,
        ), "duplicate")

    def test_projection_redacts_credentials_paths_and_mentions(self):
        self.assertEqual(self.gateway.store.enqueue_projection(
            attention_id="a-redact", source_event_id="event-redact", task_id="T-REDACT",
            kind="HUMAN_ACTION_REQUIRED",
            body={"reason_code": "WAIT", "safe_context":
                  "token=do-not-store /private/raw/result.dat @operator"},
        ), "enqueued")
        body = self.store.conn.execute(
            "SELECT body_json FROM telegram_projections WHERE attention_id='a-redact'"
        ).fetchone()[0]
        for forbidden in ("do-not-store", "/private/raw/result.dat", "@operator"):
            self.assertNotIn(forbidden, body)
        self.assertIn("[REDACTED]", body)
        self.assertIn("[path]", body)
        self.assertIn("[mention]", body)

    def test_ambiguous_send_is_at_least_once_with_stable_marker(self):
        self.gateway.store.enqueue_projection(
            attention_id="a-2", source_event_id="event-2", task_id="T-2",
            kind="RECOVERY_FAILED", body={"reason_code": "RECOVERY", "safe_context": "Needs operator"},
        )
        self.transport.failure = TimeoutError("ambiguous")
        self.assertEqual(self.gateway.deliver_once(), "SEND_OUTCOME_UNKNOWN")
        row = self.store.conn.execute("SELECT * FROM telegram_deliveries").fetchone()
        self.assertEqual(row["state"], "SEND_OUTCOME_UNKNOWN")
        self.now += 31
        self.transport.failure = None
        self.assertEqual(self.gateway.deliver_once(), "sent")
        row = self.store.conn.execute("SELECT * FROM telegram_deliveries").fetchone()
        self.assertEqual(row["state"], "SENT")
        self.assertEqual(row["attempts"], 2)
        self.assertIn("ref:" + row["delivery_id"][:10], self.transport.sent[0][0])

    def test_ambiguous_send_honors_bounded_retry_budget(self):
        self.fx.cfg["telegram"]["max_delivery_attempts"] = 1
        self.gateway.store.enqueue_projection(
            attention_id="a-bounded", source_event_id="event-bounded", task_id="T-BOUNDED",
            kind="RECOVERY_FAILED", body={"reason_code": "RECOVERY", "safe_context": "Needs operator"},
        )
        self.transport.failure = TimeoutError("ambiguous")
        self.assertEqual(self.gateway.deliver_once(), "SEND_OUTCOME_UNKNOWN")
        row = self.store.conn.execute("SELECT * FROM telegram_deliveries").fetchone()
        self.assertEqual(row["state"], "DEAD_LETTER")
        self.now += 31
        self.transport.failure = None
        self.assertEqual(self.gateway.deliver_once(), "idle")

    def test_bot_api_send_timeout_is_not_coerced_to_definite_failure(self):
        api = TelegramBotAPI(self.secrets, api_base="https://api.telegram.org", timeout_seconds=1)
        with mock.patch("task_orchestrator.telegram.request.urlopen", side_effect=TimeoutError()), \
                self.assertRaises(SendOutcomeUnknown):
            api.send_message(text="fixture", reply_markup=None)

    def test_expired_claim_recovers_as_unknown_not_blind_sent(self):
        self.gateway.store.enqueue_projection(
            attention_id="a-3", source_event_id="event-3", task_id="T-3",
            kind="PROJECT_STALLED", body={"reason_code": "BLOCKED", "safe_context": "Review"},
        )
        claimed = self.gateway.store.claim_delivery("crashed", self.now, 10)
        self.assertIsNotNone(claimed)
        self.assertEqual(self.gateway.store.reconcile_expired_claims(self.now + 11), 1)
        self.assertEqual(self.store.conn.execute("SELECT state FROM telegram_deliveries").fetchone()[0], "SEND_OUTCOME_UNKNOWN")

    def test_first_valid_response_wins_and_creates_one_user_decision(self):
        self.gateway.store.open_question(attention_id="question-1", task_id="TASK-1")
        self.assertEqual(self.gateway.store.accept_response(
            attention_id="question-1", update_id=20, text="option A"
        ), "ACCEPTED")
        self.assertEqual(self.gateway.store.accept_response(
            attention_id="question-1", update_id=21, text="option B"
        ), "REJECTED_ALREADY_ANSWERED")
        self.assertEqual(self.gateway.store.accept_response(
            attention_id="question-1", update_id=20, text="option A"
        ), "DUPLICATE")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM telegram_user_decisions").fetchone()[0], 1)
        decision = json.loads(self.store.conn.execute("SELECT decision_json FROM telegram_user_decisions").fetchone()[0])
        self.assertEqual(decision["authority"], "INPUT_ONLY_NON_AUTHORITATIVE")

    def test_response_cancellation_is_append_only_and_cannot_cancel_consumed(self):
        self.gateway.store.open_question(attention_id="question-2", task_id="TASK-2")
        self.gateway.store.accept_response(attention_id="question-2", update_id=30, text="answer")
        self.assertEqual(self.gateway.store.cancel_response("question-2", 31), "CANCEL_REQUESTED")
        self.store.conn.execute("UPDATE telegram_user_decisions SET consumed_at='2026-01-01T00:00:00Z'")
        self.assertEqual(self.gateway.store.cancel_response("question-2", 32), "ALREADY_CONSUMED")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM telegram_responses").fetchone()[0], 1)

    def test_read_only_commands_do_not_change_task_state(self):
        task = self.fx.task("READONLY-TASK-001")
        self.store.ingest(task)
        self.store.conn.execute("UPDATE tasks SET state='WAITING_USER',reason='Need choice' WHERE task_id=?", (task.task_id,))
        before = tuple(self.store.conn.execute("SELECT state,attempt,approved_at FROM tasks WHERE task_id=?", (task.task_id,)).fetchone())
        for number, command in enumerate(("/help", "/status", "/health", "/attention", "/last", f"/task {task.task_id}"), 40):
            self.assertEqual(self.gateway.process_update(self.update(number, command)), "processed")
        after = tuple(self.store.conn.execute("SELECT state,attempt,approved_at FROM tasks WHERE task_id=?", (task.task_id,)).fetchone())
        self.assertEqual(before, after)
        self.assertNotIn("/shell", self.gateway._help().casefold())

    def test_control_requires_callback_confirmation_and_engine_enforces_it(self):
        task = self.fx.task("CONTROLLED-LLM-001", task_type="llm_semantic", action="semantic_helper")
        self.assertEqual(self.gateway.process_update(self.update(50, "/safe")), "processed")
        self.assertEqual(self.gateway.store.state()["control_mode"], "NORMAL")
        token = self.store.conn.execute("SELECT token FROM telegram_confirmations").fetchone()[0]
        self.assertEqual(self.gateway.process_update(self.callback(51, f"confirm:{token}")), "processed")
        self.assertEqual(self.gateway.store.state()["control_mode"], "SAFE")
        engine = Engine(self.fx.cfg, self.store)
        self.assertEqual(engine.ingest(task), "admission_paused")
        self.assertIsNone(self.store.get(task.task_id))
        deterministic = self.fx.task("CONTROLLED-DETERMINISTIC-001")
        self.assertEqual(engine.ingest(deterministic), "admission_paused")
        self.assertIsNone(self.store.get(deterministic.task_id))

    def test_resume_requires_fresh_health_and_state_recheck(self):
        self.store.conn.execute("UPDATE telegram_gateway_state SET control_mode='SAFE'")
        self.assertEqual(self.gateway.process_update(self.update(60, "/resume")), "processed")
        token = self.store.conn.execute("SELECT token FROM telegram_confirmations").fetchone()[0]
        self.assertEqual(self.gateway.process_update(self.callback(61, f"confirm:{token}")), "processed")
        self.assertEqual(self.gateway.store.state()["control_mode"], "NORMAL")
        self.store.conn.execute("UPDATE telegram_gateway_state SET control_mode='SAFE'")
        self.control.checkpoint(AUTONOMY_VISIBILITY_STATE="AUTONOMY_VISIBILITY_DEGRADED")
        self.gateway.process_update(self.update(62, "/resume"))
        token = self.store.conn.execute("SELECT token FROM telegram_confirmations WHERE update_id=62").fetchone()[0]
        self.gateway.process_update(self.callback(63, f"confirm:{token}"))
        self.assertEqual(self.gateway.store.state()["control_mode"], "SAFE")

    def test_hold_and_release_are_exact_task_bound_and_durable(self):
        task = self.fx.task("HELD-TASK-001")
        self.gateway.process_update(self.update(70, f"/hold {task.task_id}"))
        token = self.store.conn.execute("SELECT token FROM telegram_confirmations WHERE update_id=70").fetchone()[0]
        self.gateway.process_update(self.callback(71, f"confirm:{token}"))
        self.assertEqual(Engine(self.fx.cfg, self.store).ingest(task), "admission_paused")
        self.gateway.process_update(self.update(72, f"/release {task.task_id}"))
        token = self.store.conn.execute("SELECT token FROM telegram_confirmations WHERE update_id=72").fetchone()[0]
        self.gateway.process_update(self.callback(73, f"confirm:{token}"))
        self.assertEqual(Engine(self.fx.cfg, self.store).ingest(task), "created")

    def test_gateway_outage_isolated_and_dashboard_observation_is_explicit(self):
        task = self.fx.task("OUTAGE-SAFE-001")
        Engine(self.fx.cfg, self.store).ingest(task)
        state_before = self.store.get(task.task_id)["state"]
        self.transport.failure = ConnectionError("offline")
        result = self.gateway.cycle()
        self.assertEqual(result["observation"]["state"], "DEGRADED")
        self.assertEqual(self.store.get(task.task_id)["state"], state_before)
        data = snapshot(self.fx.cfg)
        self.assertEqual(data["telegram"]["state"], "DEGRADED")

    def test_successful_cycle_exposes_fresh_gateway_observation(self):
        result = self.gateway.cycle()
        self.assertEqual(result["observation"]["state"], "HEALTHY")
        row = self.store.conn.execute("SELECT state_json FROM controller_state").fetchone()
        self.assertEqual(json.loads(row[0])["TELEGRAM_GATEWAY"]["state"], "HEALTHY")

    def test_trusted_historical_lifecycle_is_not_notified(self):
        task = self.fx.task("HISTORICAL-WAITING-001")
        self.store.ingest(task)
        self.store.conn.execute(
            "UPDATE tasks SET state='WAITING_USER',reason='historical question' WHERE task_id=?",
            (task.task_id,),
        )
        request = {
            "schema_version": 1, "operation_type": "CLOSE",
            "author_role": "00_PROJECT_CONTROL", "canonical_head": self.fx.head,
            "issue": {"number": task.source_issue, "state": "closed", "labels": ["orchestrator:task"]},
            "task": task.envelope_dict(),
            "existing_binding": {"source_issue": task.source_issue, "task_id": task.task_id,
                                 "envelope_hash": task.envelope_hash},
            "required_repository_paths": [], "dependency_bindings": [],
            "review_binding": None, "context_delta_bundle": None,
            "accepted_state_changes": [{
                "identity": "HISTORICAL-TELEGRAM-FILTER-001", "result_sha256": "a" * 64,
                "materialization_state": "NOT_STATE_CHANGING", "materialization_commit": None,
                "reason": None,
            }],
            "lifecycle": {"disposition": "CLOSED_HISTORICAL", "target_task_id": task.task_id,
                          "target_envelope_hash": task.envelope_hash, "successor_task_id": None,
                          "reason": "Accepted historical disposition."},
            "project_status": {
                "project_progress": "COMPLETED", "human_action_required": False,
                "semantic_state": "ACCEPTED", "design_state": "REVIEWED",
                "implementation_state": "COMPLETED", "deployment_state": "NOT_AUTHORIZED",
                "canonicalization_state": "NOT_STATE_CHANGING",
            },
            "execution_context": "SEPARATE_BOUNDED_WORK",
            "persistent_chat_role": "00_PROJECT_CONTROL",
            "chatgpt_scheduler_requested": False,
        }
        self.store.put_authoring_receipt(preflight_authoring(
            request, self.fx.cfg, observed_canonical_head=self.fx.head,
        ))
        self.assertEqual(self.gateway.sync_attention(), 0)
        self.assertEqual(self.gateway._attention(), "No current user-attention items.")

    def test_secrets_are_environment_only_and_transport_rejects_other_base(self):
        cfg = deepcopy(self.fx.cfg)
        secret_file = self.fx.root / "telegram-environment"
        secret_file.write_text("environment is loaded by systemd\n", encoding="utf-8")
        secret_file.chmod(0o600)
        cfg["telegram"]["secret_file"] = str(secret_file)
        env = {
            cfg["telegram"]["token_env"]: "local-secret-value",
            cfg["telegram"]["allowed_user_id_env"]: str(self.USER),
            cfg["telegram"]["allowed_chat_id_env"]: str(self.CHAT),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            secrets = TelegramSecrets.from_environment(cfg)
        self.assertEqual(secrets.user_id, self.USER)
        with self.assertRaises(RuntimeError):
            TelegramBotAPI(secrets, api_base="https://example.invalid", timeout_seconds=1)
        schema = "\n".join(row[0] for row in self.store.conn.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
        ))
        self.assertNotIn("local-secret-value", schema)

    def test_secret_file_permissions_fail_closed(self):
        cfg = deepcopy(self.fx.cfg)
        secret_file = self.fx.root / "telegram-environment"
        secret_file.write_text("not a secret fixture\n", encoding="utf-8")
        secret_file.chmod(0o644)
        cfg["telegram"]["secret_file"] = str(secret_file)
        env = {
            cfg["telegram"]["token_env"]: "fixture-token",
            cfg["telegram"]["allowed_user_id_env"]: str(self.USER),
            cfg["telegram"]["allowed_chat_id_env"]: str(self.CHAT),
        }
        with mock.patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            TelegramSecrets.from_environment(cfg)

    def test_cancel_never_terminates_a_task_or_process(self):
        task = self.fx.task("NO-KILL-001")
        Engine(self.fx.cfg, self.store).ingest(task)
        before = self.store.get(task.task_id)["state"]
        self.gateway.process_update(self.update(80, f"/cancel {task.task_id}"))
        self.assertEqual(self.store.get(task.task_id)["state"], before)


if __name__ == "__main__":
    unittest.main()
