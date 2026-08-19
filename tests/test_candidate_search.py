from packages.opus_solver.candidate_search import (
    apply_schedule_group_offsets,
    enumerate_schedule_variants,
    validation_rank,
)


def _schedule():
    return {
        "summary": {"scheduleComplete": True},
        "instanceStartCycles": {
            "convergence": 5,
            "branch-0:input": 1,
            "branch-0:upstream-0": 0,
            "branch-1:input": 2,
            "tail-0": 7,
        },
    }


def test_group_offsets_preserve_internal_branch_timing():
    shifted = apply_schedule_group_offsets(_schedule(), {"branch-0": 2, "tail-0": -1})
    starts = shifted["instanceStartCycles"]
    assert starts["branch-0:input"] - starts["branch-0:upstream-0"] == 1
    assert starts["branch-0:input"] == 3
    assert starts["tail-0"] == 6
    assert starts["convergence"] == 5


def test_schedule_variants_try_historical_timing_first():
    variants = enumerate_schedule_variants(_schedule(), radius=1, limit=10)
    assert variants
    assert variants[0]["summary"]["variantOffsets"] == {
        "branch-0": 0,
        "branch-1": 0,
        "tail-0": 0,
    }


def test_schedule_variants_are_deduplicated_after_normalization():
    variants = enumerate_schedule_variants(_schedule(), radius=1, limit=100)
    signatures = [tuple(sorted(item["instanceStartCycles"].items())) for item in variants]
    assert len(signatures) == len(set(signatures))


def test_validation_rank_prefers_progress_then_lower_displacement():
    stalled = {
        "complete": False,
        "terminatedWithError": True,
        "totalDelivered": 0,
        "totalDeficit": 6,
        "completedCycles": 3,
    }
    progressing = {
        "complete": False,
        "terminatedWithError": False,
        "totalDelivered": 1,
        "totalDeficit": 5,
        "completedCycles": 20,
    }
    assert validation_rank(progressing, displacement=2) > validation_rank(stalled, displacement=0)
    assert validation_rank(progressing, displacement=1) > validation_rank(progressing, displacement=2)


def test_validation_rank_always_prefers_complete_solution():
    complete = {
        "complete": True,
        "terminatedWithError": False,
        "totalDelivered": 6,
        "totalDeficit": 0,
        "completedCycles": 20,
    }
    incomplete = {
        "complete": False,
        "terminatedWithError": False,
        "totalDelivered": 100,
        "totalDeficit": 0,
        "completedCycles": 1000,
    }
    assert validation_rank(complete, displacement=10) > validation_rank(incomplete, displacement=0)


def test_validation_rank_prefers_chemical_progress_over_idle_survival():
    chemically_active = {
        "complete": False,
        "terminatedWithError": True,
        "totalDelivered": 0,
        "totalDeficit": 6,
        "distinctChemistryEventCount": 1,
        "chemistryEventCount": 1,
        "manipulationEventCount": 2,
        "completedCycles": 12,
    }
    idle_survivor = {
        "complete": False,
        "terminatedWithError": False,
        "totalDelivered": 0,
        "totalDeficit": 6,
        "distinctChemistryEventCount": 0,
        "chemistryEventCount": 0,
        "manipulationEventCount": 0,
        "completedCycles": 1000,
    }

    assert validation_rank(chemically_active) > validation_rank(idle_survivor)


def test_validation_rank_prefers_required_chemistry_over_off_plan_activity():
    required_progress = {
        "complete": False,
        "totalDelivered": 0,
        "totalDeficit": 6,
        "distinctRequiredChemistryEventCount": 1,
        "requiredChemistryEventCount": 1,
        "distinctChemistryEventCount": 1,
        "chemistryEventCount": 1,
    }
    off_plan_activity = {
        "complete": False,
        "totalDelivered": 0,
        "totalDeficit": 6,
        "distinctRequiredChemistryEventCount": 0,
        "requiredChemistryEventCount": 0,
        "distinctChemistryEventCount": 3,
        "chemistryEventCount": 20,
    }

    assert validation_rank(required_progress) > validation_rank(off_plan_activity)
