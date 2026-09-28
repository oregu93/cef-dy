from __future__ import annotations

import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

from task_orchestrator.dashboard import create_server, snapshot
from task_orchestrator.engine import Engine
from task_orchestrator.model import State
from task_orchestrator.reliability import Admission, M1bController, SubprocessAITransport
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
            "status": "SUCCEEDED", "checks": [], "artifacts": [], "error": None,
        })


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
        before = self.store.conn.execute("SELECT count(*) FROM events").fetchone()[0]
        server = create_server(self.fx.cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            payload = json.load(urllib.request.urlopen(url + "/api/status", timeout=2))
            self.assertTrue(payload["dashboard"]["read_only"])
            self.assertEqual(payload["dashboard"]["health"], "HEALTHY")
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


if __name__ == "__main__":
    unittest.main()
