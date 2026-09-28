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

The final frozen implementation commit is `3c933c77bc4401b645bba020d975ca4a8784626f`. The final suite completed 94 tests successfully, including a 100-task synthetic load, eight-way task claim race, cross-task global AI-slot race, crash recovery, quota auto-resume, exact-once results, preview-to-live promotion, stale-attention supersession, and repeated attention episodes. A fresh focused control adjudicator reran all 94 tests plus 11 blocker regressions and returned `DEPLOY` with no P0/P1/P2 code blocker.

No scientific execution, holdout access, Structure-A execution, or protected-path modification is part of this evidence.
