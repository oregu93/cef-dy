from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

import yaml

from .github import GitHubIssueSource, IssueSource, SourceUnavailable, backoff_seconds
from .model import State, Task, TransitionError, utc_now
from .policy import task_has_issue_approval, validate_task_policy
from .schema import parse_issue_body, validate_task
from .store import Store
from . import workers


class Engine:
    def __init__(self, cfg: dict[str, Any], store: Store):
        self.cfg = cfg
        self.store = store
        self.state_dir = Path(cfg["state_dir"])
        self.results_dir = self.state_dir / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def ingest(self, task: Task) -> str:
        outcome = self.store.ingest(task)
        if outcome == "conflict":
            raise TransitionError(f"task_id {task.task_id} already exists with a different TASK envelope")
        if outcome in {"duplicate", "metadata_updated"}:
            return outcome
        try:
            validate_task_policy(task, self.cfg)
        except Exception as exc:
            self.store.transition(task.task_id, State.REJECTED, str(exc))
            return "rejected"
        self.store.transition(task.task_id, State.VALIDATED, "schema and policy valid")
        self._route(task)
        return "created"

    def _route(self, task: Task) -> None:
        dep_states = self.store.dependency_states(task)
        if any(value in {State.FAILED.value, State.REJECTED.value, State.BLOCKED.value} for value in dep_states.values()):
            self.store.transition(task.task_id, State.BLOCKED, "dependency terminal failure")
        elif any(value != State.SUCCEEDED.value for value in dep_states.values()):
            self.store.transition(task.task_id, State.WAITING_DEPENDENCY, "dependencies incomplete")
        elif task.is_llm:
            issue_ok = task_has_issue_approval(task, self.cfg)
            local_ok = not self.cfg["llm"].get("require_local_approval", True)
            if issue_ok and local_ok and self.cfg["llm"].get("dispatch_enabled") and self.cfg["mode"] == "pilot":
                self.store.transition(task.task_id, State.READY, "authorized bounded AI task ready")
            else:
                self.store.transition(task.task_id, State.WAITING_APPROVAL, "AI task authorization incomplete")
        else:
            self.store.transition(task.task_id, State.READY, "deterministic task ready")

    def reevaluate_waiting(self) -> None:
        for row in self.store.list_state(State.WAITING_DEPENDENCY):
            task = self.store.task(row)
            states = self.store.dependency_states(task)
            if any(value in {State.FAILED.value, State.REJECTED.value, State.BLOCKED.value} for value in states.values()):
                self.store.transition(task.task_id, State.BLOCKED, "dependency terminal failure")
            elif all(value == State.SUCCEEDED.value for value in states.values()):
                self.store.transition(task.task_id, State.WAITING_APPROVAL if task.is_llm else State.READY, "dependencies complete")
        for row in self.store.list_state(State.WAITING_APPROVAL, State.WAITING_USER):
            task = self.store.task(row)
            if not task.is_llm:
                continue
            local = bool(row["approved_at"]) or not self.cfg["llm"].get("require_local_approval", True)
            issue = task_has_issue_approval(task, self.cfg)
            if local and issue and self.cfg["llm"].get("dispatch_enabled") and self.cfg["mode"] == "pilot":
                self.store.transition(task.task_id, State.READY, "dual approval satisfied")

    def detect_cycles(self) -> list[list[str]]:
        graph = {row["task_id"]: list(self.store.task(row).dependencies) for row in self.store.list_state()}
        visited: set[str] = set()
        active: list[str] = []
        cycles: list[list[str]] = []

        def visit(node: str) -> None:
            if node in active:
                cycle = active[active.index(node):] + [node]
                cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            active.append(node)
            for dep in graph.get(node, []):
                if dep in graph:
                    visit(dep)
            active.pop()

        for node in sorted(graph):
            visit(node)
        for cycle in cycles:
            for task_id in set(cycle):
                row = self.store.get(task_id)
                if row and row["state"] not in {s.value for s in (State.SUCCEEDED, State.FAILED, State.REJECTED, State.BLOCKED)}:
                    self.store.transition(task_id, State.BLOCKED, "dependency cycle: " + " -> ".join(cycle), force_recovery=True)
        return cycles

    def recover_orphans(self, now_epoch: float | None = None) -> int:
        now_epoch = now_epoch or time.time()
        count = 0
        for row in self.store.list_state(State.RUNNING):
            stamp = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")).timestamp()
            if now_epoch - stamp <= int(self.cfg["orphaned_run_after_seconds"]):
                continue
            task = self.store.task(row)
            target = State.WAITING_APPROVAL if task.is_llm else State.READY
            self.store.transition(task.task_id, target, "orphaned RUNNING recovered after restart", force_recovery=True)
            count += 1
        return count

    def run_ready(self) -> list[dict[str, Any]]:
        results = []
        if self.cfg["mode"] in {"shadow", "dry-run"}:
            return results
        for row in self.store.list_state(State.READY)[: int(self.cfg["max_concurrent_workers"])]:
            task = self.store.task(row)
            if task.is_llm:
                self.store.transition(task.task_id, State.WAITING_APPROVAL, "no automatic LLM dispatcher is implemented")
                continue
            self.store.transition(task.task_id, State.RUNNING, "deterministic worker started")
            attempt = self.store.increment_attempt(task.task_id)
            result = workers.run(task, attempt, self.cfg)
            self._atomic_yaml(self.results_dir / f"{task.task_id}.yaml", result.as_dict())
            target = State.SUCCEEDED if result.status == "SUCCEEDED" else State.FAILED
            self.store.transition(task.task_id, target, result.error or "worker completed")
            results.append(result.as_dict())
        self.write_summary()
        return results

    def pause_quota(self, task_id: str) -> None:
        row = self.store.get(task_id)
        if not row or row["state"] not in {State.RUNNING.value, State.READY.value}:
            raise TransitionError("quota pause requires READY or RUNNING task")
        self.store.transition(task_id, State.QUOTA_WAIT, "quota exhaustion; automatic resume scheduled", force_recovery=row["state"] == State.READY.value)

    def poll(self, source: IssueSource | None = None) -> dict[str, Any]:
        if not self.cfg["github"]["enabled"]:
            return {"status": "disabled", "llm_calls": 0}
        source = source or GitHubIssueSource(self.cfg["github"])
        state = self.store.source("github")
        now = time.time()
        if now < float(state["backoff_until"]):
            return {"status": "backoff", "until": state["backoff_until"], "llm_calls": 0}
        try:
            issues, etag, unchanged = source.fetch(state.get("etag"))
        except SourceUnavailable as exc:
            failures = int(state["failures"]) + 1
            delay = backoff_seconds(failures, int(self.cfg["github"]["backoff_initial_seconds"]), int(self.cfg["github"]["backoff_max_seconds"]))
            self.store.update_source("github", etag=state.get("etag"), backoff_until=now + delay, failures=failures)
            self.store.append_event(None, "SOURCE_OUTAGE", None, None, {"error": str(exc), "backoff_seconds": delay})
            return {"status": "outage", "backoff_seconds": delay, "llm_calls": 0}
        self.store.update_source("github", etag=etag, backoff_until=0, failures=0)
        accepted = rejected = duplicates = updated = manual_changes = 0
        if not unchanged:
            for issue in issues:
                existing_task_id = self.store.task_id_for_issue(issue.number)
                has_task_label = self.cfg["github"]["task_label"] in issue.labels
                if not has_task_label and not existing_task_id:
                    continue
                snapshot_status, changed_fields = self.store.record_issue_snapshot(issue, existing_task_id)
                if snapshot_status == "changed":
                    manual_changes += 1
                try:
                    if not has_task_label:
                        self.store.pause_for_manual_issue_change(existing_task_id, "manual removal of orchestrator task label")
                        continue
                    allowed_control_labels = {self.cfg["github"]["task_label"], self.cfg["llm"]["require_issue_label"]}
                    unexpected = sorted(label for label in issue.labels if label.startswith("orchestrator:") and label not in allowed_control_labels)
                    if unexpected:
                        raise ValueError("unexpected orchestrator labels: " + ", ".join(unexpected))
                    task = parse_issue_body(issue.body, source_issue=issue.number, labels=issue.labels)
                    if existing_task_id and task.task_id != existing_task_id:
                        raise ValueError(f"manual TASK_ID change from {existing_task_id} to {task.task_id}")
                    outcome = self.ingest(task)
                    self.store.record_issue_snapshot(issue, task.task_id)
                    if outcome == "duplicate": duplicates += 1
                    elif outcome == "metadata_updated": updated += 1
                    elif outcome == "rejected": rejected += 1
                    else: accepted += 1
                    if issue.state != "open":
                        self.store.pause_for_manual_issue_change(task.task_id, f"GitHub Issue manually closed ({issue.state_reason or 'no reason'})")
                    elif task.is_llm and not task_has_issue_approval(task, self.cfg):
                        row = self.store.get(task.task_id)
                        if row and row["state"] not in {s.value for s in (State.SUCCEEDED, State.FAILED, State.REJECTED, State.BLOCKED)}:
                            self.store.transition(task.task_id, State.WAITING_USER, "manual removal of LLM approval label", force_recovery=True)
                except Exception as exc:
                    rejected += 1
                    affected = existing_task_id or self.store.task_id_for_issue(issue.number)
                    if affected:
                        self.store.pause_for_manual_issue_change(affected, f"manual GitHub Issue edit requires review: {exc}")
                    self.store.append_event(affected, "ISSUE_REJECTED", None, None, {"issue": issue.number, "error": str(exc)})
        self.detect_cycles()
        self.reevaluate_waiting()
        self.recover_orphans()
        self.write_summary()
        return {"status": "unchanged" if unchanged else "ok", "accepted": accepted, "rejected": rejected, "duplicates": duplicates, "updated": updated, "manual_changes": manual_changes, "llm_calls": 0}

    def write_summary(self) -> Path:
        summary = self.status()
        path = self.state_dir / "pc_inbox.yaml"
        self._atomic_yaml(path, summary)
        return path

    def status(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        items = []
        for row in self.store.list_state():
            counts[row["state"]] = counts.get(row["state"], 0) + 1
            items.append({"task_id": row["task_id"], "state": row["state"], "reason": row["reason"], "source_issue": row["source_issue"], "updated_at": row["updated_at"]})
        return {
            "schema_version": 1,
            "generated_at": utc_now(),
            "mode": self.cfg["mode"],
            "authority": "operational_only_not_project_control",
            "llm_dispatch_enabled": bool(self.cfg["llm"]["dispatch_enabled"]),
            "llm_calls": 0,
            "counts": dict(sorted(counts.items())),
            "tasks": items,
        }

    @staticmethod
    def _atomic_yaml(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(value, handle, sort_keys=False, allow_unicode=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try: os.unlink(temp_name)
            except FileNotFoundError: pass
            raise
