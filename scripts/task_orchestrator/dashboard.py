"""Localhost-only, read-only operator dashboard.

The HTML view is a human-facing projection. Exact finite-state-machine values,
timestamps, hashes and operational tables remain in diagnostics and the JSON API.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any
from urllib.parse import urlsplit

from .authoring import lifecycle_receipt_for_task, validate_preflight_receipt
from .model import ValidationError


GRAPH_NODE_LIMIT = 24
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "REJECTED", "BLOCKED"}
ATTENTION_STATES = {"WAITING_USER", "WAITING_APPROVAL", "BLOCKED", "FAILED", "REJECTED"}
STATE_LABELS = {
    "RECEIVED": "Received", "VALIDATED": "Validated", "READY": "Ready",
    "RUNNING": "Running", "WAITING_USER": "Needs your input",
    "WAITING_APPROVAL": "Needs approval", "WAITING_DEPENDENCY": "Waiting for dependency",
    "WAITING_RESOURCE": "Waiting for resource", "QUOTA_WAIT": "Waiting for quota",
    "PAUSED_QUOTA": "Paused for quota", "FAILED_RETRYABLE": "Retry pending",
    "SUCCEEDED": "Completed", "BLOCKED": "Blocked", "FAILED": "Failed",
    "REJECTED": "Rejected",
}
ROLE_LABELS = {
    "00": "Project Control", "00_PROJECT_CONTROL": "Project Control",
    "01": "Literature & Physics", "01_LITERATURE": "Literature & Physics",
    "01_LITERATURE_PHYSICS": "Literature & Physics",
    "02": "TAIPAN Data Reduction", "02_TAIPAN_DATA_REDUCTION": "TAIPAN Data Reduction",
    "03": "CEF Modelling & Fit Design", "03_CEF": "CEF Modelling & Fit Design",
    "03_CEF_MODELLING_FIT_DESIGN": "CEF Modelling & Fit Design",
    "04": "Structure & Conventions", "04_STRUCTURE": "Structure & Conventions",
    "04_STRUCTURE_CONVENTIONS": "Structure & Conventions",
    "07": "Infrastructure", "07_INFRASTRUCTURE": "Infrastructure",
    "07_RESEARCH_SOFTWARE_INFRASTRUCTURE": "Infrastructure",
}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def _utc_age(value: str | None, now: datetime | None = None) -> float | None:
    stamp = _parse_time(value)
    if stamp is None:
        return None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (reference.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()


def human_time(value: str | None, now: datetime | None = None) -> str:
    """Return a compact local-time label while leaving stored timestamps untouched."""
    stamp = _parse_time(value)
    if stamp is None:
        return "Unknown"
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    local = stamp.astimezone()
    local_now = reference.astimezone(local.tzinfo)
    seconds = int((local_now - local).total_seconds())
    if seconds < 0:
        return "Future timestamp"
    if seconds < 15:
        return "just now"
    if seconds < 60:
        return f"{seconds} sec ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if local.date() == local_now.date() and seconds < 6 * 3600:
        return f"{seconds // 3600} h ago"
    if local.date() == local_now.date():
        return local.strftime("%H:%M")
    if (local_now.date() - local.date()).days == 1:
        return "yesterday " + local.strftime("%H:%M")
    return local.strftime("%b %d, %H:%M")


def _humanize_identifier(value: str) -> str:
    words = re.sub(r"[_-]+", " ", value).strip().split()
    if words and words[0].isdigit():
        words = words[1:]
    return " ".join(word if word.isdigit() else word.capitalize() for word in words) or "Unknown"


def human_state(value: str | None) -> str:
    raw = str(value or "UNKNOWN")
    return STATE_LABELS.get(raw, _humanize_identifier(raw))


def human_role(value: str | None) -> str:
    raw = str(value or "UNKNOWN")
    return ROLE_LABELS.get(raw, _humanize_identifier(raw))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def open_readonly(path: Path) -> sqlite3.Connection:
    # A live WAL database must not use immutable=1: immutable readers can miss
    # committed schema/data that still exists only in the WAL file.
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True,
            timeout=3, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _task_title(task: dict[str, Any]) -> str:
    explicit = task.get("issue_title") or task.get("title")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    parts = str(task.get("task_id", "Task")).split("-")
    while parts and parts[-1].isdigit():
        parts.pop()
    return " ".join(part if part.isupper() and len(part) <= 8 else part.capitalize() for part in parts) or "Task"


def _next_condition(task: dict[str, Any]) -> str:
    state = task["state"]
    reason = str(task.get("reason") or "").strip()
    dependencies = task.get("dependencies") or []
    if state == "WAITING_USER":
        return reason or "Your input is required before work can continue."
    if state == "WAITING_APPROVAL":
        return reason or "Explicit approval is required."
    if state == "WAITING_DEPENDENCY":
        return "Waiting for " + ", ".join(map(str, dependencies)) if dependencies else (reason or "Waiting for a dependency.")
    if state in {"WAITING_RESOURCE", "QUOTA_WAIT", "PAUSED_QUOTA"}:
        return reason or "Waiting for the required execution resource."
    if state == "RUNNING":
        return reason or "Work is in progress."
    if state in {"RECEIVED", "VALIDATED", "READY"}:
        return reason or "Ready for the next controller cycle."
    return reason or human_state(state)


def _historical_non_actionable(task: dict[str, Any]) -> bool:
    # Only the validated, append-only Project-Control authoring receipt is
    # authoritative.  Issue closure, payload hints, and free text remain
    # insufficient to hide a present failure.
    return task.get("lifecycle_disposition") in {
        "SUPERSEDED", "RETIRED", "CLOSED_HISTORICAL",
    }


def _component(label: str, state: str, detail: str, *, material: bool = True,
               observed_at: str | None = None) -> dict[str, Any]:
    return {
        "label": label, "state": state, "human_state": _humanize_identifier(state),
        "detail": detail, "material": material, "observed_at": observed_at,
    }


def _overall_health(components: dict[str, dict[str, Any]]) -> str:
    states = {item["state"] for item in components.values() if item.get("material", True)}
    if states & {"FAILED", "DEGRADED", "UNAVAILABLE"}:
        return "DEGRADED"
    if "STALE" in states:
        return "STALE"
    if not states or "UNKNOWN" in states:
        return "UNKNOWN"
    if "WAITING" in states:
        return "WAITING"
    return "HEALTHY"


def _observation_state(value: str | None, now: datetime,
                       stale_after_seconds: int) -> tuple[str, float | None]:
    age = _utc_age(value, now)
    if age is None or age < 0:
        return "UNKNOWN", age
    if age > stale_after_seconds:
        return "STALE", age
    return "FRESH", age


def _resource_component(tasks: list[dict[str, Any]], lanes: list[dict[str, Any]],
                        ai_lane: dict[str, Any], now: datetime,
                        stale_after_seconds: int) -> dict[str, Any]:
    if any(task["state"] in {"WAITING_RESOURCE", "QUOTA_WAIT", "PAUSED_QUOTA"} for task in tasks):
        return _component("Worker resources", "WAITING", "One or more tasks are waiting for an execution resource.")
    local = next((lane for lane in lanes if lane.get("lane_id") == "LOCAL_DETERMINISTIC"), None)
    if local:
        freshness, _ = _observation_state(local.get("updated_at"), now, stale_after_seconds)
        if freshness == "UNKNOWN":
            return _component("Worker resources", "UNKNOWN", "The deterministic lane observation time is missing, invalid, or in the future.", observed_at=local.get("updated_at"))
        if freshness == "STALE":
            return _component("Worker resources", "STALE", "The deterministic lane observation is stale.", observed_at=local.get("updated_at"))
        state = str(local.get("availability_state", "UNKNOWN"))
        if state == "AVAILABLE":
            return _component("Worker resources", "HEALTHY", "The deterministic execution lane is available.", observed_at=local.get("updated_at"))
        if state in {"FAILED", "UNAVAILABLE"}:
            return _component("Worker resources", "DEGRADED", f"The deterministic lane reports {state.lower()}.", observed_at=local.get("updated_at"))
        return _component("Worker resources", "UNKNOWN", f"Deterministic lane state: {state}.", observed_at=local.get("updated_at"))
    if ai_lane:
        freshness, _ = _observation_state(ai_lane.get("updated_at"), now, stale_after_seconds)
        if freshness == "UNKNOWN":
            return _component("Worker resources", "UNKNOWN", "The AI lane observation time is missing, invalid, or in the future.", observed_at=ai_lane.get("updated_at"))
        if freshness == "STALE":
            return _component("Worker resources", "STALE", "The AI lane observation is stale.", observed_at=ai_lane.get("updated_at"))
        state = str(ai_lane.get("state", "UNKNOWN"))
        if state in {"QUOTA_WAIT", "WAITING", "PAUSED_QUOTA"}:
            return _component("Worker resources", "WAITING", "A worker lane is waiting for quota or approval.", observed_at=ai_lane.get("updated_at"))
    return _component("Worker resources", "UNKNOWN", "No explicit current worker-lane observation is available.")


def _telegram_projection(controller: dict[str, Any] | None, now: datetime,
                         stale_after_seconds: int) -> dict[str, Any]:
    gateway = (controller or {}).get("TELEGRAM_GATEWAY")
    if not isinstance(gateway, dict):
        return {"state": "NOT_ACTIVATED", "label": "Not activated", "detail": "No production gateway state is available.", "observed_at": None}
    observed_at = gateway.get("observed_at")
    age = _utc_age(observed_at, now)
    if age is None:
        return {"state": "UNKNOWN", "label": "Unknown", "detail": "Gateway state lacks an explicit observation time.", "observed_at": observed_at}
    if age < 0:
        return {"state": "UNKNOWN", "label": "Unknown", "detail": "Gateway observation time is in the future; check the clock.", "observed_at": observed_at}
    if age > stale_after_seconds:
        return {"state": "STALE", "label": "Stale", "detail": "The production gateway observation is stale.", "observed_at": observed_at}
    state = str(gateway.get("state", "UNKNOWN")).upper()
    labels = {"HEALTHY": "Operational", "DEGRADED": "Degraded", "STALE": "Stale", "UNAVAILABLE": "Unavailable", "UNKNOWN": "Unknown"}
    return {"state": state, "label": labels.get(state, "Unknown"), "detail": str(gateway.get("detail") or "Production gateway observation."), "observed_at": observed_at}


def _task_graph(tasks: list[dict[str, Any]], limit: int = GRAPH_NODE_LIMIT) -> dict[str, Any]:
    active = [task for task in tasks if (
        task["state"] not in TERMINAL_STATES and not _historical_non_actionable(task)
    )]
    recent_complete = [task for task in tasks if (
        task["state"] == "SUCCEEDED" and not _historical_non_actionable(task)
    )]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def admit(task: dict[str, Any]) -> None:
        if task["task_id"] not in seen and len(selected) < limit:
            selected.append(task)
            seen.add(task["task_id"])

    for task in active:
        admit(task)
    by_id = {task["task_id"]: task for task in tasks}
    for task in list(selected):
        for dependency in task.get("dependencies") or []:
            if dependency in by_id:
                admit(by_id[dependency])
    for task in recent_complete:
        admit(task)
        if len(selected) >= min(limit, max(8, len(active))):
            break
    nodes = [{
        "task_id": task["task_id"], "title": _task_title(task), "state": task["state"],
        "human_state": human_state(task["state"]), "role": task.get("role"),
        "human_role": human_role(task.get("role")), "updated_at": task.get("updated_at"),
        "user_action_required": bool(task.get("user_action_required")),
    } for task in selected]
    edges = []
    for task in selected:
        for dependency in task.get("dependencies") or []:
            if dependency in seen:
                edges.append({"from": dependency, "to": task["task_id"]})
    return {"nodes": nodes, "edges": edges, "limit": limit, "truncated": len(tasks) > len(selected)}


def snapshot(cfg: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    reference = now or datetime.now(timezone.utc)
    database = Path(cfg["state_dir"]) / "state.sqlite3"
    with open_readonly(database) as conn:
        integrity_row = conn.execute("PRAGMA quick_check(1)").fetchone()
        sqlite_ok = bool(integrity_row and integrity_row[0] == "ok")
        issue_rows = [dict(row) for row in conn.execute(
            "SELECT issue_number,title,issue_state FROM issue_snapshots"
        )] if _table_exists(conn, "issue_snapshots") else []
        issues = {row["issue_number"]: row for row in issue_rows}
        tasks = [dict(row) for row in conn.execute(
            "SELECT task_id,envelope_hash,state,reason,attempt,source_issue,created_at,updated_at,payload_json "
            "FROM tasks ORDER BY updated_at DESC,task_id"
        )]
        authoring_receipts: dict[str, dict[str, Any]] = {}
        if _table_exists(conn, "authoring_receipts"):
            for row in conn.execute(
                "SELECT a.task_id,a.receipt_json FROM authoring_receipts a "
                "WHERE a.rowid=(SELECT max(b.rowid) FROM authoring_receipts b "
                "WHERE b.task_id=a.task_id)"
            ):
                try:
                    value = validate_preflight_receipt(
                        json.loads(row["receipt_json"]), authorizing=True,
                        require_current_manifest=False,
                    )
                except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                    continue
                authoring_receipts[row["task_id"]] = value
        for task in tasks:
            payload = json.loads(task.pop("payload_json"))
            task["role"] = payload.get("role")
            task["task_type"] = payload.get("task_type")
            task["dependencies"] = payload.get("dependencies", [])
            task["inputs"] = payload.get("inputs", {})
            issue = issues.get(task.get("source_issue"), {})
            task["issue_title"] = issue.get("title")
            task["issue_state"] = issue.get("issue_state")
            task["human_state"] = human_state(task["state"])
            task["human_role"] = human_role(task.get("role"))
            task["title"] = _task_title(task)
            task["next_condition"] = _next_condition(task)
            receipt = lifecycle_receipt_for_task(
                authoring_receipts.get(task["task_id"]),
                task_id=task["task_id"], envelope_hash=task["envelope_hash"],
            )
            task["fsm_state"] = task["state"]
            task["authoring_receipt_sha256"] = receipt.get("receipt_sha256") if receipt else None
            task["lifecycle_disposition"] = receipt.get("lifecycle_disposition", "UNRECORDED") if receipt else "UNRECORDED"
            task["project_progress"] = receipt.get("project_progress", "UNKNOWN") if receipt else "UNKNOWN"
            task["human_action_required"] = bool(receipt.get("human_action_required")) if receipt else False
            for facet in (
                "semantic_state", "design_state", "implementation_state",
                "deployment_state", "canonicalization_state",
            ):
                task[facet] = receipt.get(facet, "UNKNOWN") if receipt else "UNKNOWN"
            task["user_action_required"] = (
                task["state"] in {"WAITING_USER", "WAITING_APPROVAL"}
                or task["human_action_required"]
            ) and not _historical_non_actionable(task)
        events = [dict(row) for row in conn.execute(
            "SELECT event_id,task_id,event_type,old_state,new_state,detail_json,created_at "
            "FROM events ORDER BY event_id DESC LIMIT ?",
            (int(cfg["dashboard"]["recent_events"]),),
        )]
        leases = [dict(row) for row in conn.execute(
            "SELECT * FROM worker_leases ORDER BY claimed_at DESC"
        )] if _table_exists(conn, "worker_leases") else []
        lane = dict(conn.execute("SELECT * FROM ai_lane WHERE singleton=1").fetchone()) \
            if _table_exists(conn, "ai_lane") else {"state": "UNKNOWN"}
        routes = [dict(row) for row in conn.execute(
            "SELECT * FROM task_routes ORDER BY updated_at DESC,task_id"
        )] if _table_exists(conn, "task_routes") else []
        resource_lanes = [dict(row) for row in conn.execute(
            "SELECT * FROM resource_lanes ORDER BY cost_priority,lane_id"
        )] if _table_exists(conn, "resource_lanes") else []
        reviews = [dict(row) for row in conn.execute(
            "SELECT * FROM review_requirements ORDER BY updated_at DESC,parent_task_id"
        )] if _table_exists(conn, "review_requirements") else []
        results = [dict(row) for row in conn.execute(
            "SELECT task_id,attempt_id,result_sha256,accepted_at FROM accepted_results ORDER BY accepted_at DESC"
        )] if _table_exists(conn, "accepted_results") else []
        dependency_bundles = [dict(row) for row in conn.execute(
            "SELECT task_id,bundle_sha256,dependency_count,created_at,updated_at "
            "FROM dependency_result_bundles ORDER BY updated_at DESC,task_id"
        )] if _table_exists(conn, "dependency_result_bundles") else []
        publications = [dict(row) for row in conn.execute(
            "SELECT publication_id,task_id,result_sha256,target,status,attempts,reason,remote_id,created_at,updated_at "
            "FROM publication_outbox ORDER BY updated_at DESC,publication_id"
        )] if _table_exists(conn, "publication_outbox") else []
        controller = None
        controller_updated = None
        if _table_exists(conn, "controller_state"):
            row = conn.execute(
                "SELECT state_json,updated_at FROM controller_state ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row:
                controller, controller_updated = json.loads(row["state_json"]), row["updated_at"]

    repo = Path(cfg["repository_root"])
    canonical_head = _git(repo, "rev-parse", "refs/remotes/origin/main")
    local_head = _git(repo, "rev-parse", "HEAD")
    stale_after = int(cfg["dashboard"]["stale_after_seconds"])
    age = _utc_age(controller_updated, reference)
    if age is None:
        heartbeat = _component("Orchestrator", "UNKNOWN", "No controller heartbeat has been observed.")
    elif age < 0:
        heartbeat = _component("Orchestrator", "UNKNOWN", "The controller heartbeat is in the future; check the clock.", observed_at=controller_updated)
    elif age > stale_after:
        heartbeat = _component("Orchestrator", "STALE", "The last controller heartbeat is older than the configured limit.", observed_at=controller_updated)
    else:
        heartbeat = _component("Orchestrator", "HEALTHY", "Controller heartbeat is fresh.", observed_at=controller_updated)
    if canonical_head is None or local_head is None:
        repository = _component("Repository", "UNKNOWN", "Canonical or local Git identity is unavailable.")
        sync = {"state": "UNKNOWN", "label": "Repository state unknown", "short_sha": None}
    elif canonical_head == local_head:
        repository = _component("Repository", "HEALTHY", "Local HEAD matches local origin/main.")
        sync = {"state": "SYNCHRONIZED", "label": "Local HEAD matches local origin/main", "short_sha": local_head[:7]}
    else:
        repository = _component("Repository", "DEGRADED", "Local HEAD differs from local origin/main.")
        sync = {"state": "MISMATCH", "label": "Local HEAD differs from local origin/main", "short_sha": local_head[:7]}
    sqlite_health = _component("Operational database", "HEALTHY" if sqlite_ok else "FAILED", "SQLite quick check passed." if sqlite_ok else "SQLite quick check failed.")
    resources = _resource_component(tasks, resource_lanes, lane, reference, stale_after)
    publishing_enabled = bool(cfg.get("publishing", {}).get("enabled"))
    publication = _component(
        "Publication transport", "UNKNOWN" if publishing_enabled else "UNAVAILABLE",
        "No fresh live transport observation is available." if publishing_enabled else "Live publication is disabled; previews remain local.",
        material=publishing_enabled,
    )
    components = {"orchestrator": heartbeat, "repository": repository, "sqlite": sqlite_health,
                  "resources": resources, "publication": publication}
    health = _overall_health(components)
    attention = [task for task in tasks if (
        task["state"] in ATTENTION_STATES or task["human_action_required"]
    ) and not _historical_non_actionable(task)]
    blockers = [task for task in tasks if (
        task["state"] in {"BLOCKED", "FAILED", "REJECTED"}
        and not _historical_non_actionable(task)
    )]
    active = [task for task in tasks if (
        not _historical_non_actionable(task)
        and (
            task["state"] not in TERMINAL_STATES
            or task["project_progress"] in {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "DEFERRED"}
        )
    )]
    latest = events[0] if events else None
    next_action = (controller or {}).get("NEXT_EXACT_ACTION")
    if not next_action and active:
        next_action = active[0]["next_condition"]
    operator_progress = {
        "CURRENT": [f"{task['task_id']}: {task['state']}" for task in active[:8]] or ["idle"],
        "LAST_PROGRESS": f"{latest['created_at']} {latest['task_id'] or '-'} {latest['event_type']}" if latest else "no durable activity",
        "NEXT_ACTION": next_action or "next controller cycle",
        "NEEDS_USER": [f"{task['task_id']}: {task['reason']}" for task in attention[:8]],
    }
    recent_progress = [{**event, "human_event": _humanize_identifier(event["event_type"]),
                        "human_time": human_time(event["created_at"], reference)}
                       for event in events if event.get("event_type") != "POLL_UNCHANGED"][:8]
    return {
        # Keep the additive JSON diagnostic contract on schema v1. Dashboard v2
        # changes presentation and adds fields without removing v1 keys.
        "schema_version": 1,
        "generated_at": reference.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dashboard": {"read_only": True, "health": health, "human_health": _humanize_identifier(health),
                      "components": components, "controller_age_seconds": age,
                      "source_of_truth": str(database)},
        "orchestrator": controller or {"CURRENT_PHASE": "UNKNOWN"},
        "git": {"canonical_head": canonical_head, "local_head": local_head,
                "branch": _git(repo, "branch", "--show-current"), "projection": sync},
        "ai_lane": lane,
        "quota_windows": cfg["visibility"]["quota"],
        "quota_evidence": {"main_page_visible": False, "reason": "Configuration projections are not treated as observed quota telemetry."},
        "telegram": _telegram_projection(controller, reference, stale_after),
        "tasks": tasks, "workers": leases, "routes": routes, "resource_lanes": resource_lanes,
        "reviews": reviews, "results": results, "dependency_bundles": dependency_bundles,
        "publications": publications, "operator_progress": operator_progress,
        "current_work": active, "attention": attention, "blockers": blockers,
        "recent_progress": recent_progress, "task_graph": _task_graph(tasks),
        "recent_activity": events,
    }


def _table(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    head = "".join(f"<th>{html.escape(name)}</th>" for name in columns)
    body = []
    for row in rows:
        cells = []
        for name in columns:
            value = row.get(name, "")
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            cells.append(f"<td>{html.escape(str(value if value is not None else ''))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    empty = f'<tr><td colspan="{len(columns)}" class="muted">None</td></tr>' if not body else ""
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body) or empty}</tbody></table>"


def _time_html(value: str | None, now: datetime) -> str:
    exact = html.escape(str(value or "Unknown"), quote=True)
    return f'<time title="{exact}">{html.escape(human_time(value, now))}</time>'


def _task_map_svg(graph: dict[str, Any]) -> str:
    nodes = graph["nodes"]
    if not nodes:
        return '<p class="muted">No current or recent task relationships.</p>'
    roles = list(dict.fromkeys(node["human_role"] for node in nodes))
    columns = {role: index for index, role in enumerate(roles)}
    positions: dict[str, tuple[int, int]] = {}
    row_by_role = {role: 0 for role in roles}
    for node in nodes:
        role = node["human_role"]
        positions[node["task_id"]] = (30 + columns[role] * 210, 65 + row_by_role[role] * 78)
        row_by_role[role] += 1
    width = max(420, 60 + len(roles) * 210)
    height = max(160, 100 + max(row_by_role.values()) * 78)
    edge_svg = []
    for edge in graph["edges"]:
        if edge["from"] not in positions or edge["to"] not in positions:
            continue
        x1, y1 = positions[edge["from"]]
        x2, y2 = positions[edge["to"]]
        edge_svg.append(f'<path class="edge" marker-end="url(#dependency-arrow)" d="M{x1 + 174},{y1 + 24} C{x1 + 190},{y1 + 24} {x2 - 16},{y2 + 24} {x2},{y2 + 24}"/>')
    node_svg = []
    symbols = {"RUNNING": "▶", "SUCCEEDED": "✓", "WAITING_USER": "!", "WAITING_APPROVAL": "!", "BLOCKED": "×", "FAILED": "×"}
    for node in nodes:
        x, y = positions[node["task_id"]]
        css = "node " + ("current" if node["state"] == "RUNNING" else "needs" if node["user_action_required"] or node["state"] in {"BLOCKED", "FAILED"} else "done" if node["state"] == "SUCCEEDED" else "waiting")
        title = html.escape(node["title"][:25])
        state = html.escape(node["human_state"][:24])
        exact = html.escape(node["task_id"], quote=True)
        symbol = symbols.get(node["state"], "○")
        node_svg.append(f'<g class="{css}" transform="translate({x},{y})"><title>{exact}</title>'
                        f'<rect width="174" height="48" rx="8"/><text x="9" y="19">{symbol} {title}</text>'
                        f'<text class="node-state" x="9" y="37">{state}</text></g>')
    headers = "".join(f'<text class="lane-label" x="{30 + index * 210}" y="28">{html.escape(role)}</text>'
                      for role, index in columns.items())
    note = '<p class="muted">Map is capped to current work and recent dependencies.</p>' if graph["truncated"] else ""
    marker = '<defs><marker id="dependency-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>'
    return f'{note}<div class="map-scroll"><svg class="task-map" role="img" aria-labelledby="task-map-title" viewBox="0 0 {width} {height}"><title id="task-map-title">Dependencies point toward dependent tasks</title>{marker}{headers}{"".join(edge_svg)}{"".join(node_svg)}</svg></div>'


def _current_work_html(tasks: list[dict[str, Any]], now: datetime) -> str:
    if not tasks:
        return '<p class="empty">No task is currently active.</p>'
    cards = []
    for task in tasks[:12]:
        action = '<strong class="needs-user">User action required</strong>' if task["user_action_required"] else ""
        progress = human_state(task["project_progress"]) if task["project_progress"] != "UNKNOWN" else "Unknown"
        cards.append('<article class="work-item">'
                     f'<div><h3>{html.escape(task["title"])}</h3><p>{html.escape(task["human_role"])} · '
                     f'<strong>{html.escape(task["human_state"])}</strong> · updated {_time_html(task["updated_at"], now)}</p>'
                     f'<p>Project progress: <strong>{html.escape(progress)}</strong> · '
                     f'canonicalization: {html.escape(human_state(task["canonicalization_state"]))}</p></div>'
                     f'<p>{html.escape(task["next_condition"])}</p>{action}'
                     f'<small class="mono">{html.escape(task["task_id"])}</small></article>')
    return "".join(cards)


def render(data: dict[str, Any], *, now: datetime | None = None) -> bytes:
    reference = now or _parse_time(data.get("generated_at")) or datetime.now(timezone.utc)
    dashboard, git = data["dashboard"], data["git"]
    sync = git["projection"]
    health_cards = "".join(
        f'<div class="card component {html.escape(component["state"].lower())}"><b>{html.escape(component["label"])}</b>'
        f'<span>{html.escape(component["human_state"])}</span><small>{html.escape(component["detail"])}</small></div>'
        for component in dashboard["components"].values())
    attention_html = "".join(
        f'<article class="attention-item"><strong>{html.escape(task["title"])}</strong> — '
        f'{html.escape(task["human_state"])}<p>{html.escape(task["next_condition"])}</p>'
        f'<small class="mono">{html.escape(task["task_id"])}</small></article>'
        for task in data["attention"]) or '<p class="empty">Nothing currently requires your action.</p>'
    progress = "".join(
        f'<li><span>{html.escape(item["human_event"])}</span> '
        f'<small>{html.escape(str(item.get("task_id") or "System"))} · {_time_html(item["created_at"], reference)}</small></li>'
        for item in data["recent_progress"]) or '<li class="muted">No durable activity recorded.</li>'
    quota_rows = [{"window": name, **value} for name, value in data["quota_windows"].items()]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="15">
<title>CEF Dy · Operations</title><style>
:root{{--bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#64717d;--line:#d9e0e6;--accent:#2457a6;--good:#176b3a;--warn:#8a5b00;--bad:#a12828}}
*{{box-sizing:border-box}}body{{font:15px/1.45 system-ui,sans-serif;margin:0;background:var(--bg);color:var(--ink)}}main{{max-width:1180px;margin:auto;padding:24px}}h1{{margin:0}}h2{{margin:30px 0 12px}}h3{{margin:0 0 4px;font-size:1rem}}a{{color:var(--accent)}}.subtitle,.muted,small{{color:var(--muted)}}
.topline{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}}.status-strip,.cards{{display:flex;gap:10px;flex-wrap:wrap}}.pill,.card,.work-item,.attention-item,.empty,details{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 15px}}.pill strong{{display:block;font-size:1.05rem}}.cards{{margin-top:14px}}.card{{min-width:170px;flex:1}}.card span{{display:block;font-weight:700;margin:3px 0}}.card small{{display:block}}.healthy span{{color:var(--good)}}.degraded span,.failed span{{color:var(--bad)}}.stale span,.unknown span,.unavailable span,.waiting span{{color:var(--warn)}}
.work-item{{display:grid;grid-template-columns:minmax(220px,1fr) minmax(240px,1fr);gap:8px 22px;margin-bottom:9px}}.work-item small{{grid-column:1/-1}}.needs-user{{color:var(--bad)}}.attention-item{{border-left:5px solid var(--bad);margin-bottom:9px}}.attention-item p{{margin:4px 0}}.progress{{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:0;padding:8px 8px 8px 34px}}.progress li{{padding:5px}}.progress small{{display:block}}
.map-scroll{{overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}}.task-map{{width:100%;min-width:720px;max-height:520px}}.edge{{fill:none;stroke:#8795a1;stroke-width:2}}.node rect{{fill:#f8fafb;stroke:#71808c;stroke-width:1.5}}.node text{{font:12px system-ui;fill:var(--ink)}}.node .node-state{{font-size:11px;fill:var(--muted)}}.node.current rect{{stroke:var(--accent);stroke-width:3}}.node.needs rect{{stroke:var(--bad);stroke-width:3;stroke-dasharray:5 3}}.node.done rect{{fill:#edf6f0;stroke:#7a9984}}.node.waiting rect{{stroke:var(--warn)}}.lane-label{{font:600 12px system-ui;fill:#46545f}}
details{{margin-top:30px}}summary{{cursor:pointer;font-weight:700;font-size:1.08rem}}table{{border-collapse:collapse;width:100%;background:white;margin:10px 0 22px;font-size:12px}}th,td{{padding:7px;border:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#eaf0f6}}.mono{{font-family:ui-monospace,monospace;overflow-wrap:anywhere}}.diag-scroll{{overflow:auto}}.telegram{{margin-top:10px}}@media(max-width:700px){{main{{padding:16px}}.work-item{{grid-template-columns:1fr}}.work-item small{{grid-column:auto}}.card{{min-width:145px}}}}
</style></head><body><main>
<div class="topline"><div><h1>CEF Dy</h1><p class="subtitle">Read-only operational view · refreshed every 15 seconds</p></div><a href="/api/status">JSON diagnostics</a></div>
<div class="status-strip"><div class="pill"><span>System state</span><strong>{html.escape(dashboard["human_health"])}</strong></div>
<div class="pill" title="canonical {html.escape(str(git.get('canonical_head')), quote=True)} · local {html.escape(str(git.get('local_head')), quote=True)}"><span>{html.escape(sync["label"])}</span><strong class="mono">{html.escape(str(sync.get("short_sha") or "Unknown"))}</strong></div>
<div class="pill telegram"><span>Telegram</span><strong>{html.escape(data["telegram"]["label"])}</strong></div></div><div class="cards">{health_cards}</div>
<h2>Current work</h2>{_current_work_html(data["current_work"], reference)}
<h2>Task map</h2>{_task_map_svg(data["task_graph"])}
<h2>Needs attention</h2>{attention_html}
<h2>Recent meaningful progress</h2><ol class="progress">{progress}</ol>
<details><summary>Technical details</summary><div class="diag-scroll"><p>Exact values below are diagnostic data. Quota entries are configuration/projection values, not live telemetry unless an explicit observation source says otherwise.</p>
<h3>Git identity</h3>{_table([git], ('canonical_head','local_head','branch'))}
<h3>Quota projections</h3>{_table(quota_rows, ('window','state','observed_at','reset_at'))}
<h3>All tasks</h3>{_table(data['tasks'], ('task_id','fsm_state','project_progress','human_action_required','semantic_state','design_state','implementation_state','deployment_state','canonicalization_state','lifecycle_disposition','authoring_receipt_sha256','role','task_type','dependencies','attempt','reason','created_at','updated_at'))}
<h3>Workers and leases</h3>{_table(data['workers'], ('task_id','worker_id','attempt_id','claimed_at','lease_expires_at'))}
<h3>Resource lanes</h3>{_table(data['resource_lanes'], ('lane_id','availability_state','quota_state','next_probe_at','concurrency_limit','capability_json','cost_priority','refusal_count','updated_at'))}
<h3>Specialist routes</h3>{_table(data['routes'], ('task_id','role_id','suitability','allowed_lanes_json','selected_lane','route_status','reason','updated_at'))}
<h3>Reviews</h3>{_table(data['reviews'], ('parent_task_id','review_task_id','role_id','status','reason','updated_at'))}
<h3>Results</h3>{_table(data['results'], ('task_id','attempt_id','result_sha256','accepted_at'))}
<h3>Publication outbox</h3>{_table(data['publications'], ('publication_id','task_id','result_sha256','target','status','attempts','reason','remote_id','created_at','updated_at'))}
<h3>Dependency result bundles</h3>{_table(data['dependency_bundles'], ('task_id','bundle_sha256','dependency_count','created_at','updated_at'))}
<h3>Raw event log</h3>{_table(data['recent_activity'], ('event_id','created_at','task_id','event_type','old_state','new_state','detail_json'))}</div></details>
</main></body></html>"""
    return page.encode("utf-8")


def make_handler(cfg: dict[str, Any]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CEF-Dy-Dashboard/2"

        def _reply(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            try:
                data = snapshot(cfg)
                if path == "/":
                    self._reply(200, "text/html; charset=utf-8", render(data))
                elif path == "/api/status":
                    self._reply(200, "application/json; charset=utf-8",
                                json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
                else:
                    self._reply(404, "text/plain; charset=utf-8", b"Not found\n")
            except Exception as exc:
                body = json.dumps({"status": "UNAVAILABLE", "error": str(exc)}).encode("utf-8")
                self._reply(503, "application/json; charset=utf-8", body)

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def _readonly(self) -> None:
            self._reply(405, "application/json; charset=utf-8", b'{"error":"read-only"}')

        do_POST = do_PUT = do_PATCH = do_DELETE = _readonly

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def create_server(cfg: dict[str, Any]) -> ThreadingHTTPServer:
    host = cfg["dashboard"]["host"]
    if host != "127.0.0.1":
        raise ValueError("dashboard host must be loopback-only")
    return ThreadingHTTPServer((host, int(cfg["dashboard"]["port"])), make_handler(cfg))


def serve(cfg: dict[str, Any]) -> None:
    if not cfg["dashboard"]["enabled"]:
        raise ValueError("dashboard is disabled")
    server = create_server(cfg)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
