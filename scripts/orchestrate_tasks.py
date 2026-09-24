#!/usr/bin/env python3
"""CLI for the deterministic CEF Dy task orchestrator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import yaml

from task_orchestrator.config import load_config
from task_orchestrator.engine import Engine
from task_orchestrator.locking import LockBusy, ProcessLock
from task_orchestrator.model import ValidationError
from task_orchestrator.schema import validate_task
from task_orchestrator.store import Store
from task_orchestrator.visibility import QuotaSnapshot, QuotaWindow, project_board
from task_orchestrator.publishing import enqueue_result_preview
from task_orchestrator.chat_health import (
    explicit_health_observation,
    unknown_health_projection,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("poll-once", "run-ready", "status", "recover", "integrity-check"):
        sub.add_parser(name)
    sub.add_parser("board-preview")
    health = sub.add_parser("chat-health")
    health.add_argument("chat_id")
    health.add_argument("--logical-role", default="UNKNOWN")
    health.add_argument("--role", default="UNKNOWN")
    preview = sub.add_parser("publication-preview")
    preview.add_argument("result", type=Path)
    preview.add_argument("--target", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("task", type=Path)
    validate = sub.add_parser("validate-task")
    validate.add_argument("task", type=Path)
    for name in ("approve", "resume", "quota-pause"):
        cmd = sub.add_parser(name)
        cmd.add_argument("task_id")
    return p


def read_task(path: Path):
    try:
        return validate_task(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cfg = load_config(args.config.resolve())
        state_dir = Path(cfg["state_dir"])
        if args.command == "validate-task":
            task = read_task(args.task)
            print(json.dumps({"status": "VALID", "task_id": task.task_id, "payload_hash": task.payload_hash}, indent=2))
            return 0
        lock = ProcessLock(state_dir / "orchestrator.lock", int(cfg["lock_stale_after_seconds"]))
        with lock:
            store = Store(state_dir / "state.sqlite3")
            try:
                engine = Engine(cfg, store)
                if args.command == "ingest": result = {"status": engine.ingest(read_task(args.task))}
                elif args.command == "poll-once": result = engine.poll()
                elif args.command == "run-ready": result = {"results": engine.run_ready(), "llm_calls": 0}
                elif args.command == "approve": store.approve(args.task_id); engine.reevaluate_waiting(); result = {"status": "approved", "task_id": args.task_id}
                elif args.command == "resume": store.resume(args.task_id); result = {"status": "waiting_approval", "task_id": args.task_id}
                elif args.command == "quota-pause": engine.pause_quota(args.task_id); result = {"status": "PAUSED_QUOTA", "task_id": args.task_id}
                elif args.command == "recover": result = {"orphaned_recovered": engine.recover_orphans(), "cycles": engine.detect_cycles()}
                elif args.command == "status": result = engine.status()
                elif args.command == "board-preview":
                    quota_cfg = cfg["visibility"]["quota"]
                    quota = QuotaSnapshot(
                        QuotaWindow("five_hour", **quota_cfg["five_hour"]),
                        QuotaWindow("weekly", **quota_cfg["weekly"]),
                        int(cfg["visibility"]["quota_stale_after_seconds"]),
                    )
                    result = project_board(store, quota, now_epoch=time.time())
                elif args.command == "chat-health":
                    row = store.chat_health(args.chat_id)
                    if row:
                        result = explicit_health_observation(
                            json.loads(row["record_json"]),
                            now_epoch=time.time(),
                            stale_after_seconds=int(
                                cfg["chat_health"]["observation_stale_after_seconds"]
                            ),
                        )
                    else:
                        result = unknown_health_projection(
                            args.chat_id, args.logical_role, args.role, "UNKNOWN",
                            "1970-01-01T00:00:00Z", "UNKNOWN",
                        )
                elif args.command == "publication-preview":
                    result = enqueue_result_preview(
                        store, repository=cfg["github"]["repository"],
                        target=args.target, result_path=args.result.resolve(), preview_only=True,
                    )
                elif args.command == "integrity-check": store.integrity_check(); result = {"status": "PASS"}
                else: raise AssertionError(args.command)
                engine.write_summary()
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            finally:
                store.close()
    except (ValidationError, LockBusy, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
