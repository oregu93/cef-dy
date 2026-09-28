# M1b architecture decision

Status: deployed after independent review and control adjudication

Task: `ORCH-M1B-RELIABILITY-REBUILD-001`

Canonical baseline: `137bc5f78c1d22c9f574615f8f7e133b1d3cc053`

## Decision

The only authoritative supervisor is a deterministic `cycle-once` process invoked by a user-level systemd timer. SQLite in WAL mode owns task state, worker leases, accepted-result identities, AI-lane state, retry/probe scheduling, publication outbox state, and controller checkpoints. Codex is an optional disposable bounded worker and never supervises, schedules, or owns continuation.

The controller runs these independent lanes every cycle: recovery/result ingestion, GitHub polling, publication reconciliation, deterministic work, attention-state projection, and—only when admitted—the AI lane. A failure or pause in one lane does not stop another.

## Task state and leases

The implemented state vocabulary includes `RECEIVED`, `VALIDATED`, `READY`, `RUNNING`, `QUOTA_WAIT`, `WAITING_DEPENDENCY`, `WAITING_USER`, `FAILED_RETRYABLE`, `BLOCKED`, and `SUCCEEDED`. Legacy states remain readable for database migration.

A `RUNNING` task has one row in `worker_leases` containing `worker_id`, `task_id`, `attempt_id`, `claimed_at`, and `lease_expires_at`. Claiming uses `BEGIN IMMEDIATE`, a primary key on `task_id`, a unique `attempt_id`, and a conditional `READY -> RUNNING` update. Expired leases return unfinished tasks to an eligible state. Results written before acknowledgement are recovered from an atomic spool.

Accepted results have a primary key on `task_id`. The acceptance transaction inserts the result identity, updates task state, records the event, and deletes the lease. Re-delivery of the same result is a no-op; a different result for an already accepted task is a conflict.

## Quota semantics

Backend refusal is authoritative for the AI lane. A refusal:

- persists `QUOTA_WAIT` and the refusal evidence;
- schedules one probe at `reset_at + guard` when known, otherwise uses deterministic capped backoff;
- releases the worker lease;
- does not increment the ordinary task attempt counter;
- never creates a global blocker or terminates the controller.

A successful due probe changes the lane to `AVAILABLE` and atomically returns all eligible `QUOTA_WAIT` tasks to `READY`. The same cycle may then dispatch the highest ordered eligible AI task without user action.

## Safety boundary

The system does not authorize scientific execution, holdout/raw access, FullProf Structure-A execution, project-stage transitions, scientific promotion, or changes to protected paths. AI workers receive a read-only sandbox contract. Deterministic commands remain exact-argv allowlisted.

## Deployment and rollback

The reviewed unit calls `cycle-once`; the persistent timer schedules a new cycle after the previous one is inactive. Only the `cef-dy-orchestrator.service` and matching timer are authoritative. Rollback disables these units, restores their captured predecessor files, reloads systemd, and retains the SQLite state. Obsolete shadow-expiry and historical watchdog mechanisms must remain inactive.
