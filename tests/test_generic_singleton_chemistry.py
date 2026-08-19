from __future__ import annotations

import unittest

from packages.opus_solver.generic_chemistry import build_element_recipes, generic_singleton_chemistry_plan
from packages.opus_solver.manufacturing_extensions import repeated_singleton_assembly_plan


def atom(element: str, q: int = 0, r: int = 0, atom_id: str = "a0") -> dict:
    return {"id": atom_id, "element": element, "position": [q, r]}


def singleton_reagent(element: str, index: int) -> dict:
    return {"id": index, "atoms": [atom(element)], "bonds": []}


def singleton_product(element: str, index: int) -> dict:
    return {"id": index, "atoms": [atom(element)], "bonds": []}


class GenericSingletonChemistryTests(unittest.TestCase):
    def test_purification_chain_reaches_gold(self) -> None:
        puzzle = {
            "reagents": [singleton_reagent("lead", 0)],
            "products": [singleton_product("gold", 0)],
            "availableParts": {"glyphs": ["purification"], "arms": ["arm1"]},
        }
        routes = build_element_recipes(puzzle)
        self.assertIn("gold", routes)
        self.assertEqual(routes["gold"].kind, "purification")
        self.assertEqual(routes["gold"].depth, 5)
        plan = generic_singleton_chemistry_plan(puzzle)
        self.assertIsNotNone(plan)
        self.assertTrue(plan.supported)
        self.assertEqual(plan.strategy, "generic-singleton-chemistry-v1")
        self.assertIn("glyph-purification", plan.required_glyphs)
        self.assertEqual(sum(operation.kind == "deliver" for operation in plan.operations), 1)

    def test_projection_prefers_quicksilver_promotion_over_deeper_purification(self) -> None:
        puzzle = {
            "reagents": [singleton_reagent("lead", 0), singleton_reagent("quicksilver", 1)],
            "products": [singleton_product("iron", 0)],
            "availableParts": {"glyphs": ["projection", "purification"], "arms": ["arm1"]},
        }
        routes = build_element_recipes(puzzle)
        self.assertEqual(routes["tin"].kind, "projection")
        self.assertEqual(routes["iron"].kind, "projection")

    def test_animismus_supports_two_outputs_without_solution_knowledge(self) -> None:
        puzzle = {
            "reagents": [singleton_reagent("salt", 0)],
            "products": [singleton_product("mors", 0), singleton_product("vitae", 1)],
            "availableParts": {"glyphs": ["animismus"], "arms": ["arm1"]},
        }
        plan = generic_singleton_chemistry_plan(puzzle)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.strategy, "generic-singleton-chemistry-v1")
        self.assertEqual(sum(operation.kind == "deliver" for operation in plan.operations), 2)
        self.assertIn("glyph-animismus", plan.required_glyphs)

    def test_connected_multiatom_product_is_assembled(self) -> None:
        product = {
            "id": 0,
            "atoms": [atom("earth", 0, 0, "a0"), atom("earth", 1, 0, "a1"), atom("salt", 2, 0, "a2")],
            "bonds": [
                {"from": [0, 0], "to": [1, 0], "type": "normal"},
                {"from": [1, 0], "to": [2, 0], "type": "normal"},
            ],
        }
        puzzle = {
            "reagents": [singleton_reagent("earth", 0)],
            "products": [product],
            "availableParts": {"glyphs": ["bonder", "calcification"], "arms": ["arm1"]},
        }
        # The older specialized route still recognizes this family; the generic
        # route is independently capable of expressing it as well.
        self.assertIsNotNone(repeated_singleton_assembly_plan(puzzle))
        plan = generic_singleton_chemistry_plan(puzzle)
        self.assertIsNotNone(plan)
        self.assertEqual(sum(operation.kind == "bond" for operation in plan.operations), 2)
        self.assertEqual(sum(operation.kind == "deliver" for operation in plan.operations), 1)

    def test_missing_reaction_returns_no_generic_plan(self) -> None:
        puzzle = {
            "reagents": [singleton_reagent("salt", 0)],
            "products": [singleton_product("gold", 0)],
            "availableParts": {"glyphs": [], "arms": ["arm1"]},
        }
        self.assertIsNone(generic_singleton_chemistry_plan(puzzle))


if __name__ == "__main__":
    unittest.main()
