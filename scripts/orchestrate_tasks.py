#!/usr/bin/env python3
"""CLI for the deterministic CEF Dy task orchestrator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
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
from task_orchestrator.autonomy import (
    AutonomyError, build_plan, checkpoint_status, disabled_result,
    open_readonly_database, publish_checkpoint, verify_git_identity,
)
from task_orchestrator.reliability import M1bController, M1bStore
from task_orchestrator.dashboard import serve as serve_dashboard
from task_orchestrator.authoring import (
    interface_manifest, preflight_authoring, reconcile_repository_renewal_r1,
)
from task_orchestrator.telegram import TelegramBotAPI, TelegramGateway, TelegramSecrets


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    sub = p.add_subparsers(dest="command", required=True)
    for name in (
        "poll-once", "run-ready", "status", "recover", "integrity-check",
        "autonomy-plan", "autonomy-status", "cycle-plan", "cycle-once",
        "reliability-status",
        "dashboard-serve",
        "telegram-serve",
        "authoring-manifest",
    ):
        sub.add_parser(name)
    worker_once = sub.add_parser("worker-once")
    worker_once.add_argument("task_id")
    worker_once.add_argument("attempt_id")
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
    authoring = sub.add_parser("authoring-preflight")
    authoring.add_argument("request", type=Path)
    renewal = sub.add_parser("repository-renewal-r1-reconcile")
    renewal.add_argument("--authority-id", required=True)
    renewal.add_argument("--authority-result-sha256", required=True)
    renewal.add_argument("--dry-run", action="store_true")
    for name in ("approve", "resume", "quota-pause"):
        cmd = sub.add_parser(name)
        cmd.add_argument("task_id")
    return p


def read_task(path: Path):
    try:
        return validate_task(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(str(exc)) from exc


def read_mapping(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("input document must be a mapping")
    return value


def observed_origin_main(repo: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "refs/remotes/origin/main"], cwd=repo,
            capture_output=True, text=True, timeout=10, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"canonical Git identity unavailable: {exc}") from exc
    value = proc.stdout.strip()
    if proc.returncode != 0 or len(value) != 40:
        raise ValidationError("canonical Git identity unavailable")
    return value


def refreshed_origin_main(repo: Path) -> str:
    """Refresh the canonical remote-tracking ref before authoring proof.

    A pre-existing refs/remotes/origin/main value is not evidence that GitHub
    main is current.  Failure to refresh is therefore a fail-closed preflight
    error rather than permission to continue from stale local metadata.
    """
    try:
        proc = subprocess.run(
            ["git", "fetch", "--no-tags", "origin", "main"], cwd=repo,
            capture_output=True, text=True, timeout=30, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"canonical Git refresh failed: {exc}") from exc
    if proc.returncode != 0:
        raise ValidationError("canonical Git refresh failed")
    return observed_origin_main(repo)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cfg = load_config(args.config.resolve())
        state_dir = Path(cfg["state_dir"])
        if args.command == "authoring-manifest":
            print(json.dumps(interface_manifest(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "authoring-preflight":
            result = preflight_authoring(
                read_mapping(args.request), cfg,
                observed_canonical_head=refreshed_origin_main(Path(cfg["repository_root"])),
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["status"] == "PREFLIGHT_PASS" else 3
        if args.command == "dashboard-serve":
            serve_dashboard(cfg)
            return 0
        if args.command == "telegram-serve":
            if not cfg["telegram"]["enabled"]:
                raise ValidationError("Telegram gateway is disabled")
            secrets = TelegramSecrets.from_environment(cfg)
            store = Store(state_dir / "state.sqlite3")
            try:
                transport = TelegramBotAPI(
                    secrets, api_base=cfg["telegram"]["api_base"],
                    timeout_seconds=int(cfg["telegram"]["request_timeout_seconds"]),
                )
                TelegramGateway(cfg, store.conn, transport, secrets).run_forever()
                return 0
            finally:
                store.close()
        if args.command == "autonomy-status":
            print(json.dumps(checkpoint_status(cfg), indent=2, ensure_ascii=False))
            return 0
        if args.command == "autonomy-plan" and not cfg["autonomy"]["enabled"]:
            print(json.dumps(disabled_result(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "validate-task":
            task = read_task(args.task)
            print(json.dumps({"status": "VALID", "task_id": task.task_id, "payload_hash": task.payload_hash}, indent=2))
            return 0
        if args.command == "worker-once":
            store = Store(state_dir / "state.sqlite3")
            try:
                result = M1bController(cfg, store).run_leased_ai(args.task_id, args.attempt_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            finally:
                store.close()
        lock = ProcessLock(state_dir / "orchestrator.lock", int(cfg["lock_stale_after_seconds"]))
        with lock:
            if args.command == "autonomy-plan":
                head = verify_git_identity(Path(cfg["repository_root"]))
                conn = open_readonly_database(state_dir / "state.sqlite3")
                try:
                    result = publish_checkpoint(cfg, build_plan(cfg, conn, head))
                finally:
                    conn.close()
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            store = Store(state_dir / "state.sqlite3")
            try:
                if args.command == "repository-renewal-r1-reconcile":
                    result = reconcile_repository_renewal_r1(
                        store, cfg,
                        observed_canonical_head=refreshed_origin_main(
                            Path(cfg["repository_root"])
                        ),
                        authority_id=args.authority_id,
                        authority_result_sha256=args.authority_result_sha256,
                        dry_run=args.dry_run,
                    )
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 0
                engine = Engine(cfg, store)
                if args.command == "reliability-status":
                    print(json.dumps(M1bStore(store.conn, cfg).status(), indent=2, ensure_ascii=False))
                    return 0
                if args.command == "cycle-once":
                    result = M1bController(cfg, store).cycle()
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 0
                if args.command == "cycle-plan":
                    poll = engine.poll()
                    if poll.get("status") not in {"ok", "unchanged", "disabled"}:
                        raise AutonomyError("PLAN_SUPPRESSED_SOURCE_UNAVAILABLE")
                    if not cfg["autonomy"]["enabled"]:
                        result = {"poll": poll, "plan": disabled_result()}
                    else:
                        head = verify_git_identity(Path(cfg["repository_root"]))
                        result = {"poll": poll, "plan": publish_checkpoint(
                            cfg, build_plan(cfg, store.conn, head)
                        )}
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 0
                if args.command == "ingest": result = {"status": engine.ingest(read_task(args.task))}
                elif args.command == "poll-once": result = engine.poll()
                elif args.command == "run-ready": result = {"results": engine.run_ready(), "llm_calls": 0}
                elif args.command == "approve": store.approve(args.task_id); engine.reevaluate_waiting(); result = {"status": "approved", "task_id": args.task_id}
                elif args.command == "resume": store.resume(args.task_id); result = {"status": "waiting_approval", "task_id": args.task_id}
                elif args.command == "quota-pause": engine.pause_quota(args.task_id); result = {"status": "QUOTA_WAIT", "task_id": args.task_id}
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
    except (ValidationError, LockBusy, RuntimeError, ValueError, AutonomyError) as exc:
        print(json.dumps({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
