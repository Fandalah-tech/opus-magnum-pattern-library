from __future__ import annotations

import unittest

from packages.opus_analysis.timeline import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_solver.candidate_solution import rotary_singleton_accumulator_adaptation
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan


def _p016_shape():
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


def _learned_parts():
    return [
        {"id": "part-0", "type": "bonder", "enabled": True, "position": [0, 0], "rotation": 0, "length": 1, "which": 0, "armNumber": 0, "program": []},
        {"id": "part-1", "type": "glyph-calcification", "enabled": True, "position": [-1, 1], "rotation": 4, "length": 1, "which": 0, "armNumber": 0, "program": []},
        {"id": "part-2", "type": "input", "enabled": True, "position": [2, -1], "rotation": 0, "length": 1, "which": 0, "armNumber": 0, "program": []},
        {
            "id": "part-3", "type": "arm1", "enabled": True, "position": [3, -1], "rotation": 3,
            "length": 1, "which": 0, "armNumber": 1,
            "program": [
                {"cycle": 0, "instruction": "grab"},
                {"cycle": 1, "instruction": "rotate_cw"},
                {"cycle": 2, "instruction": "drop"},
                {"cycle": 4, "instruction": "grab"},
                {"cycle": 5, "instruction": "pivot_cw"},
                {"cycle": 6, "instruction": "reset"},
            ],
        },
        {"id": "part-4", "type": "out-std", "enabled": True, "position": [1, 1], "rotation": 5, "length": 1, "which": 0, "armNumber": 0, "program": []},
    ]


def _alignment():
    return [{"partId": "part-2", "sourcePartId": "source-input", "servingArmId": "source-arm", "position": [2, -1], "grabPosition": [2, -1], "reagentIndex": 0}]


def _expected_program():
    return [
        {"cycle": 0, "instruction": "grab"},
        {"cycle": 1, "instruction": "rotate_cw"},
        {"cycle": 2, "instruction": "drop"},
        {"cycle": 3, "instruction": "rotate_ccw"},
        {"cycle": 4, "instruction": "repeat"},
        {"cycle": 8, "instruction": "repeat"},
        {"cycle": 16, "instruction": "repeat"},
        {"cycle": 32, "instruction": "repeat"},
        {"cycle": 64, "instruction": "repeat"},
    ]


def _adapt(puzzle=None):
    puzzle = puzzle or _p016_shape()
    return rotary_singleton_accumulator_adaptation(
        _learned_parts(), puzzle, build_manufacturing_plan(puzzle), _alignment(),
        {"source-arm": "part-3", "source-input": "part-2"},
    )


class RotarySingletonAccumulatorTests(unittest.TestCase):
    def test_p016_geometry_is_recognized_as_rotary_accumulator_arc(self) -> None:
        result = _adapt()
        self.assertIsNotNone(result)
        self.assertEqual([part["type"] for part in result["parts"]], ["bonder", "input", "arm1", "out-std"])
        by_type = {part["type"]: part for part in result["parts"]}
        self.assertEqual(by_type["input"]["position"], [2, -1])
        self.assertEqual(by_type["bonder"]["position"], [2, -1])
        self.assertEqual(by_type["bonder"]["rotation"], 1)
        self.assertEqual(by_type["out-std"]["position"], [3, 0])
        self.assertEqual(by_type["out-std"]["rotation"], 3)
        self.assertEqual(by_type["arm1"]["program"], _expected_program())
        self.assertEqual(result["metadata"]["arcCells"], [[2, -1], [2, 0], [3, 0], [4, -1]])
        self.assertEqual(result["metadata"]["expandedTapePeriod"], 128)
        self.assertEqual(result["metadata"]["targetSolutionBytesUsed"], 0)

    def test_rotary_accumulator_delivers_the_four_atom_chain_in_engine(self) -> None:
        puzzle = _p016_shape()
        adapted = _adapt(puzzle)
        self.assertIsNotNone(adapted)
        solution = {"parts": adapted["parts"], "metrics": {}}
        timeline = build_program_timeline(solution, max_cycles=16)
        trace = Simulator.from_models(puzzle, solution).run_timeline(timeline)
        delivered = [event for frame in trace["frames"] for event in frame.get("events", []) if event.get("kind") == "product-delivered"]
        errors = [event for frame in trace["frames"] for event in frame.get("events", []) if event.get("kind") == "simulation-error"]
        self.assertFalse(errors)
        self.assertTrue(delivered)

    def test_compact_repeat_tape_expands_beyond_first_product_window(self) -> None:
        adapted = _adapt()
        self.assertIsNotNone(adapted)
        timeline = build_program_timeline({"parts": adapted["parts"], "metrics": {}})
        self.assertEqual(timeline["summary"]["globalPeriod"], 128)
        self.assertGreaterEqual(timeline["summary"]["horizon"], 128)
        arm = timeline["arms"][0]
        self.assertEqual(arm["instructionCount"], 9)
        self.assertGreaterEqual(arm["expandedInstructionCount"], 64)

    def test_non_arc_product_does_not_trigger_rotary_adaptation(self) -> None:
        puzzle = _p016_shape()
        puzzle["products"][0] = {
            "atoms": [
                {"id": "a0", "element": "earth", "position": [0, 0]},
                {"id": "a1", "element": "earth", "position": [1, 0]},
                {"id": "a2", "element": "earth", "position": [2, 0]},
                {"id": "a3", "element": "earth", "position": [3, 0]},
            ],
            "bonds": [
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [1, 0], "to": [2, 0]},
                {"type": "normal", "from": [2, 0], "to": [3, 0]},
            ],
        }
        self.assertIsNone(_adapt(puzzle))


if __name__ == "__main__":
    unittest.main()
