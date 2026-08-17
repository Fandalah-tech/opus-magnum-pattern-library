from __future__ import annotations

import unittest

from packages.opus_solver.chemistry_composition import required_flow_relations
from packages.opus_solver.generic_chemistry import build_element_recipes, generic_singleton_chemistry_plan


def bonded_reagent_puzzle() -> dict:
    return {
        "reagents": [
            {
                "atoms": [
                    {"id": "a0", "element": "earth", "position": [0, 0]},
                    {"id": "a1", "element": "earth", "position": [1, 0]},
                ],
                "bonds": [
                    {"type": "normal", "from": [0, 0], "to": [1, 0]},
                ],
            }
        ],
        "products": [
            {
                "atoms": [
                    {"id": "p0", "element": "earth", "position": [0, 0]},
                    {"id": "p1", "element": "salt", "position": [1, 0]},
                ],
                "bonds": [
                    {"type": "normal", "from": [0, 0], "to": [1, 0]},
                ],
            }
        ],
        "availableParts": {
            "arms": ["arm1"],
            "glyphs": ["bonder", "unbonder", "calcification"],
        },
    }


class GenericReagentChemistryTests(unittest.TestCase):
    def test_bonded_reagent_atom_becomes_extractable_source(self) -> None:
        routes = build_element_recipes(bonded_reagent_puzzle())
        earth = routes["earth"]
        salt = routes["salt"]

        self.assertEqual(earth.kind, "extract")
        self.assertEqual(earth.reagent_index, 0)
        self.assertEqual(earth.extraction_bond_count, 1)
        self.assertEqual(salt.kind, "calcification")
        self.assertEqual(salt.inputs[0].kind, "extract")

    def test_generic_plan_exposes_required_unbond_relation(self) -> None:
        plan = generic_singleton_chemistry_plan(bonded_reagent_puzzle())
        self.assertIsNotNone(plan)
        assert plan is not None

        self.assertTrue(plan.supported)
        self.assertEqual(plan.strategy, "generic-reagent-chemistry-v1")
        self.assertEqual(set(plan.required_glyphs), {"bonder", "glyph-calcification", "unbonder"})
        self.assertEqual(
            required_flow_relations(plan),
            {
                "bond-created": 1,
                "bond-removed": 2,
                "calcify": 1,
                "delivered": 1,
            },
        )

    def test_unbonder_is_required_for_bonded_feed_extraction(self) -> None:
        puzzle = bonded_reagent_puzzle()
        puzzle["availableParts"]["glyphs"].remove("unbonder")
        routes = build_element_recipes(puzzle)
        self.assertNotIn("earth", routes)
        self.assertIsNone(generic_singleton_chemistry_plan(puzzle))


if __name__ == "__main__":
    unittest.main()
