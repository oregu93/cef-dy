# M1b rollback verification

Rollback backup: `/home/oleg/.config/cef-dy-orchestrator/backups/20260928-033414`

The active timer was stopped, predecessor config/service/timer files were restored, and their hashes matched the captured backup exactly. The predecessor was not started. The obsolete shadow-expiry path remained inactive. The reviewed M1b config, units, and cadence drop-in were then reinstalled and the timer returned to `active`.

The durable SQLite database was retained throughout. No scientific path was changed and no legacy AI supervisor was reactivated.
