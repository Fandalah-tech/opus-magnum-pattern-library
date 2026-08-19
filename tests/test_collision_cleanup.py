from __future__ import annotations

import unittest

from packages.opus_solver.collision_cleanup import (
    add_cleanup_arm,
    first_stationary_collision,
)


class CollisionCleanupTests(unittest.TestCase):
    def test_parses_stationary_collision_target(self) -> None:
        summary = {
            "firstError": {
                "cycle": 205,
                "message": "Atom moving-0 collides with stationary atom input-spawn-1-atom-2 at (9, 1); other diagnostics",
            },
        }

        collision = first_stationary_collision(summary)

        self.assertIsNotNone(collision)
        self.assertEqual(collision["cycle"], 205)
        self.assertEqual(collision["movingAtomId"], "moving-0")
        self.assertEqual(collision["stationaryAtomId"], "input-spawn-1-atom-2")
        self.assertEqual(collision["position"], [9, 1])

    def test_adds_cleanup_arm_with_tip_on_blocker(self) -> None:
        solution = {
            "source": {},
            "parts": [
                {"id": "arm-old", "type": "arm1", "armNumber": 3, "position": [0, 0], "rotation": 0, "program": []},
            ],
        }

        repaired = add_cleanup_arm(
            solution,
            grab_position=(9, 1),
            base_direction_index=0,
            rotation_instruction="rotate_ccw",
            grab_cycle=204,
            motion_cycle=205,
        )

        arm = repaired["parts"][-1]
        self.assertEqual(arm["type"], "arm1")
        self.assertEqual(arm["position"], [8, 1])
        self.assertEqual(arm["rotation"], 0)
        self.assertEqual(arm["armNumber"], 4)
        self.assertEqual(
            [(item["cycle"], item["instruction"]) for item in arm["program"]],
            [(204, "grab"), (205, "rotate_ccw"), (206, "drop")],
        )
        self.assertEqual(repaired["source"]["collisionCleanupRepairs"][0]["targetSolutionBytesUsed"], 0)
        self.assertEqual(len(solution["parts"]), 1)


if __name__ == "__main__":
    unittest.main()
