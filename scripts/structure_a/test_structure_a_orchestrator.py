#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

SPEC = importlib.util.spec_from_file_location(
    "m",
    HERE / "structure_a_orchestrator.py",
)

m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def cfg_for_input(
    sha,
    *,
    real=False,
    authorized=True,
    registered=True,
):
    items = []

    if registered:
        items.append(
            {
                "artifact_id": "X",
                "sha256": sha if real else None,
                "input_role":
                    "real_derivative"
                    if real
                    else "fixture",
                "real_data": real,
                "execution_authorized":
                    authorized,
            }
        )

    return {
        "input_authorizations": {
            "registered_inputs": items
        }
    }


def conv_cfg():
    return {
        "max_blocks": 5,
        "Rwp_change_threshold": 0.05,
        "chi2_change_threshold": 0.05,
        "parameter_change_thresholds": {
            "fixture.parameter": 0.01
        },
        "minimum_consecutive_stable_blocks": 2,
        "stagnation_window": 2,
        "oscillation_window": 3,
        "oscillation_rule": "alternating_sign",
    }


def history(
    index,
    rwp,
    chi2,
    parameter_delta=0.005,
    ok=True,
):
    return {
        "block_index": index,
        "rwp": rwp,
        "chi2": chi2,
        "monitored_parameter_deltas": {
            "fixture.parameter":
                parameter_delta
        },
        "execution_ok": ok,
        "parse_ok": ok,
    }


class Tests(unittest.TestCase):

    def test_ascii_path_pass(self):
        m.ensure_ascii_path(Path("/tmp/x"))

    def test_non_ascii_path_rejected(self):
        with self.assertRaises(RuntimeError):
            m.ensure_ascii_path(
                Path("/tmp/Документы")
            )

    def test_T01_fixture_input_authorized(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.dat"
            path.write_text("x")
            sha = m.sha256_file(path)

            identity = m.build_input_identity(
                "X",
                path,
                sha,
                "fixture",
                False,
                True,
            )

            m.guard_diffraction_input(
                identity,
                cfg_for_input(sha),
            )

    def test_T02_real_derivative_not_registered_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.dat"
            path.write_text("x")
            sha = m.sha256_file(path)

            identity = m.build_input_identity(
                "X",
                path,
                sha,
                "real_derivative",
                True,
                True,
            )

            with self.assertRaises(RuntimeError):
                m.guard_diffraction_input(
                    identity,
                    cfg_for_input(
                        sha,
                        real=True,
                        registered=False,
                    ),
                )

    def test_T03_real_registered_not_authorized_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.dat"
            path.write_text("x")
            sha = m.sha256_file(path)

            identity = m.build_input_identity(
                "X",
                path,
                sha,
                "real_derivative",
                True,
                False,
            )

            with self.assertRaises(RuntimeError):
                m.guard_diffraction_input(
                    identity,
                    cfg_for_input(
                        sha,
                        real=True,
                        authorized=False,
                    ),
                )

    def fixture_targets(self):
        return {
            "fixture.target": {
                "selector": {
                    "kind": "exact_line_token",
                    "line_match": "TARGET_LINE",
                    "token_index": 2,
                },
                "value_type": "float",
            },
            "fixture.other": {
                "selector": {
                    "kind": "exact_line_token",
                    "line_match": "OTHER_LINE",
                    "token_index": 2,
                },
                "value_type": "float",
            },
        }

    def delta(self):
        return {
            "delta_id": "DELTA-FIXTURE-001",
            "changes": [
                {
                    "target_id": "fixture.target",
                    "before": 0.0,
                    "after": 1.0,
                }
            ],
        }

    def test_T04_pcr_allowed_delta_pass(self):
        baseline = (
            "TARGET_LINE A 0.0 Z\n"
            "OTHER_LINE B 5.0 Z\n"
        )

        candidate = (
            m.apply_authorized_pcr_delta(
                baseline,
                "DELTA-FIXTURE-001",
                self.delta(),
                self.fixture_targets(),
            )
        )

        result = m.compare_target_state(
            m.extract_target_state(
                baseline,
                self.fixture_targets(),
            ),
            m.extract_target_state(
                candidate,
                self.fixture_targets(),
            ),
            self.delta(),
        )

        self.assertEqual(
            result["status"],
            "PASS",
        )

    def test_T05_pcr_unauthorized_change_rejected(self):
        baseline = (
            "TARGET_LINE A 0.0 Z\n"
            "OTHER_LINE B 5.0 Z\n"
        )

        candidate = (
            "TARGET_LINE A 1.0 Z\n"
            "OTHER_LINE B 6.0 Z\n"
        )

        targets = self.fixture_targets()

        result = m.compare_target_state(
            m.extract_target_state(
                baseline,
                targets,
            ),
            m.extract_target_state(
                candidate,
                targets,
            ),
            self.delta(),
        )

        self.assertEqual(
            result["status"],
            "REJECT_UNEXPECTED_CHANGE",
        )

    def test_T06_pcr_incomplete_delta_rejected(self):
        baseline = (
            "TARGET_LINE A 0.0 Z\n"
            "OTHER_LINE B 5.0 Z\n"
        )

        targets = self.fixture_targets()

        result = m.compare_target_state(
            m.extract_target_state(
                baseline,
                targets,
            ),
            m.extract_target_state(
                baseline,
                targets,
            ),
            self.delta(),
        )

        self.assertEqual(
            result["status"],
            "REJECT_INCOMPLETE_DELTA",
        )

    def test_T07_stage_transition_allowed(self):
        table = {
            "FIXTURE-S0": {
                "next": {
                    "FIXTURE-S1": {
                        "permitted_delta_ids": [
                            "DELTA-FIXTURE-001"
                        ]
                    }
                }
            }
        }

        self.assertEqual(
            m.validate_stage_transition(
                "FIXTURE-S0",
                "FIXTURE-S1",
                table,
                {"status": "PASS"},
                "DELTA-FIXTURE-001",
            ),
            "PASS",
        )

    def test_T08_stage_transition_rejected(self):
        self.assertEqual(
            m.validate_stage_transition(
                "FIXTURE-S0",
                "FIXTURE-S2",
                {},
                {"status": "PASS"},
                "D",
            ),
            "REJECT_UNAUTHORIZED_TRANSITION",
        )

    def test_T09_sum_missing_required_field(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.sum"

            path.write_text(
                "Rwp = 3.0\n"
                "Chi2 = 2.0\n"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "PARSE_FAILURE",
            ):
                m.parse_sum_required(
                    path,
                    {
                        "sum_required_fields_before_readiness": [
                            "rwp",
                            "chi2",
                            "bragg_r",
                        ]
                    },
                )

    def test_T10_failure_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "scratch"
            destination = Path(td) / "saved"

            scratch.mkdir()

            (
                scratch / "x.pcr"
            ).write_text("p")

            artifacts = m.preserve_attempt(
                scratch,
                destination,
                {
                    "stdout": "hello",
                    "stderr": "bad",
                },
                [
                    "x.pcr",
                    "x.sum",
                ],
            )

            self.assertTrue(
                (destination / "x.pcr").exists()
            )

            self.assertTrue(
                (
                    destination
                    / "stdout.txt"
                ).exists()
            )

            self.assertIn(
                "stderr.txt",
                artifacts,
            )

    def test_T11_convergence_continue(self):
        self.assertEqual(
            m.classify_convergence(
                [
                    history(
                        1,
                        4.0,
                        4.0,
                    )
                ],
                conv_cfg(),
            ),
            "CONTINUE",
        )

    def test_T12_convergence_converged(self):
        self.assertEqual(
            m.classify_convergence(
                [
                    history(1, 4.00, 4.00),
                    history(2, 3.98, 3.98),
                    history(3, 3.97, 3.97),
                ],
                conv_cfg(),
            ),
            "CONVERGED",
        )

    def test_T13_convergence_stagnated(self):
        self.assertEqual(
            m.classify_convergence(
                [
                    history(1, 4.00, 4.00, 0.1),
                    history(2, 3.99, 3.99, 0.1),
                    history(3, 3.98, 3.98, 0.1),
                ],
                conv_cfg(),
            ),
            "STAGNATED",
        )

    def test_T14_convergence_oscillatory(self):
        self.assertEqual(
            m.classify_convergence(
                [
                    history(1, 4.0, 4.0, 0.1),
                    history(2, 3.0, 3.0, 0.1),
                    history(3, 4.0, 4.0, 0.1),
                    history(4, 3.0, 3.0, 0.1),
                ],
                conv_cfg(),
            ),
            "OSCILLATORY",
        )

    def test_T15_convergence_max_blocks(self):
        self.assertEqual(
            m.classify_convergence(
                [
                    history(
                        5,
                        4.0,
                        4.0,
                        0.1,
                    )
                ],
                conv_cfg(),
            ),
            "MAX_BLOCKS_REACHED",
        )

    def test_T16_convergence_failed(self):
        self.assertEqual(
            m.classify_convergence(
                [
                    history(
                        1,
                        4.0,
                        4.0,
                        ok=False,
                    )
                ],
                conv_cfg(),
            ),
            "FAILED",
        )

    def test_T17_provenance_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {"config_id": "C"}
                )
            )

            pcr = root / "x.pcr"
            pcr.write_text("x")

            data = root / "x.dat"
            data.write_text("d")

            identity = (
                m.build_input_identity(
                    "X",
                    data,
                    m.sha256_file(data),
                    "fixture",
                    False,
                    True,
                )
            )

            manifest = (
                m.build_provenance_manifest(
                    block_id="B",
                    stage_id="S",
                    timestamp_start="a",
                    timestamp_end="b",
                    argv=["fp"],
                    fp2k_sha256="f",
                    config_path=config,
                    input_pcr_path=pcr,
                    diffraction_input=identity,
                    return_code=0,
                    stdout="",
                    stderr="",
                    produced_artifacts={},
                    parser_status="PASS",
                    convergence_status="CONTINUE",
                    failure_category=None,
                    implementation_path=Path(
                        __file__
                    ),
                )
            )

            required = {
                "task_id",
                "block_id",
                "stage_id",
                "timestamp_start",
                "timestamp_end",
                "argv",
                "platform",
                "fp2k_sha256",
                "orchestrator",
                "config",
                "input_pcr",
                "diffraction_input",
                "return_code",
                "stdout_sha256",
                "stderr_sha256",
                "produced_artifacts",
                "parser_status",
                "convergence_status",
                "failure_category",
            }

            self.assertFalse(
                required - set(manifest)
            )

    def test_T18_fp2k_pin_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fp2k"

            path.write_text("fake")
            path.chmod(0o755)

            with self.assertRaisesRegex(
                RuntimeError,
                "SHA256 mismatch",
            ):
                m.qualify_fullprof_executable(
                    path
                )

    def test_missing_output_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(
                RuntimeError
            ):
                m.require_output(
                    Path(td) / "x"
                )

    def test_prf_no_numeric_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.prf"

            path.write_text(
                "text only\n"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "PARSE_FAILURE",
            ):
                m.parse_prf_required(
                    path,
                    {
                        "prf_required_before_readiness": [
                            "numeric_profile_present"
                        ]
                    },
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
