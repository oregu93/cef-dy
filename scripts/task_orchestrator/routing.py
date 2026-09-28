"""M2 specialist registry and durable production routing layered over M1b."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from .model import State, Task, utc_now


ROLE_IDS = ("00", "01", "02", "03", "04", "07")
ROLE_ALIASES = {
    "00": "00", "00_PROJECT_CONTROL": "00", "PROJECT_CONTROL": "00",
    "01": "01", "01_LITERATURE_PHYSICS": "01", "LITERATURE_PHYSICS": "01",
    "02": "02", "02_TAIPAN_DATA_REDUCTION": "02", "TAIPAN_DATA_REDUCTION": "02",
    "03": "03", "03_CEF_MODELLING_FIT_DESIGN": "03", "CEF_MODELLING_FIT_DESIGN": "03",
    "04": "04", "04_STRUCTURE_CONVENTIONS": "04", "STRUCTURE_CONVENTIONS": "04",
    "07": "07", "07_INFRASTRUCTURE": "07",
    "07_RESEARCH_SOFTWARE_INFRASTRUCTURE": "07", "RESEARCH_SOFTWARE_INFRASTRUCTURE": "07",
}

M2_SCHEMA = """
CREATE TABLE IF NOT EXISTS specialist_roles (
  role_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  bootstrap_sha256 TEXT NOT NULL,
  bootstrap_text TEXT NOT NULL,
  source_path TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_routes (
  task_id TEXT PRIMARY KEY,
  role_id TEXT,
  bootstrap_sha256 TEXT,
  preferred_lane TEXT NOT NULL,
  selected_lane TEXT NOT NULL,
  route_status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_requirements (
  parent_task_id TEXT PRIMARY KEY,
  review_task_id TEXT UNIQUE,
  role_id TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SpecialistRole:
    role_id: str
    title: str
    bootstrap_text: str
    bootstrap_sha256: str


def canonical_role(value: str) -> str | None:
    key = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    return ROLE_ALIASES.get(key)


def load_registry(path: Path) -> dict[str, SpecialistRole]:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^## (00|01|02|03|04|07) - ([^\n]+)\n", text))
    found: dict[str, SpecialistRole] = {}
    for index, match in enumerate(matches):
        role_id = match.group(1)
        if role_id in found:
            raise ValueError(f"duplicate canonical specialist bootstrap: {role_id}")
        next_heading = re.search(r"(?m)^## ", text[match.end():])
        end = match.end() + next_heading.start() if next_heading else len(text)
        section = text[match.start():end].rstrip() + "\n"
        found[role_id] = SpecialistRole(
            role_id, match.group(2).strip(), section,
            hashlib.sha256(section.encode("utf-8")).hexdigest(),
        )
    missing = sorted(set(ROLE_IDS) - set(found))
    if missing or len(found) != len(ROLE_IDS):
        raise ValueError("canonical specialist bootstrap registry incomplete: " + ",".join(missing))
    return found


def bootstrap_for_task(cfg: dict[str, Any], role: str) -> SpecialistRole:
    role_id = canonical_role(role)
    if role_id is None:
        raise ValueError(f"unknown specialist role: {role}")
    return load_registry(Path(cfg["routing"]["bootstrap_path"]))[role_id]


class ProductionRouter:
    def __init__(self, cfg: dict[str, Any], store: Any, engine: Any):
        self.cfg, self.store, self.engine = cfg, store, engine
        self.conn: sqlite3.Connection = store.conn
        self.conn.executescript(M2_SCHEMA)

    @property
    def enabled(self) -> bool:
        return bool(self.cfg["routing"]["enabled"])

    def sync_registry(self) -> dict[str, SpecialistRole]:
        roles = load_registry(Path(self.cfg["routing"]["bootstrap_path"]))
        now = utc_now()
        with self.store.transaction():
            for role in roles.values():
                self.conn.execute(
                    "INSERT INTO specialist_roles VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(role_id) DO UPDATE SET title=excluded.title,bootstrap_sha256=excluded.bootstrap_sha256,"
                    "bootstrap_text=excluded.bootstrap_text,source_path=excluded.source_path,updated_at=excluded.updated_at",
                    (role.role_id, role.title, role.bootstrap_sha256, role.bootstrap_text,
                     str(self.cfg["routing"]["bootstrap_path"]), now),
                )
        return roles

    def _record_route(self, task: Task, roles: dict[str, SpecialistRole]) -> str | None:
        role_id = canonical_role(task.role)
        preferred = "AI_BOUNDED_SPECIALIST" if task.is_llm else "LOCAL_DETERMINISTIC"
        if role_id is None:
            status, lane, reason, digest = "INVALID_ROLE", "HUMAN_DECISION", "unknown canonical specialist role", None
        else:
            status, lane, reason = "ROUTED", preferred, "canonical specialist route selected"
            digest = roles[role_id].bootstrap_sha256
        now = utc_now()
        self.conn.execute(
            "INSERT INTO task_routes VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET role_id=excluded.role_id,bootstrap_sha256=excluded.bootstrap_sha256,"
            "preferred_lane=excluded.preferred_lane,selected_lane=excluded.selected_lane,route_status=excluded.route_status,"
            "reason=excluded.reason,updated_at=excluded.updated_at",
            (task.task_id, role_id, digest, preferred, lane, status, reason, now, now),
        )
        row = self.store.get(task.task_id)
        if role_id is None and row and row["state"] not in {
            State.SUCCEEDED.value, State.FAILED.value, State.REJECTED.value, State.BLOCKED.value,
        }:
            self.store.transition(task.task_id, State.WAITING_USER, reason, force_recovery=True)
        return role_id

    def _review(self, task: Task, role_id: str | None) -> str:
        if not bool(task.inputs.get("review_required", False)):
            return "NOT_REQUIRED"
        review_role = canonical_role(str(task.inputs.get("review_role", "00")))
        if review_role is None:
            review_role = "00"
        review_id = f"{task.task_id}-REVIEW-001"
        now = utc_now()
        existing = self.store.get(review_id)
        if existing is not None:
            status = existing["state"]
            reason = "bounded review task exists"
        elif self.store.get(task.task_id)["state"] != State.SUCCEEDED.value:
            status, reason, review_id = "WAITING_PARENT", "parent result not complete", None
        elif not bool(task.inputs.get("auto_review_authorized", False)):
            status, reason, review_id = "WAITING_USER", "automatic review worker not authorized", None
        elif not self.cfg["routing"]["auto_create_reviews"]:
            status, reason, review_id = "WAITING_USER", "automatic review creation disabled", None
        else:
            labels = ("orchestrator:llm-approved",)
            review = Task(
                schema_version=1, task_id=review_id, role=review_role,
                canonical_head=task.canonical_head, task_type="llm_worker",
                action="semantic_helper", dependencies=(task.task_id,),
                inputs={"review_of": task.task_id, "independent_review": True,
                        "parent_role": role_id},
                allowed_paths=(), expected_artifacts=(), timeout_seconds=task.timeout_seconds,
                stop_condition="Independently return PASS or actionable findings; do not modify files or project authority.",
                source_issue=None, labels=labels,
            )
            outcome = self.engine.ingest(review)
            if outcome not in {"created", "duplicate", "metadata_updated"}:
                status, reason = "WAITING_USER", f"review creation outcome: {outcome}"
                review_id = None
            else:
                self.store.approve(review.task_id)
                self.engine.reevaluate_waiting()
                self._record_route(
                    review,
                    load_registry(Path(self.cfg["routing"]["bootstrap_path"])),
                )
                status, reason = self.store.get(review.task_id)["state"], "bounded independent review created"
        self.conn.execute(
            "INSERT INTO review_requirements VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(parent_task_id) DO UPDATE SET review_task_id=excluded.review_task_id,role_id=excluded.role_id,"
            "status=excluded.status,reason=excluded.reason,updated_at=excluded.updated_at",
            (task.task_id, review_id, review_role, status, reason, now, now),
        )
        return status

    def reconcile(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "DISABLED", "routes": 0, "reviews": 0}
        roles = self.sync_registry()
        routed = reviews = 0
        for row in self.store.list_state():
            task = self.store.task(row)
            role_id = self._record_route(task, roles)
            routed += 1
            if bool(task.inputs.get("review_required", False)):
                self._review(task, role_id)
                reviews += 1
        return {"status": "OPERATIONAL", "roles": len(roles), "routes": routed, "reviews": reviews}

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"M2_PRODUCTION_ROUTING": "DISABLED"}
        return {
            "M2_PRODUCTION_ROUTING": "OPERATIONAL",
            "SPECIALIST_ROLE_ROUTING": "VERIFIED" if self.conn.execute("SELECT count(*) FROM specialist_roles").fetchone()[0] == 6 else "DEGRADED",
            "ROUTES": self.conn.execute("SELECT count(*) FROM task_routes").fetchone()[0],
            "REVIEWS": self.conn.execute("SELECT count(*) FROM review_requirements").fetchone()[0],
        }
