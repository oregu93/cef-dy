---
title: "CEF Dy - Telegram attention gateway"
type: protocol
status: candidate_pending_independent_review
version: "1.0"
updated: 2026-10-04
---

# Telegram attention gateway

## Authority boundary

Telegram is a private one-user attention and bounded-response transport. It is
not scientific, Project-Control, Git, stage, holdout, service-management, or
shell authority. Canonical Git remains project authority; SQLite/WAL remains
operational authority; GitHub remains the durable control-plane projection.
Persistent 00 remains NON-WORK.

The candidate is disabled by default. Production deployment, a real Bot API
smoke test, service activation, and the one-time activation message require an
independent review ACCEPT and a separate Project-Control authorization.

## Identity and secrets

The gateway accepts only a private chat whose exact numeric `user_id` and
`chat_id` both match machine-local environment values. Authorization is checked
before command parsing. Forwarded-message authority is rejected. The bot token
and numeric identifiers are never repository/config/log/result values; only
their environment-variable names are canonical. The machine-local environment
file must be mode 0600.

The MVP uses outbound HTTPS long polling and opens no inbound listener. The
systemd unit does not claim destination-level egress restriction: address-family
hardening is not proof that traffic can reach only Telegram.

## Durable state machines

The gateway adds namespaced tables to the existing local SQLite database. It
does not create a second authority database.

- projection: `VALIDATED`, `REJECTED`, `SUPERSEDED`;
- delivery: `READY`, `CLAIMED`, `SEND_OUTCOME_UNKNOWN`, `SENT`,
  `RETRY_WAIT`, `DEAD_LETTER`, `CANCELLED`;
- question: `OPEN`, `ANSWERED`, `EXPIRED`, `WITHDRAWN`, `SUPERSEDED`;
- response: `ACCEPTED`, `CANCEL_REQUESTED`, `CONSUMED` plus immutable rejection
  audit events.

`SENT` requires a persisted Telegram `message_id`. Timeout/disconnect after a
send begins is `SEND_OUTCOME_UNKNOWN`, never success. Expired claims reconcile
to the same state. A later bounded retry retains the immutable delivery identity
and visible short marker. Unknown sends consume the same bounded retry budget
and eventually become `DEAD_LETTER`. Telegram can therefore display duplicates;
this is safe at-least-once delivery, not an exactly-once claim.

Inbound `update_id` plus payload hash is durable. An exact replay is a no-op; a
different payload for the same ID is quarantined as a conflict. A crash after
ingest but before processing resumes the `RECEIVED` update after restart.

## Questions and USER decisions

For each `(attention_id, question_version)`, one transaction implements
first-valid-response-wins: it accepts only an `OPEN` question, records the
response, closes the question, and creates exactly one durable `USER_DECISION`.
The decision is explicitly `INPUT_ONLY_NON_AUTHORITATIVE`; logical 00 consumes
it through the durable local path. Later answers are immutable rejected events.
Cancellation is an append-only request and cannot erase a consumed decision.

## Notification policy

Primary notification classes are `HUMAN_ACTION_REQUIRED`, `PROJECT_STALLED`,
`SCIENTIFIC_DECISION_REQUIRED`, and `RECOVERY_FAILED`. `MAJOR_MILESTONE` is an
explicit opt-in. Routine heartbeat/progress and repeated identical projections
are suppressed. Projections contain only bounded safe context, reason code,
requested response, consequence of no action, review state, timestamps, and
source identities—never raw/holdout/private payload, tracebacks, secrets, or
absolute paths.

## Command surface

Read-only, no-AI commands:

- `/help`, `/status`, `/health`, `/attention`, `/last`, `/task <id>`;
- `/respond <attention_id> <answer>` creates bounded USER input;
- `/cancel <attention_id>` requests response cancellation only and never kills
  a task or process.

Operational controls are exact commands and require a short-lived callback
confirmation plus current-state recheck: `/pause_ai`, `/drain`, `/quiesce`,
`/safe`, `/resume`, `/mute`, `/unmute`, `/hold`, and `/release`. They can affect
only orchestrator admission, notification mute state, or an exact task hold.
Engine admission consumes the durable control state so direct CLI paths cannot
bypass it. `/resume` additionally requires durable recovery proof `PROVEN`,
current `AUTONOMY_VISIBILITY_OK`, and no hard blocker. There is no arbitrary
text, shell, Git, stage, holdout, service, or scientific command endpoint.

## Health and failure isolation

Each loop writes a fresh explicit `TELEGRAM_GATEWAY` observation to the existing
controller checkpoint. The dashboard projects `HEALTHY`, `DEGRADED`, `STALE`,
or `UNKNOWN`; configured enablement alone is never health evidence. Telegram
failure leaves Orch tasks and accepted results unchanged. Dashboard/Tailscale
and GitHub remain independent fallback surfaces.

## Review, deployment, and rollback

Review must inspect exact code/tests and verify the candidate is disabled. A
later separately authorized deployment may install the reviewed unit and local
config, then perform exactly bounded outbound-attention and `/status` roundtrip
smokes. Only after both pass and a fresh dashboard observation exists may a
one-time activation notice be sent.

Rollback is: stop/disable only the Telegram unit, restore the previous local
config, and retain all SQLite gateway rows as audit evidence. Do not delete
updates, deliveries, decisions, or events. Orch must continue independently.

## Current implementation gate

The candidate adds focused deterministic tests for allowlisting, update
idempotency/conflict/restart, projection filtering, at-least-once delivery,
ambiguous sends, response arbitration/cancellation, read-only commands,
confirmed controls, Engine enforcement, outage isolation, explicit dashboard
observation, and secret/endpoint boundaries. Real Telegram and production
services are not exercised by these tests.
