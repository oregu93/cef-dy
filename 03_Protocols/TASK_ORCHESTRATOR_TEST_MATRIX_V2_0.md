---
title: "CEF Dy - production task orchestrator verification matrix"
type: validation_report
status: current_production_baseline
version: "2.0"
updated: 2026-10-03
source_commit: 55f8ad3a8b6bdb42151532c10a08af5784f867aa
---

# Production task orchestrator verification matrix

## Current accepted suite

The current candidate baseline is **208/208 PASS**. The count is the test inventory at
the source commit above; validators and compilation are reported separately.

| Module | Tests | Result |
|---|---:|---|
| `test_admission.py` | 7 | PASS |
| `test_authoring_preflight.py` | 16 | PASS |
| `test_chat_health.py` | 10 | PASS |
| `test_cli.py` | 2 | PASS |
| `test_dashboard_v2.py` | 22 | PASS |
| `test_m2_routing_dashboard.py` | 42 | PASS |
| `test_poll_lock_recovery.py` | 13 | PASS |
| `test_reliability.py` | 45 | PASS |
| `test_schema_policy.py` | 9 | PASS |
| `test_store_engine.py` | 20 | PASS |
| `test_visibility_publishing.py` | 16 | PASS |
| `test_workers.py` | 6 | PASS |
| **Total** | **208** | **PASS** |

## Production invariants covered

| Area | Accepted evidence |
|---|---|
| TASK/RESULT identity | strict schemas, duplicate idempotency, envelope conflict, accepted-result hashing |
| SQLite/WAL durability | restart, integrity, orphan recovery, leases, atomic result ingestion |
| GitHub control plane | paging, ETag polling, manual edits, close/reopen behavior, bounded outage/backoff |
| M1b execution | cycle lock, bounded claims, retry handling, crash recovery, no accepted-result rerun |
| M2 routing | canonical roles, deterministic-first lanes, dependency bundles, exact review creation |
| Quota | `QUOTA_WAIT`, bounded probes/backoff, automatic lane recovery, no retry-budget consumption |
| Publication | preview/live outbox, idempotency, ambiguous send reconciliation, conflict/forgery handling |
| Admission | visibility health, high-water/age guards, no queue amplification, anti-replacement rules |
| Recovery proof | two observations, restart reconstruction, direct Engine/CLI fail-closed behavior |
| Mandatory review | exact task/parent/role/result/material binding; alternative identity rejected |
| Authoring preflight | immutable Issue/TASK identity, operations, HEAD/label/lane/path compatibility, review/dependency/rerun/supersession bindings |
| State freshness | exact materialization states, non-authorizing debt receipt, exact reviewed context-delta bridge |
| Lifecycle/status | trusted append-only disposition, historical attention filtering, independent progress/action/FSM/facet projection |
| Chat/visibility | explicit observation only, stale/unknown behavior, re-entry and handoff projections |
| Dashboard regression | read-only access and existing dashboard behavior; Dashboard v2 deployment is deferred |

The suite includes adversarial coverage for forged task-provided diagnostic or
recovery authority, publication failure without worker rerun, current opaque
state overriding durable proof, paused admission across READY/waiting/retry
paths, and controller-only proof advancement.

## Repository validation gate

The baseline documentation candidate must additionally pass:

```text
python -m unittest discover -s scripts/task_orchestrator/tests -t scripts -v
python -m compileall -q scripts/task_orchestrator scripts/orchestrate_tasks.py
python scripts/kb_refresh.py --check
python scripts/kb_validate.py --strict
git diff --check
```

## Historical counts

The `307 PASS` aggregate and smaller orchestrator counts in
[v1](TASK_ORCHESTRATOR_TEST_MATRIX_V1_0.md) describe earlier shadow-era suites.
They are retained for provenance and must not be presented as the current
production test baseline.
