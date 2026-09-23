from __future__ import annotations

import hashlib
import subprocess
import unittest

from task_orchestrator import workers

from .common import Fixture


class WorkerTests(unittest.TestCase):
    def setUp(self): self.fx = Fixture()
    def tearDown(self): self.fx.close()

    def run_task(self, **kwargs): return workers.run(self.fx.task(**kwargs), 1, self.fx.cfg)

    def test_head_and_status(self):
        self.assertEqual(self.run_task().status, "SUCCEEDED")
        self.assertEqual(self.run_task(action="status_check").status, "SUCCEEDED")

    def test_head_drift(self):
        result = workers.run(self.fx.task(canonical_head="b" * 40), 1, self.fx.cfg)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("HEAD_DRIFT", result.error)

    def test_sha_and_missing_artifact(self):
        digest = hashlib.sha256(b"safe\n").hexdigest()
        ok = self.run_task(action="sha256_check", inputs={"files": {"safe.txt": digest}})
        self.assertEqual(ok.status, "SUCCEEDED")
        bad = self.run_task(action="sha256_check", inputs={"files": {"safe.txt": "0" * 64}})
        self.assertIn("SHA_MISMATCH", bad.error)
        missing = self.run_task(action="artifact_check", expected_artifacts=("missing.txt",))
        self.assertIn("missing artifact", missing.error)

    def test_schema(self):
        ok = self.run_task(action="schema_check", inputs={"paths": ["sample.yaml"], "required_keys": ["schema_version", "name"]})
        self.assertEqual(ok.status, "SUCCEEDED")
        bad = self.run_task(action="schema_check", inputs={"paths": ["sample.yaml"], "required_keys": ["missing"]})
        self.assertEqual(bad.status, "FAILED")

    def test_allowlisted_command_pass_fail_timeout(self):
        self.assertEqual(self.run_task(action="test_command", inputs={"command_id": "pass"}).status, "SUCCEEDED")
        self.assertIn("exit code 3", self.run_task(action="test_command", inputs={"command_id": "fail"}).error)
        self.assertIn("WORKER_TIMEOUT", self.run_task(action="test_command", inputs={"command_id": "timeout"}).error)

    def test_unauthorized_command(self):
        task = self.fx.task(action="test_command", inputs={"command_id": "shell"})
        result = workers.run(task, 1, self.fx.cfg)
        self.assertEqual(result.status, "FAILED")


if __name__ == "__main__": unittest.main()
