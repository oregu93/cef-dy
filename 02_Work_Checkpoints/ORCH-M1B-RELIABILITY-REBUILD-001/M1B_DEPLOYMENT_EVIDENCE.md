# M1b deployment evidence

Deployment time: 2026-09-28 (Europe/Moscow)

- Local canonical `main`: `3c933c77bc4401b645bba020d975ca4a8784626f`.
- Remote `origin/main`: `137bc5f78c1d22c9f574615f8f7e133b1d3cc053` pending explicit approval for the blocked remote push.
- User timer: enabled and active with an effective two-minute `OnUnitInactiveSec` drop-in.
- User service: successful oneshot cycles, `ExecMainStatus=0`, `NRestarts=0`.
- Linger: `yes`.
- Obsolete shadow-expiry timer/service: disabled and inactive.
- Installed service SHA-256: `53d3985124ecb28c316521c9a356991c9a15425359d2e4b2ea8f080d2577a9ed`.
- Installed timer SHA-256: `74e734069598c854b6ef592f4982fcbca9a46112a34d3502f0d5b600d283030e`.
- Cadence drop-in SHA-256: `42eccd0971038f97ad6d75bbc4ed83d2436cdfd833b48fe83ed76a4f3da3b77a`.
- Installed config SHA-256: `6259c368094644df74eaf708c6207bb094d559fc2e2c79eff2fbc1ea85d41af7`.
- Durable database: `CEF_Dy_Backup/task_orchestrator/state.sqlite3`; SQLite integrity check `ok`.

Publishing is deliberately fail-closed (`preview_only`) until a `GITHUB_TOKEN` is installed. GitHub polling remains active and consumes no AI quota.
