---
title: "CEF Dy - Project Control to Orchestrator authoring preflight"
type: protocol
status: current
version: "1.1"
updated: 2026-10-08
source_commit: 55f8ad3a8b6bdb42151532c10a08af5784f867aa
parent_semantic_task: ORCH-PC-AUTHORING-PREFLIGHT-IMPLEMENTATION-001
accepted_semantic_result_sha256: 5f1f1b5b6aaab6d24dc1657362d2310b48ccbb840ea9dce55477325e1b7230f0
parent_design_review: ORCH-PC-AUTHORING-PREFLIGHT-ARCH-001-REVIEW-001
---

# Project Control to Orchestrator authoring preflight

## Purpose and authority boundary

Project Control remains the governance authority; the preflight is a
deterministic consistency gate, not a decision maker. It validates a proposed
Issue/TASK operation against the same executable TASK schema, policy, role
aliases, and resource-suitability table used by CEF-Orch. It performs no
GitHub, repository, scheduler, worker, scientific, or SQLite mutation.

The persistent `00 - Project Control rN` chat remains **NON-WORK**. Repository
execution is routed to a separately authorized bounded execution context.
ChatGPT scheduled tasks/automations from persistent 00 are forbidden; they do
not become a second orchestration authority.

## Commands

```text
python scripts/orchestrate_tasks.py --config CONFIG authoring-manifest
python scripts/orchestrate_tasks.py --config CONFIG authoring-preflight REQUEST.yaml
```

`authoring-manifest` is derived from the executable constants. It inventories
TASK fields, task/action types, roles, lanes, suitability, operation types,
materialization states, and its own SHA-256. Before reading
`refs/remotes/origin/main`, `authoring-preflight` must successfully refresh
`origin/main`; an unavailable refresh fails closed, so a stale remote-tracking
ref is not proof of current GitHub main. Neither command opens the operational
database.

## Immutable identities and operations

Supported `operation_type` values are:

- `NEW_ISSUE`;
- `UPDATE_EXISTING`;
- `RERUN`;
- `SUPERSEDE`;
- `CLOSE`;
- `REOPEN`.

An existing Issue remains bound to its original TASK ID and envelope SHA-256.
Changing that envelope is rejected. `RERUN` and `SUPERSEDE` require a new TASK
identity plus an exact structured reference to the original TASK. The
preflight checks the configured Issue labels, canonical role, task/action
compatibility, resource requirement, allowed lanes, repository path scope,
review material, and dependency RESULT bindings.

Independent review material is bound by exact parent TASK, review TASK,
canonical review role, accepted RESULT SHA-256, and review-material SHA-256.
Dependencies with `bind_dependency_results=true` must have an exact one-to-one
set of successful, identity-bound RESULT records.

## Canonical state freshness and materialization debt

Every accepted state change has exactly one state:

- `MATERIALIZED`;
- `PENDING_MATERIALIZATION`;
- `EXPLICITLY_DEFERRED_WITH_REASON`;
- `NOT_STATE_CHANGING`.
- `UNRESOLVED_SOURCE_RECOVERY`.

The request list is not the debt authority. Before issuing a receipt, the
preflight loads `00_Project/CANONICAL_STATE_FRESHNESS.yaml` and
`00_Project/MATERIALIZATION_DEBT_LEDGER.yaml`, validates their exact assessed
HEAD and durable source identities, and intersects debt with the exact TASK
identity and repository path scope. Omitted known relevant debt fails closed.
Debt confined to an unrelated TASK/path does not become a project-wide block.
Relevant unresolved source recovery always fails closed.

`MATERIALIZED` requires an exact commit. Explicit deferral requires a reason.
Pending materialization without an exact reviewed context-delta bundle returns
`STATE_SYNC_REQUIRED`; that receipt is non-authorizing. A bundle is accepted
only when it exactly covers the pending identities, carries immutable hashes
and review identity, and preserves mandatory later materialization. The
receipt retains both the bundle ID/hash and exact review ID/result hash so the
authority can be reconstructed durably. This is a
bounded bridge, not a substitute for accepted-decision fast-follow.

## Durable receipt and dashboard projection

An authorizing receipt is deterministic and hash-bound to:

- the TASK envelope and canonical HEAD;
- the executable-interface manifest;
- the repository authority hash, assessed HEAD, observed HEAD, and exact
  relevant debt identities;
- Issue/operation identity;
- dependency and review material;
- materialization records and freshness;
- lifecycle disposition;
- `PROJECT_PROGRESS` and `HUMAN_ACTION_REQUIRED`;
- semantic, design, implementation, deployment, and canonicalization facets.

Validated receipts may later be appended to local operational state only
through the trusted local Project-Control Store integration. Receipt SHA-256
provides deterministic integrity, not cryptographic authentication or
task-provided authority. Receipts are immutable; a subsequent accepted
operation creates a new receipt. This task does not apply receipts to
production state.

Only a validated Project-Control receipt bound to the exact TASK ID, envelope,
operation/disposition, and explicit reason can mark a task `SUPERSEDED`,
`RETIRED`, or `CLOSED_HISTORICAL`. This overlay may classify a stranded
non-terminal FSM record as historical without rewriting its FSM or event
history. Issue closure, task payload hints, age, free text, and FSM state alone
cannot hide a current task. The dashboard keeps FSM
state separate from project progress and the semantic/design/implementation/
deployment/canonicalization facets. `HUMAN_ACTION_REQUIRED` is a separate
boolean and is never inferred solely from project progress.

## Failure behavior

Unknown/oversized fields, malformed TASK envelopes, HEAD drift, identity
rebinding, insufficient path scope, label/lane mismatch, incomplete review or
dependency material, receipt tampering, and stale relevant canonical state
fail closed. The preflight never creates an Issue, dispatches work, mutates
scientific state, accesses raw/holdout data, or deploys services.

## Verification

Focused coverage is in
`scripts/task_orchestrator/tests/test_authoring_preflight.py` and
`scripts/task_orchestrator/tests/test_repository_r2.py`, with CLI,
dashboard, Store, routing, and full-suite regression coverage recorded in
[the v2 matrix](TASK_ORCHESTRATOR_TEST_MATRIX_V2_0.md).
