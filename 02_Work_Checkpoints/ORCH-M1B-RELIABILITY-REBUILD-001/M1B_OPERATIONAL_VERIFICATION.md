# M1b operational verification

Production observations:

- Repeated timer cycles completed successfully with `llm_calls=0` while idle.
- Live state: `OPERATIONAL`; control plane `ACTIVE`; deterministic lane `ACTIVE`; AI lane `AVAILABLE`; active leases `0`.
- Service and timer restart completed without state loss.
- Minimal real AI admission probe returned `ACCEPTED`.
- Controlled non-scientific user-systemd scenario verified: backend quota refusal -> persisted `QUOTA_WAIT`; controller stayed `OPERATIONAL`; independent deterministic task succeeded; ordinary retry remained `0`; exactly one due probe succeeded; exactly one AI continuation ran; final task `SUCCEEDED`; lane returned `AVAILABLE`; exactly two accepted results.
- SQLite integrity: `ok`; no malformed spool, zombie lease, or duplicate dispatch observed.

Authenticated GitHub mutation was not tested because no token is installed. The local outbox remains durable and in preview mode.
