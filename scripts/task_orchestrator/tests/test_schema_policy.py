from __future__ import annotations

import random
import string
import unittest
from datetime import date
from pathlib import Path

import yaml

from task_orchestrator.model import ValidationError
from task_orchestrator.policy import normalize_relative, validate_task_policy
from task_orchestrator.schema import parse_issue_body, validate_task

from .common import Fixture


BASE = {"schema_version": 1, "task_id": "INFRA-TASK-001", "role": "07_INFRASTRUCTURE", "canonical_head": "a" * 40, "task_type": "deterministic", "action": "head_check", "stop_condition": "stop"}


class SchemaPolicyTests(unittest.TestCase):
    def test_github_issue_form_preserves_task_contract(self):
        root = Path(__file__).resolve().parents[3]
        form_path = root / ".github" / "ISSUE_TEMPLATE" / "orchestrator_task.yml"
        form = yaml.safe_load(form_path.read_text(encoding="utf-8"))
        self.assertIn("orchestrator:task", form["labels"])
        textareas = [item for item in form["body"] if item.get("type") == "textarea"]
        self.assertEqual(len(textareas), 1)
        textarea = textareas[0]
        self.assertEqual(textarea["attributes"]["render"], "yaml")
        self.assertTrue(textarea["validations"]["required"])
        task = parse_issue_body(
            f"## TASK envelope\n\n```yaml\n{textarea['attributes']['placeholder']}```",
            source_issue=1,
            labels=("orchestrator:task",),
        )
        self.assertEqual(task.task_id, "INFRA-EXAMPLE-001")

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

    def test_symlink_cannot_bypass_forbidden_path(self):
        fixture = Fixture()
        try:
            forbidden = fixture.root / "CEF_Dy_Data"
            forbidden.mkdir()
            (forbidden / "holdout.txt").write_text("protected", encoding="utf-8")
            (fixture.root / "innocent.txt").symlink_to(forbidden / "holdout.txt")
            task = fixture.task(action="artifact_check", expected_artifacts=("innocent.txt",))
            with self.assertRaises(ValidationError):
                validate_task_policy(task, fixture.cfg)
        finally:
            fixture.close()

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

    def test_dependency_result_binding_is_explicit_and_semantic_only(self):
        with self.assertRaisesRegex(ValidationError, "semantic task"):
            validate_task({**BASE, "dependencies": ["PARENT-001"],
                           "inputs": {"bind_dependency_results": True}})
        semantic = {**BASE, "task_type": "llm_semantic", "action": "semantic_helper"}
        with self.assertRaisesRegex(ValidationError, "at least one dependency"):
            validate_task({**semantic, "inputs": {"bind_dependency_results": True}})
        with self.assertRaisesRegex(ValidationError, "must be boolean"):
            validate_task({**semantic, "dependencies": ["PARENT-001"],
                           "inputs": {"bind_dependency_results": "yes"}})
        task = validate_task({**semantic, "dependencies": ["PARENT-001"],
                              "inputs": {"bind_dependency_results": True}})
        self.assertEqual(task.dependencies, ("PARENT-001",))


if __name__ == "__main__": unittest.main()
