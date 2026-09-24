from __future__ import annotations

import copy
from contextlib import redirect_stdout
from datetime import datetime
import io
import json
import time
import unittest
from unittest import mock

import yaml

from orchestrate_tasks import main
from task_orchestrator.chat_health import (
    ContextHealth, DeliveryHealth, FinalizationHealth, MigrationState,
    archive_readiness, compare_handoff, explicit_health_observation,
    generate_reentry_package, health_record_hash, unknown_health_projection,
    validate_health_record, validate_reentry_package,
)
from task_orchestrator.model import ValidationError
from task_orchestrator.store import Store

from .common import Fixture


class ChatHealthTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture(mode="shadow")
        self.store = Store(self.fx.root / "state" / "db.sqlite3")

    def tearDown(self):
        self.store.close()
        self.fx.close()

    def record(self, **changes):
        value = {
            "chat_id": "WKB-R3", "logical_role": "bounded execution",
            "role": "WKB-R3", "bootstrap_version": "1.0",
            "bootstrap_last_refresh": "2026-09-24T00:00:00Z",
            "canonical_baseline": self.fx.head, "current_task": "ORCH-M1-001",
            "last_substantive_activity": "2026-09-24T00:00:00Z",
            "open_task_count": 1, "CONTEXT_HEALTH": "GREEN",
            "FINALIZATION_HEALTH": "HEALTHY",
            "DELIVERY_HEALTH": "NO_KNOWN_ISSUE",
            "MIGRATION_STATE": "CONTEXT_HEALTHY",
            "observation_source": "EXPLICIT_USER_OBSERVATION",
            "observed_at": "2026-09-24T00:00:00Z", "warning_reason": None,
        }
        value.update(changes)
        return value

    def package(self, **changes):
        value = {
            "CHAT_REENTRY_ID": "REENTRY-WKB-R3-001", "ROLE": "WKB-R3",
            "BOOTSTRAP_VERSION": "1.0", "BOOTSTRAP_LAST_REFRESH": "2026-09-24",
            "CURRENT_CANONICAL_BASELINE": self.fx.head, "CURRENT_TASK": "ORCH-M1-001",
            "TASK_STATUS": "REENTRY_PREPARE", "AUTHORITATIVE_INPUTS": ["canonical Git"],
            "FROZEN_CONSTRAINTS": ["TASK v1"], "CURRENT_DECISIONS": ["preview first"],
            "IMPORTANT_NEGATIVE_CONSTRAINTS": ["no production"],
            "WORK_COMPLETED": ["foundation"], "OPEN_QUESTIONS": ["review"],
            "PENDING_DECISIONS": ["07 verdict"], "NEXT_EXACT_ACTION": "07 review",
            "FILES_PATHS_HASHES": ["scripts/task_orchestrator/visibility.py"],
            "REVIEW_IDS": ["07-PENDING"], "AUTHORIZATIONS": ["local tests"],
            "EXPLICITLY_NOT_AUTHORIZED": ["production", "scientific execution"],
            "KNOWN_RISKS": ["missing persistent-chat telemetry"],
            "RESEARCH_PORTFOLIO_REFERENCES": ["Stage03R landscape", "deferred detector bridge"],
        }
        value.update(changes)
        return value

    def cli_health(self, record, *, now_epoch, stale_after_seconds=60):
        state_store = Store(self.fx.root / "state" / "state.sqlite3")
        try:
            state_store.put_chat_health(record)
        finally:
            state_store.close()
        self.fx.cfg["chat_health"]["observation_stale_after_seconds"] = stale_after_seconds
        config = self.fx.root / "orchestrator.yaml"
        config.write_text(yaml.safe_dump(self.fx.cfg, sort_keys=False), encoding="utf-8")
        output = io.StringIO()
        with mock.patch("orchestrate_tasks.time.time", return_value=now_epoch):
            with redirect_stdout(output):
                code = main(["--config", str(config), "chat-health", record["chat_id"]])
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_all_canonical_health_enum_values_validate_with_consistent_migration(self):
        contexts = {
            "GREEN": "CONTEXT_HEALTHY", "YELLOW": "REENTRY_PREPARE",
            "YELLOW_HIGH": "REENTRY_PREPARE", "RED": "MIGRATE_SAME_ROLE",
        }
        for context, migration in contexts.items():
            record = self.record(CONTEXT_HEALTH=context, MIGRATION_STATE=migration,
                                 warning_reason=None if context == "GREEN" else "explicit signal")
            self.assertEqual(validate_health_record(record)["CONTEXT_HEALTH"], context)
        for value in FinalizationHealth:
            migration = "MIGRATE_SAME_ROLE" if value == FinalizationHealth.SEVERELY_DEGRADED else "REENTRY_PREPARE" if value == FinalizationHealth.DEGRADED else "CONTEXT_HEALTHY"
            record = self.record(FINALIZATION_HEALTH=value.value, MIGRATION_STATE=migration,
                                 warning_reason=None if migration == "CONTEXT_HEALTHY" else "signal")
            validate_health_record(record)
        for value in DeliveryHealth:
            migration = "REENTRY_PREPARE" if value == DeliveryHealth.SEVERELY_DEGRADED else "CONTEXT_HEALTHY"
            record = self.record(DELIVERY_HEALTH=value.value, MIGRATION_STATE=migration,
                                 warning_reason=None if migration == "CONTEXT_HEALTHY" else "signal")
            validate_health_record(record)

    def test_missing_and_stale_telemetry_are_unknown_not_green(self):
        missing = unknown_health_projection(
            "03-r2", "CEF modelling", "03", "1.0", "2026-09-01T00:00:00Z",
            self.fx.head,
        )
        self.assertEqual(missing["CONTEXT_HEALTH"], "UNKNOWN")
        self.assertEqual(missing["FINALIZATION_HEALTH"], "UNKNOWN")
        self.assertEqual(missing["DELIVERY_HEALTH"], "UNKNOWN")
        stale = explicit_health_observation(
            self.record(), now_epoch=time.time() + 10_000_000, stale_after_seconds=60,
        )
        self.assertEqual(stale["MIGRATION_STATE"], "UNKNOWN")

    def test_cli_downgrades_stale_stored_green_to_unknown(self):
        observed_at = "2026-09-24T00:00:00Z"
        observed_epoch = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        ).timestamp()
        result = self.cli_health(
            self.record(observed_at=observed_at),
            now_epoch=observed_epoch + 61,
        )
        self.assertEqual(result["CONTEXT_HEALTH"], "UNKNOWN")
        self.assertEqual(result["FINALIZATION_HEALTH"], "UNKNOWN")
        self.assertEqual(result["DELIVERY_HEALTH"], "UNKNOWN")
        self.assertEqual(result["MIGRATION_STATE"], "UNKNOWN")
        self.assertEqual(result["warning_reason"], "explicit observation is stale")

    def test_cli_preserves_fresh_stored_green(self):
        observed_at = "2026-09-24T00:00:00Z"
        observed_epoch = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        ).timestamp()
        record = self.record(observed_at=observed_at)
        result = self.cli_health(record, now_epoch=observed_epoch + 59)
        self.assertEqual(result, record)

    def test_health_dimensions_are_independent_and_green_emits_no_noise(self):
        healthy = validate_health_record(self.record())
        self.assertIsNone(healthy["warning_reason"])
        delivery = validate_health_record(self.record(
            DELIVERY_HEALTH="USER_REPORTED_DEGRADED"))
        self.assertEqual(delivery["CONTEXT_HEALTH"], "GREEN")
        self.assertEqual(delivery["DELIVERY_HEALTH"], "USER_REPORTED_DEGRADED")

    def test_percent_inference_partial_oversized_and_inconsistent_state_rejected(self):
        with self.assertRaises(ValidationError):
            validate_health_record({**self.record(), "context_percent": 50})
        partial = self.record(); partial.pop("role")
        with self.assertRaises(ValidationError):
            validate_health_record(partial)
        with self.assertRaises(ValidationError):
            validate_health_record(self.record(CONTEXT_HEALTH="RED"))
        with self.assertRaises(ValidationError):
            validate_health_record(self.record(warning_reason="x" * 3000))

    def test_registry_accepts_only_explicit_valid_observation(self):
        record = self.record()
        self.assertEqual(self.store.put_chat_health(record), "created")
        self.assertEqual(self.store.put_chat_health(record), "duplicate")
        row = self.store.chat_health("WKB-R3")
        self.assertEqual(row["record_hash"], health_record_hash(record))
        self.assertEqual(json.loads(row["record_json"])["observation_source"],
                         "EXPLICIT_USER_OBSERVATION")
        with self.assertRaises(ValidationError):
            self.store.put_chat_health(self.record(observation_source="INFERRED_HISTORY"))

    def test_reentry_package_is_complete_deterministic_and_preserves_portfolio(self):
        first = generate_reentry_package(**self.package())
        second = generate_reentry_package(**copy.deepcopy(self.package()))
        self.assertEqual(first, second)
        self.assertIn("Stage03R landscape", first["RESEARCH_PORTFOLIO_REFERENCES"])
        self.assertIn("no production", first["IMPORTANT_NEGATIVE_CONSTRAINTS"])
        self.assertIn("production", first["EXPLICITLY_NOT_AUTHORIZED"])

    def test_reentry_partial_oversized_and_missing_prohibitions_fail_closed(self):
        partial = self.package(); partial.pop("KNOWN_RISKS")
        with self.assertRaises(ValidationError):
            validate_reentry_package(partial)
        with self.assertRaises(ValidationError):
            validate_reentry_package(self.package(EXPLICITLY_NOT_AUTHORIZED=[]))
        with self.assertRaises(ValidationError):
            validate_reentry_package(self.package(WORK_COMPLETED=["x" * 70_000]))

    def test_exact_handoff_required_before_old_chat_archive_ready(self):
        package = self.package()
        verified = compare_handoff(package, copy.deepcopy(package))
        self.assertEqual(verified["status"], "HANDOFF_VERIFIED")
        self.assertEqual(archive_readiness(verified), "OLD_CHAT_ARCHIVE_READY")
        changed = self.package(NEXT_EXACT_ACTION="different")
        mismatch = compare_handoff(package, changed)
        self.assertEqual(mismatch["status"], "CHAT_HANDOFF_REQUIRED")
        with self.assertRaises(ValidationError):
            archive_readiness(mismatch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
