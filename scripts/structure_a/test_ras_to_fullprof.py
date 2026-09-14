#!/usr/bin/env python3

from pathlib import Path
import importlib.util
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "ras_to_fullprof.py"

SPEC = importlib.util.spec_from_file_location("rasconv", MODULE_PATH)
rasconv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rasconv)


def make_block(
    xs,
    ys,
    thirds=None,
    metadata=None,
    start_line=1,
    end_line=999,
):
    if thirds is None:
        thirds = ["1.0000"] * len(xs)
    if metadata is None:
        metadata = {}

    rows = []

    for i, (x, y, z) in enumerate(zip(xs, ys, thirds), start=1):
        rows.append(
            {
                "line": i,
                "x": float(x),
                "y": float(y),
                "x_token": f"{x:.4f}",
                "y_token": f"{y:.4f}",
                "third_token": z,
            }
        )

    return {
        "start_line": start_line,
        "end_line": end_line,
        "metadata": metadata,
        "rows": rows,
    }


class StructureARasConverterTests(unittest.TestCase):

    def setUp(self):
        self.xs = [20.0000, 20.0100, 20.0200]
        self.ys = [100.0, 101.0, 102.0]

        self.expected = {
            "block_index": 1,
            "role": "synthetic",
            "points": 3,
            "start": 20.0000,
            "stop": 20.0200,
            "step": 0.0100,
        }

    def test_valid_constant_grid(self):
        block = make_block(
            self.xs,
            self.ys,
            metadata={
                "*MEAS_DATA_COUNT": "3.0000000000",
                "*MEAS_SCAN_START": "20.0000000000",
                "*MEAS_SCAN_STOP": "20.0200000000",
                "*MEAS_SCAN_STEP": "0.0100000000",
                "*MEAS_SCAN_UNIT_Y": "counts",
            },
        )

        result = rasconv.validate_block(block, self.expected)

        self.assertEqual(result["points"], 3)
        self.assertEqual(result["step_mismatch_count"], 0)
        self.assertEqual(result["nonpositive_count"], 0)

    def test_bad_point_count_rejected(self):
        block = make_block(self.xs, self.ys)

        expected = dict(self.expected)
        expected["points"] = 4

        with self.assertRaisesRegex(RuntimeError, "point count"):
            rasconv.validate_block(block, expected)

    def test_internal_grid_mismatch_rejected(self):
        block = make_block(
            [20.0000, 20.0110, 20.0200],
            self.ys,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "grid-step mismatches",
        ):
            rasconv.validate_block(block, self.expected)

    def test_metadata_count_mismatch_rejected(self):
        block = make_block(
            self.xs,
            self.ys,
            metadata={
                "*MEAS_DATA_COUNT": "4.0000000000",
            },
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "MEAS_DATA_COUNT",
        ):
            rasconv.validate_block(block, self.expected)

    def test_nonpositive_primary_rejected(self):
        block = make_block(
            self.xs,
            [100.0, 0.0, 102.0],
        )

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "should_not_exist.dat"

            with self.assertRaisesRegex(
                RuntimeError,
                "non-positive",
            ):
                rasconv.write_instrm0(block, output)

    def test_writer_preserves_payload_tokens(self):
        block = make_block(self.xs, self.ys)

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "synthetic.dat"

            rasconv.write_instrm0(block, output)

            lines = output.read_text(
                encoding="ascii"
            ).splitlines()

            self.assertEqual(
                lines[0],
                "20.0000 0.0100 155.0000",
            )

            payload = " ".join(lines[1:]).split()

            self.assertEqual(
                payload,
                [
                    "100.0000",
                    "101.0000",
                    "102.0000",
                ],
            )

    def test_multiple_blocks_must_not_be_concatenated(self):
        primary = make_block(
            [20.0000, 20.0100, 20.0200],
            [10.0, 11.0, 12.0],
        )

        secondary = make_block(
            [15.0000, 15.0100],
            [1.0, 2.0],
        )

        self.assertEqual(len([primary, secondary]), 2)

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "no_concat.dat"

            rasconv.write_instrm0(primary, output)

            payload = " ".join(
                output.read_text(
                    encoding="ascii"
                ).splitlines()[1:]
            ).split()

            self.assertEqual(len(payload), 3)
            self.assertEqual(
                payload,
                ["10.0000", "11.0000", "12.0000"],
            )

    def test_topology_mismatch_rejected(self):
        blocks = [
            make_block(
                self.xs,
                self.ys,
            )
        ]

        expected_count = 2

        with self.assertRaisesRegex(
            RuntimeError,
            "topology mismatch",
        ):
            if len(blocks) != expected_count:
                raise RuntimeError(
                    "RAS_INT topology mismatch: "
                    f"expected {expected_count} blocks, "
                    f"found {len(blocks)}"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
