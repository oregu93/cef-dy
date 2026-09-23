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


if __name__ == "__main__":
    unittest.main()
