from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import yaml

from task_orchestrator.config import DEFAULTS
from task_orchestrator.model import Task


class Fixture:
    def __init__(self, mode="pilot"):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        (self.root / "safe.txt").write_text("safe\n", encoding="utf-8")
        (self.root / "sample.yaml").write_text("schema_version: 1\nname: sample\n", encoding="utf-8")
        subprocess.run(["git", "add", "safe.txt", "sample.yaml"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", self.head], cwd=self.root, check=True)
        project = self.root / "00_Project"
        project.mkdir()
        freshness = {
            "schema_version": 2,
            "record_id": "TEST-CANONICAL-STATE-FRESHNESS",
            "status": "FRESH",
            "assessed_at": "2026-10-08",
            "assessed_head": self.head,
            "authority": "PROJECT_CONTROL",
            "purpose": "Deterministic test authority.",
            "freshness_semantics": {},
            "layers": {
                "scientific_core": {"status": "CURRENT_WITH_SCOPED_DEBT"},
                "project_control": {"status": "FRESH"},
                "infrastructure": {"status": "FRESH"},
                "literature_and_supporting_knowledge": {
                    "status": "CURRENT_WITH_SCOPED_DEBT",
                },
            },
            "materialization_commit_policy": "Exact fixture head.",
            "materialization_paths": [],
            "consequential_task_gate": {},
            "scientific_boundary": {
                "milestone": "M03R",
                "state": "LEVEL_2_established_LEVEL_3_blocked",
                "level_3": "absent",
                "level_4": "absent",
                "stage03d": "suspended",
                "exchange": "deferred",
                "holdout": "unauthorized",
                "taipan_18_247_meV": "candidate_with_caveat_only",
                "new_scientific_interpretation": "none",
            },
            "prohibitions": [],
        }
        ledger = {
            "schema_version": 1,
            "ledger_id": "TEST-MATERIALIZATION-DEBT",
            "assessed_head": self.head,
            "authority": "PROJECT_CONTROL",
            "derivation_rule": "Exact deterministic fixture.",
            "states": sorted({
                "MATERIALIZED", "PENDING_MATERIALIZATION",
                "EXPLICITLY_DEFERRED_WITH_REASON", "NOT_STATE_CHANGING",
                "UNRESOLVED_SOURCE_RECOVERY",
            }),
            "inventory_ids": [],
            "items": [],
        }
        (project / "CANONICAL_STATE_FRESHNESS.yaml").write_text(
            yaml.safe_dump(freshness, sort_keys=False), encoding="utf-8",
        )
        (project / "MATERIALIZATION_DEBT_LEDGER.yaml").write_text(
            yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8",
        )
        self.cfg = deepcopy(DEFAULTS)
        self.cfg["mode"] = mode
        self.cfg["repository_root"] = str(self.root)
        self.cfg["state_dir"] = str(self.root / "state")
        self.cfg["commands"]["allow"] = {
            "pass": {"argv": ["python", "-c", "print('ok')"], "timeout_seconds": 5},
            "fail": {"argv": ["python", "-c", "raise SystemExit(3)"], "timeout_seconds": 5},
            "timeout": {"argv": ["python", "-c", "import time; time.sleep(2)"], "timeout_seconds": 1},
        }

    def close(self):
        self.temp.cleanup()

    def task(self, task_id="INFRA-TEST-001", **overrides):
        data = dict(schema_version=1, task_id=task_id, role="07_INFRASTRUCTURE", canonical_head=self.head, task_type="deterministic", action="head_check", stop_condition="stop", dependencies=(), inputs={}, allowed_paths=(), expected_artifacts=(), timeout_seconds=10, source_issue=1, labels=("orchestrator:task",))
        data.update(overrides)
        return Task(**data)
