from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from task_orchestrator.dashboard import (
    GRAPH_NODE_LIMIT, _overall_health, _resource_component, create_server,
    human_time, open_readonly, render, snapshot,
)
from task_orchestrator.authoring import preflight_authoring
from task_orchestrator.reliability import M1bStore
from task_orchestrator.store import Store

from .common import Fixture


class DashboardV2Tests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.fx.cfg["dashboard"].update(enabled=True, port=0, stale_after_seconds=300)
        self.store = Store(self.fx.root / "state" / "state.sqlite3")
        self.control = M1bStore(self.store.conn, self.fx.cfg)
        self.control.checkpoint(CURRENT_PHASE="READY")
        self.checkpoint()

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def checkpoint(self):
        self.store.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def add_task(self, task_id, state, *, reason=None, role="07_INFRASTRUCTURE",
                 dependencies=(), inputs=None):
        task = self.fx.task(
            task_id=task_id, role=role, dependencies=tuple(dependencies), inputs=inputs or {},
        )
        self.store.ingest(task)
        self.store.conn.execute(
            "UPDATE tasks SET state=?,reason=? WHERE task_id=?", (state, reason, task_id),
        )
        self.checkpoint()
        return task

    def apply_control_projection(self, task, *, disposition="CURRENT",
                                 project_progress="IN_PROGRESS",
                                 human_action_required=False):
        operation = "CLOSE" if disposition != "CURRENT" else "UPDATE_EXISTING"
        reason = "Accepted historical disposition." if disposition != "CURRENT" else None
        request = {
            "schema_version": 1, "operation_type": operation,
            "author_role": "00_PROJECT_CONTROL", "canonical_head": self.fx.head,
            "issue": {"number": task.source_issue,
                      "state": "closed" if operation == "CLOSE" else "open",
                      "labels": ["orchestrator:task"]},
            "task": task.envelope_dict(),
            "existing_binding": {"source_issue": task.source_issue,
                                 "task_id": task.task_id,
                                 "envelope_hash": task.envelope_hash},
            "required_repository_paths": [], "dependency_bindings": [],
            "review_binding": None,
            "accepted_state_changes": [{
                "identity": "DASHBOARD-PROJECTION-" + task.task_id,
                "result_sha256": "a" * 64,
                "materialization_state": "NOT_STATE_CHANGING",
                "materialization_commit": None, "reason": None,
            }],
            "context_delta_bundle": None,
            "lifecycle": {
                "disposition": disposition, "target_task_id": task.task_id,
                "target_envelope_hash": task.envelope_hash,
                "successor_task_id": None, "reason": reason,
            },
            "project_status": {
                "project_progress": project_progress,
                "human_action_required": human_action_required,
                "semantic_state": "ACCEPTED", "design_state": "REVIEWED",
                "implementation_state": "PENDING",
                "deployment_state": "NOT_AUTHORIZED",
                "canonicalization_state": "PENDING_MATERIALIZATION",
            },
            "execution_context": "SEPARATE_BOUNDED_WORK",
            "persistent_chat_role": "00_PROJECT_CONTROL",
            "chatgpt_scheduler_requested": False,
        }
        receipt = preflight_authoring(
            request, self.fx.cfg, observed_canonical_head=self.fx.head,
        )
        self.store.put_authoring_receipt(receipt)
        self.checkpoint()
        return receipt

    def test_material_stale_or_unknown_component_prevents_global_healthy(self):
        self.store.conn.execute(
            "UPDATE controller_state SET updated_at='2026-01-01T00:00:00Z'"
        )
        self.checkpoint()
        data = snapshot(
            self.fx.cfg, now=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(data["dashboard"]["components"]["orchestrator"]["state"], "STALE")
        self.assertEqual(data["dashboard"]["health"], "STALE")
        components = {
            "a": {"state": "HEALTHY", "material": True},
            "b": {"state": "UNKNOWN", "material": True},
        }
        self.assertEqual(_overall_health(components), "UNKNOWN")
        components["b"]["state"] = "FAILED"
        self.assertEqual(_overall_health(components), "DEGRADED")

    def test_unobserved_configured_quota_is_diagnostics_only(self):
        self.fx.cfg["visibility"]["quota"]["five_hour"]["state"] = "AVAILABLE"
        self.fx.cfg["visibility"]["quota"]["weekly"]["state"] = "AVAILABLE"
        data = snapshot(self.fx.cfg)
        page = render(data).decode()
        self.assertFalse(data["quota_evidence"]["main_page_visible"])
        self.assertNotIn("<b>5h quota</b>", page)
        self.assertNotIn("<b>Weekly quota</b>", page)
        self.assertIn("Quota projections", page)
        self.assertIn("not live telemetry", page)

    def test_equal_heads_render_compact_synchronized_identity(self):
        data = snapshot(self.fx.cfg)
        self.assertEqual(data["git"]["projection"]["state"], "SYNCHRONIZED")
        page = render(data).decode()
        self.assertIn("Local HEAD matches local origin/main", page)
        self.assertIn(self.fx.head[:7], page)
        self.assertNotIn("<b>Canonical HEAD</b>", page)

    def test_different_heads_render_clear_warning(self):
        subprocess.run(
            ["git", "commit", "--allow-empty", "-qm", "local divergence"],
            cwd=self.fx.root, check=True,
        )
        data = snapshot(self.fx.cfg)
        self.assertEqual(data["git"]["projection"]["state"], "MISMATCH")
        self.assertIn("Local HEAD differs from local origin/main", render(data).decode())

    def test_human_state_and_role_are_primary_but_raw_values_remain_diagnostic(self):
        self.add_task(
            "HUMAN-LABEL-001", "WAITING_USER", reason="Choose the reviewed option",
            role="01_LITERATURE_PHYSICS",
        )
        data = snapshot(self.fx.cfg)
        page = render(data).decode()
        task = next(item for item in data["tasks"] if item["task_id"] == "HUMAN-LABEL-001")
        self.assertEqual(task["human_state"], "Needs your input")
        self.assertEqual(task["human_role"], "Literature & Physics")
        self.assertIn("Needs your input", page)
        self.assertIn("WAITING_USER", page)

    def test_human_time_is_deterministic_and_exact_time_is_tooltip(self):
        now = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(human_time("2026-09-29T14:59:50Z", now), "just now")
        self.assertEqual(human_time("2026-09-29T14:57:00Z", now), "3 min ago")
        previous_day = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)
        local_clock = previous_day.astimezone().strftime("%H:%M")
        self.assertEqual(human_time(previous_day.isoformat(), now), f"yesterday {local_clock}")
        self.add_task("TIME-LABEL-001", "RUNNING")
        data = snapshot(self.fx.cfg, now=now)
        page = render(data, now=now).decode()
        self.assertIn('title="', page)
        self.assertIn("T", page)

    def test_future_timestamp_is_not_rendered_as_fresh(self):
        now = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(human_time("2026-09-29T15:00:01Z", now), "Future timestamp")
        self.store.conn.execute(
            "UPDATE controller_state SET updated_at='2026-09-29T15:01:00Z'"
        )
        self.checkpoint()
        data = snapshot(self.fx.cfg, now=now)
        component = data["dashboard"]["components"]["orchestrator"]
        self.assertEqual(component["state"], "UNKNOWN")
        self.assertNotEqual(data["dashboard"]["health"], "HEALTHY")

    def test_terminal_free_text_does_not_suppress_attention(self):
        self.add_task(
            "OLD-FAILURE-001", "FAILED", reason="superseded by corrected execution",
        )
        self.add_task(
            "LIVE-QUESTION-001", "WAITING_USER", reason="Select the next bounded action",
        )
        data = snapshot(self.fx.cfg)
        attention_ids = {item["task_id"] for item in data["attention"]}
        blocker_ids = {item["task_id"] for item in data["blockers"]}
        self.assertIn("OLD-FAILURE-001", attention_ids)
        self.assertIn("OLD-FAILURE-001", blocker_ids)
        self.assertIn("LIVE-QUESTION-001", attention_ids)
        page = render(data).decode()
        main_attention = page.split("<h2>Needs attention</h2>", 1)[1].split("<h2>Recent", 1)[0]
        self.assertIn("User action required", page)
        self.assertIn("OLD-FAILURE-001", main_attention)
        self.assertIn("LIVE-QUESTION-001", main_attention)

    def test_closed_issue_and_untrusted_payload_hints_do_not_hide_failure(self):
        self.add_task(
            "CLOSED-FAILURE-001", "FAILED", reason="unresolved failure",
            inputs={"control_status": "closed", "operator_attention": False},
        )
        self.store.conn.execute(
            "INSERT INTO issue_snapshots "
            "(issue_number,task_id,snapshot_hash,title,body_hash,labels_json,issue_state,comments_count,github_updated_at,seen_at) "
            "VALUES(1,'CLOSED-FAILURE-001','snapshot','Closed issue','body','[]','closed',0,'2026-09-29T12:00:00Z','2026-09-29T12:00:00Z')"
        )
        data = snapshot(self.fx.cfg)
        self.assertIn("CLOSED-FAILURE-001", {item["task_id"] for item in data["attention"]})

    def test_blocked_historical_text_and_waiting_approval_remain_attention(self):
        self.add_task(
            "HISTORICAL-TEXT-001", "BLOCKED",
            reason="historical only; defect corrected; not planned",
            inputs={"historical": True, "superseded_by": "OTHER-TASK"},
        )
        self.add_task("APPROVAL-001", "WAITING_APPROVAL", reason="approval required")
        attention_ids = {item["task_id"] for item in snapshot(self.fx.cfg)["attention"]}
        self.assertIn("HISTORICAL-TEXT-001", attention_ids)
        self.assertIn("APPROVAL-001", attention_ids)

    def test_trusted_historical_disposition_suppresses_only_that_terminal_item(self):
        historical = self.add_task("HISTORICAL-RECEIPT-001", "FAILED")
        live = self.add_task("LIVE-FAILURE-002", "FAILED")
        self.apply_control_projection(
            historical, disposition="CLOSED_HISTORICAL",
            project_progress="COMPLETED",
        )
        data = snapshot(self.fx.cfg)
        attention_ids = {item["task_id"] for item in data["attention"]}
        blocker_ids = {item["task_id"] for item in data["blockers"]}
        self.assertNotIn(historical.task_id, attention_ids)
        self.assertNotIn(historical.task_id, blocker_ids)
        self.assertIn(live.task_id, attention_ids)
        self.assertIn(live.task_id, blocker_ids)

    def test_corrupt_authoring_receipt_fails_safe_and_keeps_failure_visible(self):
        task = self.add_task("CORRUPT-RECEIPT-001", "FAILED")
        self.store.conn.execute(
            "INSERT INTO authoring_receipts(receipt_sha256,task_id,envelope_hash,"
            "operation_type,lifecycle_disposition,project_progress,"
            "human_action_required,receipt_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("f" * 64, task.task_id, task.envelope_hash, "CLOSE",
             "CLOSED_HISTORICAL", "COMPLETED", 0,
             '{"not":"a validated receipt"}', "2026-10-03T00:00:00Z"),
        )
        self.checkpoint()
        data = snapshot(self.fx.cfg)
        self.assertIn(task.task_id, {item["task_id"] for item in data["attention"]})
        projected = next(item for item in data["tasks"] if item["task_id"] == task.task_id)
        self.assertEqual(projected["lifecycle_disposition"], "UNRECORDED")

    def test_fsm_and_project_control_dimensions_remain_separate(self):
        task = self.add_task("FACETED-SUCCESS-001", "SUCCEEDED")
        self.apply_control_projection(
            task, project_progress="IN_PROGRESS", human_action_required=True,
        )
        data = snapshot(self.fx.cfg)
        projected = next(item for item in data["tasks"] if item["task_id"] == task.task_id)
        self.assertEqual(projected["fsm_state"], "SUCCEEDED")
        self.assertEqual(projected["project_progress"], "IN_PROGRESS")
        self.assertEqual(projected["implementation_state"], "PENDING")
        self.assertEqual(projected["deployment_state"], "NOT_AUTHORIZED")
        self.assertTrue(projected["human_action_required"])
        self.assertIn(task.task_id, {item["task_id"] for item in data["attention"]})
        page = render(data).decode()
        self.assertIn("Project progress", page)
        self.assertIn("canonicalization", page)

    def test_resource_observation_freshness_controls_health(self):
        now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
        lane = {"lane_id": "LOCAL_DETERMINISTIC", "availability_state": "AVAILABLE",
                "updated_at": "2026-09-29T11:59:00Z"}
        fresh = _resource_component([], [lane], {}, now, 300)
        self.assertEqual(fresh["state"], "HEALTHY")
        lane["updated_at"] = "2026-09-29T11:00:00Z"
        stale = _resource_component([], [lane], {}, now, 300)
        self.assertEqual(stale["state"], "STALE")
        self.assertNotEqual(_overall_health({"resources": stale}), "HEALTHY")
        lane["updated_at"] = None
        self.assertEqual(_resource_component([], [lane], {}, now, 300)["state"], "UNKNOWN")
        lane["updated_at"] = "2026-09-29T12:01:00Z"
        self.assertEqual(_resource_component([], [lane], {}, now, 300)["state"], "UNKNOWN")

    def test_readonly_connection_observes_committed_wal_only_schema_and_data(self):
        database = self.fx.root / "state" / "state.sqlite3"
        self.add_task("WAL-VISIBLE-001", "RUNNING")
        self.store.conn.execute("PRAGMA wal_autocheckpoint=0")
        self.store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.store.conn.execute("CREATE TABLE wal_probe(value TEXT NOT NULL)")
        self.store.conn.execute("INSERT INTO wal_probe VALUES('committed in wal')")
        self.store.conn.execute(
            "UPDATE tasks SET state='WAITING_USER',reason='visible WAL update' "
            "WHERE task_id='WAL-VISIBLE-001'"
        )
        wal = database.with_name(database.name + "-wal")
        self.assertTrue(wal.exists())
        self.assertGreater(wal.stat().st_size, 0)
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (database, wal)}
        with open_readonly(database) as conn:
            self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT value FROM wal_probe").fetchone()[0], "committed in wal")
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO wal_probe VALUES('forbidden')")
        data = snapshot(self.fx.cfg)
        task = next(item for item in data["tasks"] if item["task_id"] == "WAL-VISIBLE-001")
        self.assertEqual(task["state"], "WAITING_USER")
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (database, wal)}
        self.assertEqual(after, before)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM wal_probe").fetchone()[0], 1)

    def test_dependency_graph_has_correct_edge(self):
        self.add_task("GRAPH-PARENT-001", "SUCCEEDED")
        self.add_task(
            "GRAPH-CHILD-001", "WAITING_DEPENDENCY", dependencies=("GRAPH-PARENT-001",),
        )
        graph = snapshot(self.fx.cfg)["task_graph"]
        self.assertIn({"from": "GRAPH-PARENT-001", "to": "GRAPH-CHILD-001"}, graph["edges"])
        self.assertEqual(
            {node["task_id"] for node in graph["nodes"]},
            {"GRAPH-PARENT-001", "GRAPH-CHILD-001"},
        )
        page = render(snapshot(self.fx.cfg)).decode()
        self.assertIn('marker-end="url(#dependency-arrow)"', page)
        self.assertIn("Dependencies point toward dependent tasks", page)

    def test_dependency_graph_is_bounded_for_large_history(self):
        for index in range(GRAPH_NODE_LIMIT + 20):
            self.add_task(f"HISTORY-{index:03d}", "SUCCEEDED")
        graph = snapshot(self.fx.cfg)["task_graph"]
        self.assertLessEqual(len(graph["nodes"]), GRAPH_NODE_LIMIT)
        self.assertTrue(graph["truncated"])

    def test_odd_text_is_html_escaped(self):
        hostile = '<img src=x onerror="alert(1)"> @everyone'
        self.add_task("ESCAPE-TEXT-001", "WAITING_USER", reason=hostile)
        page = render(snapshot(self.fx.cfg)).decode()
        self.assertNotIn(hostile, page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img", page)
        self.assertIn("@everyone", page)

    def test_dashboard_http_is_read_only_and_api_retains_raw_diagnostics(self):
        self.add_task("API-RAW-001", "WAITING_USER", reason="answer required")
        before = self.store.conn.execute("SELECT count(*) FROM events").fetchone()[0]
        server = create_server(self.fx.cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            payload = json.load(urllib.request.urlopen(base + "/api/status", timeout=2))
            self.assertTrue(payload["dashboard"]["read_only"])
            self.assertEqual(payload["schema_version"], 1)
            self.assertIn("components", payload["dashboard"])
            self.assertIn("tasks", payload)
            self.assertIn("recent_activity", payload)
            v1_keys = {
                "schema_version", "generated_at", "dashboard", "orchestrator", "git",
                "ai_lane", "quota_windows", "tasks", "workers", "routes",
                "resource_lanes", "reviews", "results", "dependency_bundles",
                "operator_progress", "attention", "blockers", "recent_activity",
            }
            self.assertTrue(v1_keys.issubset(payload), v1_keys - set(payload))
            task = next(item for item in payload["tasks"] if item["task_id"] == "API-RAW-001")
            self.assertEqual(task["state"], "WAITING_USER")
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                request = urllib.request.Request(base + "/", data=b"{}", method=method)
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(rejected.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM events").fetchone()[0], before)

    def test_telegram_is_not_activated_without_real_gateway_observation(self):
        data = snapshot(self.fx.cfg)
        self.assertEqual(data["telegram"]["state"], "NOT_ACTIVATED")
        self.assertIn("Telegram", render(data).decode())
        self.assertIn("Not activated", render(data).decode())

    def test_telegram_uses_only_fresh_explicit_gateway_observation(self):
        now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
        self.control.checkpoint(TELEGRAM_GATEWAY={
            "state": "HEALTHY", "observed_at": "2026-09-29T11:59:00Z",
            "detail": "Production gateway probe passed.",
        })
        self.checkpoint()
        self.assertEqual(snapshot(self.fx.cfg, now=now)["telegram"]["state"], "HEALTHY")
        stale_now = datetime(2026, 9, 29, 12, 10, tzinfo=timezone.utc)
        self.assertEqual(snapshot(self.fx.cfg, now=stale_now)["telegram"]["state"], "STALE")

    def test_unknown_git_identity_is_not_reported_healthy(self):
        real_git = __import__("task_orchestrator.dashboard", fromlist=["_git"])._git

        def missing_remote(repo, *args):
            if args == ("rev-parse", "refs/remotes/origin/main"):
                return None
            return real_git(repo, *args)

        with patch("task_orchestrator.dashboard._git", side_effect=missing_remote):
            data = snapshot(self.fx.cfg)
        self.assertEqual(data["dashboard"]["components"]["repository"]["state"], "UNKNOWN")
        self.assertNotEqual(data["dashboard"]["health"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()
