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


def puzzle_with_reagent_bond(bond_code: int) -> bytes:
    return b"".join([
        i32(3), net_string("Bond Test"), u64(42), u64(0x0000010F),
        i32(1),
        i32(2), bytes([4, 0, 0, 2, 1, 0]),
        i32(1), bytes([bond_code, 0, 0, 1, 0]),
        i32(1),
        i32(1), bytes([1, 0, 0]), i32(0),
        i32(1), bytes([0]),
    ])


class PuzzleParserTests(unittest.TestCase):
    def test_minimal_puzzle(self):
        data = puzzle_with_reagent_bond(1)
        result = parse_puzzle_bytes(data, source_name="test.puzzle")
        self.assertEqual(result["name"], "Bond Test")
        self.assertEqual(result["schemaVersion"], "0.1.1")
        self.assertEqual(result["reagents"][0]["atoms"][0]["element"], "fire")
        self.assertEqual(result["reagents"][0]["bonds"][0]["type"], "normal")
        self.assertEqual(result["reagents"][0]["bonds"][0]["rawCode"], 1)
        self.assertFalse(result["production"])
        self.assertEqual(result["trailingBytes"], 0)

    def test_decodes_triplex_bond_channel_bitmask(self):
        cases = {
            2: ["red"],
            4: ["black"],
            8: ["yellow"],
            14: ["red", "black", "yellow"],
        }
        for bond_code, expected_channels in cases.items():
            with self.subTest(bond_code=bond_code):
                result = parse_puzzle_bytes(puzzle_with_reagent_bond(bond_code))
                bond = result["reagents"][0]["bonds"][0]
                self.assertEqual(bond["type"], "triplex")
                self.assertEqual(bond["rawCode"], bond_code)
                self.assertEqual(bond["triplexChannels"], expected_channels)

    def test_rejects_mixed_normal_and_triplex_bond_bits(self):
        with self.assertRaisesRegex(ParseError, "mixed normal/triplex"):
            parse_puzzle_bytes(puzzle_with_reagent_bond(3))

    def test_rejects_unknown_bond_bits(self):
        with self.assertRaisesRegex(ParseError, "Unknown bond code 16"):
            parse_puzzle_bytes(puzzle_with_reagent_bond(16))

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
