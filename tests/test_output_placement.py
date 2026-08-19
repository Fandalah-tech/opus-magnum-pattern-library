from __future__ import annotations

import unittest

from packages.opus_solver.output_placement import (
    add_standard_output,
    product_output_opportunities,
)


class OutputPlacementTests(unittest.TestCase):
    def test_finds_rigid_product_match_without_solution_geometry(self) -> None:
        puzzle = {
            "products": [{
                "atoms": [
                    {"id": "a", "element": "copper", "position": [0, 0]},
                    {"id": "b", "element": "silver", "position": [1, 0]},
                ],
                "bonds": [
                    {"from": [0, 0], "to": [1, 0], "type": "normal"},
                ],
            }],
        }
        replay = {
            "frames": [{
                "cycle": 12,
                "world": {
                    "atoms": [
                        {"id": "x", "element": "copper", "position": [4, -2], "heldBy": []},
                        {"id": "y", "element": "silver", "position": [4, -1], "heldBy": []},
                    ],
                    "bonds": [
                        {"fromAtomId": "x", "toAtomId": "y", "type": "normal"},
                    ],
                    "molecules": [
                        {"id": "m0", "atomIds": ["x", "y"], "bondKeys": []},
                    ],
                },
            }],
        }

        opportunities = product_output_opportunities(puzzle, replay)

        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item["productIndex"], 0)
        self.assertEqual(item["origin"], [4, -2])
        self.assertEqual(item["rotation"], 1)
        self.assertEqual(item["firstCycle"], 12)

    def test_rejects_held_product_molecule_by_default(self) -> None:
        puzzle = {
            "products": [{
                "atoms": [{"id": "a", "element": "gold", "position": [0, 0]}],
                "bonds": [],
            }],
        }
        replay = {
            "frames": [{
                "cycle": 3,
                "world": {
                    "atoms": [{"id": "g", "element": "gold", "position": [2, 2], "heldBy": ["arm"]}],
                    "bonds": [],
                    "molecules": [{"id": "m0", "atomIds": ["g"], "bondKeys": []}],
                },
            }],
        }

        self.assertEqual(product_output_opportunities(puzzle, replay), [])
        self.assertEqual(len(product_output_opportunities(puzzle, replay, require_unheld=False)), 6)

    def test_appends_output_with_target_product_index(self) -> None:
        solution = {"source": {}, "parts": []}
        opportunity = {
            "productIndex": 2,
            "origin": [3, -1],
            "rotation": 4,
            "firstCycle": 20,
            "observationCount": 1,
        }

        updated = add_standard_output(solution, opportunity)

        self.assertEqual(len(updated["parts"]), 1)
        part = updated["parts"][0]
        self.assertEqual(part["type"], "out-std")
        self.assertEqual(part["which"], 2)
        self.assertEqual(part["position"], [3, -1])
        self.assertEqual(part["rotation"], 4)
        self.assertEqual(updated["source"]["outputPlacementRepairs"][0]["targetSolutionBytesUsed"], 0)
        self.assertEqual(solution["parts"], [])


if __name__ == "__main__":
    unittest.main()
