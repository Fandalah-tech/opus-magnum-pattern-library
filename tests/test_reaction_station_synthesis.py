from __future__ import annotations

import unittest

from packages.opus_solver.reaction_station_synthesis import add_purification_station


class ReactionStationSynthesisTests(unittest.TestCase):
    def test_adds_multiple_unbonders_and_keeps_existing_parts(self) -> None:
        solution = {
            "source": {},
            "parts": [
                {"id": "existing-purifier", "type": "glyph-purification", "position": [9, 9], "rotation": 0, "program": []},
            ],
        }
        opportunity = {
            "producedElement": "silver",
            "origin": [7, -1],
            "rotation": 2,
        }
        unbonds = [
            {"origin": [6, 0], "rotation": 3, "second": [5, 0]},
            {"origin": [6, 0], "rotation": 1, "second": [6, 1]},
        ]

        result = add_purification_station(solution, opportunity, unbond_candidates=unbonds)

        self.assertEqual(len(solution["parts"]), 1)
        self.assertEqual(len(result["parts"]), 4)
        self.assertEqual(result["parts"][0]["position"], [9, 9])
        self.assertEqual([part["type"] for part in result["parts"][1:]], [
            "unbonder", "unbonder", "glyph-purification",
        ])
        self.assertEqual(result["parts"][-1]["position"], [7, -1])
        self.assertEqual(result["parts"][-1]["rotation"], 2)
        metadata = result["source"]["additivePurificationStations"][0]
        self.assertEqual(metadata["producedElement"], "silver")
        self.assertEqual(len(metadata["unbonderPartIds"]), 2)
        self.assertEqual(metadata["targetSolutionBytesUsed"], 0)

    def test_deduplicates_same_unbonder_bond(self) -> None:
        solution = {"source": {}, "parts": []}
        opportunity = {"producedElement": "silver", "origin": [0, 0], "rotation": 0}
        unbonds = [
            {"origin": [1, 0], "rotation": 0, "second": [2, 0]},
            {"origin": [2, 0], "rotation": 3, "second": [1, 0]},
        ]

        result = add_purification_station(solution, opportunity, unbond_candidates=unbonds)

        self.assertEqual(sum(part["type"] == "unbonder" for part in result["parts"]), 1)
        self.assertEqual(sum(part["type"] == "glyph-purification" for part in result["parts"]), 1)


if __name__ == "__main__":
    unittest.main()
