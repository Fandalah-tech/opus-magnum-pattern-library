from __future__ import annotations

import unittest

from packages.opus_solver.feed_lane_repair import _candidate_input_placements


class FeedLaneRepairTests(unittest.TestCase):
    def test_places_target_atom_on_observed_grab_tip(self) -> None:
        puzzle = {
            "reagents": [{
                "atoms": [
                    {"id": "left", "element": "lead", "position": [0, 0]},
                    {"id": "right", "element": "tin", "position": [1, 0]},
                ],
                "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
            }],
        }
        input_part = {
            "id": "input-0",
            "type": "input",
            "position": [7, 7],
            "rotation": 0,
            "which": 0,
            "program": [],
        }
        solution = {
            "parts": [
                input_part,
                {
                    "id": "arm-0",
                    "type": "arm1",
                    "position": [0, 0],
                    "rotation": 0,
                    "length": 1,
                    "armNumber": 1,
                    "program": [{"cycle": 0, "instruction": "grab"}],
                },
            ]
        }

        placements = _candidate_input_placements(
            puzzle,
            solution,
            input_part,
            max_grab_cycles=4,
            placement_limit=24,
        )

        self.assertTrue(placements)
        # Anchoring the reagent's atom at local [1,0] with rotation 0 onto the
        # arm tip [1,0] places the input glyph origin at [0,0].
        self.assertTrue(any(
            item["position"] == [0, 0]
            and item["rotation"] == 0
            and any(evidence["anchoredAtomIndex"] == 1 for evidence in item["evidence"])
            for item in placements
        ))

    def test_placement_limit_is_respected(self) -> None:
        puzzle = {
            "reagents": [{
                "atoms": [{"id": "a", "element": "lead", "position": [0, 0]}],
                "bonds": [],
            }],
        }
        input_part = {
            "id": "input-0",
            "type": "input",
            "position": [9, 9],
            "rotation": 0,
            "which": 0,
            "program": [],
        }
        solution = {
            "parts": [
                input_part,
                {
                    "id": "arm-0",
                    "type": "arm1",
                    "position": [0, 0],
                    "rotation": 0,
                    "length": 1,
                    "armNumber": 1,
                    "program": [{"cycle": 0, "instruction": "grab"}],
                },
            ]
        }

        placements = _candidate_input_placements(
            puzzle,
            solution,
            input_part,
            max_grab_cycles=4,
            placement_limit=3,
        )

        self.assertLessEqual(len(placements), 3)


if __name__ == "__main__":
    unittest.main()
