# ORCH-M2-DATAFLOW-00-FANIN-CLOSURE-001 implementation evidence

## Boundary

- Baseline: `fdb85756eac2b12fd60c6c1109dfae5fb36e2ed5`
- Branch: `orch/m2-dataflow-00-fanin-closure`
- Mode: bounded infrastructure implementation only
- Production deployment: not authorized and not performed
- Scientific execution, raw/holdout access, stage transitions, and persistent-chat automation: not performed

## Implemented closure

- Semantic tasks may explicitly opt in with `inputs.bind_dependency_results: true`; schema validation requires at least one dependency and rejects deterministic consumers.
- The router creates one immutable durable bundle per consumer after every dependency has a successful accepted result.
- Each dependency material binds task ID, attempt ID, canonical HEAD, accepted-result SHA-256, delivery mode, and a material SHA-256.
- Dependencies and their prompt sections are sorted by task ID, producing deterministic multi-parent fan-in for role `00` and other semantic consumers.
- Small results are embedded. Large results use the existing bounded `results/<TASK_ID>.yaml` artifact mechanism with path, size, content, and hash validation.
- Missing, failed, rejected, malformed, stale, hash-mismatched, identity-mismatched, or modified materials fail closed before worker execution.
- Both Work/Codex and verified alternate semantic lanes receive the same verified dependency prompt material.
- Existing review-material verification, leases, accepted-result exactly-once handling, quota isolation, and branch-local `WAITING_USER` behavior remain intact.
- The localhost read-only dashboard now exposes durable dependency bundles and `CURRENT`, `LAST_PROGRESS`, `NEXT_ACTION`, and `NEEDS_USER` projections. It remains a separate read-only consumer of durable state.

## Verification

- Focused regressions: 9/9 PASS.
  - explicit semantic-only opt-in validation
  - two-parent exact ordered fan-in to role `00`
  - dependency bundle tamper fail-closed before worker
  - oversized dependency artifact delivery
  - failed and rejected dependencies are not consumed
  - mixed deterministic and semantic fan-in
  - fan-in consumer executes and accepts exactly once
  - existing independent-review material binding remains green
  - dashboard remains localhost-only, read-only, and nonblocking
- Full orchestrator regression suite: 134/134 PASS.
- `git diff --check`: PASS.

## Preserved controls

- No modification to `main`.
- No deployment or production-service change.
- No GitHub publication-authority change.
- No protected scientific artifact changed.
- No force operation.
