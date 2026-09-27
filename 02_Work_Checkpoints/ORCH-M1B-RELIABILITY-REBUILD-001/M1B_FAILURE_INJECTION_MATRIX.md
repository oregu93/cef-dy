# M1b failure-injection matrix

Status values in this file describe the candidate test suite. Deployment evidence records the production run separately.

| Area | Injected condition / asserted property | Test evidence | Candidate |
|---|---|---|---|
| Identity | duplicate task delivery is a no-op; changed envelope conflicts | `test_duplicate_delivery_and_identity_conflict` | PASS |
| Result identity | duplicate result accepted once; changed duplicate conflicts | `test_result_is_accepted_exactly_once` | PASS |
| Claim concurrency | eight simultaneous claimers produce one lease/winner | `test_eight_way_claim_race_has_one_winner` | PASS |
| Controller concurrency | process lock excludes a second cycle; stale lock recovers | `test_lock_concurrent_and_stale` | PASS |
| Worker crash | expired lease returns task to eligible state | `test_expired_lease_is_recovered` | PASS |
| Crash before ACK | atomic spool is ingested by a fresh controller | `test_crash_after_result_before_ack_is_reconciled` | PASS |
| Crash after DB accept | replayed spool is deduplicated | `test_result_after_database_accept_before_ack_is_deduplicated` | PASS |
| Atomic artifacts | failed replace preserves previous checkpoint | `test_interrupted_atomic_write_preserves_previous` | PASS |
| Restart | database reopens with state intact | `test_restart_reopens_database` | PASS |
| Corruption | corrupt SQLite is detected and quarantinable | `test_corrupted_state_is_detected_and_quarantinable` | PASS |
| Quota known reset | task enters `QUOTA_WAIT`; retry count unchanged | `test_quota_wait_does_not_consume_retry_and_local_work_continues` | PASS |
| Quota auto-resume | due probe succeeds and task completes without operator action | `test_automatic_post_reset_probe_and_resume` | PASS |
| Quota indefinite | repeated refusal keeps controller operational | `test_repeated_quota_refusal_never_blocks_controller` | PASS |
| Lane isolation | deterministic task completes while AI is quota-blocked | `test_quota_wait_does_not_consume_retry_and_local_work_continues` | PASS |
| GitHub outage | source outage/backoff does not stop deterministic lane | `test_github_outage_does_not_stop_local_lane` | PASS |
| GitHub projection | timeout/429/5xx, ambiguous ACK and reconciliation are durable | publication test group | PASS |
| Governance | path escape, forbidden path and malformed task fail closed | schema/policy test group | PASS |
| Waiting user | waiting task does not stall unrelated ready task | `test_waiting_user_does_not_stall_ready_work` | PASS |
| Dependency graph | completion/failure propagation and cycles | store/engine dependency tests | PASS |
| Load | 100 tasks complete once, no lease remains, no starvation | `test_hundred_task_load_has_no_double_execution_or_starvation` | PASS |
| No hidden AI supervisor | idle polling exposes no OpenAI/Codex launch surface | `test_idle_loop_has_no_openai_or_codex_call_surface` | PASS |

The suite uses fake AI admission/worker transports. A real AI smoke is a separate post-review deployment gate and must not substitute for these deterministic assertions.
