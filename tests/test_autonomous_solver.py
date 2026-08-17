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
        result = solve_puzzle_auto(_simple_bonded_pair(), objective="cycles")

        self.assertTrue(result.validation["complete"])
        self.assertEqual(result.validation["solverRoute"], "direct-generator-v1")
        self.assertEqual(result.validation["optimizationObjective"], "cycles")
        self.assertEqual(result.validation["optimizationMetricSource"], "opus-engine-local")
        self.assertIsInstance(result.validation["localCandidateMetrics"]["cycles"], int)
        self.assertGreater(result.validation["localCandidateMetrics"]["instructions"], 0)
        self.assertEqual(result.strategy, "bonded-pair-v1")

    def test_direct_generator_can_use_authoritative_oracle_objective(self) -> None:
        calls = []

        def oracle(solution: dict) -> dict:
            calls.append(solution)
            return {
                "valid": True,
                "metrics": {
                    "cost": 40,
                    "cycles": 77,
                    "area": 9,
                    "instructions": 13,
                },
                "rate": 11,
                "issues": [],
            }

        result = solve_puzzle_auto(
            _simple_bonded_pair(),
            objective="cost",
            oracle_validator=oracle,
            oracle_name="fake-omsim",
        )

        self.assertEqual(len(calls), 1)
        self.assertTrue(result.validation["complete"])
        self.assertEqual(result.validation["optimizationObjective"], "cost")
        self.assertEqual(result.validation["optimizationMetricSource"], "fake-omsim")
        self.assertEqual(result.validation["oracleMetrics"]["cost"], 40)
        self.assertEqual(result.validation["oracleMetrics"]["rate"], 11)
        self.assertEqual(result.validation["objectiveKey"], [40, 9, 77, 13])
        self.assertEqual(result.validation["oracleScoredCandidateCount"], 1)
        self.assertEqual(result.validation["oracleValidCandidateCount"], 1)

    def test_requires_knowledge_before_composition_fallback(self) -> None:
        with self.assertRaises(UnsupportedPuzzleError):
            solve_puzzle_auto(_unsupported_shape())

    def test_requires_oracle_for_official_only_objective(self) -> None:
        with self.assertRaises(ValueError):
            solve_puzzle_auto(_simple_bonded_pair(), objective="cost")

    def test_rejects_unknown_optimization_objective(self) -> None:
        with self.assertRaises(ValueError):
            solve_puzzle_auto(_simple_bonded_pair(), objective="banana")


if __name__ == "__main__":
    unittest.main()
