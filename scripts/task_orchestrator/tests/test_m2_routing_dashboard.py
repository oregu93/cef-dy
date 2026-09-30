from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

import yaml

from task_orchestrator.dashboard import create_server, open_readonly, snapshot
from task_orchestrator.engine import Engine
from task_orchestrator.model import State
from task_orchestrator.reliability import Admission, M1bController, M1bStore, SubprocessAITransport
from task_orchestrator.routing import ROLE_IDS, ProductionRouter, load_registry
from task_orchestrator.store import Store

from .common import Fixture


ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAPS = ROOT / "03_Protocols" / "CHAT_BOOTSTRAPS.md"


class FakeAI:
    def __init__(self):
        self.tasks = []

    def probe(self):
        return Admission("ACCEPTED", {"text": "ADMISSION_OK"})

    def execute(self, task, attempt):
        self.tasks.append(task.task_id)
        return Admission("ACCEPTED", {
            "status": "SUCCEEDED", "summary": "completed",
            "checks": [], "artifacts": [], "error": None,
        })


class SequenceAI(FakeAI):
    def __init__(self, outcomes):
        super().__init__()
        self.outcomes = list(outcomes)

    def execute(self, task, attempt):
        self.tasks.append(task.task_id)
        return self.outcomes.pop(0)


class M2RoutingDashboardTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.fx.cfg["autonomy"]["enabled"] = True
        self.fx.cfg["autonomy"]["max_batch_tasks"] = 16
        self.fx.cfg["routing"].update(enabled=True, bootstrap_path=str(BOOTSTRAPS))
        self.fx.cfg["dashboard"].update(enabled=True, port=0, stale_after_seconds=300)
        self.fx.cfg["llm"].update(
            dispatch_enabled=True, detached_workers=False, require_local_approval=False,
        )
        self.store = Store(self.fx.root / "state" / "state.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def test_registry_is_exact_complete_and_stably_hashed(self):
        roles = load_registry(BOOTSTRAPS)
        self.assertEqual(tuple(sorted(roles)), ROLE_IDS)
        for role_id, role in roles.items():
            self.assertTrue(role.bootstrap_text.startswith(f"## {role_id} - "))
            self.assertEqual(len(role.bootstrap_sha256), 64)
        broken = self.fx.root / "broken.md"
        broken.write_text("## 07 - Only one\ntext\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            load_registry(broken)

    def test_routes_aliases_and_prefers_local_before_ai(self):
        fake = FakeAI()
        self.engine.ingest(self.fx.task(
            task_id="AI-FIRST-001", role="03_CEF_MODELLING_FIT_DESIGN",
            task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:llm-approved",),
            inputs={"resource_requirement": "WORK_REQUIRED"},
        ))
        self.engine.ingest(self.fx.task(task_id="LOCAL-SECOND-001"))
        output = M1bController(self.fx.cfg, self.store, fake).cycle()
        self.assertEqual([item["task_id"] for item in output["dispatched"]],
                         ["LOCAL-SECOND-001", "AI-FIRST-001"])
        routes = {row["task_id"]: dict(row) for row in self.store.conn.execute("SELECT * FROM task_routes")}
        self.assertEqual(routes["LOCAL-SECOND-001"]["role_id"], "07")
        self.assertEqual(routes["AI-FIRST-001"]["role_id"], "03")

    def test_waiting_user_does_not_block_unrelated_work(self):
        self.engine.ingest(self.fx.task(task_id="UNKNOWN-ROLE-001", role="not-a-role"))
        self.engine.ingest(self.fx.task(task_id="LOCAL-INDEPENDENT-001"))
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.assertEqual(self.store.get("UNKNOWN-ROLE-001")["state"], State.WAITING_USER.value)
        self.assertEqual(self.store.get("LOCAL-INDEPENDENT-001")["state"], State.SUCCEEDED.value)

    def test_invalid_route_never_executes_even_after_waiting_reevaluation(self):
        fake = FakeAI()
        task = self.fx.task(
            task_id="INVALID-ROUTE-001", role="not-a-role", task_type="llm_worker",
            action="semantic_helper", labels=("orchestrator:llm-approved",),
        )
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, fake).cycle()
        self.assertEqual(fake.tasks, [])
        self.assertEqual(self.store.get(task.task_id)["state"], State.WAITING_USER.value)
        self.assertEqual(self.store.conn.execute("SELECT route_status FROM task_routes WHERE task_id=?", (task.task_id,)).fetchone()[0], "INVALID_ROLE")

    def test_malformed_review_flags_never_create_review(self):
        task = self.fx.task(
            task_id="MALFORMED-REVIEW-001",
            inputs={"review_required": "false", "auto_review_authorized": "false", "review_role": "NOT_A_ROLE"},
        )
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.assertIsNone(self.store.get(task.task_id + "-REVIEW-001"))

    def test_lane_type_confusion_and_human_lane_never_execute(self):
        fake = FakeAI()
        semantic = self.fx.task(
            task_id="SEMANTIC-NOT-DETERMINISTIC-001", role="03_CEF",
            task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:llm-approved",),
            inputs={"resource_requirement": "DETERMINISTIC_REQUIRED",
                    "allowed_lanes": ["LOCAL_DETERMINISTIC"]},
        )
        human = self.fx.task(
            task_id="HUMAN-NEVER-AUTO-001",
            inputs={"resource_requirement": "HUMAN_REQUIRED",
                    "allowed_lanes": ["HUMAN_DECISION"]},
        )
        self.engine.ingest(semantic)
        self.engine.ingest(human)
        M1bController(self.fx.cfg, self.store, fake).cycle()
        self.assertEqual(fake.tasks, [])
        self.assertEqual(self.store.get(semantic.task_id)["state"], State.WAITING_USER.value)
        self.assertEqual(self.store.get(human.task_id)["state"], State.WAITING_USER.value)

    def test_undeclared_semantic_suitability_fails_closed_without_work_default(self):
        fake = FakeAI()
        task = self.fx.task(
            task_id="UNDECLARED-SEMANTIC-001", role="03_CEF", task_type="llm_worker",
            action="semantic_helper", labels=("orchestrator:llm-approved",), inputs={},
        )
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, fake).cycle()
        route = self.store.conn.execute("SELECT * FROM task_routes WHERE task_id=?", (task.task_id,)).fetchone()
        self.assertEqual(route["route_status"], "INVALID_SUITABILITY")
        self.assertEqual(fake.tasks, [])

    def test_success_creates_authorized_bounded_review(self):
        parent = self.fx.task(
            task_id="LOCAL-REVIEWED-001",
            inputs={"review_required": True, "review_role": "00", "auto_review_authorized": True},
        )
        self.engine.ingest(parent)
        controller = M1bController(self.fx.cfg, self.store, FakeAI())
        controller.cycle()
        controller.cycle()
        review_id = "LOCAL-REVIEWED-001-REVIEW-001"
        self.assertEqual(self.store.get(review_id)["state"], State.SUCCEEDED.value)
        requirement = self.store.conn.execute(
            "SELECT * FROM review_requirements WHERE parent_task_id=?", (parent.task_id,)
        ).fetchone()
        self.assertEqual(requirement["review_task_id"], review_id)
        route = self.store.conn.execute("SELECT * FROM task_routes WHERE task_id=?", (review_id,)).fetchone()
        self.assertEqual(route["role_id"], "00")

    def reviewed_semantic_task(self, task_id):
        return self.fx.task(
            task_id=task_id, role="07_INFRASTRUCTURE",
            task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:task", "orchestrator:llm-approved"),
            inputs={"resource_requirement": "WORK_REQUIRED", "review_required": True,
                    "review_role": "00", "auto_review_authorized": True},
        )

    @staticmethod
    def semantic_outcome(verdict="FAILED", summary="negative audit findings"):
        return Admission("ACCEPTED", {
            "status": verdict, "summary": summary,
            "checks": [{"check": "scope", "status": "PASS"}],
            "artifacts": [], "error": None,
        })

    def test_negative_semantic_verdict_completes_execution_and_creates_review(self):
        parent = self.reviewed_semantic_task("NEGATIVE-AUDIT-001")
        self.engine.ingest(parent)
        fake = SequenceAI([
            self.semantic_outcome(),
            self.semantic_outcome("PASS", "independent review complete"),
        ])
        controller = M1bController(self.fx.cfg, self.store, fake)
        controller.cycle()
        self.assertEqual(self.store.get(parent.task_id)["state"], State.SUCCEEDED.value)
        accepted = json.loads(self.store.conn.execute(
            "SELECT result_json FROM accepted_results WHERE task_id=?", (parent.task_id,)
        ).fetchone()[0])
        self.assertEqual(accepted["status"], "SUCCEEDED")
        self.assertEqual(accepted["semantic_verdict"], "FAILED")
        controller.cycle()
        review_id = parent.task_id + "-REVIEW-001"
        self.assertEqual(self.store.get(review_id)["state"], State.SUCCEEDED.value)
        requirement = self.store.conn.execute(
            "SELECT * FROM review_requirements WHERE parent_task_id=?", (parent.task_id,)
        ).fetchone()
        self.assertEqual(requirement["review_task_id"], review_id)

    def test_semantic_summary_survives_accepted_and_public_result(self):
        task = self.reviewed_semantic_task("SUMMARY-E2E-001")
        summary = "P1 protocol gap: substantive findings are negative."
        self.engine.ingest(task)
        M1bController(
            self.fx.cfg, self.store, SequenceAI([self.semantic_outcome(summary=summary)])
        ).cycle()
        durable = json.loads(self.store.conn.execute(
            "SELECT result_json FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone()[0])
        public = yaml.safe_load(
            (self.fx.root / "state" / "results" / f"{task.task_id}.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(durable["summary"], summary)
        self.assertEqual(public["summary"], summary)
        self.assertEqual(public["semantic_verdict"], "FAILED")

    def test_duplicate_semantic_result_remains_exactly_once(self):
        task = self.reviewed_semantic_task("SEMANTIC-DUPLICATE-001")
        self.engine.ingest(task)
        controller = M1bController(
            self.fx.cfg, self.store, SequenceAI([self.semantic_outcome()])
        )
        controller.cycle()
        row = self.store.conn.execute(
            "SELECT * FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone()
        self.assertEqual(controller.state.accept(row["attempt_id"], json.loads(row["result_json"])), "duplicate")
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone()[0], 1)

    def test_transport_failure_is_distinct_from_negative_semantic_verdict(self):
        transport_task = self.reviewed_semantic_task("A-TRANSPORT-FAILURE-001")
        negative_task = self.reviewed_semantic_task("B-NEGATIVE-VERDICT-002")
        self.engine.ingest(transport_task)
        self.engine.ingest(negative_task)
        fake = SequenceAI([
            Admission("FAILED_RETRYABLE", reason="worker transport disconnected"),
            self.semantic_outcome(),
        ])
        M1bController(self.fx.cfg, self.store, fake).cycle()
        self.assertEqual(self.store.get(transport_task.task_id)["state"], State.FAILED_RETRYABLE.value)
        self.assertIsNone(self.store.conn.execute(
            "SELECT 1 FROM accepted_results WHERE task_id=?", (transport_task.task_id,)
        ).fetchone())
        self.assertEqual(self.store.get(negative_task.task_id)["state"], State.SUCCEEDED.value)
        negative = json.loads(self.store.conn.execute(
            "SELECT result_json FROM accepted_results WHERE task_id=?", (negative_task.task_id,)
        ).fetchone()[0])
        self.assertEqual(negative["semantic_verdict"], "FAILED")
        self.assertIsNone(negative["error"])

    def test_review_worker_failure_does_not_rewrite_parent_execution(self):
        parent = self.reviewed_semantic_task("REVIEW-FAILURE-ISOLATION-001")
        self.engine.ingest(parent)
        fake = SequenceAI([
            self.semantic_outcome("PASS", "parent execution complete"),
            Admission("FAILED_RETRYABLE", reason="review worker transport failed"),
        ])
        controller = M1bController(self.fx.cfg, self.store, fake)
        controller.cycle()
        before = dict(self.store.conn.execute(
            "SELECT * FROM accepted_results WHERE task_id=?", (parent.task_id,)
        ).fetchone())
        controller.cycle()
        self.assertEqual(self.store.get(parent.task_id)["state"], State.SUCCEEDED.value)
        self.assertEqual(dict(self.store.conn.execute(
            "SELECT * FROM accepted_results WHERE task_id=?", (parent.task_id,)
        ).fetchone()), before)
        self.assertEqual(
            self.store.get(parent.task_id + "-REVIEW-001")["state"],
            State.FAILED_RETRYABLE.value,
        )

    def test_production_telemetry_reports_runtime_and_admitted_ai_attempts(self):
        task = self.reviewed_semantic_task("PRODUCTION-TELEMETRY-001")
        self.engine.ingest(task)
        controller = M1bController(
            self.fx.cfg, self.store,
            SequenceAI([self.semantic_outcome("PASS", "telemetry fixture")]),
        )
        controller.cycle()
        engine_status = self.engine.status()
        controller_status = controller.state.status()
        self.assertEqual(engine_status["mode"], "production")
        self.assertEqual(engine_status["configured_mode"], "pilot")
        self.assertEqual(engine_status["llm_calls"], 1)
        self.assertEqual(controller_status["RUNTIME_MODE"], "PRODUCTION")
        self.assertEqual(controller_status["LLM_EXECUTION_ATTEMPTS"], 1)

    def bound_review(self, task_id="BOUND-REVIEW-001", summary="exact parent summary"):
        parent = self.reviewed_semantic_task(task_id)
        self.engine.ingest(parent)
        controller = M1bController(
            self.fx.cfg, self.store,
            SequenceAI([self.semantic_outcome("FAILED", summary)]),
        )
        controller.cycle()
        controller.router.reconcile()
        review_row = self.store.get(task_id + "-REVIEW-001")
        self.assertIsNotNone(review_row)
        return parent, controller, self.store.task(review_row)

    def test_review_prompt_contains_exact_bound_parent_result(self):
        summary = "P1 exact evidence binding sentinel"
        parent, _controller, review = self.bound_review(summary=summary)
        accepted = self.store.conn.execute(
            "SELECT * FROM accepted_results WHERE task_id=?", (parent.task_id,)
        ).fetchone()
        captured = {}
        transport = SubprocessAITransport(self.fx.cfg)

        def capture(prompt):
            captured["prompt"] = prompt
            return Admission("ACCEPTED", {"text": json.dumps({
                "status": "PASS", "summary": "reviewed exact evidence",
                "checks": [], "artifacts": [], "error": None,
            })})

        transport._run = capture  # type: ignore[method-assign]
        self.assertEqual(transport.execute(review, 1).status, "ACCEPTED")
        prompt = captured["prompt"]
        self.assertIn(summary, prompt)
        self.assertIn('"semantic_verdict":"FAILED"', prompt)
        self.assertIn(accepted["result_sha256"], prompt)
        material = review.inputs["review_material"]
        self.assertEqual(material["accepted_result_sha256"], accepted["result_sha256"])
        self.assertEqual(material["parent_task_id"], parent.task_id)

    def test_review_material_hash_tamper_fails_closed_waiting_user(self):
        parent, controller, review = self.bound_review("BOUND-TAMPER-001")
        row = self.store.get(review.task_id)
        payload = json.loads(row["payload_json"])
        payload["inputs"]["review_material"]["accepted_result_sha256"] = "0" * 64
        self.store.conn.execute(
            "UPDATE tasks SET payload_json=? WHERE task_id=?",
            (json.dumps(payload, sort_keys=True), review.task_id),
        )
        controller.cycle()
        self.assertEqual(self.store.get(review.task_id)["state"], State.WAITING_USER.value)
        route = self.store.conn.execute(
            "SELECT * FROM task_routes WHERE task_id=?", (review.task_id,)
        ).fetchone()
        self.assertEqual(route["route_status"], "INVALID_REVIEW_MATERIAL")
        self.assertIn("hash mismatch", route["reason"])
        self.assertEqual(self.store.get(parent.task_id)["state"], State.SUCCEEDED.value)

    def test_legacy_semantic_result_without_summary_does_not_create_review(self):
        parent = self.reviewed_semantic_task("LEGACY-INCOMPLETE-RESULT-001")
        self.engine.ingest(parent)
        controller = M1bController(
            self.fx.cfg, self.store,
            SequenceAI([self.semantic_outcome("FAILED", "will be removed")]),
        )
        controller.cycle()
        accepted = self.store.conn.execute(
            "SELECT * FROM accepted_results WHERE task_id=?", (parent.task_id,)
        ).fetchone()
        legacy = json.loads(accepted["result_json"])
        for key in ("summary", "semantic_verdict", "semantic_error"):
            legacy.pop(key)
        encoded = json.dumps(legacy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.store.conn.execute(
            "UPDATE accepted_results SET result_json=?,result_sha256=? WHERE task_id=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest(), parent.task_id),
        )
        controller.router.reconcile()
        self.assertIsNone(self.store.get(parent.task_id + "-REVIEW-001"))
        requirement = self.store.conn.execute(
            "SELECT * FROM review_requirements WHERE parent_task_id=?", (parent.task_id,)
        ).fetchone()
        self.assertEqual(requirement["status"], "WAITING_USER")
        self.assertIn("legacy parent result", requirement["reason"])

    def test_oversized_embedded_review_material_uses_verified_artifact(self):
        summary = "bounded-artifact-sentinel-" + ("x" * 70_000)
        parent, _controller, review = self.bound_review("BOUND-ARTIFACT-001", summary)
        material = review.inputs["review_material"]
        self.assertEqual(material["delivery"], "artifact")
        self.assertEqual(material["parent_task_id"], parent.task_id)
        self.assertNotIn("summary", material)
        captured = {}
        transport = SubprocessAITransport(self.fx.cfg)

        def capture(prompt):
            captured["prompt"] = prompt
            return Admission("ACCEPTED", {"text": json.dumps({
                "status": "PASS", "summary": "large artifact reviewed",
                "checks": [], "artifacts": [], "error": None,
            })})

        transport._run = capture  # type: ignore[method-assign]
        self.assertEqual(transport.execute(review, 1).status, "ACCEPTED")
        self.assertIn("bounded-artifact-sentinel-", captured["prompt"])

    def fanin_task(self, task_id, dependencies):
        return self.fx.task(
            task_id=task_id, role="00_PROJECT_CONTROL",
            task_type="llm_worker", action="semantic_helper",
            dependencies=tuple(dependencies),
            labels=("orchestrator:task", "orchestrator:llm-approved"),
            inputs={"resource_requirement": "WORK_REQUIRED", "bind_dependency_results": True},
        )

    def capture_transport(self, captured):
        transport = SubprocessAITransport(self.fx.cfg)

        def capture(prompt):
            captured["prompt"] = prompt
            return Admission("ACCEPTED", {"text": json.dumps({
                "status": "PASS", "summary": "fan-in complete",
                "checks": [], "artifacts": [], "error": None,
            })})

        transport._run = capture  # type: ignore[method-assign]
        return transport

    def test_two_parent_fanin_reaches_role_00_with_exact_ordered_results(self):
        parent_b = self.work_task("FANIN-B-001")
        parent_a = self.work_task("FANIN-A-001")
        child = self.fanin_task("FANIN-00-001", (parent_b.task_id, parent_a.task_id))
        for task in (parent_b, parent_a, child):
            self.engine.ingest(task)
        fake = SequenceAI([
            self.semantic_outcome("PASS", "exact-result-A"),
            self.semantic_outcome("PASS", "exact-result-B"),
        ])
        controller = M1bController(self.fx.cfg, self.store, fake)
        controller.cycle()
        captured = {}
        controller.transport = self.capture_transport(captured)
        controller.cycle()
        self.assertEqual(self.store.get(child.task_id)["state"], State.SUCCEEDED.value)
        bundle = json.loads(self.store.conn.execute(
            "SELECT bundle_json FROM dependency_result_bundles WHERE task_id=?", (child.task_id,)
        ).fetchone()[0])
        self.assertEqual(bundle["ordered_dependency_ids"], [parent_a.task_id, parent_b.task_id])
        prompt = captured["prompt"]
        bound_prompt = prompt.split("VERIFIED ORDERED DEPENDENCY RESULT BUNDLE:", 1)[1]
        first_material = bound_prompt.index("VERIFIED DEPENDENCY " + parent_a.task_id)
        second_material = bound_prompt.index("VERIFIED DEPENDENCY " + parent_b.task_id)
        self.assertLess(first_material, second_material)
        for parent in (parent_a, parent_b):
            accepted = self.store.conn.execute(
                "SELECT result_sha256 FROM accepted_results WHERE task_id=?", (parent.task_id,)
            ).fetchone()[0]
            self.assertIn(accepted, prompt)
        route = self.store.conn.execute(
            "SELECT role_id FROM task_routes WHERE task_id=?", (child.task_id,)
        ).fetchone()
        self.assertEqual(route["role_id"], "00")

    def test_dependency_bundle_tamper_fails_closed_before_worker(self):
        parent = self.work_task("BIND-TAMPER-PARENT-001")
        child = self.fanin_task("BIND-TAMPER-CHILD-001", (parent.task_id,))
        self.engine.ingest(parent)
        self.engine.ingest(child)
        controller = M1bController(
            self.fx.cfg, self.store,
            SequenceAI([self.semantic_outcome("PASS", "untampered parent")]),
        )
        controller.cycle()
        controller.router.reconcile()
        self.store.conn.execute(
            "UPDATE dependency_result_bundles SET bundle_json=? WHERE task_id=?",
            ('{"tampered":true}', child.task_id),
        )
        capture = SequenceAI([self.semantic_outcome("PASS", "must not run")])
        controller.transport = capture
        controller.cycle()
        self.assertEqual(capture.tasks, [])
        self.assertEqual(self.store.get(child.task_id)["state"], State.WAITING_USER.value)
        route = self.store.conn.execute(
            "SELECT route_status,reason FROM task_routes WHERE task_id=?", (child.task_id,)
        ).fetchone()
        self.assertEqual(route["route_status"], "INVALID_DEPENDENCY_MATERIAL")
        self.assertIn("modified", route["reason"])

    def test_oversized_dependency_material_uses_bounded_artifact(self):
        sentinel = "dependency-artifact-sentinel-" + ("x" * 70_000)
        parent = self.work_task("BIND-LARGE-PARENT-001")
        child = self.fanin_task("BIND-LARGE-CHILD-001", (parent.task_id,))
        self.engine.ingest(parent)
        self.engine.ingest(child)
        controller = M1bController(
            self.fx.cfg, self.store,
            SequenceAI([self.semantic_outcome("PASS", sentinel)]),
        )
        controller.cycle()
        captured = {}
        controller.transport = self.capture_transport(captured)
        controller.cycle()
        bundle = json.loads(self.store.conn.execute(
            "SELECT bundle_json FROM dependency_result_bundles WHERE task_id=?", (child.task_id,)
        ).fetchone()[0])
        self.assertEqual(bundle["materials"][0]["delivery"], "artifact")
        self.assertIn("dependency-artifact-sentinel-", captured["prompt"])

    def test_failed_dependency_is_never_consumed(self):
        parent = self.fx.task(
            task_id="BIND-FAILED-PARENT-001", action="test_command",
            inputs={"command_id": "fail"},
        )
        child = self.fanin_task("BIND-FAILED-CHILD-001", (parent.task_id,))
        self.engine.ingest(parent)
        self.engine.ingest(child)
        fake = FakeAI()
        controller = M1bController(self.fx.cfg, self.store, fake)
        controller.cycle()
        controller.cycle()
        self.assertEqual(self.store.get(parent.task_id)["state"], State.FAILED.value)
        self.assertEqual(self.store.get(child.task_id)["state"], State.BLOCKED.value)
        self.assertEqual(fake.tasks, [])
        self.assertIsNone(self.store.conn.execute(
            "SELECT 1 FROM dependency_result_bundles WHERE task_id=?", (child.task_id,)
        ).fetchone())
        rejected = self.fx.task(
            task_id="BIND-REJECTED-PARENT-001", action="test_command",
            inputs={"command_id": "not-allowlisted"},
        )
        rejected_child = self.fanin_task("BIND-REJECTED-CHILD-001", (rejected.task_id,))
        self.assertEqual(self.engine.ingest(rejected), "rejected")
        self.engine.ingest(rejected_child)
        controller.cycle()
        self.assertEqual(self.store.get(rejected_child.task_id)["state"], State.BLOCKED.value)
        self.assertIsNone(self.store.conn.execute(
            "SELECT 1 FROM dependency_result_bundles WHERE task_id=?", (rejected_child.task_id,)
        ).fetchone())

    def test_mixed_deterministic_and_semantic_fanin_and_exactly_once(self):
        deterministic = self.fx.task(task_id="FANIN-LOCAL-001")
        semantic = self.work_task("FANIN-SEMANTIC-001")
        child = self.fanin_task("FANIN-MIXED-00-001", (semantic.task_id, deterministic.task_id))
        for task in (deterministic, semantic, child):
            self.engine.ingest(task)
        parent_transport = SequenceAI([self.semantic_outcome("PASS", "semantic-parent")])
        controller = M1bController(self.fx.cfg, self.store, parent_transport)
        controller.cycle()
        child_transport = SequenceAI([self.semantic_outcome("PASS", "combined-once")])
        controller.transport = child_transport
        controller.cycle()
        controller.cycle()
        self.assertEqual(child_transport.tasks.count(child.task_id), 1)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM accepted_results WHERE task_id=?", (child.task_id,)
        ).fetchone()[0], 1)
        bundle = json.loads(self.store.conn.execute(
            "SELECT bundle_json FROM dependency_result_bundles WHERE task_id=?", (child.task_id,)
        ).fetchone()[0])
        self.assertEqual(bundle["ordered_dependency_ids"], sorted(child.dependencies))
        self.assertEqual({item["parent_task_id"] for item in bundle["materials"]},
                         {deterministic.task_id, semantic.task_id})

    def test_ai_prompt_contains_exact_canonical_bootstrap(self):
        task = self.fx.task(role="07_INFRASTRUCTURE", task_type="llm_worker", action="semantic_helper")
        transport = SubprocessAITransport(self.fx.cfg)
        captured = {}
        def capture(prompt):
            captured["prompt"] = prompt
            return Admission("FAILED_RETRYABLE", reason="captured")
        transport._run = capture  # type: ignore[method-assign]
        self.assertEqual(transport.execute(task, 1).status, "FAILED_RETRYABLE")
        exact = load_registry(BOOTSTRAPS)["07"].bootstrap_text
        self.assertIn(exact, captured["prompt"])

    def test_dashboard_is_read_only_local_and_failure_nonblocking(self):
        self.engine.ingest(self.fx.task(task_id="DASH-TASK-001"))
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.store.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        before = self.store.conn.execute("SELECT count(*) FROM events").fetchone()[0]
        server = create_server(self.fx.cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            payload = json.load(urllib.request.urlopen(url + "/api/status", timeout=2))
            self.assertTrue(payload["dashboard"]["read_only"])
            self.assertEqual(payload["dashboard"]["health"], "HEALTHY")
            self.assertEqual(
                set(payload["operator_progress"]),
                {"CURRENT", "LAST_PROGRESS", "NEXT_ACTION", "NEEDS_USER"},
            )
            request = urllib.request.Request(url + "/api/status", data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(rejected.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM events").fetchone()[0], before)
        self.engine.ingest(self.fx.task(task_id="AFTER-DASH-FAILURE-001"))
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        self.assertEqual(self.store.get("AFTER-DASH-FAILURE-001")["state"], State.SUCCEEDED.value)
        self.assertTrue(snapshot(self.fx.cfg)["dashboard"]["read_only"])

    def test_readonly_database_uri_handles_non_ascii_path(self):
        directory = self.fx.root / "Данные"
        directory.mkdir()
        database = directory / "состояние.sqlite3"
        source = Store(database)
        source.close()
        with open_readonly(database) as conn:
            self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)

    def work_task(self, task_id="WORK-REQUIRED-001", **inputs):
        return self.fx.task(
            task_id=task_id, role="03_CEF", task_type="llm_worker",
            action="semantic_helper", labels=("orchestrator:llm-approved",),
            inputs={"resource_requirement": "WORK_REQUIRED", **inputs},
        )

    def force_work_quota_wait(self, next_probe=1000.0):
        M1bStore(self.store.conn, self.fx.cfg)
        self.store.conn.execute(
            "UPDATE ai_lane SET state='QUOTA_WAIT',next_probe_at=?,refusal_count=refusal_count+1 WHERE singleton=1",
            (next_probe,),
        )

    def test_01_work_quota_refusal_does_not_stop_m2(self):
        self.engine.ingest(self.work_task())
        fake = FakeAI()
        fake.execute = lambda task, attempt: Admission("QUOTA_REFUSED", reason="quota", reset_at=1000.0)
        output = M1bController(self.fx.cfg, self.store, fake, clock=lambda: 100.0).cycle()
        self.assertEqual(output["status"]["ORCHESTRATOR_M1B_STATE"], "OPERATIONAL")
        self.assertEqual(self.store.get("WORK-REQUIRED-001")["state"], State.WAITING_RESOURCE.value)

    def test_02_deterministic_executes_while_work_quota_waits(self):
        self.force_work_quota_wait()
        self.engine.ingest(self.fx.task(task_id="LOCAL-DURING-WORK-WAIT-001"))
        M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0).cycle()
        self.assertEqual(self.store.get("LOCAL-DURING-WORK-WAIT-001")["state"], State.SUCCEEDED.value)

    def test_03_verified_non_work_lane_routes_away_from_work(self):
        self.fx.cfg["non_work_ai"].update(
            enabled=True, verified_interface=True,
            command={"argv": ["/bin/false"], "timeout_seconds": 5},
        )
        self.force_work_quota_wait()
        task = self.fx.task(
            task_id="NON-WORK-CAPABLE-001", role="01_LITERATURE",
            task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:llm-approved",),
            inputs={"resource_requirement": "NON_WORK_AI_OK",
                    "allowed_lanes": ["NON_WORK_AI", "WORK_CODEX"]},
        )
        self.engine.ingest(task)
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        controller.router.reconcile()
        route = self.store.conn.execute("SELECT * FROM task_routes WHERE task_id=?", (task.task_id,)).fetchone()
        self.assertEqual((route["selected_lane"], route["route_status"]), ("NON_WORK_AI", "ROUTED"))

    def test_04_work_required_waits_without_retry_budget(self):
        self.force_work_quota_wait()
        task = self.work_task("WORK-WAITS-001")
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0).cycle()
        row = self.store.get(task.task_id)
        self.assertEqual((row["state"], row["attempt"]), (State.WAITING_RESOURCE.value, 0))

    def test_05_work_probe_reactivates_only_work_lane(self):
        self.force_work_quota_wait(next_probe=100.0)
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0)
        controller.cycle()
        lanes = {row["lane_id"]: dict(row) for row in self.store.conn.execute("SELECT * FROM resource_lanes")}
        self.assertEqual(self.store.conn.execute("SELECT state FROM ai_lane").fetchone()[0], "AVAILABLE")
        self.assertEqual(lanes["LOCAL_DETERMINISTIC"]["availability_state"], "AVAILABLE")

    def test_06_waiting_work_task_resumes_exactly_once(self):
        self.force_work_quota_wait(next_probe=100.0)
        task = self.work_task("WORK-RESUME-ONCE-001")
        self.engine.ingest(task)
        fake = FakeAI()
        controller = M1bController(self.fx.cfg, self.store, fake, clock=lambda: 101.0)
        controller.cycle()
        controller.cycle()
        self.assertEqual(self.store.get(task.task_id)["state"], State.SUCCEEDED.value)
        self.assertEqual(fake.tasks.count(task.task_id), 1)

    def test_07_work_recovery_does_not_duplicate_running_non_work(self):
        self.fx.cfg["non_work_ai"].update(
            enabled=True, verified_interface=True,
            command={"argv": ["/bin/false"], "timeout_seconds": 5},
        )
        self.force_work_quota_wait(next_probe=100.0)
        task = self.work_task(
            "NONWORK-RUNNING-001", resource_requirement="NON_WORK_AI_OK",
            allowed_lanes=["NON_WORK_AI", "WORK_CODEX"],
        )
        self.engine.ingest(task)
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0)
        controller.router.reconcile()
        lease = controller.state.claim(self.store.get(task.task_id), "already-running", 99.0)
        self.assertIsNotNone(lease)
        controller.cycle()
        self.assertEqual(self.store.get(task.task_id)["state"], State.RUNNING.value)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM dispatch_attempts WHERE task_id=?", (task.task_id,)).fetchone()[0], 1)

    def test_08_lane_quota_state_is_isolated(self):
        self.force_work_quota_wait()
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        controller.router.reconcile()
        lanes = {row["lane_id"]: dict(row) for row in self.store.conn.execute("SELECT * FROM resource_lanes")}
        self.assertEqual(lanes["WORK_CODEX"]["quota_state"], "QUOTA_WAIT")
        self.assertEqual(lanes["LOCAL_DETERMINISTIC"]["quota_state"], "AVAILABLE")
        self.assertNotEqual(lanes["NON_WORK_AI"]["quota_state"], "QUOTA_WAIT")

    def test_09_dashboard_shows_every_lane_separately(self):
        M1bController(self.fx.cfg, self.store, FakeAI()).cycle()
        lane_ids = {row["lane_id"] for row in snapshot(self.fx.cfg)["resource_lanes"]}
        self.assertEqual(lane_ids, {"LOCAL_DETERMINISTIC", "LOCAL_OSS_MODEL", "NON_WORK_AI", "WORK_CODEX", "HUMAN_DECISION"})

    def test_10_no_unsupported_persistent_chat_automation_claim(self):
        controller = M1bController(self.fx.cfg, self.store, FakeAI())
        controller.router.reconcile()
        status = controller.router.status()
        self.assertIs(status["UNSUPPORTED_PERSISTENT_CHAT_AUTOMATION"], False)
        non_work = self.store.conn.execute("SELECT * FROM resource_lanes WHERE lane_id='NON_WORK_AI'").fetchone()
        self.assertEqual(non_work["availability_state"], "UNVERIFIED")

    def test_work_probe_does_not_promote_unrelated_local_resource_wait(self):
        self.force_work_quota_wait(next_probe=100.0)
        task = self.fx.task(
            task_id="LOCAL-OSS-ONLY-WAIT-001", role="01_LITERATURE",
            task_type="llm_worker", action="semantic_helper",
            labels=("orchestrator:llm-approved",),
            inputs={"resource_requirement": "LOCAL_SEMANTIC_OK",
                    "allowed_lanes": ["LOCAL_OSS_MODEL"]},
        )
        self.engine.ingest(task)
        M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0).cycle()
        self.assertEqual(self.store.get(task.task_id)["state"], State.WAITING_RESOURCE.value)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM publication_outbox WHERE task_id=?", (task.task_id,)
        ).fetchone()[0], 0)

    def test_expired_non_work_lease_is_not_poisoned_by_work_quota(self):
        self.fx.cfg["non_work_ai"].update(
            enabled=True, verified_interface=True,
            command={"argv": ["/bin/false"], "timeout_seconds": 5},
        )
        self.force_work_quota_wait(next_probe=1000.0)
        task = self.work_task(
            "NONWORK-EXPIRED-001", resource_requirement="NON_WORK_AI_OK",
            allowed_lanes=["NON_WORK_AI", "WORK_CODEX"],
        )
        self.engine.ingest(task)
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        controller.router.reconcile()
        lease = controller.state.claim(self.store.get(task.task_id), "expired", 0.0)
        self.store.conn.execute("UPDATE worker_leases SET lease_expires_at=30 WHERE attempt_id=?", (lease["attempt_id"],))
        self.fx.cfg["autonomy"]["plan_only"] = True
        controller.cycle()
        self.assertEqual(self.store.get(task.task_id)["state"], State.READY.value)
        self.assertEqual(self.store.conn.execute(
            "SELECT selected_lane FROM task_routes WHERE task_id=?", (task.task_id,)
        ).fetchone()[0], "NON_WORK_AI")

    def test_alternate_lane_quota_refusal_is_durable_and_retry_free(self):
        self.fx.cfg["non_work_ai"].update(
            enabled=True, verified_interface=True,
            command={"argv": ["/bin/sh", "-c", "echo quota >&2; exit 1"], "timeout_seconds": 5},
        )
        task = self.work_task(
            "NONWORK-QUOTA-001", resource_requirement="NON_WORK_AI_OK",
            allowed_lanes=["NON_WORK_AI"],
        )
        self.engine.ingest(task)
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 100.0)
        controller.cycle()
        row = self.store.get(task.task_id)
        lane = self.store.conn.execute("SELECT * FROM resource_lanes WHERE lane_id='NON_WORK_AI'").fetchone()
        self.assertEqual((row["state"], row["attempt"]), (State.WAITING_RESOURCE.value, 0))
        self.assertEqual((lane["quota_state"], lane["refusal_count"]), ("QUOTA_WAIT", 1))
        controller = M1bController(self.fx.cfg, self.store, FakeAI(), clock=lambda: 101.0)
        controller.cycle()
        lane = self.store.conn.execute("SELECT * FROM resource_lanes WHERE lane_id='NON_WORK_AI'").fetchone()
        self.assertEqual((lane["quota_state"], lane["refusal_count"]), ("QUOTA_WAIT", 1))


if __name__ == "__main__":
    unittest.main()
