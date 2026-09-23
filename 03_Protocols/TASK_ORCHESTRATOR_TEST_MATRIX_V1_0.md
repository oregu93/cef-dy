---
title: "CEF Dy - task orchestrator verification matrix"
type: validation_report
status: shadow_ready_not_production_authorized
version: "1.0"
updated: 2026-09-23
baseline_commit: 46fa52555f39408acef67a8052438e64e49c2bc5
---

# Task orchestrator verification matrix

This report covers the orchestrator feature in the canonical local checkout.
Feature commits are local only. No push, GitHub mutation, systemd installation,
scientific execution, stage transition, raw-data access, or private-repository
write was performed.

| Risk / requirement | Verification | Result |
|---|---|---|
| malformed / partial / unknown TASK fields | strict parser negative tests | PASS |
| large / odd fields and NUL / invalid IDs | bounds and randomized path fuzz (500 inputs) | PASS |
| duplicate delivery / repeated polling | payload hash and duplicate event tests | PASS |
| task ID reused with changed payload | identity conflict test | PASS |
| restart / durable recovery | SQLite reopen and integrity test | PASS |
| interrupted summary write | injected `os.replace` failure preserves old file | PASS |
| stale / concurrent lock | live lock denial and dead-PID stale rotation | PASS |
| concurrent workers | global process lock + bounded worker batch | PASS at unit boundary; real multi-process soak pending |
| dependency wait / failure / cycle | transition and graph-cycle tests | PASS |
| HEAD / origin drift | exact full-SHA worker tests | PASS |
| unauthorized paths/actions | traversal, absolute, forbidden tree, allowlist tests | PASS |
| GitHub/network outage | fail-closed source error and exponential backoff | PASS |
| rate limiting | bounded backoff math; `Retry-After` captured in error | PASS; live GitHub observation pending |
| corrupted local state | invalid SQLite detection and non-destructive quarantine copy | PASS |
| missing artifact / SHA mismatch | deterministic worker negative tests | PASS |
| timeout / non-zero worker exit | allowlisted subprocess tests | PASS |
| worker crash / orphaned RUNNING | injected crash plus age-based recovery | PASS |
| quota exhaustion | explicit `PAUSED_QUOTA` transition | PASS |
| quota reset cannot auto-resume | reevaluation leaves `PAUSED_QUOTA` unchanged | PASS |
| unexpected orchestrator labels | rejected before ingestion | PASS |
| manually created web Issue | discovered and ingested through ordinary polling | PASS |
| GitHub Issue Form compatibility | tracked form emits one required fenced YAML TASK envelope | PASS |
| CLI status observability | status reports durable task state without worker/LLM execution | PASS |
| manual title/comment activity | snapshot diff and event; no command execution | PASS |
| manual TASK body edit | envelope conflict and `WAITING_APPROVAL` | PASS |
| manual close / task-label removal | non-terminal task paused | PASS |
| manual approval-label edit | labels synchronized; local gate preserved | PASS |
| closed-Issue visibility | `state=all`, local label filtering | PASS |
| idempotent replay | same task/payload is a no-op with event | PASS |
| manual LLM gates | issue label + local approval + pilot feature flag required | PASS |
| automatic paid/OpenAI fallback | forbidden config invariant; no OpenAI/Codex call surface | PASS |
| 24/7 idle behavior | 100 repeated unchanged polls report `llm_calls: 0` | PASS in simulated source; long-duration soak pending |
| optional Ollama | loopback-only adapter; disabled/unset by default | PASS by inspection; live model not required |
| rollback / recovery | ignored state isolation and worktree removal procedure | PASS by design; operator drill pending |

## Executed suites

- New orchestrator suite: 37 tests PASS.
- Existing Structure-A suites: 38 tests PASS.
- Existing Zotero/literature suites: 136 tests PASS.
- Existing Stage03R compatibility suite: 26 tests PASS.
- Existing Scientific Understanding selftest: 39 tests PASS.
- Existing Work recovery selftest: 31 cases PASS.
- `kb_refresh.py --check`: `REENTRY_OK`.
- `kb_validate.py --strict`: 0 errors, 0 warnings.
- Python bytecode compilation: PASS.
- Real public GitHub SHADOW poll at baseline/origin `46fa525`: 0 accepted,
  0 rejected, 0 duplicates, `llm_calls: 0`; no matching open Issues existed.
- Immediate repeated real poll returned `unchanged` through ETag handling with
  `llm_calls: 0`.
- Post-migration all-state SHADOW polling and SQLite integrity check: PASS;
  repeated polls remained `unchanged` with `llm_calls: 0`.

Total explicitly reported test cases: 307 PASS. Validators are reported
separately because they are repository checks rather than unit-test cases.

## Remaining evidence required before production

1. Read-only shadow observation with a deliberately labelled real test Issue,
   plus a natural or injected live rate-limit response.
2. At least 24 hours of timer-driven shadow soak with event/CPU/network review.
3. Multi-process contention soak and service restart drill on the target host.
4. Manual corruption/restore and rollback drill using a copied state directory.
5. Project Control review of this contract and an exact bounded pilot envelope.

Verdict: `SHADOW_READY`; `PRODUCTION_NOT_AUTHORIZED`.
