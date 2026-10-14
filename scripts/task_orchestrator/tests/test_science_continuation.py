import json
import subprocess
import unittest
from dataclasses import replace
from unittest import mock

from task_orchestrator.engine import Engine
from task_orchestrator.reliability import Admission, M1bController
from task_orchestrator.store import Store
from task_orchestrator.science_continuation import (
    CanonicalRefreshUnavailable,
    delegated,
    planning_task,
    reconcile,
    refresh_origin_main,
)
from task_orchestrator.routing import canonical_role
from .common import Fixture
from .test_m2_routing_dashboard import BOOTSTRAPS, FakeAI


class ScienceClosureTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.fx.cfg["autonomy"].update(enabled=True, max_batch_tasks=16)
        self.fx.cfg["routing"].update(enabled=True, bootstrap_path=str(BOOTSTRAPS))
        self.fx.cfg["llm"].update(dispatch_enabled=True, detached_workers=False, require_local_approval=False)
        self.fx.cfg["science_continuation"].update(enabled=True, seed_task_ids=["SCI-SEED-001"])
        self.remote = self.fx.root / ".science-origin.git"
        subprocess.run(
            ["git", "init", "--bare", "-q", str(self.remote)], check=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(self.remote)],
            cwd=self.fx.root, check=True,
        )
        subprocess.run(
            ["git", "push", "-q", "origin", "HEAD:refs/heads/main"],
            cwd=self.fx.root, check=True,
        )
        self.store = Store(self.fx.root / "state/state.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)
        self.parent = self.fx.task("SCI-SEED-001", role="03_CEF", task_type="llm_worker", action="semantic_helper",
            stop_condition="Stop before requesting new measurements; only compare existing derived observations.",
            labels=("orchestrator:task", "orchestrator:llm-approved"),
            inputs={"purpose": "Compare existing evidence only", "additional_scope_boundary": "No new fitting campaign",
                    "constraints": ["no_raw_or_holdout_access", "no_stage_transition",
                                    "no_exchange_activation", "no_ACCEPTED_promotion"],
                    "resource_requirement": "WORK_REQUIRED", "review_required": True,
                    "auto_review_authorized": True, "review_role": "00_PROJECT_CONTROL"})
        self.engine.ingest(self.parent)
        self.controller = M1bController(self.fx.cfg, self.store, FakeAI())
        self.controller.cycle()

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def reviewer(self, decision="FOLLOW_UP", verdict="PASS", wrong_sha=False):
        sha = self.store.conn.execute("SELECT result_sha256 FROM accepted_results WHERE task_id=?", (self.parent.task_id,)).fetchone()[0]
        closure = {"decision": decision, "parent_result_sha256": "0" * 64 if wrong_sha else sha,
                   "canonical_head": self.fx.head, "rationale": "One unresolved comparison within parent scope",
                   "question": "Compare the remaining existing evidence" if decision == "FOLLOW_UP" else None}
        class Reviewer(FakeAI):
            def execute(self, task, attempt):
                return Admission("ACCEPTED", {"status": verdict, "summary": "Independent review",
                    "checks": [{"scientific_closure": closure}], "artifacts": [], "error": None})
        return Reviewer()

    def review(self, decision="FOLLOW_UP", verdict="PASS", wrong_sha=False):
        self.controller.transport = self.reviewer(decision, verdict, wrong_sha)
        self.controller.cycle()
        self.controller.cycle()
        return reconcile(self.controller.router)

    def test_followup_exact_bindings_dedupe_and_real_controller_execution(self):
        outcomes = self.review()
        self.assertEqual(outcomes[0]["state"], "ENROLLED")
        successor = outcomes[0]["successor_task_id"]
        task = self.store.task(self.store.get(successor))
        self.assertEqual(task.dependencies[0], self.parent.task_id)
        self.assertTrue(task.dependencies[1].startswith("SCI-CLOSURE-PLAN-"))
        self.assertEqual(task.canonical_head, self.fx.head)
        self.assertEqual(task.inputs["scientific_status"], "PROVISIONAL")
        self.assertFalse(task.allowed_paths)
        self.assertEqual(canonical_role(task.role), "03")
        self.assertEqual(task.inputs["authorized_root_envelope"], self.parent.envelope_dict())
        self.assertEqual(task.inputs["parent_stop_condition"], self.parent.stop_condition)
        self.assertIn("authorized_root_envelope", task.stop_condition)
        self.assertIn("No infrastructure", task.stop_condition)
        self.assertIn("raw/holdout", task.stop_condition)
        self.assertIn("stage transition", task.stop_condition)
        self.assertIn("exchange activation", task.stop_condition)
        self.assertIn("ACCEPTED promotion", task.stop_condition)
        with mock.patch(
            "task_orchestrator.science_continuation.refresh_origin_main"
        ) as refresh:
            for _ in range(3):
                reconcile(self.controller.router)
            refresh.assert_not_called()
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM scientific_closures").fetchone()[0], 1)
        self.controller.transport = FakeAI()
        self.controller.cycle()
        self.assertEqual(self.store.get(successor)["state"], "SUCCEEDED")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM accepted_results WHERE task_id=?", (successor,)).fetchone()[0], 1)
        # A successor still needs its own exact independent review/plan; merely
        # completing execution never manufactures the next successor.
        self.controller.cycle()
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM scientific_closures").fetchone()[0], 1)
        review = self.store.task(self.store.get(successor + "-REVIEW-001"))
        self.assertIn("scientific_closure_contract", review.inputs)

    def test_close_does_not_manufacture_work(self):
        self.assertEqual(self.review("CLOSE")[0]["state"], "CLOSE")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM tasks").fetchone()[0], 3)

    def test_waiting_user_only_blocks_its_branch(self):
        self.assertEqual(self.review("WAITING_USER")[0]["state"], "WAITING_USER")
        self.engine.ingest(self.fx.task("INFRA-OTHER-001"))
        self.controller.cycle()
        self.assertEqual(self.store.get("INFRA-OTHER-001")["state"], "SUCCEEDED")
        self.assertEqual(self.store.get(self.parent.task_id)["state"], "SUCCEEDED")

    def test_negative_review_cannot_authorize_successor(self):
        self.assertEqual(self.review(verdict="FAILED")[0]["state"], "WAITING_USER")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM tasks WHERE task_id LIKE 'SCI-CLOSURE-PLAN-%'").fetchone()[0], 0)
        self.assertEqual(self.store.conn.execute("SELECT state FROM scientific_continuation_observations WHERE task_id=?", (self.parent.task_id,)).fetchone()[0], "WAITING_USER")
        self.controller.transport = FakeAI()
        self.controller.cycle()
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM scientific_closures").fetchone()[0], 0)

    def test_wrong_parent_hash_cannot_authorize_successor(self):
        self.assertEqual(self.review(wrong_sha=True)[0]["state"], "WAITING_USER")

    def test_head_drift_fails_closed(self):
        self.controller.transport = self.reviewer()
        self.controller.cycle()
        self.engine.ingest(self.fx.task(
            "INFRA-ALREADY-AUTHORIZED-001", action="test_command",
            inputs={"command_id": "pass"},
        ))
        tree = subprocess.check_output(
            ["git", "rev-parse", self.fx.head + "^{tree}"],
            cwd=self.fx.root, text=True,
        ).strip()
        remote_head = subprocess.check_output(
            ["git", "commit-tree", tree, "-p", self.fx.head, "-m", "remote drift"],
            cwd=self.fx.root, text=True,
        ).strip()
        subprocess.run(
            ["git", "push", "-q", "origin",
             remote_head + ":refs/heads/main"],
            cwd=self.fx.root, check=True,
        )
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", self.fx.head],
            cwd=self.fx.root, check=True,
        )
        self.assertEqual(
            subprocess.check_output(
                ["git", "rev-parse", "refs/remotes/origin/main"],
                cwd=self.fx.root, text=True,
            ).strip(),
            self.fx.head,
        )
        self.controller.cycle()
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM tasks WHERE task_id LIKE 'SCI-CLOSURE-PLAN-%'"
        ).fetchone()[0], 0)
        observation = self.store.conn.execute(
            "SELECT state,detail_json FROM scientific_continuation_observations "
            "WHERE task_id=?", (self.parent.task_id,),
        ).fetchone()
        self.assertEqual(observation["state"], "WAITING_CANONICAL_HEAD")
        self.assertNotIn("WAITING_USER", observation["detail_json"])
        self.assertEqual(
            subprocess.check_output(
                ["git", "rev-parse", "refs/remotes/origin/main"],
                cwd=self.fx.root, text=True,
            ).strip(),
            remote_head,
        )
        independent = self.store.get("INFRA-ALREADY-AUTHORIZED-001")
        self.assertEqual(independent["state"], "SUCCEEDED", dict(independent))

    def test_fetch_failure_is_retryable_and_recovers_without_blocking(self):
        self.controller.transport = self.reviewer()
        self.controller.cycle()
        self.engine.ingest(self.fx.task(
            "INFRA-FETCH-INDEPENDENT-001", action="test_command",
            inputs={"command_id": "pass"},
        ))
        with mock.patch(
            "task_orchestrator.science_continuation.refresh_origin_main",
            side_effect=CanonicalRefreshUnavailable("timeout"),
        ):
            outcomes = reconcile(self.controller.router)
            self.assertEqual(
                outcomes[0]["state"], "WAITING_CANONICAL_REFRESH"
            )
            self.assertEqual(self.store.conn.execute(
                "SELECT count(*) FROM tasks "
                "WHERE task_id LIKE 'SCI-CLOSURE-PLAN-%'"
            ).fetchone()[0], 0)
            self.controller.cycle()
        self.assertEqual(
            self.store.get("INFRA-FETCH-INDEPENDENT-001")["state"],
            "SUCCEEDED",
        )
        self.assertEqual(self.store.get(self.parent.task_id)["state"], "SUCCEEDED")
        self.controller.cycle()
        recovered = reconcile(self.controller.router)
        self.assertEqual(recovered[0]["state"], "ENROLLED")
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM scientific_closures WHERE parent_task_id=?",
            (self.parent.task_id,),
        ).fetchone()[0], 1)

    def test_fetch_timeout_is_classified_as_transient(self):
        with mock.patch(
            "task_orchestrator.science_continuation.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git fetch", 30),
        ):
            with self.assertRaises(CanonicalRefreshUnavailable):
                refresh_origin_main(self.fx.root)

    def test_old_unstructured_review_does_not_authorize(self):
        self.controller.cycle()
        self.controller.cycle()
        self.assertEqual(reconcile(self.controller.router)[0]["state"], "WAITING_USER")

    def test_disabled_is_noop(self):
        self.fx.cfg["science_continuation"]["enabled"] = False
        self.assertEqual(reconcile(self.controller.router), [])

    def test_infrastructure_seed_never_delegated(self):
        self.assertFalse(delegated(self.fx.cfg, replace(self.parent, role="07_INFRASTRUCTURE")))

    def test_protected_write_scope_never_delegated(self):
        self.assertFalse(delegated(self.fx.cfg, replace(self.parent, allowed_paths=("04_Results",))))

    def test_restart_between_review_and_planning_recovers_exactly_once(self):
        parent_sha = self.store.conn.execute(
            "SELECT result_sha256 FROM accepted_results WHERE task_id=?",
            (self.parent.task_id,),
        ).fetchone()[0]
        closure = {
            "decision": "FOLLOW_UP",
            "parent_result_sha256": parent_sha,
            "canonical_head": self.fx.head,
            "rationale": "One bounded need remains",
            "question": "Compare the remaining existing evidence",
        }

        class Reviewer(FakeAI):
            def execute(self, task, attempt):
                return Admission("ACCEPTED", {
                    "status": "PASS", "summary": "reviewed",
                    "checks": [{"scientific_closure": closure}],
                    "artifacts": [], "error": None,
                })

        self.controller.transport = Reviewer()
        self.controller.cycle()
        self.store.close()
        self.store = Store(self.fx.root / "state/state.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)
        self.controller = M1bController(self.fx.cfg, self.store, Reviewer())
        self.controller.cycle()
        outcomes = reconcile(self.controller.router)
        self.assertEqual(outcomes[0]["state"], "ENROLLED")
        for _ in range(3):
            reconcile(self.controller.router)
        self.assertEqual(self.store.conn.execute(
            "SELECT count(*) FROM scientific_closures WHERE parent_task_id=?",
            (self.parent.task_id,),
        ).fetchone()[0], 1)

    def test_same_role_lease_cap_is_atomic_and_other_role_unblocked(self):
        self.fx.cfg["autonomy"]["max_parallel_local"] = 2
        for task_id, role in (("SCI-A-001", "03_CEF"), ("SCI-B-001", "03_CEF"), ("SCI-C-001", "01_LITERATURE")):
            self.engine.ingest(self.fx.task(task_id, role=role))
        self.controller.router.reconcile()
        claim = self.controller.state.claim
        self.assertIsNotNone(claim(self.store.get("SCI-A-001"), "worker-a", 1000))
        self.assertIsNone(claim(self.store.get("SCI-B-001"), "worker-b", 1000))
        self.assertIsNotNone(claim(self.store.get("SCI-C-001"), "worker-c", 1000))

    def test_authoring_receipt_preserves_provisional_status_and_hashes(self):
        successor = self.review()[0]["successor_task_id"]
        receipt = json.loads(self.store.conn.execute("SELECT receipt_json FROM authoring_receipts WHERE task_id=?", (successor,)).fetchone()[0])
        self.assertEqual(receipt["semantic_state"], "PROVISIONAL")
        self.assertEqual(receipt["status"], "PREFLIGHT_PASS")
        self.assertEqual(len(receipt["dependency_bindings"]), 2)
        for dependency in receipt["dependency_bindings"]:
            accepted = self.store.conn.execute("SELECT result_sha256 FROM accepted_results WHERE task_id=?", (dependency["task_id"],)).fetchone()[0]
            self.assertEqual(dependency["result_sha256"], accepted)

    def test_existing_65_67_result_shapes_plan_on_current_head(self):
        existing = (
            ("SCI-DYFEO3-18MEV-EVIDENCE-APPLICATION-2026-10-12-001",
             "03_CEF_MODELLING_FIT_DESIGN", "WORK_REQUIRED"),
            ("SCI-CS15-HIST-MINI-ENSEMBLE-FAMILY-ANALYSIS-2026-10-12-001",
             "03_CEF_MODELLING_FIT_DESIGN", "LOCAL_SEMANTIC_OK"),
            ("SCI-ORTHOFERRITE-PRIMARY-SOURCE-DELTA-2026-10-12-001",
             "01_LITERATURE_PHYSICS", "WORK_REQUIRED"),
        )
        self.fx.cfg["science_continuation"]["seed_task_ids"] = [x[0] for x in existing]
        old_head = "45fcf89f5a2571d534da6cf3f70018d3de620d7e"
        for task_id, role, resource in existing:
            parent = replace(
                self.parent,
                task_id=task_id,
                role=role,
                canonical_head=old_head,
                inputs={**self.parent.inputs,
                        "resource_requirement": resource,
                        "scientific_mode": "EXISTING_RESULT_COMPATIBILITY"},
            )
            review = replace(
                self.parent,
                task_id=task_id + "-REVIEW-001",
                role="00_PROJECT_CONTROL",
                canonical_head=old_head,
            )
            self.assertTrue(delegated(self.fx.cfg, parent))
            plan = planning_task(
                self.fx.cfg, parent, review,
                {"result_sha256": "a" * 64},
                {"result_sha256": "b" * 64},
                self.fx.head,
            )
            self.assertEqual(plan.canonical_head, self.fx.head)
            self.assertEqual(plan.inputs["parent_result_sha256"], "a" * 64)
            self.assertEqual(plan.inputs["original_envelope"], parent.envelope_dict())
