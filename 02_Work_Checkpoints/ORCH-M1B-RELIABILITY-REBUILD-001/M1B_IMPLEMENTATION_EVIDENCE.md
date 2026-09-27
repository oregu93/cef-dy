# M1b implementation evidence

Task: `ORCH-M1B-RELIABILITY-REBUILD-001`

## Candidate contents

- deterministic `cycle-once` entry point;
- SQLite/WAL controller checkpoint, leases, dispatch attempts, accepted results, and AI-lane tables;
- atomic result spool and exactly-once acceptance transaction;
- reset-aware and capped-backoff quota probing;
- automatic `QUOTA_WAIT -> READY` recovery;
- independent deterministic and GitHub polling lanes;
- disposable read-only Codex worker transport behind an explicit local enable gate;
- user-systemd service/timer with no terminal dependency;
- fail-closed task/path/command policies inherited from M1.

## Candidate verification

The pre-freeze suite completed 74 tests successfully, including an asserted 100-task synthetic load and an eight-way claim race. Exact frozen commit, hashes, rerun counts, reviewer findings, deployment commands, service state, soak observations, and rollback evidence are recorded by the later gate artifacts in this directory.

No scientific execution, holdout access, Structure-A execution, or protected-path modification is part of this evidence.
