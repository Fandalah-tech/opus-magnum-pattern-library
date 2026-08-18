from __future__ import annotations

import unittest

from packages.opus_solver.input_footprint_repair import (
    first_grabbed_input_anchors,
    rotate_input_around_anchor,
)


class InputFootprintRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.puzzle = {
            "reagents": [{
                "atoms": [
                    {"id": "a0", "element": "iron", "position": [0, 0]},
                    {"id": "a1", "element": "iron", "position": [1, 0]},
                ],
                "bonds": [{"from": [0, 0], "to": [1, 0], "type": "normal"}],
            }],
        }
        self.solution = {
            "source": {},
            "parts": [{
                "id": "input-a",
                "type": "input",
                "position": [5, -2],
                "rotation": 0,
                "which": 0,
                "program": [],
            }],
        }

    def test_infers_first_grab_atom_and_world_anchor_from_id(self) -> None:
        replay = {
            "frames": [{
                "cycle": 7,
                "events": [{
                    "kind": "atom-grabbed",
                    "cycle": 7,
                    "atomId": "input-a-spawn-0-atom-1",
                    "armId": "arm",
                    "branchIndex": 0,
                }],
            }],
        }

        anchors = first_grabbed_input_anchors(self.puzzle, self.solution, replay)

        self.assertEqual(len(anchors), 1)
        item = anchors[0]
        self.assertEqual(item["inputId"], "input-a")
        self.assertEqual(item["atomIndex"], 1)
        self.assertEqual(item["anchorWorldPosition"], [6, -2])
        self.assertEqual(item["firstGrabCycle"], 7)

    def test_rotation_preserves_grabbed_atom_world_position(self) -> None:
        anchor = {
            "inputId": "input-a",
            "reagentIndex": 0,
            "atomIndex": 1,
            "atomLocalPosition": [1, 0],
            "anchorWorldPosition": [6, -2],
            "currentOrigin": [5, -2],
            "currentRotation": 0,
        }

        rotated = rotate_input_around_anchor(self.solution, anchor, rotation=1)

        part = rotated["parts"][0]
        self.assertEqual(part["rotation"], 1)
        # Local (1,0) rotated by +1 is (0,1), so origin must move to (6,-3).
        self.assertEqual(part["position"], [6, -3])
        repair = rotated["source"]["inputFootprintRepairs"][0]
        self.assertEqual(repair["anchorWorldPosition"], [6, -2])
        self.assertEqual(repair["targetSolutionBytesUsed"], 0)
        self.assertEqual(self.solution["parts"][0]["position"], [5, -2])


if __name__ == "__main__":
    unittest.main()
