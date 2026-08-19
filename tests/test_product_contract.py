from __future__ import annotations

import unittest

from packages.opus_solver.product_contract import enforce_puzzle_product_contract


class ProductContractTests(unittest.TestCase):
    def test_missing_product_output_cannot_be_silently_ignored(self) -> None:
        puzzle = {
            "products": [
                {"atoms": [{"element": "gold", "position": [0, 0]}], "bonds": []},
                {"atoms": [{"element": "silver", "position": [0, 0]}], "bonds": []},
            ]
        }
        solution = {
            "parts": [
                {"id": "out-0", "type": "out-std", "which": 0},
            ]
        }
        legacy = {
            "complete": True,
            "failureMode": None,
            "deliveredByProduct": {"0": 6},
            "outputDeficits": {"0": 0},
            "totalDeficit": 0,
        }

        result = enforce_puzzle_product_contract(puzzle, solution, legacy, target=6)

        self.assertFalse(result["complete"])
        self.assertEqual(result["failureMode"], "missing-product-output")
        self.assertEqual(result["expectedProductIndices"], [0, 1])
        self.assertEqual(result["missingProductOutputIndices"], [1])
        self.assertEqual(result["outputDeficits"], {"0": 0, "1": 6})
        self.assertEqual(result["totalDeficit"], 6)

    def test_all_product_outputs_preserve_complete_validation(self) -> None:
        puzzle = {"products": [{}, {}, {}]}
        solution = {
            "parts": [
                {"id": "out-0", "type": "out-std", "which": 0},
                {"id": "out-1", "type": "out-std", "which": 1},
                {"id": "out-2", "type": "out-std", "which": 2},
            ]
        }
        legacy = {
            "complete": True,
            "failureMode": None,
            "deliveredByProduct": {"0": 6, "1": 6, "2": 6},
            "outputDeficits": {"0": 0, "1": 0, "2": 0},
            "totalDeficit": 0,
        }

        result = enforce_puzzle_product_contract(puzzle, solution, legacy, target=6)

        self.assertTrue(result["complete"])
        self.assertEqual(result["missingProductOutputIndices"], [])
        self.assertTrue(result["productOutputContractComplete"])

    def test_duplicate_outputs_do_not_substitute_for_missing_product_index(self) -> None:
        puzzle = {"products": [{}, {}]}
        solution = {
            "parts": [
                {"id": "out-a", "type": "out-std", "which": 0},
                {"id": "out-b", "type": "out-std", "which": 0},
            ]
        }
        legacy = {
            "complete": True,
            "failureMode": None,
            "deliveredByProduct": {"0": 12},
        }

        result = enforce_puzzle_product_contract(puzzle, solution, legacy, target=6)

        self.assertFalse(result["complete"])
        self.assertEqual(result["missingProductOutputIndices"], [1])
        self.assertEqual(result["outputGlyphsByProduct"]["0"], ["out-a", "out-b"])


if __name__ == "__main__":
    unittest.main()
