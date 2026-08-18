from __future__ import annotations

import unittest

from packages.opus_solver.product_delivery import (
    add_singleton_product_extractor,
    ensure_all_standard_outputs,
)


class ProductDeliveryTests(unittest.TestCase):
    def test_adds_one_rotation_extractor_and_output(self) -> None:
        puzzle = {
            "products": [{
                "atoms": [{"id": "a0", "element": "gold", "position": [0, 0]}],
                "bonds": [],
            }],
        }
        solution = {
            "source": {},
            "parts": [{
                "id": "arm0",
                "type": "arm1",
                "enabled": True,
                "position": [0, 0],
                "length": 1,
                "rotation": 0,
                "which": 0,
                "armNumber": 1,
                "program": [],
            }],
        }
        opportunity = {
            "productIndex": 0,
            "origin": [4, -2],
            "rotation": 0,
            "firstCycle": 12,
            "lastCycle": 15,
            "observationCount": 4,
            "atomIds": ["gold-0"],
            "held": False,
        }

        updated = add_singleton_product_extractor(
            puzzle,
            solution,
            opportunity,
            base_rotation=0,
            motion_instruction="rotate_cw",
        )

        self.assertEqual(len(solution["parts"]), 1)
        self.assertEqual(solution["source"], {})
        outputs = [part for part in updated["parts"] if part["type"] == "out-std"]
        extractors = [part for part in updated["parts"] if part["id"].startswith("product-extractor-arm-")]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(len(extractors), 1)
        self.assertEqual(outputs[0]["which"], 0)
        self.assertEqual([item["cycle"] for item in extractors[0]["program"]], [12, 13, 14])
        repair = updated["source"]["productDeliveryRepairs"][0]
        self.assertEqual(repair["productIndex"], 0)
        self.assertEqual(repair["targetSolutionBytesUsed"], 0)
        self.assertNotEqual(repair["sourcePosition"], repair["destination"])

    def test_respects_nonzero_local_product_atom_position(self) -> None:
        puzzle = {
            "products": [{
                "atoms": [{"id": "a0", "element": "silver", "position": [1, 0]}],
                "bonds": [],
            }],
        }
        solution = {"source": {}, "parts": []}
        opportunity = {
            "productIndex": 0,
            "origin": [3, 2],
            "rotation": 0,
            "firstCycle": 5,
            "atomIds": ["s0"],
        }

        updated = add_singleton_product_extractor(
            puzzle,
            solution,
            opportunity,
            base_rotation=0,
            motion_instruction="rotate_ccw",
        )

        repair = updated["source"]["productDeliveryRepairs"][0]
        self.assertEqual(repair["sourcePosition"], [4, 2])
        self.assertEqual(solution["parts"], [])
        self.assertEqual(solution["source"], {})

    def test_places_every_missing_product_in_reserved_layout(self) -> None:
        puzzle = {
            "products": [
                {"atoms": [{"element": "gold", "position": [0, 0]}], "bonds": []},
                {"atoms": [{"element": "gold", "position": [0, 0]}], "bonds": []},
                {"atoms": [{"element": "silver", "position": [0, 0]}], "bonds": []},
            ],
        }
        solution = {
            "source": {},
            "parts": [
                {"id": "out0", "type": "out-std", "position": [2, 1], "rotation": 0, "which": 0},
                {"id": "arm0", "type": "arm1", "position": [8, 4], "rotation": 0, "length": 1, "armNumber": 1},
            ],
        }

        updated = ensure_all_standard_outputs(puzzle, solution)

        outputs = [part for part in updated["parts"] if part["type"] == "out-std"]
        self.assertEqual({part["which"] for part in outputs}, {0, 1, 2})
        generated = [part for part in outputs if part["id"] != "out0"]
        self.assertEqual(len(generated), 2)
        self.assertTrue(all(part["position"][0] > 8 and part["position"][1] > 4 for part in generated))
        repairs = [item for item in updated["source"]["productDeliveryRepairs"] if item["mode"] == "reserved-output-completeness"]
        self.assertEqual({item["productIndex"] for item in repairs}, {1, 2})
        self.assertEqual(solution["parts"][0]["position"], [2, 1])


if __name__ == "__main__":
    unittest.main()
