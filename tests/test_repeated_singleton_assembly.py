from __future__ import annotations

import unittest

from packages.opus_solver import build_manufacturing_plan
from packages.opus_solver.chemistry_composition import manufacturing_requirements, required_flow_relations
from packages.opus_solver.candidate_solution import assign_branch_reagent_indices


def _singleton(element: str) -> dict:
    return {
        "atoms": [{"id": "a0", "element": element, "position": [0, 0]}],
        "bonds": [],
    }


def _four_atom_chain(element: str = "earth") -> dict:
    return {
        "atoms": [
            {"id": "a0", "element": element, "position": [-1, 1]},
            {"id": "a1", "element": element, "position": [0, 0]},
            {"id": "a2", "element": element, "position": [1, 0]},
            {"id": "a3", "element": element, "position": [1, 1]},
        ],
        "bonds": [
            {"type": "normal", "from": [1, 0], "to": [1, 1]},
            {"type": "normal", "from": [0, 0], "to": [1, 0]},
            {"type": "normal", "from": [-1, 1], "to": [0, 0]},
        ],
    }


def _renewable_singleton_puzzle() -> dict:
    return {
        "availableParts": {
            "arms": ["arm1", "arm2", "arm3", "arm6", "piston"],
            "glyphs": ["equilibrium", "bonder", "unbonder", "multibonder", "calcification"],
        },
        "reagents": [_singleton("earth")],
        "products": [_four_atom_chain("earth")],
    }


class RepeatedSingletonAssemblyTests(unittest.TestCase):
    def test_reuses_one_reagent_for_every_product_atom(self) -> None:
        plan = build_manufacturing_plan(_renewable_singleton_puzzle())

        self.assertTrue(plan.supported)
        self.assertEqual(plan.strategy, "repeated-singleton-assembly-v1")
        self.assertEqual(plan.required_glyphs, ("bonder",))
        self.assertEqual(plan.atom_flows, ())

        sources = [operation for operation in plan.operations if operation.kind == "source"]
        bonds = [operation for operation in plan.operations if operation.kind == "bond"]
        placements = [operation for operation in plan.operations if operation.kind == "place"]
        self.assertEqual(len(sources), 4)
        self.assertEqual(len(placements), 4)
        self.assertEqual(len(bonds), 3)
        self.assertEqual(
            {operation.metadata["reagentIndex"] for operation in sources},
            {0},
        )
        self.assertTrue(all(operation.metadata["reusableSource"] for operation in sources))

    def test_manufacturing_requirements_capture_three_bonds_and_four_spawns(self) -> None:
        plan = build_manufacturing_plan(_renewable_singleton_puzzle())
        requirements = manufacturing_requirements(plan)
        relations = required_flow_relations(plan)

        self.assertEqual(requirements["sourceCount"], 4)
        self.assertEqual(requirements["placementCount"], 4)
        self.assertEqual(requirements["convergenceInputCount"], 2)
        self.assertTrue(requirements["requiresConvergence"])
        self.assertEqual(relations["bond-created"], 3)
        self.assertEqual(relations["delivered"], 1)

    def test_single_reagent_maps_to_any_number_of_assembly_branches(self) -> None:
        plan = build_manufacturing_plan(_renewable_singleton_puzzle())
        candidate = {"branches": [[], [], []]}

        self.assertEqual(assign_branch_reagent_indices(candidate, plan), {0: 0, 1: 0, 2: 0})

    def test_can_calcify_reused_singleton_when_target_requires_salt(self) -> None:
        puzzle = _renewable_singleton_puzzle()
        puzzle["products"] = [_four_atom_chain("salt")]
        plan = build_manufacturing_plan(puzzle)

        self.assertTrue(plan.supported)
        self.assertEqual(plan.strategy, "repeated-singleton-assembly-v1")
        self.assertEqual(plan.required_glyphs, ("bonder", "glyph-calcification"))
        self.assertEqual(
            len([operation for operation in plan.operations if operation.kind == "transform"]),
            4,
        )

    def test_rejects_disconnected_multi_atom_product(self) -> None:
        puzzle = _renewable_singleton_puzzle()
        puzzle["products"][0]["bonds"] = [
            {"type": "normal", "from": [-1, 1], "to": [0, 0]},
        ]
        plan = build_manufacturing_plan(puzzle)

        self.assertFalse(plan.supported)

    def test_existing_two_atom_bonded_pair_keeps_specialized_base_strategy(self) -> None:
        puzzle = {
            "availableParts": {"glyphs": ["bonder", "calcification"]},
            "reagents": [_singleton("water"), _singleton("fire")],
            "products": [{
                "atoms": [
                    {"id": "a0", "element": "salt", "position": [0, 0]},
                    {"id": "a1", "element": "fire", "position": [1, 0]},
                ],
                "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
            }],
        }

        plan = build_manufacturing_plan(puzzle)

        self.assertTrue(plan.supported)
        self.assertEqual(plan.strategy, "bonded-pair-v1")


if __name__ == "__main__":
    unittest.main()
