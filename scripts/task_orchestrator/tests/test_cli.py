from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import unittest

import yaml

from orchestrate_tasks import main
from task_orchestrator.engine import Engine
from task_orchestrator.store import Store

from .common import Fixture


class CliTests(unittest.TestCase):
    def test_status_command_reports_tasks_without_execution(self):
        fixture = Fixture(mode="shadow")
        try:
            store = Store(fixture.root / "state" / "state.sqlite3")
            try:
                Engine(fixture.cfg, store).ingest(fixture.task("INFRA-CLI-STATUS-001"))
            finally:
                store.close()
            config = fixture.root / "orchestrator.yaml"
            config.write_text(yaml.safe_dump(fixture.cfg, sort_keys=False), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--config", str(config), "status"])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result["mode"], "shadow")
            self.assertEqual(result["counts"], {"READY": 1})
            self.assertEqual(result["tasks"][0]["task_id"], "INFRA-CLI-STATUS-001")
            self.assertEqual(result["llm_calls"], 0)
        finally:
            fixture.close()

    def test_authoring_manifest_and_preflight_do_not_open_operational_database(self):
        fixture = Fixture(mode="shadow")
        try:
            config = fixture.root / "orchestrator.yaml"
            config.write_text(yaml.safe_dump(fixture.cfg, sort_keys=False), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--config", str(config), "authoring-manifest"])
            manifest = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(manifest["persistent_project_control_mode"], "NON_WORK")
            self.assertFalse((fixture.root / "state" / "state.sqlite3").exists())

            task = fixture.task(source_issue=None, labels=())
            request = {
                "schema_version": 1, "operation_type": "NEW_ISSUE",
                "author_role": "00_PROJECT_CONTROL", "canonical_head": fixture.head,
                "issue": {"number": None, "state": "open",
                          "labels": ["orchestrator:task"]},
                "task": task.envelope_dict(), "existing_binding": None,
                "required_repository_paths": [], "dependency_bindings": [],
                "review_binding": None,
                "accepted_state_changes": [{
                    "identity": "CLI-NOT-STATE-CHANGING", "result_sha256": "a" * 64,
                    "materialization_state": "NOT_STATE_CHANGING",
                    "materialization_commit": None, "reason": None,
                }],
                "context_delta_bundle": None,
                "lifecycle": {
                    "disposition": "CURRENT", "target_task_id": task.task_id,
                    "target_envelope_hash": task.envelope_hash,
                    "successor_task_id": None, "reason": None,
                },
                "project_status": {
                    "project_progress": "NOT_STARTED", "human_action_required": False,
                    "semantic_state": "ACCEPTED", "design_state": "REVIEWED",
                    "implementation_state": "AUTHORIZED",
                    "deployment_state": "NOT_AUTHORIZED",
                    "canonicalization_state": "NOT_STATE_CHANGING",
                },
                "execution_context": "SEPARATE_BOUNDED_WORK",
                "persistent_chat_role": "00_PROJECT_CONTROL",
                "chatgpt_scheduler_requested": False,
            }
            request_path = fixture.root / "authoring.yaml"
            request_path.write_text(yaml.safe_dump(request, sort_keys=False), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--config", str(config), "authoring-preflight", str(request_path)])
            receipt = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(receipt["status"], "PREFLIGHT_PASS")
            self.assertFalse((fixture.root / "state" / "state.sqlite3").exists())
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
