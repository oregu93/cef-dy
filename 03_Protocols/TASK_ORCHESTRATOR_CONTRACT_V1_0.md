---
title: "CEF Dy - local task orchestrator contract"
type: protocol
status: superseded_historical
version: "1.0"
updated: 2026-09-23
superseded_by: TASK_ORCHESTRATOR_CONTRACT_V2_0.md
---

# Local task orchestrator contract

> Historical provenance only. This contract records the v1 shadow-era design
> and is not current production authority. See
> [TASK_ORCHESTRATOR_CONTRACT_V2_0](TASK_ORCHESTRATOR_CONTRACT_V2_0.md).

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

The orchestrator does not generate separate user-facing handoff reports by
default. Durable operational evidence is the SQLite event log, RESULT files and
the compact PC inbox. A Markdown report is created only when explicitly needed
for canonical review or requested by the user.

## Manual GitHub web changes

GitHub web UI and API changes are equivalent external inputs. Polling uses
`state=all` and local filtering so it can observe newly labelled tasks, manual
label removal, closing/reopening, title/body edits and comment-count changes.

- A newly created, correctly labelled Issue is ingested normally.
- Title changes and comment activity are recorded as `ISSUE_WEB_CHANGE`; comment
  text is not interpreted as an executable command.
- Labels are synchronized. Adding or removing the LLM approval label updates the
  approval gate, but never replaces the required local approval/resume action.
- Removing the task label or closing the Issue pauses a non-terminal task in
  `WAITING_APPROVAL`.
- Changing a previously ingested TASK envelope is never applied silently. The
  envelope hash conflict is logged and the task is paused for review.
- Changing `TASK_ID` in place is rejected. A materially revised or completed
  task uses a new task ID according to the rerun/dedup governance rules.
- Reopening or reverting an Issue does not silently resume execution.

The issue timeline is a human-readable projection, not canonical scientific
authority. Manual web activity cannot authorize repository writes, scientific
execution, stage transitions, raw/holdout access or LLM dispatch.

The repository provides `.github/ISSUE_TEMPLATE/orchestrator_task.yml` for
manual creation through the GitHub web UI. Its required textarea is rendered as
the single fenced YAML block accepted by the parser. Before using the form, the
repository maintainer creates the `orchestrator:task` label once if it does not
already exist; GitHub does not create labels merely because a template names
them. Blank and ordinary scientific/project Issues remain outside orchestrator
scope unless that label is deliberately applied.

## Bounded OSS design review

The implementation was compared with GitHub Issue Forms/IssueOps, OpenAI
Symphony, Probot, Dagu, Dagster and Temporal. The review produced these choices:

- Adopt the Symphony separation between tracker adapter, coordination policy,
  execution worker and observability, plus bounded concurrency, reconciliation,
  explicit claims and backoff. Do not adopt its automatic coding-agent runner:
  this project's default loop must make zero LLM calls and quota reset must not
  cause dispatch.
- Adopt GitHub Issue Forms only as a human-entry aid. Keep the canonical TASK
  schema, strict local validation, snapshot deduplication and event history.
  Comments remain discussion, never commands.
- Keep polling as the first deployment mode. A future webhook receiver must
  verify signatures, validate event/action, deduplicate `X-GitHub-Delivery`,
  respond quickly and enqueue work rather than execute it in the request.
- Defer Probot and GitHub App infrastructure until authenticated GitHub writes
  are explicitly authorized. They add a public webhook, credentials and another
  runtime without improving the current read-only shadow gate.
- Do not add Dagu, Dagster, Prefect or Temporal now. Their scheduling, UI and
  recovery features are useful at larger scale, but would duplicate a small
  durable SQLite finite-state machine and expand the failure/dependency surface.
  Re-evaluate only if multiple hosts, many heterogeneous workflows or a shared
  operational UI become actual requirements.

This review is a design decision inside the canonical contract, not a separate
user-facing handoff report.

Primary references reviewed:

- [GitHub Issue Form syntax](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)
- [GitHub webhook best practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks)
- [IssueOps organization](https://github.com/issue-ops)
- [OpenAI Symphony specification](https://github.com/openai/symphony/blob/main/SPEC.md)
- [Probot documentation](https://probot.github.io/docs/README/)
- [Dagu repository](https://github.com/dagucloud/dagu)
- [Dagster OSS webserver and daemon](https://docs.dagster.io/guides/operate/webserver)
- [Temporal documentation](https://docs.temporal.io/)

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
