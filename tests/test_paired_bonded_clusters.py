from __future__ import annotations

import unittest

from packages.opus_solver import build_manufacturing_plan
from packages.opus_solver.candidate_solution import (
    assign_branch_reagent_indices,
    resolve_input_reagent_index,
)


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
        source_groups = {
            operation.metadata.get("interchangeableSourceGroup")
            for operation in plan.operations
            if operation.kind == "source"
        }
        self.assertEqual(source_groups, {"homologous-bonded-clusters"})

    def test_maps_interchangeable_sources_deterministically(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        candidate = {
            "branches": [
                [{"relation": "calcify"}, {"relation": "calcify"}],
                [{"relation": "calcify"}],
            ],
            "convergence": {"inputs": [{"relations": ["calcify"]}, {"relations": ["calcify"]}]},
        }
        self.assertEqual(assign_branch_reagent_indices(candidate, plan), {0: 0, 1: 1})

    def test_shared_input_can_feed_interchangeable_branches(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        raw_part = {
            "id": "shared-input",
            "sourceFragmentInstances": [
                "branch-0:upstream-2:part-0",
                "branch-1:upstream-1:part-0",
            ],
        }
        resolved = resolve_input_reagent_index(raw_part, {0: 0, 1: 1}, [0, 1], plan)
        self.assertEqual(resolved, 0)

    def test_unattributed_input_can_use_interchangeable_source(self) -> None:
        plan = build_manufacturing_plan(_aqueous_like_puzzle())
        resolved = resolve_input_reagent_index({"id": "shared-root"}, {0: 0, 1: 1}, [0, 1], plan)
        self.assertEqual(resolved, 0)

    def test_rejects_cluster_when_calcification_is_unavailable(self) -> None:
        puzzle = _aqueous_like_puzzle()
        puzzle["availableParts"]["glyphs"].remove("calcification")
        plan = build_manufacturing_plan(puzzle)
        self.assertFalse(plan.supported)
        self.assertEqual(plan.strategy, "bonded-pair-v1")


if __name__ == "__main__":
    unittest.main()
