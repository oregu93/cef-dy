---
title: "CEF Dy - local task orchestrator contract"
type: protocol
status: draft_for_shadow_validation
version: "1.0"
updated: 2026-09-22
---

# Local task orchestrator contract

## Purpose and authority

The orchestrator is a deterministic infrastructure component. GitHub Issues is
transport/control-plane input; canonical project authority remains the public
`oregu93/cef-dy` repository and the documents named by `PROJECT_MANIFEST.yaml`.
ChatGPT chats `00/01/03/04/07` are human-facing contexts and are never treated as
programmatically addressable workers.

The orchestrator MUST NOT make scientific decisions, promote results, change a
scientific stage, access holdout/raw data, or write to canonical governance and
scientific files. A GitHub label is not sufficient authority for a repository
write, commit, push, scientific execution, or stage transition.

## Cost boundary

The polling and deterministic worker loop contains no OpenAI API call and no
automatic Codex/Work dispatch. `llm.dispatch_enabled` defaults to `false`, paid
fallback is forbidden, and `max_concurrent_llm_runs` is fixed at one or less.
Quota exhaustion enters `PAUSED_QUOTA`. Time passing or quota reset never resumes
that state. Resume requires both the configured approval label and a new local
`approve` followed by `resume` action.

Optional Ollama use is a semantic helper only. It is feature-flagged, loopback by
default, never required by core tests, and cannot change task state or execute a
worker action by itself.

## State machine

```text
RECEIVED -> VALIDATED -> READY -> RUNNING -> SUCCEEDED
                  |        |         |          |-> FAILED
                  |        |         |          |-> PAUSED_QUOTA
                  |        |         |-> WAITING_APPROVAL
                  |        |-> WAITING_DEPENDENCY
                  |-> REJECTED

WAITING_DEPENDENCY -> READY | BLOCKED
WAITING_APPROVAL   -> READY | BLOCKED
PAUSED_QUOTA       -> WAITING_APPROVAL  (explicit local resume only)
orphaned RUNNING   -> READY              (deterministic jobs only)
orphaned RUNNING   -> WAITING_APPROVAL   (LLM-class jobs)
```

Terminal states are `SUCCEEDED`, `FAILED`, `REJECTED`, and `BLOCKED`. Re-delivery
of the same `task_id` and canonical payload hash is a no-op. A different payload
for an existing `task_id` is rejected as an identity conflict. All accepted
transitions and operator actions are appended to a durable SQLite event log.

## TASK envelope

Issue bodies contain one fenced `yaml` block with this shape. Unknown fields fail
closed.

```yaml
schema_version: 1
task_id: INFRA-EXAMPLE-001
role: 07_INFRASTRUCTURE
canonical_head: 0123456789abcdef0123456789abcdef01234567
task_type: deterministic
action: head_check
dependencies: []
inputs: {}
allowed_paths: []
expected_artifacts: []
timeout_seconds: 60
stop_condition: Return after the check; do not modify repository files.
```

Supported deterministic actions are `head_check`, `sha256_check`,
`schema_check`, `dependency_check`, `status_check`, `artifact_check`, and
allowlisted `test_command`. Paths are repository-relative, normalized, cannot
escape the repository, and are checked against configured forbidden patterns.

## RESULT envelope

```yaml
schema_version: 1
task_id: INFRA-EXAMPLE-001
attempt: 1
status: SUCCEEDED
canonical_head: 0123456789abcdef0123456789abcdef01234567
worker: head_check
started_at: 2026-09-22T00:00:00Z
finished_at: 2026-09-22T00:00:01Z
checks: []
artifacts: []
error: null
```

Results and Project Control summaries are local operational artifacts under the
ignored state directory. They do not alter `PROJECT_CONTROL`, `PROJECT_STATE`,
registers, checkpoints, or scientific results. Summary publication into a chat
or canonical file is a separate human-controlled action.

## Deployment gates

1. Unit, integration, transition, failure and recovery suites PASS.
2. `shadow` mode against real issue metadata; no GitHub mutation and no task
   execution that changes scientific state.
3. Review event log, rejected inputs, rate-limit behavior, path denials, and the
   explicit assertion that no OpenAI/Codex endpoint or executable is reachable.
4. A separately authorized bounded pilot may use only a low-risk
   `07 Infrastructure -> deterministic Work -> 07 review -> 00 Project Control`
   path. Production mode and repository writes remain out of scope until that
   review grants exact-path authority.

## Shadow installation and operation

Run from the reviewed repository checkout. Do not install the timer until the
local config has been reviewed.

```text
cp configs/task_orchestrator.example.yaml configs/task_orchestrator.yaml
python scripts/orchestrate_tasks.py --config configs/task_orchestrator.yaml integrity-check
python -m unittest discover -s scripts/task_orchestrator/tests -t scripts -v
python scripts/orchestrate_tasks.py --config configs/task_orchestrator.yaml poll-once
```

For real read-only shadow polling, set only `github.enabled: true`; keep
`mode: shadow` and `llm.dispatch_enabled: false`. A public repository can be
read without a token at the lower GitHub rate limit. If a token is used, it is
read from `GITHUB_TOKEN`, never from tracked configuration, and should be a
fine-grained read-only Issues token.

Optional user-systemd installation after review:

```text
mkdir -p ~/.config/systemd/user
cp systemd/cef-dy-orchestrator.service ~/.config/systemd/user/
cp systemd/cef-dy-orchestrator.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cef-dy-orchestrator.timer
systemctl --user status cef-dy-orchestrator.timer
```

The supplied unit is a one-shot poller. `Persistent=false` prevents a backlog of
missed polls after downtime. The service has no permission to write outside the
ignored local state directory.

## Rollback

Stop and disable the timer first. State deletion is not required for rollback;
rename it so event history remains recoverable.

```text
systemctl --user disable --now cef-dy-orchestrator.timer
mv CEF_Dy_Backup/task_orchestrator CEF_Dy_Backup/task_orchestrator.rollback-YYYYMMDDTHHMMSSZ
rm ~/.config/systemd/user/cef-dy-orchestrator.service
rm ~/.config/systemd/user/cef-dy-orchestrator.timer
systemctl --user daemon-reload
```

Repository rollback is a normal review of the feature diff followed by removal
of the feature commit/branch or worktree. Never use destructive reset/clean in a
dirty canonical checkout. No GitHub state needs rollback because this adapter is
read-only.
