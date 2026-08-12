from __future__ import annotations

import json
from pathlib import Path
import unittest

from packages.opus_parser import parse_solution_bytes
from packages.opus_parser.tests.test_parsers import i32, net_string
from packages.opus_parser.tests.test_puzzle_schema import _assert_schema_shape


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOLUTION_SCHEMA = json.loads(
    (REPOSITORY_ROOT / "schemas" / "solution.schema.json").read_text(encoding="utf-8")
)


def solution_with_arm_and_track() -> bytes:
    return b"".join([
        i32(7), net_string("TEST.puzzle"), net_string("Solution"),
        i32(4), i32(0), i32(120), i32(1), i32(40), i32(2), i32(15), i32(3), i32(8),
        i32(2),
        net_string("arm1"), bytes([1]), i32(0), i32(0), i32(1), i32(0), i32(0),
        i32(2), i32(0), bytes([ord("G")]), i32(1), bytes([ord("R")]), i32(3),
        net_string("track"), bytes([1]), i32(1), i32(1), i32(1), i32(0), i32(0),
        i32(0), i32(2), i32(0), i32(0), i32(1), i32(0), i32(0),
    ])


def solution_with_pipe() -> bytes:
    return b"".join([
        i32(7), net_string("PRODUCTION.puzzle"), net_string("Pipe"),
        i32(0), i32(1),
        net_string("pipe"), bytes([1]), i32(-1), i32(2), i32(1), i32(0), i32(0),
        i32(0), i32(0), i32(100), i32(2), i32(0), i32(0), i32(1), i32(-1),
    ])


def version_6_solution_with_unknown_values() -> bytes:
    return b"".join([
        i32(6), net_string("OLD.puzzle"), net_string("Unknown values"),
        i32(1), i32(99), i32(-7), i32(1),
        net_string("arm1"), bytes([2]), i32(0), i32(0), i32(1), i32(-6), i32(0),
        i32(1), i32(-3), bytes([1]), i32(257),
    ])


class SolutionSchemaTests(unittest.TestCase):
    def test_schema_matches_parser_output_variants(self):
        cases = (
            ("track.solution", solution_with_arm_and_track()),
            (None, solution_with_pipe()),
            ("legacy.solution", version_6_solution_with_unknown_values()),
        )
        for source_name, data in cases:
            with self.subTest(source_name=source_name):
                solution = parse_solution_bytes(data, source_name=source_name)
                _assert_schema_shape(SOLUTION_SCHEMA, solution, root=SOLUTION_SCHEMA)


if __name__ == "__main__":
    unittest.main()
