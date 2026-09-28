"""M2 specialist registry and durable production routing layered over M1b."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import yaml

from .model import State, Task, utc_now


ROLE_IDS = ("00", "01", "02", "03", "04", "07")
ROLE_ALIASES = {
    "00": "00", "00_PROJECT_CONTROL": "00", "PROJECT_CONTROL": "00",
    "01": "01", "01_LITERATURE": "01", "01_LITERATURE_PHYSICS": "01", "LITERATURE_PHYSICS": "01",
    "02": "02", "02_TAIPAN_DATA_REDUCTION": "02", "TAIPAN_DATA_REDUCTION": "02",
    "03": "03", "03_CEF": "03", "03_CEF_MODELLING_FIT_DESIGN": "03", "CEF_MODELLING_FIT_DESIGN": "03",
    "04": "04", "04_STRUCTURE": "04", "04_STRUCTURE_CONVENTIONS": "04", "STRUCTURE_CONVENTIONS": "04",
    "07": "07", "07_INFRASTRUCTURE": "07",
    "07_RESEARCH_SOFTWARE_INFRASTRUCTURE": "07", "RESEARCH_SOFTWARE_INFRASTRUCTURE": "07",
}
LANES = ("LOCAL_DETERMINISTIC", "LOCAL_OSS_MODEL", "NON_WORK_AI", "WORK_CODEX", "HUMAN_DECISION")
SUITABILITY = {
    "DETERMINISTIC_REQUIRED": ("LOCAL_DETERMINISTIC",),
    "LOCAL_SEMANTIC_OK": ("LOCAL_OSS_MODEL", "NON_WORK_AI", "WORK_CODEX"),
    "NON_WORK_AI_OK": ("NON_WORK_AI", "LOCAL_OSS_MODEL", "WORK_CODEX"),
    "WORK_PREFERRED": ("WORK_CODEX", "LOCAL_OSS_MODEL", "NON_WORK_AI"),
    "WORK_REQUIRED": ("WORK_CODEX",),
    "HUMAN_REQUIRED": ("HUMAN_DECISION",),
}
REVIEW_EMBED_LIMIT = 60_000
REVIEW_ARTIFACT_LIMIT = 2_000_000
REVIEW_SEMANTIC_FIELDS = {"summary", "semantic_verdict", "semantic_error"}

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
  suitability TEXT NOT NULL,
  allowed_lanes_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resource_lanes (
  lane_id TEXT PRIMARY KEY,
  availability_state TEXT NOT NULL,
  quota_state TEXT NOT NULL,
  next_probe_at REAL,
  concurrency_limit INTEGER NOT NULL,
  capability_json TEXT NOT NULL,
  cost_priority INTEGER NOT NULL,
  refusal_count INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS dependency_result_bundles (
  task_id TEXT PRIMARY KEY,
  bundle_sha256 TEXT NOT NULL,
  bundle_json TEXT NOT NULL,
  dependency_count INTEGER NOT NULL,
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


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _material_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _resolve_bound_material(cfg: dict[str, Any], material: Any, label: str) -> str:
    if not isinstance(material, dict):
        raise ValueError(f"{label} material is missing")
    digest = material.get("review_material_sha256")
    core = {key: value for key, value in material.items() if key != "review_material_sha256"}
    if not isinstance(digest, str) or _material_digest(core) != digest:
        raise ValueError(f"{label} material hash mismatch")
    delivery = material.get("delivery")
    if delivery == "embedded":
        result = material.get("accepted_result")
        if not isinstance(result, dict):
            raise ValueError("embedded accepted result is missing")
        return f"\nVERIFIED {label.upper()} MATERIAL:\n" + _canonical(material) + "\n"
    if delivery != "artifact":
        raise ValueError(f"{label} material delivery is invalid")
    relative = material.get("result_path")
    if not isinstance(relative, str) or not re.fullmatch(r"results/[A-Z0-9][A-Z0-9._-]{2,127}\.yaml", relative):
        raise ValueError(f"{label} result artifact path is invalid")
    path = Path(cfg["state_dir"]) / relative
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} result artifact unavailable: {exc}") from exc
    if not raw or len(raw) > REVIEW_ARTIFACT_LIMIT:
        raise ValueError(f"{label} result artifact is empty or oversized")
    if hashlib.sha256(raw).hexdigest() != material.get("artifact_sha256"):
        raise ValueError(f"{label} result artifact hash mismatch")
    return (
        f"\nVERIFIED {label.upper()} MATERIAL BINDING:\n" + _canonical(material)
        + f"\nVERIFIED {label.upper()} RESULT ARTIFACT:\n" + raw.decode("utf-8", errors="strict") + "\n"
    )


def resolve_review_prompt_material(cfg: dict[str, Any], task: Task) -> str:
    """Resolve envelope-bound review evidence without trusting chat memory."""
    if task.inputs.get("independent_review") is not True:
        return ""
    return _resolve_bound_material(cfg, task.inputs.get("review_material"), "parent review")


def resolve_dependency_prompt_material(cfg: dict[str, Any], task: Task) -> str:
    """Resolve and verify the durable ordered dependency-result bundle."""
    if task.inputs.get("bind_dependency_results") is not True:
        return ""
    database = Path(cfg["state_dir"]) / "state.sqlite3"
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM dependency_result_bundles WHERE task_id=?", (task.task_id,)
        ).fetchone()
        if row is None:
            raise ValueError("dependency result bundle is missing")
        try:
            bundle = json.loads(row["bundle_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("dependency result bundle is malformed") from exc
        if (not isinstance(bundle, dict) or _material_digest(bundle) != row["bundle_sha256"]
                or bundle.get("consumer_task_id") != task.task_id
                or bundle.get("consumer_canonical_head") != task.canonical_head
                or bundle.get("ordered_dependency_ids") != sorted(task.dependencies)):
            raise ValueError("dependency result bundle identity/hash mismatch")
        materials = bundle.get("materials")
        if not isinstance(materials, list) or len(materials) != len(task.dependencies):
            raise ValueError("dependency result bundle cardinality mismatch")
        sections = []
        for dependency_id, material in zip(bundle["ordered_dependency_ids"], materials, strict=True):
            if not isinstance(material, dict) or material.get("parent_task_id") != dependency_id:
                raise ValueError("dependency result bundle ordering mismatch")
            accepted = conn.execute(
                "SELECT * FROM accepted_results WHERE task_id=?", (dependency_id,)
            ).fetchone()
            dependency = conn.execute(
                "SELECT payload_json,state FROM tasks WHERE task_id=?", (dependency_id,)
            ).fetchone()
            if accepted is None or dependency is None or dependency["state"] != State.SUCCEEDED.value:
                raise ValueError(f"dependency result unavailable or non-successful: {dependency_id}")
            payload = json.loads(dependency["payload_json"])
            if (material.get("parent_attempt_id") != accepted["attempt_id"]
                    or material.get("accepted_result_sha256") != accepted["result_sha256"]
                    or material.get("parent_canonical_head") != payload.get("canonical_head")):
                raise ValueError(f"dependency result identity/hash mismatch: {dependency_id}")
            if material.get("delivery") == "embedded":
                accepted_result = json.loads(accepted["result_json"])
                if material.get("accepted_result") != accepted_result:
                    raise ValueError(f"embedded dependency result mismatch: {dependency_id}")
            sections.append(_resolve_bound_material(cfg, material, f"dependency {dependency_id}"))
        return (
            "\nVERIFIED ORDERED DEPENDENCY RESULT BUNDLE:\n" + _canonical({
                "bundle_sha256": row["bundle_sha256"],
                "consumer_task_id": task.task_id,
                "ordered_dependency_ids": bundle["ordered_dependency_ids"],
            }) + "\n" + "".join(sections)
        )
    finally:
        conn.close()


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

    def sync_lanes(self) -> dict[str, dict[str, Any]]:
        work = dict(self.conn.execute("SELECT * FROM ai_lane WHERE singleton=1").fetchone())
        ollama = self.cfg["llm"]["ollama"]
        non_work = self.cfg["non_work_ai"]
        values = {
            "LOCAL_DETERMINISTIC": ("AVAILABLE", "AVAILABLE", None, int(self.cfg["autonomy"]["max_parallel_local"]), ["deterministic", "allowlisted"], 0, 0),
            "LOCAL_OSS_MODEL": (("AVAILABLE" if ollama["enabled"] and ollama["verified_interface"] and ollama["model"] else "DISABLED"), "AVAILABLE", None, int(ollama["max_concurrent_runs"]), ["semantic", "local", "non-authoritative"], 1, 0),
            "NON_WORK_AI": (("AVAILABLE" if non_work["enabled"] and non_work["verified_interface"] else "UNVERIFIED"), "AVAILABLE", None, int(non_work["max_concurrent_runs"]), ["semantic", "non-work", "bounded"], 2, 0),
            "WORK_CODEX": (("AVAILABLE" if work["state"] == "AVAILABLE" else work["state"]), work["state"], work["next_probe_at"], int(self.cfg["max_concurrent_llm_runs"]), ["semantic", "code", "bounded-specialist"], 3, int(work["refusal_count"])),
            "HUMAN_DECISION": ("AVAILABLE", "NOT_APPLICABLE", None, 1, ["scientific", "strategic", "authority"], 4, 0),
        }
        now = utc_now()
        for lane_id, value in values.items():
            existing = self.conn.execute("SELECT * FROM resource_lanes WHERE lane_id=?", (lane_id,)).fetchone()
            if lane_id in {"LOCAL_OSS_MODEL", "NON_WORK_AI"} and existing is not None and existing["quota_state"] == "QUOTA_WAIT":
                value = (existing["availability_state"], existing["quota_state"], existing["next_probe_at"],
                         value[3], value[4], value[5], existing["refusal_count"])
            self.conn.execute(
                "INSERT INTO resource_lanes VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(lane_id) DO UPDATE SET "
                "availability_state=excluded.availability_state,quota_state=excluded.quota_state,next_probe_at=excluded.next_probe_at,"
                "concurrency_limit=excluded.concurrency_limit,capability_json=excluded.capability_json,cost_priority=excluded.cost_priority,"
                "refusal_count=excluded.refusal_count,updated_at=excluded.updated_at",
                (lane_id, value[0], value[1], value[2], value[3], json.dumps(value[4]), value[5], value[6], now),
            )
        return {row["lane_id"]: dict(row) for row in self.conn.execute("SELECT * FROM resource_lanes")}

    @staticmethod
    def requirement(task: Task) -> str:
        return str(task.inputs.get("resource_requirement") or (
            "" if task.is_llm else "DETERMINISTIC_REQUIRED"
        ))

    def _select_lane(self, task: Task, lanes: dict[str, dict[str, Any]]) -> tuple[str, str, tuple[str, ...], str]:
        requirement = self.requirement(task)
        if (task.is_llm and requirement == "DETERMINISTIC_REQUIRED") or (
            not task.is_llm and requirement not in {"DETERMINISTIC_REQUIRED", "HUMAN_REQUIRED"}
        ):
            return "HUMAN_DECISION", "INVALID_SUITABILITY", (), "task type and resource suitability are incompatible"
        defaults = SUITABILITY.get(requirement)
        if defaults is None:
            return "HUMAN_DECISION", "INVALID_SUITABILITY", (), "invalid resource suitability"
        declared = task.inputs.get("allowed_lanes")
        allowed = tuple(declared) if isinstance(declared, list) else defaults
        allowed = tuple(lane for lane in allowed if lane in defaults)
        if not allowed:
            return "HUMAN_DECISION", "INVALID_SUITABILITY", allowed, "no suitable allowed lane"
        if requirement == "HUMAN_REQUIRED":
            return "HUMAN_DECISION", "WAITING_USER", allowed, "human decision explicitly required"
        for lane in allowed:
            if lanes[lane]["availability_state"] == "AVAILABLE":
                return lane, "ROUTED", allowed, "first available suitable lane selected"
        return allowed[0], "WAITING_RESOURCE", allowed, "all suitable lanes unavailable"

    def _record_route(self, task: Task, roles: dict[str, SpecialistRole], lanes: dict[str, dict[str, Any]]) -> str | None:
        role_id = canonical_role(task.role)
        requirement = self.requirement(task)
        lane, status, allowed, reason = self._select_lane(task, lanes)
        preferred = allowed[0] if allowed else "HUMAN_DECISION"
        if role_id is None:
            status, lane, reason, digest = "INVALID_ROLE", "HUMAN_DECISION", "unknown canonical specialist role", None
        else:
            digest = roles[role_id].bootstrap_sha256
        if task.inputs.get("independent_review") is True:
            valid, review_reason = self.verify_review_material(task)
            if not valid:
                status, lane, reason = "INVALID_REVIEW_MATERIAL", "HUMAN_DECISION", review_reason
        if task.inputs.get("bind_dependency_results") is True:
            dependency_rows = [self.store.get(task_id) for task_id in task.dependencies]
            dependencies_complete = bool(dependency_rows) and all(
                row is not None and row["state"] == State.SUCCEEDED.value for row in dependency_rows
            )
            if dependencies_complete:
                valid, dependency_reason = self.sync_dependency_bundle(task)
                if not valid:
                    status, lane, reason = "INVALID_DEPENDENCY_MATERIAL", "HUMAN_DECISION", dependency_reason
            elif any(row is not None and row["state"] in {
                State.FAILED.value, State.REJECTED.value, State.BLOCKED.value,
            } for row in dependency_rows):
                status, lane, reason = (
                    "INVALID_DEPENDENCY_MATERIAL", "HUMAN_DECISION",
                    "failed/rejected dependency cannot provide accepted result material",
                )
        now = utc_now()
        self.conn.execute(
            "INSERT INTO task_routes(task_id,role_id,bootstrap_sha256,preferred_lane,selected_lane,route_status,reason,suitability,allowed_lanes_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET role_id=excluded.role_id,bootstrap_sha256=excluded.bootstrap_sha256,"
            "preferred_lane=excluded.preferred_lane,selected_lane=excluded.selected_lane,route_status=excluded.route_status,"
            "reason=excluded.reason,suitability=excluded.suitability,allowed_lanes_json=excluded.allowed_lanes_json,updated_at=excluded.updated_at",
            (task.task_id, role_id, digest, preferred, lane, status, reason, requirement, json.dumps(allowed), now, now),
        )
        row = self.store.get(task.task_id)
        dependency_terminal = status == "INVALID_DEPENDENCY_MATERIAL" and any(
            dependency is not None and dependency["state"] in {
                State.FAILED.value, State.REJECTED.value, State.BLOCKED.value,
            } for dependency in (self.store.get(task_id) for task_id in task.dependencies)
        )
        if dependency_terminal and row and row["state"] not in {
            State.SUCCEEDED.value, State.FAILED.value, State.REJECTED.value, State.BLOCKED.value,
        }:
            self.store.transition(task.task_id, State.BLOCKED, reason, force_recovery=True)
        elif status in {"INVALID_ROLE", "INVALID_SUITABILITY", "INVALID_REVIEW_MATERIAL", "INVALID_DEPENDENCY_MATERIAL", "WAITING_USER"} and row and row["state"] not in {
            State.SUCCEEDED.value, State.FAILED.value, State.REJECTED.value, State.BLOCKED.value,
        }:
            self.store.transition(task.task_id, State.WAITING_USER, reason, force_recovery=True)
        elif status == "WAITING_RESOURCE" and row and row["state"] in {
            State.READY.value, State.WAITING_APPROVAL.value, State.QUOTA_WAIT.value,
        }:
            self.store.transition(task.task_id, State.WAITING_RESOURCE, reason, force_recovery=True)
        elif status == "ROUTED" and row and row["state"] == State.WAITING_RESOURCE.value:
            self.store.transition(task.task_id, State.READY, "suitable resource lane available")
        return role_id

    def _review(self, task: Task, role_id: str | None) -> str:
        if task.inputs.get("review_required", False) is not True:
            return "NOT_REQUIRED"
        review_role = canonical_role(str(task.inputs.get("review_role", "00")))
        if review_role is None:
            raise ValueError("invalid review_role")
        review_id = f"{task.task_id}-REVIEW-001"
        now = utc_now()
        existing = self.store.get(review_id)
        if existing is not None:
            status = existing["state"]
            reason = "bounded review task exists"
        elif not self._execution_complete(task):
            status, reason, review_id = "WAITING_PARENT", "parent result not complete", None
        elif task.inputs.get("auto_review_authorized", False) is not True:
            status, reason, review_id = "WAITING_USER", "automatic review worker not authorized", None
        elif not self.cfg["routing"]["auto_create_reviews"]:
            status, reason, review_id = "WAITING_USER", "automatic review creation disabled", None
        else:
            try:
                review_material = self._build_review_material(task)
            except ValueError as exc:
                status, reason, review_id = "WAITING_USER", str(exc), None
                self.conn.execute(
                    "INSERT INTO review_requirements VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(parent_task_id) DO UPDATE SET review_task_id=excluded.review_task_id,role_id=excluded.role_id,"
                    "status=excluded.status,reason=excluded.reason,updated_at=excluded.updated_at",
                    (task.task_id, review_id, review_role, status, reason, now, now),
                )
                return status
            labels = ("orchestrator:llm-approved",)
            review = Task(
                schema_version=1, task_id=review_id, role=review_role,
                canonical_head=task.canonical_head, task_type="llm_worker",
                # Creation itself is gated on the parent's durable accepted
                # execution.  Keeping this relation in review_requirements,
                # rather than as an FSM dependency, also lets legacy negative
                # semantic results receive their required review.
                action="semantic_helper", dependencies=(),
                inputs={"review_of": task.task_id, "independent_review": True,
                        "parent_role": role_id, "resource_requirement": "WORK_PREFERRED",
                        "allowed_lanes": ["LOCAL_OSS_MODEL", "NON_WORK_AI", "WORK_CODEX"],
                        "review_material": review_material},
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
                    self.sync_lanes(),
                )
                status, reason = self.store.get(review.task_id)["state"], "bounded independent review created"
        self.conn.execute(
            "INSERT INTO review_requirements VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(parent_task_id) DO UPDATE SET review_task_id=excluded.review_task_id,role_id=excluded.role_id,"
            "status=excluded.status,reason=excluded.reason,updated_at=excluded.updated_at",
            (task.task_id, review_id, review_role, status, reason, now, now),
        )
        return status

    def _accepted_review_result(self, task: Task) -> tuple[sqlite3.Row, dict[str, Any]]:
        accepted = self.conn.execute(
            "SELECT * FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone()
        if accepted is None:
            raise ValueError("parent accepted result is unavailable")
        try:
            result = json.loads(accepted["result_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("parent accepted result is malformed") from exc
        if not isinstance(result, dict):
            raise ValueError("parent accepted result is malformed")
        if task.is_llm and not REVIEW_SEMANTIC_FIELDS.issubset(result):
            raise ValueError("legacy parent result lacks complete semantic review material")
        if (result.get("task_id") != task.task_id
                or result.get("canonical_head") != task.canonical_head
                or result.get("retryable") is not False
                or result.get("status") != State.SUCCEEDED.value):
            raise ValueError("parent accepted result identity or semantic material is invalid")
        if task.is_llm:
            if (not isinstance(result.get("summary"), str)
                    or not isinstance(result.get("semantic_verdict"), str)
                    or not result.get("semantic_verdict")):
                raise ValueError("parent semantic review material is invalid")
            if result.get("semantic_error") is not None and not isinstance(result.get("semantic_error"), str):
                raise ValueError("parent semantic_error is invalid")
        if _material_digest(result) != accepted["result_sha256"]:
            raise ValueError("parent accepted result hash mismatch")
        return accepted, result

    def _build_review_material(self, task: Task) -> dict[str, Any]:
        accepted, result = self._accepted_review_result(task)
        core: dict[str, Any] = {
            "schema_version": 1,
            "delivery": "embedded",
            "parent_task_id": task.task_id,
            "parent_attempt_id": accepted["attempt_id"],
            "parent_canonical_head": task.canonical_head,
            "accepted_result_sha256": accepted["result_sha256"],
            "accepted_result": result,
        }
        if len(_canonical(core).encode()) > REVIEW_EMBED_LIMIT:
            path = Path(self.cfg["state_dir"]) / "results" / f"{task.task_id}.yaml"
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise ValueError(f"review result artifact unavailable: {exc}") from exc
            if not raw or len(raw) > REVIEW_ARTIFACT_LIMIT:
                raise ValueError("review result artifact is empty or oversized")
            try:
                public = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                raise ValueError("review result artifact is malformed") from exc
            compared = ["task_id", "attempt", "status", "canonical_head", "checks", "artifacts", "error"]
            if task.is_llm:
                compared.extend(("summary", "semantic_verdict", "semantic_error"))
            if not isinstance(public, dict) or any(public.get(key) != result.get(key) for key in compared):
                raise ValueError("review result artifact does not match accepted result")
            core = {
                "schema_version": 1,
                "delivery": "artifact",
                "parent_task_id": task.task_id,
                "parent_attempt_id": accepted["attempt_id"],
                "parent_canonical_head": task.canonical_head,
                "accepted_result_sha256": accepted["result_sha256"],
                "result_path": f"results/{task.task_id}.yaml",
                "artifact_sha256": hashlib.sha256(raw).hexdigest(),
                "semantic_verdict": result.get("semantic_verdict"),
                "summary_sha256": hashlib.sha256(str(result.get("summary", "")).encode()).hexdigest(),
                "semantic_error_sha256": hashlib.sha256(
                    _canonical(result.get("semantic_error")).encode()
                ).hexdigest(),
            }
        return {**core, "review_material_sha256": _material_digest(core)}

    def verify_review_material(self, review: Task) -> tuple[bool, str]:
        if review.inputs.get("independent_review") is not True:
            return True, "not an independent review task"
        parent_id = review.inputs.get("review_of")
        if not isinstance(parent_id, str):
            return False, "independent review parent identity is missing"
        parent_row = self.store.get(parent_id)
        if parent_row is None:
            return False, "independent review parent is unavailable"
        parent = self.store.task(parent_row)
        try:
            expected = self._build_review_material(parent)
            resolve_review_prompt_material(self.cfg, review)
        except ValueError as exc:
            return False, str(exc)
        if review.inputs.get("review_material") != expected:
            return False, "independent review material does not match durable accepted parent result"
        return True, "independent review material verified"

    def _build_dependency_bundle(self, task: Task) -> dict[str, Any]:
        if not task.is_llm or task.inputs.get("bind_dependency_results") is not True:
            raise ValueError("dependency-result binding requires an opted-in semantic task")
        ordered = sorted(task.dependencies)
        if not ordered:
            raise ValueError("dependency-result binding requires at least one dependency")
        materials = []
        for dependency_id in ordered:
            row = self.store.get(dependency_id)
            if row is None or row["state"] != State.SUCCEEDED.value:
                raise ValueError(f"dependency is not execution-complete: {dependency_id}")
            materials.append(self._build_review_material(self.store.task(row)))
        return {
            "schema_version": 1,
            "consumer_task_id": task.task_id,
            "consumer_canonical_head": task.canonical_head,
            "ordered_dependency_ids": ordered,
            "materials": materials,
        }

    def sync_dependency_bundle(self, task: Task) -> tuple[bool, str]:
        try:
            bundle = self._build_dependency_bundle(task)
            encoded = _canonical(bundle)
            digest = _material_digest(bundle)
            existing = self.conn.execute(
                "SELECT * FROM dependency_result_bundles WHERE task_id=?", (task.task_id,)
            ).fetchone()
            if existing is None:
                now = utc_now()
                self.conn.execute(
                    "INSERT INTO dependency_result_bundles(task_id,bundle_sha256,bundle_json,dependency_count,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (task.task_id, digest, encoded, len(bundle["materials"]), now, now),
                )
            elif (existing["bundle_sha256"] != digest or existing["bundle_json"] != encoded
                    or existing["dependency_count"] != len(bundle["materials"])):
                raise ValueError("durable dependency result bundle was modified or no longer matches accepted results")
            resolved = resolve_dependency_prompt_material(self.cfg, task)
            if not resolved:
                raise ValueError("dependency result bundle did not resolve")
            return True, "dependency result bundle verified"
        except (OSError, UnicodeError, ValueError, sqlite3.DatabaseError) as exc:
            return False, str(exc)

    def verify_dependency_bundle(self, task: Task) -> tuple[bool, str]:
        if task.inputs.get("bind_dependency_results") is not True:
            return True, "dependency-result binding not requested"
        try:
            expected = self._build_dependency_bundle(task)
            row = self.conn.execute(
                "SELECT * FROM dependency_result_bundles WHERE task_id=?", (task.task_id,)
            ).fetchone()
            if row is None or row["bundle_sha256"] != _material_digest(expected):
                raise ValueError("dependency result bundle identity/hash mismatch")
            if json.loads(row["bundle_json"]) != expected:
                raise ValueError("dependency result bundle does not match durable accepted results")
            resolve_dependency_prompt_material(self.cfg, task)
            return True, "dependency result bundle verified"
        except (OSError, UnicodeError, ValueError, sqlite3.DatabaseError) as exc:
            return False, str(exc)

    def _execution_complete(self, task: Task) -> bool:
        row = self.store.get(task.task_id)
        if row is not None and row["state"] == State.SUCCEEDED.value:
            return True
        if not task.is_llm:
            return False
        accepted = self.conn.execute(
            "SELECT result_json FROM accepted_results WHERE task_id=?", (task.task_id,)
        ).fetchone()
        if accepted is None:
            return False
        try:
            result = json.loads(accepted["result_json"])
        except (TypeError, json.JSONDecodeError):
            return False
        return result.get("retryable") is False and result.get("status") in {"SUCCEEDED", "FAILED"}

    def reconcile(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "DISABLED", "routes": 0, "reviews": 0}
        roles = self.sync_registry()
        lanes = self.sync_lanes()
        routed = reviews = 0
        for row in self.store.list_state():
            task = self.store.task(row)
            role_id = self._record_route(task, roles, lanes)
            routed += 1
            if task.inputs.get("review_required", False) is True:
                self._review(task, role_id)
                reviews += 1
        return {"status": "OPERATIONAL", "roles": len(roles), "lanes": len(lanes), "routes": routed, "reviews": reviews}

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"M2_PRODUCTION_ROUTING": "DISABLED"}
        return {
            "M2_PRODUCTION_ROUTING": "OPERATIONAL",
            "SPECIALIST_ROLE_ROUTING": "VERIFIED" if self.conn.execute("SELECT count(*) FROM specialist_roles").fetchone()[0] == 6 else "DEGRADED",
            "ROUTES": self.conn.execute("SELECT count(*) FROM task_routes").fetchone()[0],
            "REVIEWS": self.conn.execute("SELECT count(*) FROM review_requirements").fetchone()[0],
            "DEPENDENCY_RESULT_BUNDLES": self.conn.execute("SELECT count(*) FROM dependency_result_bundles").fetchone()[0],
            "RESOURCE_LANES": [dict(row) for row in self.conn.execute("SELECT * FROM resource_lanes ORDER BY cost_priority")],
            "MULTI_LANE_RESOURCE_ROUTING": "VERIFIED" if self.conn.execute("SELECT count(*) FROM resource_lanes").fetchone()[0] == 5 else "DEGRADED",
            "UNSUPPORTED_PERSISTENT_CHAT_AUTOMATION": False,
            "WORK_QUOTA_EXHAUSTION_DOES_NOT_STOP_PROJECT": True,
            "WORK_LANE_AUTO_RESUME": True,
            "NON_WORK_FALLBACK": "VERIFIED_IF_INTERFACE_AVAILABLE",
        }
