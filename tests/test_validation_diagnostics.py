from packages.opus_solver.solver import validate_generated_solution


def test_overlapping_inputs_are_reported_as_blocked_at_start():
    puzzle = {
        "name": "Blocked inputs",
        "reagents": [
            {"atoms": [{"id": "a0", "element": "air", "position": [0, 0]}], "bonds": []},
            {"atoms": [{"id": "a0", "element": "fire", "position": [0, 0]}], "bonds": []},
        ],
        "products": [],
    }
    solution = {
        "parts": [
            {"id": "input-a", "type": "input", "position": [0, 0], "rotation": 0, "which": 0, "program": []},
            {"id": "input-b", "type": "input", "position": [0, 0], "rotation": 0, "which": 1, "program": []},
        ]
    }
    result = validate_generated_solution(puzzle, solution)
    assert result["inputSourceCount"] == 2
    assert result["initialSpawnedInputCount"] == 1
    assert len(result["blockedInputsAtStart"]) == 1
    assert result["failureMode"] == "blocked-input-at-start"
