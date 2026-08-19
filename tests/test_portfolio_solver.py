from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

import packages.opus_solver as opus_solver
from packages.opus_solver.portfolio_solver import solve_puzzle_portfolio
from packages.opus_solver.solver import SolveResult


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


class PortfolioSolverTests(unittest.TestCase):
    def test_package_exports_unified_portfolio_entry_point(self) -> None:
        self.assertIs(opus_solver.solve_puzzle_auto, opus_solver.solve_puzzle_portfolio)

    def test_direct_only_solve_preserves_legacy_behavior_without_knowledge(self) -> None:
        result = solve_puzzle_portfolio(_simple_bonded_pair(), objective="cycles")

        self.assertTrue(result.validation["complete"])
        self.assertEqual(result.validation["solverRoute"], "direct-generator-v1")
        self.assertEqual(result.strategy, "bonded-pair-v1")

    def test_complete_learned_architecture_can_beat_direct_without_fragment_index(self) -> None:
        puzzle = _simple_bonded_pair()
        direct = opus_solver.solve_puzzle(puzzle)
        learned_solution = deepcopy(direct.solution)
        learned = {
            "id": "learned-better",
            "solution": learned_solution,
            "focusObjectives": ["cost"],
            "referenceMetrics": {"cost": 40, "cycles": 77, "area": 9, "instructions": 13},
        }
        oracle_calls = []

        def oracle(solution: dict) -> dict:
            name = str(solution.get("name") or "")
            oracle_calls.append(name)
            cost = 40 if name.endswith("learned-better") else 60
            return {
                "valid": True,
                "metrics": {
                    "cost": cost,
                    "cycles": 77,
                    "area": 9,
                    "instructions": 13,
                },
                "rate": 10,
                "issues": [],
            }

        result = solve_puzzle_portfolio(
            puzzle,
            flow_index=None,
            architecture_candidates=[learned],
            objective="cost",
            oracle_validator=oracle,
            oracle_name="test-oracle",
        )

        self.assertEqual(len(oracle_calls), 2)
        self.assertEqual(result.validation["selectedCandidateId"], "learned-better")
        self.assertEqual(result.validation["selectedCandidateSource"], "learned-architecture-bank")
        self.assertEqual(result.validation["solverRoute"], "knowledge-architecture-bank-v1")
        self.assertEqual(result.validation["oracleMetrics"]["cost"], 40)
        self.assertEqual(result.validation["oracleScoredCandidateCount"], 2)
        self.assertEqual(result.validation["oracleValidCandidateCount"], 2)
        self.assertTrue(result.validation["directGeneratorAvailable"])
        self.assertFalse(result.validation["fragmentKnowledgeAvailable"])
        self.assertEqual(result.validation["portfolioArchitectureCandidateCount"], 2)
        self.assertEqual(result.validation["learnedArchitectureCandidateCount"], 1)

    def test_direct_solution_is_injected_into_learned_portfolio_when_flow_exists(self) -> None:
        fake = SolveResult(
            puzzle_name="STABILIZED WATER",
            strategy="bonded-pair-v1+knowledge-portfolio-v1",
            plan=opus_solver.build_manufacturing_plan(_simple_bonded_pair()),
            solution={"parts": []},
            validation={
                "complete": True,
                "selectedCandidateId": "learned-seed",
                "selectedCandidateSource": "learned-architecture-bank",
            },
        )
        learned_seed = {
            "id": "learned-seed",
            "solution": {"parts": []},
            "focusObjectives": ["cycles"],
        }
        flow = {"transitions": [], "fragments": [], "convergenceMotifs": []}

        with patch(
            "packages.opus_solver.portfolio_solver.solve_puzzle_from_knowledge",
            return_value=fake,
        ) as composed:
            result = solve_puzzle_portfolio(
                _simple_bonded_pair(),
                flow_index=flow,
                architecture_candidates=[learned_seed],
                objective="cycles",
            )

        kwargs = composed.call_args.kwargs
        seeds = kwargs["architecture_candidates"]
        self.assertEqual([item["id"] for item in seeds], ["direct-generator-v1", "learned-seed"])
        self.assertEqual(seeds[0]["provenance"]["kind"], "direct-generator")
        self.assertTrue(result.validation["directGeneratorAvailable"])
        self.assertEqual(result.validation["directGeneratorStrategy"], "bonded-pair-v1")
        self.assertTrue(result.validation["fragmentKnowledgeAvailable"])
        self.assertEqual(result.validation["portfolioArchitectureCandidateCount"], 2)
        self.assertEqual(result.validation["learnedArchitectureCandidateCount"], 1)

    def test_selected_direct_seed_is_reported_as_direct_route(self) -> None:
        fake = SolveResult(
            puzzle_name="STABILIZED WATER",
            strategy="bonded-pair-v1+knowledge-portfolio-v1",
            plan=opus_solver.build_manufacturing_plan(_simple_bonded_pair()),
            solution={"parts": []},
            validation={
                "complete": True,
                "selectedCandidateId": "direct-generator-v1",
                "selectedCandidateSource": "learned-architecture-bank",
            },
        )
        flow = {"transitions": [], "fragments": [], "convergenceMotifs": []}

        with patch(
            "packages.opus_solver.portfolio_solver.solve_puzzle_from_knowledge",
            return_value=fake,
        ):
            result = solve_puzzle_portfolio(
                _simple_bonded_pair(),
                flow_index=flow,
                objective="cycles",
            )

        self.assertEqual(result.validation["solverRoute"], "direct-generator-v1")
        self.assertEqual(result.validation["selectedCandidateSource"], "direct-generator")
        self.assertEqual(result.validation["selectedCandidateKind"], "direct-complete-architecture")
        self.assertEqual(result.strategy, "bonded-pair-v1")


if __name__ == "__main__":
    unittest.main()
