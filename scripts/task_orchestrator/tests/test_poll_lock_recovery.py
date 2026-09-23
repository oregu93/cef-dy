from __future__ import annotations

import json
import os
from pathlib import Path
import time
import unittest
from unittest import mock

from task_orchestrator.engine import Engine
from task_orchestrator.github import Issue, SourceUnavailable, backoff_seconds
from task_orchestrator.locking import LockBusy, ProcessLock
from task_orchestrator.store import Store

from .common import Fixture


def body(head, task_id="INFRA-POLL-001"):
    return f"""task\n```yaml
schema_version: 1
task_id: {task_id}
role: 07_INFRASTRUCTURE
canonical_head: {head}
task_type: deterministic
action: head_check
stop_condition: stop
```"""


class Source:
    def __init__(self, issues=None, unchanged=False, error=None): self.issues, self.unchanged, self.error, self.calls = issues or [], unchanged, error, 0
    def fetch(self, etag=None):
        self.calls += 1
        if self.error: raise self.error
        return self.issues, '"etag"', self.unchanged


class PollLockRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture(mode="shadow")
        self.fx.cfg["github"]["enabled"] = True
        self.store = Store(self.fx.root / "state" / "db.sqlite3")
        self.engine = Engine(self.fx.cfg, self.store)
    def tearDown(self): self.store.close(); self.fx.close()

    def test_poll_repeat_etag_and_zero_llm_calls(self):
        issue = Issue(1, "task", body(self.fx.head), ("orchestrator:task",), "now")
        source = Source([issue])
        first = self.engine.poll(source)
        second = self.engine.poll(source)
        self.assertEqual(first["accepted"], 1)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(first["llm_calls"], 0)
        unchanged = self.engine.poll(Source(unchanged=True))
        self.assertEqual(unchanged["status"], "unchanged")

    def test_unexpected_issue_and_labels_fail_closed(self):
        bad = Issue(2, "bad", "not yaml", ("unexpected",), "now")
        result = self.engine.poll(Source([bad]))
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(len(self.store.list_state()), 0)
        labelled = Issue(3, "bad label", body(self.fx.head, "INFRA-POLL-002"), ("orchestrator:task", "orchestrator:unknown"), "now")
        result = self.engine.poll(Source([labelled]))
        self.assertEqual(result["rejected"], 1)
        self.assertIsNone(self.store.get("INFRA-POLL-002"))

    def test_idle_loop_has_no_openai_or_codex_call_surface(self):
        package = Path(__file__).resolve().parents[1]
        code = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
        for forbidden in ("api.openai.com", "openai.ChatCompletion", "subprocess.run(['codex'", 'subprocess.run(["codex"'):
            self.assertNotIn(forbidden, code)
        source = Source(unchanged=True)
        for _ in range(100):
            result = self.engine.poll(source)
            self.assertEqual(result["llm_calls"], 0)

    def test_outage_backoff_and_rate_limit_math(self):
        source = Source(error=SourceUnavailable("rate limited"))
        result = self.engine.poll(source)
        self.assertEqual(result["status"], "outage")
        again = self.engine.poll(source)
        self.assertEqual(again["status"], "backoff")
        self.assertEqual(source.calls, 1)
        self.assertEqual([backoff_seconds(n, 5, 20) for n in range(1, 6)], [5, 10, 20, 20, 20])

    def test_lock_concurrent_and_stale(self):
        path = self.fx.root / "state" / "lock"
        first = ProcessLock(path, 1); first.acquire()
        try:
            with self.assertRaises(LockBusy): ProcessLock(path, 1).acquire()
        finally: first.release()
        path.write_text(json.dumps({"pid": 99999999, "host": "x", "created": time.time() - 100}), encoding="utf-8")
        lock = ProcessLock(path, 1); lock.acquire(); lock.release()
        self.assertTrue(list(path.parent.glob("lock.stale.*")))

    def test_interrupted_atomic_write_preserves_previous(self):
        path = self.fx.root / "state" / "pc_inbox.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old: true\n", encoding="utf-8")
        with mock.patch("task_orchestrator.engine.os.replace", side_effect=OSError("injected")):
            with self.assertRaises(OSError): self.engine._atomic_yaml(path, {"new": True})
        self.assertEqual(path.read_text(encoding="utf-8"), "old: true\n")
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_corrupted_state_is_detected_and_quarantinable(self):
        db = self.fx.root / "broken.sqlite3"
        db.write_bytes(b"not sqlite")
        with self.assertRaises(Exception): Store(db)
        quarantined = Store.quarantine_corrupt(db)
        self.assertTrue(quarantined.is_file())
        self.assertEqual(quarantined.read_bytes(), b"not sqlite")


if __name__ == "__main__": unittest.main()
