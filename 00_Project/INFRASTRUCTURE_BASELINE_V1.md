---
title: "CEF Dy - Infrastructure Baseline v1"
type: operations_baseline
status: current_production_baseline
version: "1.0"
updated: 2026-10-02
source_head: 25adb37daa28550291e590a1cd2265281570f37e
source_tree: e1488ae7c222f14cfbc58db8bb7ee7a61371d700
replacement_authorization: "Issue #26 comment 5943786794"
---

# Infrastructure Baseline v1

## Current facade

| Item | Current baseline |
|---|---|
| Production contract | [Task Orchestrator Contract v2.0](../03_Protocols/TASK_ORCHESTRATOR_CONTRACT_V2_0.md) |
| Verification matrix | [Task Orchestrator Test Matrix v2.0](../03_Protocols/TASK_ORCHESTRATOR_TEST_MATRIX_V2_0.md) |
| Accepted test inventory | 188/188 PASS |
| Production controller | `cycle-once`, M1b reliability plus M2 routing |
| Operational authority | local SQLite database and WAL |
| External control plane | GitHub Issues; not scientific authority |
| Publishing | live, durable, idempotent result-comment outbox |
| Recovery proof | `PROVEN`; current visibility must also be `AUTONOMY_VISIBILITY_OK` |
| Ordinary admission | technically open when both proof and current health remain valid |

The `PROVEN` and ordinary-admission statements are the accepted production
checkpoint reported in Issue #26/#32. They are not permanent configuration
facts: every cycle recomputes current visibility, and any opaque material state
closes ordinary admission.

## Authority boundaries

- SQLite/WAL owns operational FSM, leases, routes, accepted results, outbox,
  and recovery proof.
- GitHub Issues provide source envelopes and external projection. They cannot
  authorize science, raw/holdout access, repository writes, or stages.
- systemd provides timer/service activation only. The controller retains all
  admission and execution policy.
- canonical Git owns code and governance. Scientific and strategic authority
  remains human and Project Control.

## Sanitized production identity

The accepted non-secret required-flag manifest is:

```json
{"autonomy.enabled":true,"autonomy.plan_only":false,"github.enabled":true,"mode":"pilot","poll_interval_seconds":120,"publishing.enabled":true,"publishing.preview_only":false,"routing.enabled":true}
```

Manifest SHA-256:
`cdb3d8041699258a3d0aeb35ff48c64b88c84d2475c4fa49e6705f250119c526`.

The raw machine-local production configuration identity is `NOT_CAPTURED` in
this review environment. No credential, token, environment value, or private
path was copied into this baseline.

Canonical tracked deployment units at the source tree:

| Unit | Git blob | SHA-256 |
|---|---|---|
| `systemd/cef-dy-orchestrator.service` | `ea97aa17a799c619bc8a67b3ecf9421a6c114774` | `53d3985124ecb28c316521c9a356991c9a15425359d2e4b2ea8f080d2577a9ed` |
| `systemd/cef-dy-orchestrator.timer` | `6940ca9b2e6a6007c9c91d79ff406019e1535263` | `74e734069598c854b6ef592f4982fcbca9a46112a34d3502f0d5b600d283030e` |

Installed/effective host unit hashes are `NOT_CAPTURED`. The tracked timer
requests one-shot activation one minute after the prior unit becomes inactive,
with up to ten seconds randomized delay; controller logic uses
`poll_interval_seconds: 120` for observation and recovery policy. These are
different clocks and must not be described as identical cadence.

## Deferred, non-blocking components

- Dashboard v2 (Issue #27) is deferred and is not part of this baseline.
- Telegram transport remains unactivated.
- Gate-E remains deferred.
- specialist context-continuity expansion remains deferred.
- M3/voice remains deferred.

None of these components blocks ordinary scientific operation through the
accepted production controller. Their absence does not grant any new authority.

## Control-plane cleanup

Issue #26 remains the infrastructure-convergence umbrella. Completed
infrastructure records may be closed after Project Control review; the deferred
Dashboard/WAL review branch retains unique unmaterialized work and is not part
of this baseline. Cleanup of remote branches or Issues is not performed by this
documentation task.

## Historical checkpoints

The v1 contract's shadow-only rules, explicit manual quota resume, `307 PASS`
aggregate, old `SHADOW_READY` verdict, earlier deployment-candidate branches,
and the abandoned local documentation draft are historical evidence. They must
not be interpreted as live production status. Current authority is the v2
contract and matrix linked above.
