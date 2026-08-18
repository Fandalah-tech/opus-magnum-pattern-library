from __future__ import annotations

import unittest

from packages.opus_solver.initial_overlap_repair import relocate_arm_base_preserving_tip


class InitialOverlapRepairTests(unittest.TestCase):
    def test_relocates_arm_base_while_preserving_tip(self) -> None:
        solution = {
            "source": {},
            "parts": [{
                "id": "cleanup",
                "type": "arm1",
                "position": [8, 1],
                "rotation": 0,
                "length": 1,
                "armNumber": 2,
                "program": [{"cycle": 10, "instruction": "grab"}],
            }],
        }

        updated = relocate_arm_base_preserving_tip(
            solution,
            arm_part_id="cleanup",
            preserved_tip=(9, 1),
            new_rotation=1,
        )

        arm = updated["parts"][0]
        self.assertEqual(arm["position"], [9, 0])
        self.assertEqual(arm["rotation"], 1)
        self.assertEqual(solution["parts"][0]["position"], [8, 1])
        repair = updated["source"]["initialArmBaseRepairs"][0]
        self.assertEqual(repair["preservedTip"], [9, 1])
        self.assertEqual(repair["targetSolutionBytesUsed"], 0)


if __name__ == "__main__":
    unittest.main()
