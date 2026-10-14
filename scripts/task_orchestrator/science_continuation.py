"""One bounded, reviewed follow-up per result in a delegated science branch.

No new scheduler, scientific authority, GitHub issue, or transport. Enrollment
uses Engine; execution, review and publication use the existing M1b/M2 paths.
Absent/old/unstructured review decisions do not authorize a successor.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess

from .model import Task, utc_now
from .routing import canonical_role, load_registry
from .authoring import preflight_authoring


SCHEMA = """
CREATE TABLE IF NOT EXISTS scientific_continuation_observations (
 task_id TEXT PRIMARY KEY,
 state TEXT NOT NULL,
 detail_json TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scientific_closures (
 parent_task_id TEXT PRIMARY KEY,
 parent_result_sha256 TEXT NOT NULL,
 planner_result_sha256 TEXT NOT NULL,
 canonical_head TEXT NOT NULL,
 decision_json TEXT NOT NULL,
 successor_task_id TEXT UNIQUE,
 state TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
"""


class CanonicalRefreshUnavailable(RuntimeError):
    """The remote canonical identity could not be refreshed this cycle."""


def _git_identity(repo, ref):
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", ref], cwd=repo,
            capture_output=True, text=True, timeout=10, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanonicalRefreshUnavailable(
            "canonical Git identity unavailable"
        ) from exc
    value = proc.stdout.strip()
    if proc.returncode != 0 or len(value) != 40:
        raise CanonicalRefreshUnavailable("canonical Git identity unavailable")
    return value


def refresh_origin_main(repo):
    """Boundedly refresh origin/main immediately before new authoring."""
    try:
        proc = subprocess.run(
            ["git", "fetch", "--no-tags", "origin", "main"], cwd=repo,
            capture_output=True, text=True, timeout=30, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanonicalRefreshUnavailable(
            "canonical Git refresh unavailable"
        ) from exc
    if proc.returncode != 0:
        raise CanonicalRefreshUnavailable("canonical Git refresh unavailable")
    return _git_identity(repo, "refs/remotes/origin/main")


def _fresh_authoring_head(repo):
    try:
        canonical = refresh_origin_main(repo)
        head = _git_identity(repo, "HEAD")
    except CanonicalRefreshUnavailable:
        return None, {
            "state": "WAITING_CANONICAL_REFRESH",
            "reason": "canonical Git refresh unavailable; retry next cycle",
        }
    if head != canonical:
        return None, {
            "state": "WAITING_CANONICAL_HEAD",
            "reason": "local HEAD does not match refreshed origin/main",
        }
    return head, None


def _existing_plan(router, parent, review, parent_result_sha256):
    matches = []
    for row in router.conn.execute(
        "SELECT * FROM tasks WHERE task_id LIKE 'SCI-CLOSURE-PLAN-%' "
        "ORDER BY task_id"
    ):
        task = router.store.task(row)
        if (task.dependencies == (parent.task_id, review.task_id)
                and task.inputs.get("parent_result_sha256")
                == parent_result_sha256
                and task.inputs.get("original_envelope")
                == parent.envelope_dict()):
            matches.append(task)
    if len(matches) > 1:
        raise ValueError("multiple planning identities for parent result")
    return matches[0] if matches else None


def _reserved_descendant(conn, task_id):
    if conn is None:
        return False
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='scientific_closures'"
    ).fetchone()
    if table is None:
        return False
    return conn.execute(
        "SELECT 1 FROM scientific_closures "
        "WHERE successor_task_id=? AND state='ENROLLED'",
        (task_id,),
    ).fetchone() is not None


def delegated(cfg, task, conn=None):
    policy = cfg.get("science_continuation", {})
    return (policy.get("enabled") is True
            and (task.task_id in policy.get("seed_task_ids", [])
                 or _reserved_descendant(conn, task.task_id))
            and task.is_llm and canonical_role(task.role) in {"01", "02", "03", "04"}
            and not task.allowed_paths and not task.expected_artifacts
            and task.inputs.get("review_required") is True
            and task.inputs.get("auto_review_authorized") is True)


def review_instruction(cfg, task, conn=None):
    """Added only when constructing a fresh, exact-result-bound review."""
    if not delegated(cfg, task, conn):
        return {}
    return {"scientific_closure_contract": {
        "decision": "CLOSE, WAITING_USER, or FOLLOW_UP",
        "output": "Exactly one checks entry with sole key scientific_closure",
        "fields": ["decision", "parent_result_sha256", "canonical_head", "rationale", "question"],
        "scope": ("Review the exact parent result. FOLLOW_UP only for one justified "
                  "evidence-only question within the ORIGINAL task purpose and constraints. "
                  "No infrastructure, calculation, raw/holdout access, stage transition, "
                  "exchange activation or authority promotion. Prefer CLOSE when complete; "
                  "WAITING_USER for scientific/strategic choices. question is null unless FOLLOW_UP. "
                  "Use review status PASS only if the review passes. This never makes science ACCEPTED."),
    }}


def authoring_receipt(cfg, successor, parent, review, parent_accepted, review_accepted):
    """Use the existing deterministic 00 contract, not worker-authored envelopes.

    NEW_ISSUE is the existing new-identity *preflight* operation; this driver
    never creates an Issue. The local child publishes back to the seed Issue.
    Explicit local seed delegation is the authority, not a persistent chat.
    """
    request = {
        "schema_version": 1, "operation_type": "NEW_ISSUE",
        "author_role": "00_PROJECT_CONTROL", "canonical_head": successor.canonical_head,
        "issue": {"number": None, "state": "open", "labels": list(successor.labels)},
        "task": successor.envelope_dict(), "existing_binding": None,
        "required_repository_paths": [],
        "dependency_bindings": [{"task_id": task.task_id, "result_sha256": result["result_sha256"],
            "canonical_head": task.canonical_head, "status": "SUCCEEDED"}
            for task, result in ((parent, parent_accepted), (review, review_accepted))],
        "review_binding": None,
        "accepted_state_changes": [{"identity": review.task_id,
            "result_sha256": review_accepted["result_sha256"], "materialization_state": "NOT_STATE_CHANGING",
            "materialization_commit": None, "reason": None}],
        "context_delta_bundle": None,
        "lifecycle": {"disposition": "CURRENT", "target_task_id": successor.task_id,
            "target_envelope_hash": successor.envelope_hash, "successor_task_id": None, "reason": None},
        "project_status": {"project_progress": "IN_PROGRESS", "human_action_required": False,
            "semantic_state": "PROVISIONAL", "design_state": "REVIEWED",
            "implementation_state": "AUTHORIZED", "deployment_state": "NOT_APPLICABLE",
            "canonicalization_state": "NOT_STATE_CHANGING"},
        "execution_context": "LOCAL_DETERMINISTIC", "persistent_chat_role": "00_PROJECT_CONTROL",
        "chatgpt_scheduler_requested": False,
    }
    receipt = preflight_authoring(request, cfg, observed_canonical_head=successor.canonical_head)
    if receipt["status"] != "PREFLIGHT_PASS":
        raise ValueError("scientific successor authoring preflight did not pass")
    return receipt


def planning_task(cfg, parent, review, parent_result, review_result, head):
    identity = ":".join((parent.task_id, parent_result["result_sha256"], review_result["result_sha256"], head))
    task_id = "SCI-CLOSURE-PLAN-" + hashlib.sha256(identity.encode()).hexdigest()[:32].upper()
    return Task(schema_version=1, task_id=task_id, role="00_PROJECT_CONTROL", canonical_head=head,
        task_type="llm_worker", action="semantic_helper", dependencies=(parent.task_id, review.task_id),
        inputs={"resource_requirement": "WORK_REQUIRED", "allowed_lanes": ["WORK_CODEX"],
                "bind_dependency_results": True,
                "purpose": "Independently review the parent and prior review against CURRENT canonical state, then decide bounded closure.",
                "original_envelope": parent.envelope_dict(),
                "parent_result_sha256": parent_result["result_sha256"],
                **review_instruction(cfg, parent)},
        allowed_paths=(), expected_artifacts=(), timeout_seconds=min(900, parent.timeout_seconds),
        stop_condition="Return PASS only for a justified within-scope closure. No file changes, scientific execution, authority promotion or infrastructure work.",
        source_issue=parent.source_issue, labels=parent.labels)


def reconcile(router):
    cfg, conn = router.cfg, router.conn
    if not cfg.get("science_continuation", {}).get("enabled"):
        return []
    conn.executescript(SCHEMA)
    # Descendants are discovered exclusively from durable controller reservations,
    # never from a remote task's claim to be a scientific successor.
    eligible = set(cfg["science_continuation"]["seed_task_ids"])
    edges = list(conn.execute("SELECT parent_task_id,successor_task_id FROM scientific_closures WHERE state='ENROLLED'"))
    while True:
        expanded = eligible | {r["successor_task_id"] for r in edges if r["parent_task_id"] in eligible}
        if expanded == eligible:
            break
        eligible = expanded
    scoped_cfg = {**cfg, "science_continuation": {"enabled": True, "seed_task_ids": sorted(eligible)}}
    repo = Path(cfg["repository_root"])
    outcomes = []
    for task_id in sorted(eligible):
        row = router.store.get(task_id)
        if row is None:
            continue
        task = router.store.task(row)
        if not delegated(scoped_cfg, task):
            outcomes.append({"task_id": task_id, "state": "WAITING_USER",
                             "reason": "scientific continuation scope invalid"})
            continue
        relation = conn.execute("SELECT * FROM review_requirements WHERE parent_task_id=?", (task_id,)).fetchone()
        if relation is None or not relation["review_task_id"]:
            continue
        review_row = router.store.get(relation["review_task_id"])
        if row["state"] != "SUCCEEDED" or review_row is None or review_row["state"] != "SUCCEEDED":
            continue
        review = router.store.task(review_row)
        if (canonical_role(review.role) != "00"
                or not router.verify_review_material(review)[0]):
            outcomes.append({"task_id": task_id, "state": "WAITING_USER", "reason": "review binding invalid"})
            continue
        try:
            parent_accepted, _ = router._accepted_review_result(task)
            review_accepted, review_result = router._accepted_review_result(review)
            if review_result["semantic_verdict"] != "PASS":
                raise ValueError("independent parent review has not passed")
            plan = _existing_plan(
                router, task, review, parent_accepted["result_sha256"]
            )
            if plan is None:
                head, refresh_wait = _fresh_authoring_head(repo)
                if refresh_wait is not None:
                    outcomes.append({"task_id": task_id, **refresh_wait})
                    continue
                # A fresh bounded planner revalidates historical accepted inputs
                # against the current HEAD; never require rewriting parent history.
                plan = planning_task(
                    scoped_cfg, task, review, parent_accepted,
                    review_accepted, head,
                )
                plan_receipt = authoring_receipt(
                    cfg, plan, task, review, parent_accepted, review_accepted
                )
                outcome = router.engine.ingest(plan)
                if outcome not in {"created", "duplicate", "metadata_updated"}:
                    outcomes.append({"task_id": task_id, "state": outcome,
                                     "reason": "planner admission"})
                    continue
                router.store.put_authoring_receipt(plan_receipt)
                router._record_route(
                    plan,
                    load_registry(Path(cfg["routing"]["bootstrap_path"])),
                    router.sync_lanes(),
                )
            head = plan.canonical_head
            previous = conn.execute("SELECT * FROM scientific_closures WHERE parent_task_id=?", (task_id,)).fetchone()
            if previous is not None and previous["canonical_head"] != head:
                outcomes.append({"task_id": task_id, "state": "WAITING_USER", "reason": "existing closure bound to earlier HEAD"})
                continue
            if router.store.get(plan.task_id)["state"] != "SUCCEEDED":
                outcomes.append({"task_id": task_id, "state": "WAITING_PLAN", "planner_task_id": plan.task_id})
                continue
            plan_accepted, result = router._accepted_review_result(plan)
            entries = [x["scientific_closure"] for x in result["checks"]
                       if isinstance(x, dict) and set(x) == {"scientific_closure"}]
            if result["semantic_verdict"] != "PASS" or len(entries) != 1:
                raise ValueError("no single passing structured closure")
            decision = entries[0]
            if (not isinstance(decision, dict) or set(decision) != {
                    "decision", "parent_result_sha256", "canonical_head", "rationale", "question"}
                    or decision["parent_result_sha256"] != parent_accepted["result_sha256"]
                    or decision["canonical_head"] != head
                    or decision["decision"] not in {"CLOSE", "WAITING_USER", "FOLLOW_UP"}
                    or not isinstance(decision["rationale"], str) or not decision["rationale"].strip()
                    or len(decision["rationale"]) > 2000):
                raise ValueError("invalid closure identity or decision")
            follow = decision["decision"] == "FOLLOW_UP"
            if follow:
                if not isinstance(decision["question"], str) or not 1 <= len(decision["question"].strip()) <= 2000:
                    raise ValueError("invalid bounded question")
            elif decision["question"] is not None:
                raise ValueError("non-follow-up cannot contain question")
        except (ValueError, KeyError, TypeError) as exc:
            outcomes.append({"task_id": task_id, "state": "WAITING_USER", "reason": str(exc)})
            continue
        decision_json = json.dumps(decision, sort_keys=True, separators=(",", ":"))
        successor_id = ("SCI-FOLLOWUP-" + hashlib.sha256(
            (task_id + ":" + parent_accepted["result_sha256"] + ":" + head + ":" + decision_json).encode()).hexdigest()[:32].upper()) if follow else None
        identity = (task_id, parent_accepted["result_sha256"], plan_accepted["result_sha256"],
                    head, decision_json, successor_id)
        inserted = conn.execute("INSERT OR IGNORE INTO scientific_closures VALUES(?,?,?,?,?,?,?,?)",
                     (*identity, "RESERVED" if follow else decision["decision"], utc_now())).rowcount
        if inserted:
            router.store.append_event(task_id, "SCIENTIFIC_CLOSURE_RECORDED", None, decision["decision"],
                                      {"parent_result_sha256": parent_accepted["result_sha256"],
                                       "planner_result_sha256": plan_accepted["result_sha256"],
                                       "successor_task_id": successor_id, "canonical_head": head})
        saved = conn.execute("SELECT * FROM scientific_closures WHERE parent_task_id=?", (task_id,)).fetchone()
        if tuple(saved)[:6] != identity:
            outcomes.append({"task_id": task_id, "state": "WAITING_USER", "reason": "closure identity conflict"})
            continue
        state = saved["state"]
        if follow:
            # No arbitrary worker-authored envelope. Inherit the original bounded
            # scope; bind both original and review as durable dependencies.
            inputs = {k: v for k, v in task.inputs.items() if k in {
                "purpose", "constraints", "canonical_inputs", "scientific_mode",
                "resource_requirement", "allowed_lanes", "required_output"}}
            # Preserve the entire immutable seed scope, including constraints
            # carried only by its stop condition or nonstandard input fields.
            # Descendants retain that same root rather than nesting envelopes.
            root_envelope = (task.envelope_dict() if task_id in cfg["science_continuation"]["seed_task_ids"]
                             else task.inputs["authorized_root_envelope"])
            inputs.update(bounded_follow_up=decision, review_required=True,
                          auto_review_authorized=True, review_role="00_PROJECT_CONTROL",
                          bind_dependency_results=True, scientific_status="PROVISIONAL",
                          authorized_root_envelope=root_envelope,
                          parent_stop_condition=task.stop_condition)
            successor = replace(task, task_id=successor_id, canonical_head=head, dependencies=(task_id, plan.task_id),
                                inputs=inputs, stop_condition=(
                                    "Obey the complete authorized_root_envelope (including its stop_condition and all inputs) "
                                    "and parent_stop_condition. Answer only the reviewed follow-up within that inherited scope, then stop. "
                                    "No infrastructure, raw/holdout, scientific execution, stage transition, "
                                    "exchange activation or ACCEPTED promotion."))
            existing = router.store.get(successor_id)
            if existing is None:
                fresh_head, refresh_wait = _fresh_authoring_head(repo)
                if refresh_wait is not None:
                    outcomes.append({"task_id": task_id, **refresh_wait})
                    continue
                if fresh_head != head:
                    outcomes.append({
                        "task_id": task_id,
                        "state": "WAITING_CANONICAL_HEAD",
                        "reason": "planner HEAD no longer matches refreshed origin/main",
                    })
                    continue
            try:
                receipt = authoring_receipt(cfg, successor, task, plan, parent_accepted, plan_accepted)
            except ValueError as exc:
                outcomes.append({"task_id": task_id, "state": "WAITING_USER", "reason": str(exc)})
                continue
            if existing is not None and router.store.task(existing).payload_hash != successor.payload_hash:
                state = "CONFLICT"
            else:
                outcome = router.engine.ingest(successor)
                state = "ENROLLED" if outcome in {"created", "duplicate", "metadata_updated"} else outcome
                if state == "ENROLLED":
                    router.store.put_authoring_receipt(receipt)
                    router._record_route(successor, load_registry(Path(cfg["routing"]["bootstrap_path"])), router.sync_lanes())
            conn.execute("UPDATE scientific_closures SET state=?,updated_at=? WHERE parent_task_id=?",
                         (state, utc_now(), task_id))
        outcomes.append({"task_id": task_id, "state": state, "successor_task_id": successor_id})
    for outcome in outcomes:
        detail = json.dumps(outcome, sort_keys=True, ensure_ascii=False)
        previous = conn.execute("SELECT detail_json FROM scientific_continuation_observations WHERE task_id=?",
                                (outcome["task_id"],)).fetchone()
        if previous is None or previous[0] != detail:
            conn.execute("INSERT INTO scientific_continuation_observations VALUES(?,?,?,?) "
                         "ON CONFLICT(task_id) DO UPDATE SET state=excluded.state,detail_json=excluded.detail_json,updated_at=excluded.updated_at",
                         (outcome["task_id"], outcome["state"], detail, utc_now()))
            router.store.append_event(outcome["task_id"], "SCIENTIFIC_CONTINUATION_OBSERVED", None,
                                      outcome["state"], outcome)
    return outcomes
