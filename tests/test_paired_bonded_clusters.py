from __future__ import annotations

import unittest

from packages.opus_solver import build_manufacturing_plan
from packages.opus_solver.candidate_solution import assign_branch_reagent_indices


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


def _aqueous_like_puzzle() -> dict:
    return {
        "availableParts": {
            "glyphs": ["equilibrium", "bonder", "unbonder", "multibonder", "calcification"],
        },
        "reagents": [_triangle("water"), _triangle("water")],
        "products": [{
            "atoms": [
                {"id": "a0", "element": "water", "position": [0, 0]},
                {"id": "a1", "element": "water", "position": [0, 1]},
                {"id": "a2", "element": "water", "position": [1, 0]},
                {"id": "a3", "element": "salt", "position": [0, -1]},
                {"id": "a4", "element": "salt", "position": [-1, -1]},
                {"id": "a5", "element": "salt", "position": [-1, 0]},
            ],
            "bonds": [
                {"type": "normal", "from": [0, 1], "to": [1, 0]},
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [0, 0], "to": [0, 1]},
                {"type": "normal", "from": [-1, -1], "to": [0, -1]},
                {"type": "normal", "from": [-1, 0], "to": [0, -1]},
                {"type": "normal", "from": [-1, -1], "to": [-1, 0]},
                {"type": "normal", "from": [-1, 0], "to": [0, 0]},
                {"type": "normal", "from": [0, -1], "to": [0, 0]},
            ],
        }],
    }


class PairedBondedClustersTests(unittest.TestCase):
    def test_recognizes_bond_preserving_cluster_calcification(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        self.assertTrue(plan.supported)
        self.assertEqual(plan.strategy, "paired-bonded-clusters-v1")
        self.assertEqual(plan.required_glyphs, ("bonder", "glyph-calcification"))
        kinds = [operation.kind for operation in plan.operations]
        self.assertEqual(kinds.count("source"), 2)
        self.assertEqual(kinds.count("transform"), 3)
        self.assertEqual(kinds.count("bond"), 2)
        self.assertEqual(kinds.count("deliver"), 1)
        self.assertTrue(all(
            operation.metadata.get("preserveExistingBonds")
            for operation in plan.operations
            if operation.kind == "transform"
        ))
        source_roles = {
            operation.metadata.get("branchRole"): operation.metadata.get("reagentIndex")
            for operation in plan.operations
            if operation.kind == "source"
        }
        self.assertEqual(source_roles, {"direct": 0, "calcifying": 1})

    def test_maps_calcifying_branch_to_calcified_cluster_source(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        candidate = {
            "branches": [
                [{"relation": "calcify"}],
                [{"relation": "bond-created"}],
            ],
            "convergence": {"inputs": [{}, {}]},
        }
        self.assertEqual(assign_branch_reagent_indices(candidate, plan), {0: 1, 1: 0})

    def test_maps_calcifying_branch_when_branch_order_is_reversed(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        candidate = {
            "branches": [
                [{"relation": "bond-created"}],
                [{"relation": "calcify"}],
            ],
            "convergence": {"inputs": [{}, {}]},
        }
        self.assertEqual(assign_branch_reagent_indices(candidate, plan), {0: 0, 1: 1})

    def test_rejects_ambiguous_cluster_branch_routing(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        candidate = {
            "branches": [
                [{"relation": "bond-created"}],
                [{"relation": "bond-created"}],
            ],
            "convergence": {"inputs": [{}, {}]},
        }
        with self.assertRaisesRegex(ValueError, "exactly one calcifying source branch"):
            assign_branch_reagent_indices(candidate, plan)

    def test_rejects_cluster_when_calcification_is_unavailable(self) -> None:
        puzzle = _aqueous_like_puzzle()
        puzzle["availableParts"]["glyphs"].remove("calcification")
        plan = build_manufacturing_plan(puzzle)
        self.assertFalse(plan.supported)
        self.assertEqual(plan.strategy, "bonded-pair-v1")


if __name__ == "__main__":
    unittest.main()
