from packages.opus_analysis.engine_audit import (
    bounded_audit_workers,
    classify_simulation_error,
    summarize_engine_audit,
)


def test_audit_workers_have_a_hard_upper_bound():
    assert bounded_audit_workers(100) == 10
    assert bounded_audit_workers(0) == 10
    assert bounded_audit_workers(3) == 3


def test_collision_classifier_separates_input_generations():
    assert classify_simulation_error(
        "Atom input-spawn-2-atom-0 collides with stationary atom input-spawn-1-atom-1 at (0, 0)"
    ) == "atom-collision/same-input-different-spawn"
    assert classify_simulation_error(
        "Atom input-spawn-2-atom-0 collides with stationary atom input-spawn-2-atom-1 at (0, 0)"
    ) == "atom-collision/same-molecule"


def test_audit_summary_counts_actionable_failure_categories():
    summary = summarize_engine_audit([
        {"puzzleId": "P1", "status": "engine-complete", "terminatedAfterCompletion": False},
        {"puzzleId": "P1", "status": "engine-error", "errorCategory": "motion/conflicting"},
        {"puzzleId": "P2", "status": "engine-incomplete"},
    ], workers=4)

    assert summary["engineComplete"] == 1
    assert summary["engineError"] == 1
    assert summary["engineIncomplete"] == 1
    assert summary["failureCategories"] == {"motion/conflicting": 1}
