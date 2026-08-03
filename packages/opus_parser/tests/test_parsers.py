from __future__ import annotations

import struct
import unittest

from packages.opus_parser import ParseError, parse_puzzle_bytes, parse_solution_bytes


def i32(value: int) -> bytes:
    return struct.pack("<i", value)


def u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def net_string(value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) >= 128:
        raise ValueError("test helper supports short strings only")
    return bytes([len(data)]) + data


class PuzzleParserTests(unittest.TestCase):
    def test_minimal_puzzle(self):
        data = b"".join([
            i32(3), net_string("Test Puzzle"), u64(42), u64(0x0000010F),
            i32(1),
            i32(2), bytes([4, 0, 0, 2, 1, 0]),
            i32(1), bytes([1, 0, 0, 1, 0]),
            i32(1),
            i32(1), bytes([1, 0, 0]), i32(0),
            i32(1), bytes([0]),
        ])
        result = parse_puzzle_bytes(data, source_name="test.puzzle")
        self.assertEqual(result["name"], "Test Puzzle")
        self.assertEqual(result["reagents"][0]["atoms"][0]["element"], "fire")
        self.assertEqual(result["reagents"][0]["bonds"][0]["type"], "normal")
        self.assertFalse(result["production"])
        self.assertEqual(result["trailingBytes"], 0)

    def test_rejects_wrong_version(self):
        with self.assertRaises(ParseError):
            parse_puzzle_bytes(i32(99))


class SolutionParserTests(unittest.TestCase):
    def test_minimal_solution_with_arm_and_track(self):
        data = b"".join([
            i32(7), net_string("TEST.puzzle"), net_string("Solution"),
            i32(4), i32(0), i32(120), i32(1), i32(40), i32(2), i32(15), i32(3), i32(8),
            i32(2),
            net_string("arm1"), bytes([1]), i32(0), i32(0), i32(1), i32(0), i32(0),
            i32(2), i32(0), bytes([ord("G")]), i32(1), bytes([ord("R")]), i32(3),
            net_string("track"), bytes([1]), i32(1), i32(1), i32(1), i32(0), i32(0),
            i32(0), i32(2), i32(0), i32(0), i32(1), i32(0), i32(0),
        ])
        result = parse_solution_bytes(data, source_name="test.solution")
        self.assertEqual(result["metrics"]["cycles"], 120)
        self.assertEqual(result["parts"][0]["program"][0]["instruction"], "grab")
        self.assertEqual(result["parts"][0]["armNumber"], 3)
        self.assertEqual(result["parts"][1]["trackHexes"], [[0, 0], [1, 0]])
        self.assertEqual(result["trailingBytes"], 0)

    def test_rejects_truncated_solution(self):
        with self.assertRaises(ParseError):
            parse_solution_bytes(i32(7) + b"\x05abc")


if __name__ == "__main__":
    unittest.main()
