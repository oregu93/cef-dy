from __future__ import annotations

import random
import string
import unittest
from datetime import date

from task_orchestrator.model import ValidationError
from task_orchestrator.policy import normalize_relative, validate_task_policy
from task_orchestrator.schema import parse_issue_body, validate_task

from .common import Fixture


BASE = {"schema_version": 1, "task_id": "INFRA-TASK-001", "role": "07_INFRASTRUCTURE", "canonical_head": "a" * 40, "task_type": "deterministic", "action": "head_check", "stop_condition": "stop"}


class SchemaPolicyTests(unittest.TestCase):
    def test_valid_minimal_task(self):
        self.assertEqual(validate_task(BASE).task_id, "INFRA-TASK-001")

    def test_missing_unknown_malformed_and_partial(self):
        for value in (None, [], "x", {"schema_version": 1}):
            with self.subTest(value=value), self.assertRaises(ValidationError): validate_task(value)
        with self.assertRaises(ValidationError): validate_task({**BASE, "surprise": 1})
        with self.assertRaises(ValidationError): parse_issue_body("```yaml\n: broken\n```", source_issue=1, labels=())
        with self.assertRaises(ValidationError): parse_issue_body("none", source_issue=1, labels=())
        with self.assertRaises(ValidationError): parse_issue_body("```yaml\n{}\n```\n```yaml\n{}\n```", source_issue=1, labels=())

    def test_odd_and_large_fields_fail_closed(self):
        with self.assertRaises(ValidationError): validate_task({**BASE, "task_id": "../escape"})
        with self.assertRaises(ValidationError): validate_task({**BASE, "stop_condition": "x" * 2001})
        with self.assertRaises(ValidationError): validate_task({**BASE, "inputs": {"x": "y" * 100001}})
        with self.assertRaises(ValidationError): validate_task({**BASE, "inputs": {"when": date.today()}})
        with self.assertRaises(ValidationError): validate_task({**BASE, "inputs": {"bad": float("nan")}})
        with self.assertRaises(ValidationError): validate_task({**BASE, "inputs": {1: "non-string key"}})
        with self.assertRaises(ValidationError): validate_task({**BASE, "dependencies": ["A", "A"]})
        with self.assertRaises(ValidationError): validate_task({**BASE, "timeout_seconds": True})

    def test_path_escape_absolute_and_forbidden(self):
        for value in ("../secret", "/etc/passwd", "a/../../b", ".git/config", "CEF_Dy_Data/raw.dat", "private/x"):
            with self.subTest(value=value):
                fixture = Fixture()
                try:
                    task = fixture.task(action="artifact_check", expected_artifacts=(value,))
                    with self.assertRaises(ValidationError): validate_task_policy(task, fixture.cfg)
                finally: fixture.close()

    def test_random_paths_never_escape(self):
        random.seed(42)
        for _ in range(500):
            value = "".join(random.choice(string.ascii_letters + string.digits + "./\\_") for _ in range(random.randint(0, 40)))
            try:
                normalized = normalize_relative(value)
            except ValidationError:
                continue
            self.assertFalse(normalized.startswith("/"))
            self.assertNotIn("..", normalized.split("/"))

    def test_llm_action_boundary(self):
        with self.assertRaises(ValidationError): validate_task({**BASE, "task_type": "llm_worker"})
        task = validate_task({**BASE, "task_type": "llm_semantic", "action": "semantic_helper"})
        self.assertTrue(task.is_llm)


if __name__ == "__main__": unittest.main()
