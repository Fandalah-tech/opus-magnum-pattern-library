from __future__ import annotations

import unittest

from packages.opus_solver.required_chemistry import required_chemistry_events


class RequiredChemistryTests(unittest.TestCase):
    def test_generic_transform_glyph_counts_as_required_chemistry(self) -> None:
        puzzle = {
            "reagents": [{
                "atoms": [{"id": "lead", "element": "lead", "position": [0, 0]}],
                "bonds": [],
            }],
            "products": [{
                "atoms": [{"id": "tin", "element": "tin", "position": [0, 0]}],
                "bonds": [],
            }],
            "availableParts": {
                "arms": ["arm1"],
                "glyphs": ["purification"],
            },
        }

        events = required_chemistry_events(puzzle)

        self.assertIn("atom-purified", events)
        self.assertIn("product-delivered", events)
        self.assertNotIn("atom-calcified", events)


if __name__ == "__main__":
    unittest.main()
