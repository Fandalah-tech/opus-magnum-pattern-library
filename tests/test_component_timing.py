import pytest

from packages.opus_solver.component_timing import (
    apply_component_timing_edit,
    component_program_cutpoints,
    enumerate_component_timing_variants,
    search_component_timing_candidates,
)
import packages.opus_solver.component_timing as component_timing_module


def _solution():
    return {
        "parts": [
            {
                "id": "arm-a",
                "type": "arm1",
                "program": [
                    {"cycle": 0, "instruction": "grab"},
                    {"cycle": 1, "instruction": "rotate_cw"},
                    {"cycle": 4, "instruction": "drop"},
                ],
            },
            {"id": "glyph", "type": "bonder", "program": []},
        ]
    }


def _validation(*, chemistry_cycle=4, error_cycle=5):
    return {
        "complete": False,
        "totalDeficit": 6,
        "completedCycles": error_cycle + 1,
        "terminatedWithError": True,
        "firstError": {"cycle": error_cycle, "message": "collision"},
        "requiredChemistryEventTimeline": [
            {"cycle": chemistry_cycle, "kind": "bond-created"},
        ],
        "distinctRequiredChemistryEventCount": 1,
        "requiredChemistryEventCount": 1,
    }


def test_component_timing_edit_inserts_wait_before_program_suffix():
    edited, metadata = apply_component_timing_edit(
        _solution(),
        part_id="arm-a",
        cut_cycle=1,
        delta=1,
    )

    arm = edited["parts"][0]
    assert [item["cycle"] for item in arm["program"]] == [0, 2, 5]
    assert metadata == {
        "partId": "arm-a",
        "partType": "arm1",
        "cutCycle": 1,
        "delta": 1,
        "shiftedInstructionCount": 2,
    }


def test_component_timing_edit_removes_only_an_existing_wait():
    edited, _ = apply_component_timing_edit(
        _solution(),
        part_id="arm-a",
        cut_cycle=4,
        delta=-2,
    )
    assert [item["cycle"] for item in edited["parts"][0]["program"]] == [0, 1, 2]

    with pytest.raises(ValueError, match="overlap"):
        apply_component_timing_edit(
            _solution(),
            part_id="arm-a",
            cut_cycle=1,
            delta=-1,
        )

    reordered = _solution()
    reordered["parts"][0]["program"] = [
        {"cycle": 0, "instruction": "grab"},
        {"cycle": 3, "instruction": "rotate_cw"},
        {"cycle": 4, "instruction": "drop"},
    ]
    with pytest.raises(ValueError, match="reorder"):
        apply_component_timing_edit(
            reordered,
            part_id="arm-a",
            cut_cycle=4,
            delta=-2,
        )


def test_cutpoints_and_variants_are_target_aware_and_deterministic():
    part = _solution()["parts"][0]
    cutpoints = component_program_cutpoints(part, _validation(), limit=3)
    first = enumerate_component_timing_variants(
        _solution(),
        _validation(),
        radius=2,
        cutpoint_limit=3,
        limit=20,
    )
    second = enumerate_component_timing_variants(
        _solution(),
        _validation(),
        radius=2,
        cutpoint_limit=3,
        limit=20,
    )

    assert 4 in cutpoints
    assert [item["edit"] for item in first] == [item["edit"] for item in second]
    signatures = [
        tuple(item["cycle"] for item in variant["solution"]["parts"][0]["program"])
        for variant in first
    ]
    assert len(signatures) == len(set(signatures))


def test_component_timing_search_balances_progress_and_survival(monkeypatch):
    monkeypatch.setattr(
        component_timing_module,
        "serialize_candidate_roundtrip",
        lambda solution: {"parsed": solution, "diagnostics": {"roundTripClean": True}},
    )

    def fake_validate(_puzzle, solution, max_cycles=None):
        cycles = [item["cycle"] for item in solution["parts"][0]["program"]]
        active = cycles[1] == 2
        return {
            "complete": False,
            "totalDelivered": 0,
            "totalDeficit": 6,
            "terminatedWithError": active,
            "completedCycles": 12 if active else 100,
            "distinctRequiredChemistryEventCount": int(active),
            "requiredChemistryEventCount": int(active),
            "distinctChemistryEventCount": int(active),
            "chemistryEventCount": int(active),
            "manipulationEventCount": 2,
            "firstError": {"cycle": 11} if active else None,
            "requiredChemistryEventTimeline": [],
        }

    monkeypatch.setattr(component_timing_module, "validate_generated_solution", fake_validate)
    result = search_component_timing_candidates(
        {},
        [{"solution": _solution(), "validation": _validation()}],
        source_limit=1,
        radius=1,
        cutpoint_limit=3,
        variants_per_source=10,
        result_limit=2,
    )

    assert result["summary"]["searchedSourceCount"] == 1
    assert result["summary"]["returnedVariantCount"] == 2
    assert result["summary"]["returnedObjectiveCounts"] == {
        "progress": 1,
        "survival": 1,
    }


def test_oracle_reranking_filters_locally_preferred_mechanical_errors(monkeypatch):
    monkeypatch.setattr(
        component_timing_module,
        "serialize_candidate_roundtrip",
        lambda solution: {"parsed": solution, "diagnostics": {"roundTripClean": True}},
    )
    monkeypatch.setattr(
        component_timing_module,
        "validate_generated_solution",
        lambda _puzzle, solution, max_cycles=None: {
            "complete": False,
            "totalDeficit": 6,
            "terminatedWithError": False,
            "completedCycles": 100,
            "distinctRequiredChemistryEventCount": 1,
            "requiredChemistryEventCount": 1,
            "firstError": None,
            "requiredChemistryEventTimeline": [],
        },
    )

    def oracle(solution):
        cycles = [item["cycle"] for item in solution["parts"][0]["program"]]
        if cycles[1] >= 3:
            return {
                "valid": False,
                "rawOutput": "solution did not complete within cycle limit",
                "issues": [],
            }
        return {
            "valid": False,
            "rawOutput": "collision during motion phase on cycle 2 at 0 0",
            "issues": [{"cycle": 2}],
        }

    result = search_component_timing_candidates(
        {},
        [{"solution": _solution(), "validation": _validation()}],
        source_limit=1,
        radius=2,
        cutpoint_limit=3,
        variants_per_source=20,
        result_limit=2,
        oracle_validator=oracle,
        oracle_workers=10,
    )

    assert result["summary"]["selectionPolicy"] == "oracle-progress-survival-portfolio"
    assert result["summary"]["oracleValidatedVariantCount"] > 2
    assert result["summary"]["oracleOutcomeCounts"]["cycle-limit"] >= 2
    assert {item["oracleOutcome"] for item in result["variants"]} == {"cycle-limit"}
