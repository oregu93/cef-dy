# ORCH-M2-SEMANTIC-RESULT-REVIEW-FIX-001 — implementation evidence

## Scope and baseline

- Authoritative specification: GitHub Issue #9.
- Diagnostic evidence: Issue #8 comment `issuecomment-5871068737`.
- Exact start HEAD: `a31ce6b7dd7367737fd56479a516901a159b1934`.
- Branch: `orch/m2-semantic-result-review-fix` in an isolated worktree.
- Mode: bounded infrastructure implementation; no scientific execution.

## Implemented protocol correction

- A structurally valid accepted semantic worker response now records technical
  execution as `status=SUCCEEDED` independently of its substantive verdict.
- The original substantive status is preserved as `semantic_verdict`.
- `summary` and the original semantic `error` (`semantic_error`) survive both
  the accepted SQLite result and the public durable YAML result.
- Retryable transport/launcher failure remains `FAILED_RETRYABLE` and does not
  create a terminal accepted result.
- Review creation is gated by the durable accepted terminal semantic execution,
  including legacy accepted negative results, rather than only by parent
  `SUCCEEDED` state.
- The review relation remains durable in `review_requirements`; the review task
  does not use the legacy parent FSM state as a dependency after acceptance.
- Review-worker failure does not modify the parent execution result.
- Existing result identity, lease identity, attempt identity, canonical HEAD,
  stale/duplicate rejection, quota isolation, and WAITING_USER isolation remain
  unchanged.

## Bounded supporting corrections

- Production telemetry now reports derived runtime mode `production`, retains
  `configured_mode=pilot` for compatibility, and reports the durable count of
  admitted semantic execution attempts instead of an unconditional zero.
- The writer performs a passive WAL checkpoint after a completed cycle so the
  immutable read-only dashboard snapshot sees the completed durable state. The
  dashboard remains read-only and nonblocking.
- Result publication rendering understands the optional semantic verdict and
  summary while continuing to accept legacy v1 result files.

## Focused regression evidence

The focused gate covers:

1. negative semantic verdict -> execution complete -> independent review;
2. summary preservation through accepted SQLite and public YAML results;
3. semantic result duplicate remains exactly once;
4. retryable transport failure remains distinct from negative verdict;
5. review worker failure leaves the parent execution result unchanged;
6. production runtime/call telemetry;
7. immutable dashboard visibility after a completed WAL-backed cycle.

## PREVIEW-only publication investigation

The deployed configuration was inspected read-only. It has:

- `publishing.enabled=false`;
- `publishing.preview_only=true`;
- `publishing.trusted_authors=[]`.

This is an explicit deployment/authentication policy state, not the semantic
normalization defect. Enabling live publication without a trusted-author and
credential decision would broaden authority, so no GitHub publishing redesign
or configuration mutation is included in this candidate.

## Preserved guards

- No deployment and no push to `main`.
- No protected scientific artifact changes.
- No raw or holdout access.
- No Structure-A execution.
- No scientific stage transition.
- No M3 or voice work.
- `LOCAL_OSS_MODEL` remains disabled and `NON_WORK_AI` remains unverified.

The exact reviewed candidate SHA and final test/review verdict are recorded in
the task closeout after the immutable candidate commit is created.
