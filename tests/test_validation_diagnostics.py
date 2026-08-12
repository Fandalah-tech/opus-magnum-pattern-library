from packages.opus_solver.solver import validate_generated_solution
import packages.opus_solver.solver as solver_module


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


def test_target_reached_before_later_diagnostic_error_remains_complete(monkeypatch):
    class Source:
        id = "input"
        spawn_count = 1
        footprint = ((0, 0),)

    class FakeSimulator:
        inputs = [Source()]
        delivered_products = {"output": 6}

        def run_timeline(self, _timeline):
            return {
                "summary": {"terminatedWithError": True, "completedCycles": 8},
                "frames": [{
                    "cycle": 7,
                    "events": [{"kind": "simulation-error", "cycle": 7, "message": "late collision"}],
                }],
            }

    monkeypatch.setattr(
        solver_module,
        "build_program_timeline",
        lambda _solution, max_cycles=None: {
            "summary": {"globalPeriod": 1, "declaredCycles": 8},
            "cycles": [{} for _ in range(max_cycles or 8)],
        },
    )
    monkeypatch.setattr(
        solver_module.Simulator,
        "from_models",
        classmethod(lambda _cls, _puzzle, _solution: FakeSimulator()),
    )
    result = validate_generated_solution(
        {"reagents": [], "products": []},
        {"parts": [{"id": "output", "type": "out-std", "which": 0, "program": []}]},
    )
    assert result["complete"] is True
    assert result["failureMode"] is None
    assert result["terminatedWithError"] is True
    assert result["terminatedAfterCompletion"] is True


def test_event_progress_exposes_required_chemistry_cycles():
    progress = solver_module._event_progress(
        {
            "frames": [
                {"cycle": 3, "events": [{"kind": "bond-created"}]},
                {"cycle": 8, "events": [{"kind": "bond-removed", "cycle": 8}]},
            ],
        },
        required_event_kinds={"bond-created"},
    )

    assert progress["requiredChemistryEventTimeline"] == [
        {"cycle": 3, "kind": "bond-created"},
    ]
    assert progress["chemistryEventTimeline"] == [
        {"cycle": 3, "kind": "bond-created"},
        {"cycle": 8, "kind": "bond-removed"},
    ]
