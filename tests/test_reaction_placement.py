from __future__ import annotations

import unittest

from packages.opus_solver.reaction_placement import (
    apply_purification_placement,
    apply_purification_unbond_repair,
    purification_opportunities,
)


def frame(cycle: int, atoms: list[dict], bonds: list[dict] | None = None) -> dict:
    normalized = [
        {**atom, "heldBy": list(atom.get("heldBy") or [])}
        for atom in atoms
    ]
    return {"cycle": cycle, "world": {"atoms": normalized, "bonds": bonds or []}}


class ReactionPlacementTests(unittest.TestCase):
    def test_finds_and_aggregates_faithful_purification_opportunity(self) -> None:
        atoms = [
            {"id": "a", "element": "lead", "position": [0, 0]},
            {"id": "b", "element": "lead", "position": [1, 0]},
        ]
        replay = {"frames": [frame(4, atoms), frame(5, atoms)]}

        opportunities = purification_opportunities(replay)

        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item["element"], "lead")
        self.assertEqual(item["producedElement"], "tin")
        self.assertEqual(item["origin"], [0, 0])
        self.assertEqual(item["second"], [1, 0])
        self.assertEqual(item["output"], [0, 1])
        self.assertEqual(item["rotation"], 0)
        self.assertEqual(item["observationCount"], 2)
        self.assertEqual(item["readyObservationCount"], 2)
        self.assertEqual(item["minimumBlockerCount"], 0)
        self.assertEqual(item["firstCycle"], 4)
        self.assertEqual(item["lastCycle"], 5)
        self.assertIn("faithful-purification", item["geometryEvidence"])

    def test_strict_mode_rejects_occupied_output_held_bonded_and_gold_inputs(self) -> None:
        replay = {"frames": [
            frame(0, [
                {"id": "a", "element": "lead", "position": [0, 0]},
                {"id": "b", "element": "lead", "position": [1, 0]},
                {"id": "output-blocker", "element": "salt", "position": [0, 1]},
            ]),
            frame(1, [
                {"id": "h0", "element": "tin", "position": [0, 0], "heldBy": ["arm"]},
                {"id": "h1", "element": "tin", "position": [1, 0]},
            ]),
            frame(2, [
                {"id": "c0", "element": "iron", "position": [0, 0]},
                {"id": "c1", "element": "iron", "position": [1, 0]},
            ], bonds=[{"fromAtomId": "c0", "toAtomId": "c1", "type": "normal"}]),
            frame(3, [
                {"id": "g0", "element": "gold", "position": [0, 0]},
                {"id": "g1", "element": "gold", "position": [1, 0]},
            ]),
        ]}

        self.assertEqual(purification_opportunities(replay), [])

    def test_near_ready_mode_keeps_bond_blocker_and_derives_unbonder_pose(self) -> None:
        replay = {"frames": [
            frame(7, [
                {"id": "a", "element": "iron", "position": [0, 0]},
                {"id": "b", "element": "iron", "position": [1, 0]},
                {"id": "x", "element": "salt", "position": [2, 0]},
            ], bonds=[{"fromAtomId": "b", "toAtomId": "x", "type": "normal"}]),
        ]}

        opportunities = purification_opportunities(replay, include_blocked=True)

        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item["producedElement"], "copper")
        self.assertEqual(item["readyObservationCount"], 0)
        self.assertEqual(item["minimumBlockerCount"], 1)
        self.assertTrue(item["blockersAtBestObservation"]["secondBonded"])
        self.assertEqual(item["blockersAtBestObservation"]["cycle"], 7)
        self.assertEqual(len(item["unbondCandidates"]), 1)
        unbond = item["unbondCandidates"][0]
        self.assertEqual(unbond["blockedAtomId"], "b")
        self.assertEqual(unbond["neighborAtomId"], "x")
        self.assertEqual(unbond["origin"], [1, 0])
        self.assertEqual(unbond["rotation"], 0)

    def test_moves_only_selected_purification_glyph_and_restores_solver_provenance(self) -> None:
        solution = {
            "source": {},
            "parts": [
                {"id": "p0", "type": "glyph-purification", "position": [9, 9], "rotation": 3},
                {"id": "p1", "type": "glyph-purification", "position": [8, 8], "rotation": 2},
                {"id": "arm", "type": "arm1", "position": [0, 0], "rotation": 0},
            ],
        }
        opportunity = {
            "element": "tin",
            "producedElement": "iron",
            "origin": [1, -2],
            "rotation": 5,
            "second": [2, -3],
            "output": [2, -2],
            "observationCount": 3,
        }

        moved = apply_purification_placement(solution, purifier_index=1, opportunity=opportunity)

        self.assertEqual(moved["parts"][0]["position"], [9, 9])
        self.assertEqual(moved["parts"][1]["position"], [1, -2])
        self.assertEqual(moved["parts"][1]["rotation"], 5)
        self.assertEqual(moved["source"]["generator"], "opus_solver/trace-guided-purification-v1")
        metadata = moved["source"]["reactionPlacementRepair"]
        self.assertEqual(metadata["purifierIndex"], 1)
        self.assertEqual(metadata["targetSolutionBytesUsed"], 0)
        self.assertEqual(solution["parts"][1]["position"], [8, 8])

    def test_coupled_repair_moves_selected_unbonder_and_purifier(self) -> None:
        solution = {
            "source": {},
            "parts": [
                {"id": "u0", "type": "unbonder", "position": [7, 7], "rotation": 3},
                {"id": "u1", "type": "unbonder", "position": [8, 8], "rotation": 2},
                {"id": "p0", "type": "glyph-purification", "position": [9, 9], "rotation": 3},
            ],
        }
        opportunity = {"origin": [0, 0], "rotation": 0, "second": [1, 0], "output": [0, 1]}
        unbond = {"origin": [1, 0], "rotation": 0, "second": [2, 0]}

        moved = apply_purification_unbond_repair(
            solution,
            purifier_index=0,
            unbonder_index=1,
            opportunity=opportunity,
            unbond_candidate=unbond,
        )

        self.assertEqual(moved["parts"][0]["position"], [7, 7])
        self.assertEqual(moved["parts"][1]["position"], [1, 0])
        self.assertEqual(moved["parts"][1]["rotation"], 0)
        self.assertEqual(moved["parts"][2]["position"], [0, 0])
        self.assertEqual(moved["source"]["generator"], "opus_solver/trace-guided-unbond-purification-v1")
        metadata = moved["source"]["reactionPlacementRepair"]
        self.assertEqual(metadata["kind"], "trace-guided-unbond-purification-v1")
        self.assertEqual(metadata["unbonderIndex"], 1)
        self.assertEqual(metadata["targetSolutionBytesUsed"], 0)


if __name__ == "__main__":
    unittest.main()
