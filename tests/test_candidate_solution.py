from packages.opus_solver.candidate_solution import (
    assign_branch_atom_flows,
    build_candidate_solution,
    serialize_candidate_roundtrip,
)
from packages.opus_solver.manufacturing import AtomFlow, ManufacturingPlan


def _plan():
    return ManufacturingPlan(
        strategy="bonded-pair-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(
            AtomFlow("p0", (0, 0), "salt", 1, "r1", "fire", "calcification"),
            AtomFlow("p1", (1, 0), "air", 0, "r0", "air", None),
        ),
        operations=(),
        required_glyphs=("bonder", "glyph-calcification"),
    )


def _candidate():
    return {
        "branches": [
            [{"relation": "calcify"}],
            [],
        ],
        "convergence": {
            "inputs": [
                {"relations": ["bond-created"]},
                {"relations": ["bond-created"]},
            ]
        },
    }


def _layout():
    return {
        "summary": {"layoutComplete": True, "scheduleComplete": True},
        "parts": [
            {
                "id": "input-a",
                "type": "input",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "which": 99,
                "program": [],
                "sourceFragmentInstances": ["branch-0:upstream-0"],
            },
            {
                "id": "input-b",
                "type": "input",
                "position": [2, 0],
                "rotation": 0,
                "length": 1,
                "which": 98,
                "program": [],
                "sourceFragmentInstances": ["branch-1:input"],
            },
            {
                "id": "arm",
                "type": "arm1",
                "position": [1, 0],
                "rotation": 3,
                "length": 1,
                "which": 0,
                "program": [{"cycle": 0, "instruction": "grab"}],
                "sourceFragmentInstances": ["branch-0:input"],
            },
            {
                "id": "out",
                "type": "out-std",
                "position": [3, 0],
                "rotation": 0,
                "length": 1,
                "which": 77,
                "program": [],
                "sourceFragmentInstances": ["tail-0"],
            },
        ],
    }


def test_branch_assignment_uses_chemistry_not_historical_which():
    assignment = assign_branch_atom_flows(_candidate(), _plan())
    assert assignment[0].reagent_index == 1
    assert assignment[1].reagent_index == 0


def test_candidate_rewrites_input_output_indices_and_arm_numbers():
    puzzle = {"name": "Target", "source": {"name": "P007.puzzle"}}
    solution = build_candidate_solution(puzzle, _plan(), _candidate(), _layout())
    inputs = [part for part in solution["parts"] if part["type"] == "input"]
    output = next(part for part in solution["parts"] if part["type"] == "out-std")
    arm = next(part for part in solution["parts"] if part["type"] == "arm1")
    assert [part["which"] for part in inputs] == [1, 0]
    assert output["which"] == 0
    assert arm["armNumber"] == 1
    assert solution["puzzleFile"] == "P007"
    assert solution["metrics"] == {}


def test_metric_free_candidate_serializes_and_parses_cleanly():
    puzzle = {"name": "Target", "source": {"name": "P007.puzzle"}}
    solution = build_candidate_solution(puzzle, _plan(), _candidate(), _layout())
    roundtrip = serialize_candidate_roundtrip(solution)
    assert roundtrip["diagnostics"]["roundTripClean"] is True
    assert roundtrip["diagnostics"]["parserTrailingBytes"] == 0
    assert roundtrip["parsed"]["puzzleFile"] == "P007"
    assert len(roundtrip["parsed"]["parts"]) == 4
