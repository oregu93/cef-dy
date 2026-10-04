from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

import yaml

from .admission import (
    AdmissionClass, AdmissionDecision, VisibilityAssessment, VisibilityFacts,
    VisibilityHealth, classify_admission, compute_visibility_health,
    decide_admission,
)
from .github import GitHubIssueSource, IssueSource, SourceUnavailable, backoff_seconds
from .model import State, Task, TransitionError, utc_now
from .policy import task_has_issue_approval, validate_task_policy
from .routing import _material_digest, canonical_role
from .schema import parse_issue_body, validate_task
from .store import Store
from . import workers


class Engine:
    def __init__(self, cfg: dict[str, Any], store: Store):
        self.cfg = cfg
        self.store = store
        self._recovery_barrier_controller_managed = False
        self._recovery_barrier_enabled = self._ordinary_autonomy_capable()
        self._recovery_barrier_proven = (
            self._durable_recovery_proven()
            if self._recovery_barrier_enabled else False
        )
        self.state_dir = Path(cfg["state_dir"])
        self.results_dir = self.state_dir / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def enable_recovery_barrier(self) -> None:
        """Require controller-established recovery proof for ordinary admission."""
        self._recovery_barrier_controller_managed = True
        self._recovery_barrier_enabled = True
        self._recovery_barrier_proven = False

    def set_recovery_barrier_proven(self, proven: bool) -> None:
        self._recovery_barrier_proven = bool(proven)

    def _ordinary_autonomy_capable(self) -> bool:
        autonomy = self.cfg.get("autonomy", {})
        return bool(
            self.cfg.get("mode") == "pilot"
            and self.cfg.get("github", {}).get("enabled")
            and autonomy.get("enabled")
            and not autonomy.get("plan_only")
        )

    def _durable_recovery_proven(self) -> bool:
        """Read existing controller proof without creating or advancing it."""
        try:
            table = self.store.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='controller_state'"
            ).fetchone()
            if table is None:
                return False
            row = self.store.conn.execute(
                "SELECT state_json FROM controller_state WHERE task_id=?",
                ("ORCH-M1B-RELIABILITY-REBUILD-001",),
            ).fetchone()
            state = json.loads(row["state_json"]) if row is not None else {}
        except (KeyError, TypeError, json.JSONDecodeError):
            return False
        return bool(
            isinstance(state, dict)
            and state.get("RECOVERY_PROOF_STATE") == "PROVEN"
        )

    def _live_capable(self) -> bool:
        autonomy = self.cfg.get("autonomy", {})
        publishing = self.cfg.get("publishing", {})
        return bool(
            self.cfg.get("mode") == "pilot"
            and self.cfg.get("github", {}).get("enabled")
            and autonomy.get("enabled")
            and not autonomy.get("plan_only")
            and publishing.get("enabled")
            and not publishing.get("preview_only", True)
        )

    def visibility_health(self, now_epoch: float | None = None) -> VisibilityAssessment:
        now_epoch = time.time() if now_epoch is None else float(now_epoch)
        unresolved_ages: list[float | None] = []
        required_statuses: list[str] = []
        required_outbox_identities = 0
        accepted_table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accepted_results'"
        ).fetchone()
        if accepted_table is not None:
            rows = self.store.conn.execute(
                "SELECT r.task_id,r.accepted_at,t.state,t.source_issue "
                "FROM accepted_results r JOIN tasks t USING(task_id) "
                "WHERE t.source_issue IS NOT NULL AND t.state IN ('SUCCEEDED','FAILED','REJECTED','BLOCKED') "
                "ORDER BY r.accepted_at,r.task_id"
            )
            for row in rows:
                statuses = [str(item[0]).upper() for item in self.store.conn.execute(
                    "SELECT status FROM publication_outbox WHERE task_id=? "
                    "AND marker LIKE '<!-- cef-dy-orch-result:v1 %' ORDER BY publication_id",
                    (row["task_id"],),
                )]
                live_statuses = [status for status in statuses if status != "PREVIEW"]
                if "PUBLISHED" in live_statuses:
                    continue
                # PREVIEW is maintenance/shadow evidence, not a live required
                # external acknowledgement.  Once live publication is enabled,
                # Publisher promotes eligible rows to PENDING.
                if statuses and not live_statuses:
                    continue
                try:
                    accepted_epoch = datetime.fromisoformat(
                        str(row["accepted_at"]).replace("Z", "+00:00")
                    ).timestamp()
                    age: float | None = now_epoch - accepted_epoch
                except (TypeError, ValueError):
                    age = None
                unresolved_ages.append(age)
                required_statuses.extend(live_statuses)
                if live_statuses:
                    required_outbox_identities += 1
        autonomy = self.cfg.get("autonomy", {})
        ordinary_autonomy_enabled = bool(
            self.cfg.get("mode") == "pilot"
            and self.cfg.get("github", {}).get("enabled")
            and autonomy.get("enabled")
            and not autonomy.get("plan_only")
        )
        publishing = self.cfg.get("publishing", {})
        return compute_visibility_health(VisibilityFacts(
            ordinary_autonomy_enabled=ordinary_autonomy_enabled,
            publishing_enabled=bool(publishing.get("enabled")),
            preview_only=bool(publishing.get("preview_only", True)),
            unresolved_terminal_ages_seconds=tuple(unresolved_ages),
            required_publication_statuses=tuple(required_statuses),
            required_outbox_identities=required_outbox_identities,
            max_batch_tasks=int(autonomy.get("max_batch_tasks", 1)),
            poll_interval_seconds=int(self.cfg.get("poll_interval_seconds", 300)),
        ))

    def admission_decision(
        self, task: Task, assessment: VisibilityAssessment | None = None,
    ) -> AdmissionDecision:
        assessment = assessment or self.visibility_health()
        admission_class = classify_admission(task.inputs)
        decision = decide_admission(
            assessment,
            admission_class,
            identity_bound_review=self._identity_bound_review(task),
            unresolved_replacement_identity=self._unresolved_replacement_identity(task),
        )
        proof_proven = self._recovery_barrier_proven
        if not self._recovery_barrier_controller_managed:
            # Direct Engine/CLI surfaces may consume durable controller proof,
            # but they never create or advance it.
            proof_proven = self._durable_recovery_proven()
            self._recovery_barrier_proven = proof_proven
        if (
            decision.allowed
            and admission_class is AdmissionClass.ORDINARY
            and self._ordinary_autonomy_capable()
            and (
                not proof_proven
                or assessment.state is not VisibilityHealth.AUTONOMY_VISIBILITY_OK
            )
        ):
            return AdmissionDecision(
                False,
                admission_class,
                assessment.state,
                "durable recovery proof and current healthy visibility are required",
            )
        control_allowed, control_reason = self._telegram_control_allows(task)
        if decision.allowed and not control_allowed:
            return AdmissionDecision(
                False, admission_class, assessment.state, control_reason,
            )
        return decision

    def _telegram_control_allows(self, task: Task) -> tuple[bool, str]:
        """Enforce authenticated operational controls at every Engine surface.

        Absence of the optional gateway schema preserves the pre-gateway baseline.
        Once initialized, holds and fail-safe modes are durable SQLite facts, so
        direct CLI paths cannot bypass them.
        """
        tables = {str(row[0]) for row in self.store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('telegram_gateway_state','telegram_holds')"
        )}
        if not tables:
            return True, "Telegram operational control is not initialized"
        if tables != {"telegram_gateway_state", "telegram_holds"}:
            return False, "Telegram operational control state is incomplete"
        state = self.store.conn.execute(
            "SELECT control_mode FROM telegram_gateway_state WHERE singleton=1"
        ).fetchone()
        mode = str(state[0]) if state is not None else "INVALID"
        if mode not in {"NORMAL", "AI_PAUSED", "DRAIN", "QUIESCED", "SAFE"}:
            return False, "Telegram operational control state is invalid"
        held = self.store.conn.execute(
            "SELECT 1 FROM telegram_holds WHERE task_id=? AND state='ACTIVE'",
            (task.task_id,),
        ).fetchone()
        if held is not None:
            return False, "task is held by authenticated Telegram operational control"
        if mode in {"DRAIN", "QUIESCED", "SAFE"}:
            return False, f"Telegram operational control mode is {mode}"
        if mode == "AI_PAUSED" and task.is_llm:
            return False, f"Telegram operational control mode is {mode}"
        return True, "Telegram operational control permits task"

    def _identity_bound_review(self, task: Task) -> bool:
        if classify_admission(task.inputs).value != "MANDATORY_REVIEW":
            return False
        tables = {str(row[0]) for row in self.store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('accepted_results','review_requirements')"
        )}
        if tables != {"accepted_results", "review_requirements"}:
            return False
        parent_id = task.inputs.get("review_of")
        material = task.inputs.get("review_material")
        if not isinstance(parent_id, str) or not isinstance(material, dict):
            return False
        accepted = self.store.conn.execute(
            "SELECT result_sha256,result_json FROM accepted_results WHERE task_id=?", (parent_id,)
        ).fetchone()
        parent = self.store.get(parent_id)
        requirement = self.store.conn.execute(
            "SELECT review_task_id,role_id FROM review_requirements WHERE parent_task_id=?",
            (parent_id,),
        ).fetchone()
        core = (
            {key: value for key, value in material.items() if key != "review_material_sha256"}
            if isinstance(material, dict) else {}
        )
        material_hash_valid = bool(
            isinstance(material, dict)
            and isinstance(material.get("review_material_sha256"), str)
            and material["review_material_sha256"] == _material_digest(core)
        )
        try:
            accepted_result = json.loads(accepted["result_json"]) if accepted is not None else None
        except (TypeError, json.JSONDecodeError):
            accepted_result = None
        embedded_result_valid = bool(
            material.get("delivery") != "embedded"
            or material.get("accepted_result") == accepted_result
        )
        return bool(
            accepted is not None and parent is not None and requirement is not None
            and parent["state"] in {"SUCCEEDED", "FAILED", "REJECTED", "BLOCKED"}
            and requirement["review_task_id"] == task.task_id
            and canonical_role(task.role) == requirement["role_id"]
            and material.get("parent_task_id") == parent_id
            and material.get("accepted_result_sha256") == accepted["result_sha256"]
            and material_hash_valid and embedded_result_valid
        )

    def _unresolved_replacement_identity(self, task: Task) -> bool:
        keys = ("replacement_for", "replacement_of", "supersedes_task_id")
        declared = [task.inputs[key] for key in keys if key in task.inputs]
        if not declared:
            return False
        if len(declared) != 1 or not isinstance(declared[0], str) or not declared[0]:
            return True
        original_id = declared[0]
        original = self.store.get(original_id)
        if original is None:
            return True
        if self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accepted_results'"
        ).fetchone() is None:
            return True
        accepted = self.store.conn.execute(
            "SELECT 1 FROM accepted_results WHERE task_id=?", (original_id,)
        ).fetchone()
        if accepted is None:
            return True
        if original["source_issue"] is None:
            return False
        published = self.store.conn.execute(
            "SELECT 1 FROM publication_outbox WHERE task_id=? AND status='PUBLISHED' "
            "AND marker LIKE '<!-- cef-dy-orch-result:v1 %' LIMIT 1", (original_id,)
        ).fetchone()
        return published is None

    def ingest(self, task: Task) -> str:
        if self.store.get(task.task_id) is not None:
            outcome = self.store.ingest(task)
            if outcome == "conflict":
                raise TransitionError(
                    f"task_id {task.task_id} already exists with a different TASK envelope"
                )
            return outcome
        admission_class = classify_admission(task.inputs)
        decision = self.admission_decision(task)
        policy_error: Exception | None = None
        try:
            validate_task_policy(task, self.cfg)
        except Exception as exc:
            policy_error = exc
        # A new ordinary source identity is never persisted while the
        # visibility breaker is closed, including when it is also malformed.
        # The upstream Issue remains the source record and can be reconsidered
        # by a later normal poll after the gate reopens.
        if not decision.allowed and admission_class is AdmissionClass.ORDINARY:
            return "admission_paused"
        if policy_error is not None:
            self.store.ingest(task)
            self.store.transition(task.task_id, State.REJECTED, str(policy_error))
            return "rejected"
        self.store.ingest(task)
        reason = "schema and policy valid" if decision.allowed else (
            f"{decision.visibility_state.value}: {decision.reason}"
        )
        self.store.transition(task.task_id, State.VALIDATED, reason)
        if not decision.allowed:
            self.store.transition(task.task_id, State.BLOCKED, reason)
            return "admission_blocked"
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
        assessment = self.visibility_health()
        for row in self.store.list_state(State.VALIDATED):
            task = self.store.task(row)
            if self.admission_decision(task, assessment).allowed:
                self._route(task)
        for row in self.store.list_state(State.WAITING_DEPENDENCY):
            task = self.store.task(row)
            states = self.store.dependency_states(task)
            if any(value in {State.FAILED.value, State.REJECTED.value, State.BLOCKED.value} for value in states.values()):
                self.store.transition(task.task_id, State.BLOCKED, "dependency terminal failure")
            elif (
                all(value == State.SUCCEEDED.value for value in states.values())
                and self.admission_decision(task, assessment).allowed
            ):
                self.store.transition(task.task_id, State.WAITING_APPROVAL if task.is_llm else State.READY, "dependencies complete")
        for row in self.store.list_state(State.WAITING_APPROVAL, State.WAITING_USER):
            task = self.store.task(row)
            if not task.is_llm:
                continue
            local = bool(row["approved_at"]) or not self.cfg["llm"].get("require_local_approval", True)
            issue = task_has_issue_approval(task, self.cfg)
            if (
                local and issue and self.cfg["llm"].get("dispatch_enabled")
                and self.cfg["mode"] == "pilot"
                and self.admission_decision(task, assessment).allowed
            ):
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
        assessment = self.visibility_health(now_epoch)
        count = 0
        for row in self.store.list_state(State.RUNNING):
            stamp = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")).timestamp()
            if now_epoch - stamp <= int(self.cfg["orphaned_run_after_seconds"]):
                continue
            task = self.store.task(row)
            target = State.WAITING_APPROVAL if task.is_llm else State.READY
            reason = "orphaned RUNNING recovered after restart"
            if not self.admission_decision(task, assessment).allowed:
                target = State.FAILED_RETRYABLE
                reason = "orphan recovered; retry held by visibility admission gate"
            self.store.transition(task.task_id, target, reason, force_recovery=True)
            count += 1
        return count

    def run_ready(self) -> list[dict[str, Any]]:
        results = []
        if self.cfg["mode"] in {"shadow", "dry-run"}:
            return results
        assessment = self.visibility_health()
        admitted = [row for row in self.store.list_state(State.READY)
                    if self.admission_decision(self.store.task(row), assessment).allowed]
        for row in admitted[: int(self.cfg["max_concurrent_workers"])]:
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
        accepted = rejected = duplicates = updated = deferred = manual_changes = 0
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
                    if self.store.get(task.task_id) is not None:
                        self.store.record_issue_snapshot(issue, task.task_id)
                    if outcome == "duplicate": duplicates += 1
                    elif outcome == "metadata_updated": updated += 1
                    elif outcome == "rejected": rejected += 1
                    elif outcome == "admission_paused": deferred += 1
                    else: accepted += 1
                    if issue.state != "open":
                        if self.store.get(task.task_id) is not None:
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
        if deferred:
            # Force the next normal poll to re-read deferred upstream Issues;
            # no local task row is retained while admission is paused.
            self.store.update_source("github", etag=None, backoff_until=0, failures=0)
        self.detect_cycles()
        self.reevaluate_waiting()
        self.recover_orphans()
        self.write_summary()
        return {"status": "unchanged" if unchanged else "ok", "accepted": accepted,
                "rejected": rejected, "deferred": deferred, "duplicates": duplicates,
                "updated": updated, "manual_changes": manual_changes, "llm_calls": 0}

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
        production = (
            self.cfg["mode"] == "pilot"
            and self.cfg["autonomy"]["enabled"]
            and not self.cfg["autonomy"]["plan_only"]
        )
        llm_attempts = 0
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatch_attempts'"
        ).fetchone()
        if table is not None:
            llm_attempts = int(self.store.conn.execute(
                "SELECT count(*) FROM dispatch_attempts WHERE admitted=1 AND lane IN "
                "('AI_BOUNDED_SPECIALIST','WORK_CODEX','LOCAL_OSS_MODEL','NON_WORK_AI')"
            ).fetchone()[0])
        return {
            "schema_version": 1,
            "generated_at": utc_now(),
            "mode": "production" if production else self.cfg["mode"],
            "configured_mode": self.cfg["mode"],
            "authority": "operational_only_not_project_control",
            "llm_dispatch_enabled": bool(self.cfg["llm"]["dispatch_enabled"]),
            "llm_calls": llm_attempts,
            "llm_calls_scope": "durable admitted semantic execution attempts",
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
