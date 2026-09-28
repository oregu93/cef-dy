"""Localhost-only, read-only M2 operator dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any
from urllib.parse import urlsplit


def _utc_age(value: str | None) -> float | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def open_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=2)
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


def snapshot(cfg: dict[str, Any]) -> dict[str, Any]:
    database = Path(cfg["state_dir"]) / "state.sqlite3"
    with open_readonly(database) as conn:
        tasks = [dict(row) for row in conn.execute(
            "SELECT task_id,state,reason,attempt,source_issue,created_at,updated_at,payload_json "
            "FROM tasks ORDER BY updated_at DESC,task_id"
        )]
        for task in tasks:
            payload = json.loads(task.pop("payload_json"))
            task["role"] = payload.get("role")
            task["task_type"] = payload.get("task_type")
            task["dependencies"] = payload.get("dependencies", [])
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
        reviews = [dict(row) for row in conn.execute(
            "SELECT * FROM review_requirements ORDER BY updated_at DESC,parent_task_id"
        )] if _table_exists(conn, "review_requirements") else []
        results = [dict(row) for row in conn.execute(
            "SELECT task_id,attempt_id,result_sha256,accepted_at FROM accepted_results ORDER BY accepted_at DESC"
        )] if _table_exists(conn, "accepted_results") else []
        controller = None
        controller_updated = None
        if _table_exists(conn, "controller_state"):
            row = conn.execute(
                "SELECT state_json,updated_at FROM controller_state ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row:
                controller, controller_updated = json.loads(row["state_json"]), row["updated_at"]
    stale_after = int(cfg["dashboard"]["stale_after_seconds"])
    age = _utc_age(controller_updated)
    health = "HEALTHY" if age is not None and age <= stale_after else "STALE"
    attention_states = {"WAITING_USER", "WAITING_APPROVAL", "BLOCKED", "FAILED", "REJECTED"}
    attention = [task for task in tasks if task["state"] in attention_states]
    blockers = [task for task in tasks if task["state"] in {"BLOCKED", "FAILED", "REJECTED"}]
    repo = Path(cfg["repository_root"])
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dashboard": {"read_only": True, "health": health, "controller_age_seconds": age,
                      "source_of_truth": str(database)},
        "orchestrator": controller or {"CURRENT_PHASE": "UNKNOWN"},
        "git": {
            "canonical_head": _git(repo, "rev-parse", "refs/remotes/origin/main"),
            "local_head": _git(repo, "rev-parse", "HEAD"),
            "branch": _git(repo, "branch", "--show-current"),
        },
        "ai_lane": lane,
        "quota_windows": cfg["visibility"]["quota"],
        "tasks": tasks,
        "workers": leases,
        "routes": routes,
        "reviews": reviews,
        "results": results,
        "attention": attention,
        "blockers": blockers,
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
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render(data: dict[str, Any]) -> bytes:
    health = data["dashboard"]["health"]
    git = data["git"]
    lane = data["ai_lane"]
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15"><title>CEF Dy M2 Operator Dashboard</title>
<style>body{{font:14px system-ui;margin:24px;background:#f5f7fa;color:#17202a}}h1{{margin-bottom:4px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{background:white;padding:12px 16px;border-radius:8px;box-shadow:0 1px 4px #ccd}}
table{{border-collapse:collapse;width:100%;background:white;margin-bottom:20px}}th,td{{padding:7px;border:1px solid #dde;text-align:left;vertical-align:top}}th{{background:#eaf0f6}}
.mono{{font-family:ui-monospace,monospace}}.ok{{color:#087830}}.warn{{color:#a33}}</style></head><body>
<h1>CEF Dy M2 Operator Dashboard</h1><p>Read-only local view · refreshed every 15 seconds · <a href="/api/status">JSON</a></p>
<div class="cards"><div class="card"><b>Health</b><br><span class="{'ok' if health == 'HEALTHY' else 'warn'}">{html.escape(health)}</span></div>
<div class="card"><b>AI lane</b><br>{html.escape(str(lane.get('state', 'UNKNOWN')))}</div>
<div class="card"><b>5h quota</b><br>{html.escape(str(data['quota_windows']['five_hour'].get('state', 'UNKNOWN')))}</div>
<div class="card"><b>Weekly quota</b><br>{html.escape(str(data['quota_windows']['weekly'].get('state', 'UNKNOWN')))}</div>
<div class="card"><b>Canonical HEAD</b><br><span class="mono">{html.escape(str(git.get('canonical_head')))}</span></div>
<div class="card"><b>Local HEAD</b><br><span class="mono">{html.escape(str(git.get('local_head')))}</span></div></div>
<h2>Attention and blockers</h2>{_table(data['attention'], ('task_id','state','role','reason','updated_at'))}
<h2>Terminal blockers</h2>{_table(data['blockers'], ('task_id','state','role','reason','updated_at'))}
<h2>Tasks and dependencies</h2>{_table(data['tasks'], ('task_id','state','role','task_type','dependencies','attempt','reason','updated_at'))}
<h2>Workers</h2>{_table(data['workers'], ('task_id','worker_id','attempt_id','claimed_at','lease_expires_at'))}
<h2>Specialist routes</h2>{_table(data['routes'], ('task_id','role_id','selected_lane','route_status','reason','updated_at'))}
<h2>Reviews</h2>{_table(data['reviews'], ('parent_task_id','review_task_id','role_id','status','reason','updated_at'))}
<h2>Results</h2>{_table(data['results'], ('task_id','attempt_id','result_sha256','accepted_at'))}
<h2>Recent activity</h2>{_table(data['recent_activity'], ('event_id','created_at','task_id','event_type','old_state','new_state'))}
</body></html>"""
    return page.encode("utf-8")


def make_handler(cfg: dict[str, Any]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CEF-Dy-M2-Dashboard/1"

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
