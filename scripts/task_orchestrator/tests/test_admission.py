from __future__ import annotations

import unittest

from task_orchestrator.admission import (
    AdmissionClass, VisibilityFacts, VisibilityHealth,
    classify_admission, compute_visibility_health, decide_admission,
)


class AdmissionPolicyTests(unittest.TestCase):
    @staticmethod
    def facts(**overrides):
        values = dict(
            ordinary_autonomy_enabled=True,
            publishing_enabled=True,
            preview_only=False,
            unresolved_terminal_ages_seconds=(),
            required_publication_statuses=(),
            required_outbox_identities=0,
            max_batch_tasks=1,
            poll_interval_seconds=300,
        )
        values.update(overrides)
        return VisibilityFacts(**values)

    def test_healthy_idle_is_ok_and_defaults_are_exact(self):
        assessment = compute_visibility_health(self.facts())
        self.assertEqual(assessment.state, VisibilityHealth.AUTONOMY_VISIBILITY_OK)
        self.assertEqual(assessment.unprojected_terminal_high_water, 2)
        self.assertEqual(assessment.unprojected_terminal_max_age_seconds, 600)
        self.assertEqual(assessment.outbox_required_high_water, 8)

    def test_fresh_single_terminal_is_degraded_but_two_pause(self):
        one = compute_visibility_health(self.facts(
            unresolved_terminal_ages_seconds=(30,),
            required_publication_statuses=("PREVIEW",),
            required_outbox_identities=1,
        ))
        self.assertEqual(one.state, VisibilityHealth.AUTONOMY_VISIBILITY_DEGRADED)
        two = compute_visibility_health(self.facts(
            unresolved_terminal_ages_seconds=(30, 40),
            required_publication_statuses=("PREVIEW", "PREVIEW"),
            required_outbox_identities=2,
        ))
        self.assertEqual(two.state, VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE)

    def test_age_and_configuration_fail_closed(self):
        aged = compute_visibility_health(self.facts(
            unresolved_terminal_ages_seconds=(601,),
            required_publication_statuses=("PREVIEW",),
        ))
        self.assertEqual(aged.state, VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE)
        self.assertEqual(
            compute_visibility_health(self.facts(preview_only=True)).state,
            VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE,
        )
        self.assertEqual(
            compute_visibility_health(self.facts(publishing_enabled=False)).state,
            VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE,
        )

    def test_unknown_and_conflict_required_publications_pause(self):
        for status in ("UNKNOWN", "CONFLICT"):
            with self.subTest(status=status):
                assessment = compute_visibility_health(self.facts(
                    unresolved_terminal_ages_seconds=(10,),
                    required_publication_statuses=(status,),
                    required_outbox_identities=1,
                ))
                self.assertEqual(
                    assessment.state, VisibilityHealth.ADMISSION_PAUSED_OPAQUE_STATE,
                )

    def test_threshold_formulas_scale_from_runtime_configuration(self):
        assessment = compute_visibility_health(self.facts(
            max_batch_tasks=3, poll_interval_seconds=400,
        ))
        self.assertEqual(assessment.unprojected_terminal_high_water, 6)
        self.assertEqual(assessment.unprojected_terminal_max_age_seconds, 800)
        self.assertEqual(assessment.outbox_required_high_water, 24)

    def test_task_provided_diagnostic_and_recovery_authority_is_never_trusted(self):
        paused = compute_visibility_health(self.facts(preview_only=True))
        self.assertEqual(classify_admission({"note": "diagnostic repair"}), AdmissionClass.ORDINARY)
        self.assertFalse(decide_admission(paused, AdmissionClass.ORDINARY).allowed)
        for name in (AdmissionClass.DIAGNOSTIC, AdmissionClass.RECOVERY):
            inputs = {"admission_control": {"class": name.value, "authorized": True}}
            self.assertEqual(classify_admission(inputs), name)
            self.assertFalse(decide_admission(paused, name).allowed)

    def test_mandatory_review_requires_exact_binding_and_replacement_never_bypasses(self):
        inputs = {
            "independent_review": True,
            "review_of": "PARENT-001",
            "review_material": {
                "parent_task_id": "PARENT-001",
                "accepted_result_sha256": "a" * 64,
            },
        }
        paused = compute_visibility_health(self.facts(preview_only=True))
        self.assertEqual(classify_admission(inputs), AdmissionClass.MANDATORY_REVIEW)
        self.assertTrue(decide_admission(
            paused, AdmissionClass.MANDATORY_REVIEW, identity_bound_review=True,
        ).allowed)
        self.assertFalse(decide_admission(
            paused, AdmissionClass.MANDATORY_REVIEW, identity_bound_review=False,
        ).allowed)
        self.assertFalse(decide_admission(
            paused, AdmissionClass.RECOVERY,
            unresolved_replacement_identity=True,
        ).allowed)


if __name__ == "__main__":
    unittest.main()
