from __future__ import annotations

import unittest

from packages.opus_solver.generation_extensions import generate_composed_candidates


def _triangle(element: str) -> dict:
    return {
        "atoms": [
            {"id": "a0", "element": element, "position": [-1, 0]},
            {"id": "a1", "element": element, "position": [-1, 1]},
            {"id": "a2", "element": element, "position": [0, 0]},
        ],
        "bonds": [
            {"type": "normal", "from": [-1, 0], "to": [0, 0]},
            {"type": "normal", "from": [-1, 1], "to": [0, 0]},
            {"type": "normal", "from": [-1, 0], "to": [-1, 1]},
        ],
    }


def _puzzle() -> dict:
    return {
        "availableParts": {"glyphs": ["bonder", "calcification"]},
        "reagents": [_triangle("water"), _triangle("water")],
        "products": [{
            "atoms": [
                {"id": "w0", "element": "water", "position": [0, 0]},
                {"id": "w1", "element": "water", "position": [0, 1]},
                {"id": "w2", "element": "water", "position": [1, 0]},
                {"id": "s0", "element": "salt", "position": [0, -1]},
                {"id": "s1", "element": "salt", "position": [-1, -1]},
                {"id": "s2", "element": "salt", "position": [-1, 0]},
            ],
            "bonds": [
                {"type": "normal", "from": [0, 0], "to": [0, 1]},
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [0, 1], "to": [1, 0]},
                {"type": "normal", "from": [0, -1], "to": [-1, -1]},
                {"type": "normal", "from": [0, -1], "to": [-1, 0]},
                {"type": "normal", "from": [-1, -1], "to": [-1, 0]},
                {"type": "normal", "from": [-1, 0], "to": [0, 0]},
                {"type": "normal", "from": [0, -1], "to": [0, 0]},
            ],
        }],
    }


class ExtendedGenerationRoutingTests(unittest.TestCase):
    def test_composed_generator_uses_extended_cluster_planner(self) -> None:
        result = generate_composed_candidates(
            _puzzle(),
            {"transitions": [], "convergenceMotifs": []},
            {"fragments": []},
            validate_engine=False,
        )
        self.assertTrue(result["summary"]["supported"])
        self.assertEqual(result["plan"]["strategy"], "paired-bonded-clusters-v1")
        self.assertEqual(result["summary"]["assemblyCandidateCount"], 0)


if __name__ == "__main__":
    unittest.main()
