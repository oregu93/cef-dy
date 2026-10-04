---
title: "CEF Dy - production task orchestrator contract"
type: protocol
status: current_production_authority
version: "2.0"
updated: 2026-10-03
source_commit: 55f8ad3a8b6bdb42151532c10a08af5784f867aa
---

# Production task orchestrator contract

## Authority and boundaries

The local SQLite database and its WAL are the operational authority for task
state, events, leases, routes, results, publication outbox state, and recovery
proof. GitHub Issues are the external task/control-plane source and a
human-readable projection; they do not replace durable local state or grant
scientific authority. Canonical Git remains the authority for project code and
governance.

The production entry point is `cycle-once`. It runs the M1b reliability
controller and the additive M2 routing layer. The controller may execute only
an already-authorized TASK envelope. It cannot make scientific or strategic
decisions, promote a result, change stages, enable exchange, admit Structure-A
execution, or access raw/private/holdout data. Those decisions remain with
humans and Project Control.

## Execution and resource lanes

M2 routes work across `LOCAL_DETERMINISTIC`, `LOCAL_OSS_MODEL`, `NON_WORK_AI`,
`WORK_CODEX`, and `HUMAN_DECISION`. A route is an eligibility decision, not an
authorization. Disabled or unverified machine interfaces remain unavailable,
and persistent chats are not autonomous workers.

Work/Codex admission exhaustion moves the Work/Codex lane to `QUOTA_WAIT`.
With M2 routing enabled, affected tasks wait in `WAITING_RESOURCE`; the legacy
non-routing path may use task state `QUOTA_WAIT`. A bounded, deterministic quota
probe uses configured backoff and may restore the lane after successful
admission, after which routing and admission gates determine whether affected
work can become executable. Quota exhaustion does not consume the task retry
budget. It does not authorize a different lane, paid fallback, concurrent LLM
expansion, or scientific execution.

## Accepted results and publication

An accepted RESULT is identity-bound to its TASK and attempt and is persisted
before external publication. Publication uses a durable idempotent outbox and
live GitHub comment transport only when explicitly enabled. `PENDING` and
`SENDING` are reconciled; ambiguous delivery becomes `UNKNOWN`, never a blind
retry. `CONFLICT`, `FAILED`, missing required publication identity, or another
opaque state closes ordinary admission.

Publication-only recovery never reruns an accepted worker result. The accepted
RESULT bytes and SHA-256 remain authoritative while the controller reconciles
or republishes only the projection. Historical `PREVIEW` entries are shadow
evidence, not proof of live acknowledgement and not by themselves a permanent
breaker after live activation.

## Defect-aware admission and backpressure

The controller projects one of three visibility states:

- `AUTONOMY_VISIBILITY_OK`;
- `AUTONOMY_VISIBILITY_DEGRADED`;
- `ADMISSION_PAUSED_OPAQUE_STATE`.

Ordinary autonomous enrollment requires a capable publication path. Disabled
publishing or preview-only mode in a live ordinary-autonomy configuration
immediately pauses new ordinary admission. New ordinary source tasks are not
persisted while paused, preventing deferred-queue amplification. Existing
ordinary work cannot be newly promoted, claimed, retried, or orphan-recovered
into execution while the gate is closed.

The derived guards are:

```text
UNPROJECTED_TERMINAL_HIGH_WATER = max(2, 2 * autonomy.max_batch_tasks)
UNPROJECTED_TERMINAL_MAX_AGE    = max(600 s, 2 * poll_interval_seconds)
OUTBOX_REQUIRED_HIGH_WATER      = 4 * UNPROJECTED_TERMINAL_HIGH_WATER
```

Only unresolved, required lifecycle identities count. Opaque publication
states, required backlog, and age are reconstructed from SQLite after restart;
there is no in-memory-only breaker authority.

## Recovery proof

Every live-capable Engine is fail-closed by default. Ordinary execution needs
both durable proof and currently healthy visibility:

```text
NOT_PROVEN -> ONE_HEALTHY_OBSERVATION -> PROVEN
```

The second healthy observation must occur after the configured observation
interval. Missing, malformed, or intermediate proof blocks ordinary work.
Durable `PROVEN` does not override a current opaque, unknown, conflicting,
failed, sending, or missing-projection condition.

Only the reviewed controller reconciliation path advances proof. Direct Engine
and CLI entry points (`poll-once`, `ingest`, `run-ready`, `approve`, and orphan
recovery) may consume valid durable proof but cannot create or advance it.
Restart reconstructs proof and visibility from durable state.

## Bounded exceptions

During a pause, an exact mandatory review can proceed only when all registered
bindings agree: review task ID, parent task ID, canonical review role, accepted
parent RESULT SHA-256, and review-material hash. An alternative review identity
is rejected even when it cites the correct parent result.

A task cannot grant itself `DIAGNOSTIC` or `RECOVERY` authority through its
inputs, labels, or free text. Controller-native health, reconciliation, and
lease recovery remain infrastructure operations; there is no task-provided
bypass or replacement identity for an unresolved accepted result.

## Restart and failure semantics

Each cycle restores uncertain sends, reconciles publication, recomputes
visibility, advances recovery proof only through the reviewed path, polls the
control plane, reconciles M2 routing, probes eligible quota lanes, reevaluates
waiting work, and dispatches only after all gates pass. SQLite integrity errors,
source outages, route failure, missing authority, and malformed evidence fail
closed. The controller retains accepted evidence and never rewrites scientific
state to recover infrastructure.

## Project-Control authoring preflight

Consequential Issue/TASK authoring is checked by the deterministic
[authoring preflight](TASK_ORCHESTRATOR_AUTHORING_PREFLIGHT_V1_0.md). Its
interface manifest is derived from this executable implementation's TASK
schema, policy, canonical role aliases, actions, lanes, and routing suitability
table. It validates immutable Issue/TASK identity, operation type, canonical
HEAD, labels, repository scope, dependency and review RESULT bindings,
rerun/supersession links, and materialization state before authoring proceeds.

Accepted state changes use exactly `MATERIALIZED`,
`PENDING_MATERIALIZATION`, `EXPLICITLY_DEFERRED_WITH_REASON`, or
`NOT_STATE_CHANGING`. Relevant unbound materialization debt returns the
non-authorizing `STATE_SYNC_REQUIRED`; an exceptional context-delta bridge must
be identity/hash/review bound and preserve later materialization.

Validated Project-Control receipts provide an append-only lifecycle and status
overlay. Only that exact TASK/envelope/operation-bound structured authority
may classify a TASK, including a stranded non-terminal FSM record, as
`SUPERSEDED`, `RETIRED`, or `CLOSED_HISTORICAL`. The overlay does not rewrite
FSM/event history. Issue closure, payload hints, age, free text, and FSM state
alone cannot suppress current attention. Receipt SHA-256 proves integrity, not
caller authentication; application remains a trusted local Project-Control
operation. FSM state remains distinct
from `PROJECT_PROGRESS`, `HUMAN_ACTION_REQUIRED`, and semantic, design,
implementation, deployment, and canonicalization facets.

The persistent Project-Control chat remains NON-WORK and cannot authorize a
ChatGPT scheduled task/automation. Bounded implementation continues only in a
separate explicitly authorized execution context.

## Optional Telegram attention transport

The reviewed implementation candidate is specified by the
[Telegram attention gateway protocol](TELEGRAM_ATTENTION_GATEWAY_V1_0.md).
It is an optional disabled-by-default projection adapter over the same SQLite
authority. It uses private exact-ID allowlisting, durable `update_id`
idempotency, at-least-once delivery with `SEND_OUTCOME_UNKNOWN`, atomic
first-valid-response-wins, and explicit non-authoritative USER provenance.
Configuration alone never proves gateway health: the dashboard consumes only a
fresh explicit `TELEGRAM_GATEWAY` controller observation. Independent review
and separate deployment authorization are required before activation.

## Current references

- [Infrastructure Baseline v1](../00_Project/INFRASTRUCTURE_BASELINE_V1.md)
- [Task Orchestrator Test Matrix v2.0](TASK_ORCHESTRATOR_TEST_MATRIX_V2_0.md)
- [Chat bootstraps](CHAT_BOOTSTRAPS.md)
- [Project-Control authoring preflight](TASK_ORCHESTRATOR_AUTHORING_PREFLIGHT_V1_0.md)

The v1 contract remains available as
[historical provenance](TASK_ORCHESTRATOR_CONTRACT_V1_0.md); it is not current
production authority.
