from __future__ import annotations

import unittest

from packages.opus_analysis.timeline import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_solver.candidate_solution import rotary_singleton_accumulator_adaptation
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan


def _puzzle():
    return {
        "schemaVersion": "0.1.0",
        "source": {"name": "P016.puzzle"},
        "name": "HAIR PRODUCT",
        "availableParts": {
            "arms": ["arm1", "arm2", "arm3", "arm6", "piston"],
            "glyphs": ["equilibrium", "bonder", "unbonder", "multibonder", "calcification"],
        },
        "reagents": [{"atoms": [{"id": "a0", "element": "earth", "position": [0, 0]}], "bonds": []}],
        "products": [{
            "atoms": [
                {"id": "a0", "element": "earth", "position": [-1, 1]},
                {"id": "a1", "element": "earth", "position": [0, 0]},
                {"id": "a2", "element": "earth", "position": [1, 0]},
                {"id": "a3", "element": "earth", "position": [1, 1]},
            ],
            "bonds": [
                {"type": "normal", "from": [1, 0], "to": [1, 1]},
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [-1, 1], "to": [0, 0]},
            ],
        }],
        "outputScale": 1,
        "production": False,
    }


def _parts():
    return [
        {"id":"part-0","type":"bonder","enabled":True,"position":[0,0],"rotation":0,"length":1,"which":0,"armNumber":0,"program":[]},
        {"id":"part-1","type":"glyph-calcification","enabled":True,"position":[-1,1],"rotation":4,"length":1,"which":0,"armNumber":0,"program":[]},
        {"id":"part-2","type":"input","enabled":True,"position":[2,-1],"rotation":0,"length":1,"which":0,"armNumber":0,"program":[]},
        {"id":"part-3","type":"arm1","enabled":True,"position":[3,-1],"rotation":3,"length":1,"which":0,"armNumber":1,"program":[
            {"cycle":0,"instruction":"grab"},{"cycle":1,"instruction":"rotate_cw"},{"cycle":2,"instruction":"drop"},
            {"cycle":4,"instruction":"grab"},{"cycle":5,"instruction":"pivot_cw"},{"cycle":6,"instruction":"reset"}]},
        {"id":"part-4","type":"out-std","enabled":True,"position":[1,1],"rotation":5,"length":1,"which":0,"armNumber":0,"program":[]},
    ]


def _adapt(puzzle=None):
    puzzle = puzzle or _puzzle()
    return rotary_singleton_accumulator_adaptation(
        _parts(), puzzle, build_manufacturing_plan(puzzle),
        [{"partId":"part-2","sourcePartId":"source-input","servingArmId":"source-arm","position":[2,-1],"grabPosition":[2,-1],"reagentIndex":0}],
        {"source-arm":"part-3","source-input":"part-2"},
    )


class RotarySingletonAccumulatorTests(unittest.TestCase):
    def test_geometry_and_compact_program(self):
        result = _adapt()
        self.assertIsNotNone(result)
        by_type = {part["type"]: part for part in result["parts"]}
        self.assertEqual(set(by_type), {"bonder","input","arm1","out-std"})
        self.assertEqual(by_type["bonder"]["position"], [2,-1])
        self.assertEqual(by_type["bonder"]["rotation"], 1)
        self.assertEqual(by_type["out-std"]["position"], [3,0])
        self.assertEqual(by_type["out-std"]["rotation"], 3)
        self.assertEqual(len(by_type["arm1"]["program"]), 9)
        self.assertEqual([x["cycle"] for x in by_type["arm1"]["program"][-5:]], [4,8,16,32,64])
        self.assertTrue(all(x["instruction"] == "repeat" for x in by_type["arm1"]["program"][-5:]))
        self.assertEqual(result["metadata"]["targetSolutionBytesUsed"], 0)

    def test_engine_delivers_without_collision(self):
        puzzle = _puzzle()
        adapted = _adapt(puzzle)
        solution = {"parts": adapted["parts"], "metrics": {}}
        trace = Simulator.from_models(puzzle, solution).run_timeline(build_program_timeline(solution, max_cycles=32))
        events = [event for frame in trace["frames"] for event in frame.get("events", [])]
        self.assertFalse([event for event in events if event.get("kind") == "simulation-error"])
        self.assertTrue([event for event in events if event.get("kind") == "product-delivered"])

    def test_repeat_expansion_matches_omsim_shape(self):
        adapted = _adapt()
        timeline = build_program_timeline({"parts": adapted["parts"], "metrics": {}})
        self.assertEqual(timeline["summary"]["globalPeriod"], 68)
        arm = timeline["arms"][0]
        self.assertEqual(arm["instructionCount"], 9)
        self.assertEqual(arm["expandedInstructionCount"], 24)
        self.assertGreaterEqual(timeline["summary"]["horizon"], 68 * 6)

    def test_non_arc_product_is_rejected(self):
        puzzle = _puzzle()
        puzzle["products"][0] = {
            "atoms":[
                {"id":"a0","element":"earth","position":[0,0]}, {"id":"a1","element":"earth","position":[1,0]},
                {"id":"a2","element":"earth","position":[2,0]}, {"id":"a3","element":"earth","position":[3,0]}],
            "bonds":[
                {"type":"normal","from":[0,0],"to":[1,0]}, {"type":"normal","from":[1,0],"to":[2,0]},
                {"type":"normal","from":[2,0],"to":[3,0]}],
        }
        self.assertIsNone(_adapt(puzzle))


if __name__ == "__main__":
    unittest.main()
