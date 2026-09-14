#!/usr/bin/env python3

import importlib.util
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE = HERE / "structure_a_orchestrator.py"

SPEC = importlib.util.spec_from_file_location(
    "structure_a_orchestrator",
    MODULE,
)

m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class StructureAOrchestratorTests(unittest.TestCase):

    def test_ascii_path_pass(self):
        m.ensure_ascii_path(Path("/tmp/cef-dy-test"))

    def test_non_ascii_path_rejected(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "ASCII-only",
        ):
            m.ensure_ascii_path(
                Path("/tmp/Документы")
            )

    def test_real_raw_hash_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fake.ras"
            p.write_text("synthetic", encoding="ascii")

            original = m.sha256_file

            try:
                m.sha256_file = (
                    lambda path: m.REAL_ARTIFACT_SHA256
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    "REAL_4K_FULLPROF_EXECUTION_NOT_AUTHORIZED",
                ):
                    m.guard_real_input(p)
            finally:
                m.sha256_file = original

    def test_missing_required_output_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(
                RuntimeError,
                "required output missing",
            ):
                m.require_output(
                    Path(td) / "missing.sum"
                )

    def test_empty_required_output_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.sum"
            p.touch()

            with self.assertRaisesRegex(
                RuntimeError,
                "required output empty",
            ):
                m.require_output(p)

    def test_prf_without_numeric_data_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.prf"
            p.write_text(
                "only text\nnothing numeric\n",
                encoding="ascii",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "no numeric data",
            ):
                m.parse_prf_required(p)

    def test_convergence_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            for suffix in (
                "out",
                "sum",
                "prf",
                "new",
            ):
                (root / f"x.{suffix}").write_text(
                    "x\n",
                    encoding="ascii",
                )

            result = m.classify_convergence(
                {"returncode": 0},
                {"fatal_markers": []},
                root,
                "x",
            )

            self.assertEqual(
                result["status"],
                "PASS",
            )

    def test_convergence_fails_on_fatal_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            for suffix in (
                "out",
                "sum",
                "prf",
                "new",
            ):
                (root / f"x.{suffix}").write_text(
                    "x\n",
                    encoding="ascii",
                )

            result = m.classify_convergence(
                {"returncode": 0},
                {"fatal_markers": ["fatal error"]},
                root,
                "x",
            )

            self.assertEqual(
                result["status"],
                "FAIL",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
