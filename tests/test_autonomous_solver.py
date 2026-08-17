from __future__ import annotations

import unittest

from packages.opus_solver.autonomous import solve_puzzle_auto
from packages.opus_solver import UnsupportedPuzzleError


def _simple_bonded_pair() -> dict:
    return {
        "schemaVersion": "0.1.0",
        "source": {"name": "P007.puzzle"},
        "name": "STABILIZED WATER",
        "availableParts": {
            "arms": ["arm1"],
            "glyphs": ["equilibrium", "bonder", "calcification"],
        },
        "reagents": [
            {"atoms": [{"id": "a0", "element": "water", "position": [0, 0]}], "bonds": []},
            {"atoms": [{"id": "a0", "element": "water", "position": [0, 0]}], "bonds": []},
        ],
        "products": [{
            "atoms": [
                {"id": "a0", "element": "salt", "position": [0, 0]},
                {"id": "a1", "element": "water", "position": [1, 0]},
            ],
            "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
        }],
        "outputScale": 1,
        "production": False,
    }


def _unsupported_shape() -> dict:
    puzzle = _simple_bonded_pair()
    puzzle["products"][0]["atoms"].append(
        {"id": "a2", "element": "water", "position": [2, 0]}
    )
    return puzzle


class AutonomousSolverTests(unittest.TestCase):
    def test_preserves_direct_generator_as_first_route(self) -> None:
        result = solve_puzzle_auto(_simple_bonded_pair())

        self.assertTrue(result.validation["complete"])
        self.assertEqual(result.validation["solverRoute"], "direct-generator-v1")
        self.assertEqual(result.strategy, "bonded-pair-v1")

    def test_requires_knowledge_before_composition_fallback(self) -> None:
        with self.assertRaises(UnsupportedPuzzleError):
            solve_puzzle_auto(_unsupported_shape())


if __name__ == "__main__":
    unittest.main()
