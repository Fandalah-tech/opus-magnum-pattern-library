from packages.opus_solver.scheduling import (
    materialize_assembly_schedule,
    materialize_fragment_chain_schedule,
    synchronize_layout_programs,
)


def _edge(delta):
    return {
        "relativeTimings": {
            "preferred": {
                "frame": "source-fragment-program-start",
                "programStartDelta": delta,
                "eventFirstFromSourceStart": 2,
                "eventFirstFromTargetStart": 1,
            }
        }
    }


def test_schedule_propagates_branches_and_tail_then_shifts_nonnegative():
    candidate = {
        "convergence": {
            "inputs": [
                {"sourceRole": "conversion", "sourceMechanismHash": "calc"},
                {"sourceRole": "feed", "sourceMechanismHash": "direct"},
            ],
            "samples": [
                {
                    "inputs": [
                        {"sourceRole": "conversion", "sourceMechanismHash": "calc", "relativeTimings": [{"programStartDelta": 2}]},
                        {"sourceRole": "feed", "sourceMechanismHash": "direct", "relativeTimings": [{"programStartDelta": 1}]},
                    ]
                }
            ],
        },
        "branches": [[_edge(3)], []],
        "tail": [_edge(4)],
    }
    schedule = materialize_assembly_schedule(candidate)
    starts = schedule["instanceStartCycles"]
    assert schedule["summary"]["scheduleComplete"] is True
    assert min(starts.values()) == 0
    assert starts["branch-0:input"] - starts["branch-0:upstream-0"] == 3
    assert starts["convergence"] - starts["branch-0:input"] == 2
    assert starts["convergence"] - starts["branch-1:input"] == 1
    assert starts["tail-0"] - starts["convergence"] == 4


def test_shared_part_program_contributions_are_shifted_and_merged():
    layout = {
        "summary": {},
        "parts": [
            {
                "id": "shared-arm",
                "programContributions": {
                    "a": [{"cycle": 0, "instruction": "grab"}],
                    "b": [{"cycle": 0, "instruction": "drop"}],
                },
                "program": [],
            }
        ],
    }
    schedule = {"summary": {"scheduleComplete": True}, "instanceStartCycles": {"a": 0, "b": 2}}
    synchronized = synchronize_layout_programs(layout, schedule)
    assert synchronized["parts"][0]["program"] == [
        {"cycle": 0, "instruction": "grab"},
        {"cycle": 2, "instruction": "drop"},
    ]
    assert synchronized["summary"]["programConflictCount"] == 0
    assert synchronized["summary"]["scheduleComplete"] is True


def test_shared_part_conflicting_same_cycle_actions_are_reported():
    layout = {
        "summary": {},
        "parts": [
            {
                "id": "shared-arm",
                "programContributions": {
                    "a": [{"cycle": 0, "instruction": "grab"}],
                    "b": [{"cycle": 0, "instruction": "drop"}],
                },
                "program": [],
            }
        ],
    }
    schedule = {"summary": {"scheduleComplete": True}, "instanceStartCycles": {"a": 0, "b": 0}}
    synchronized = synchronize_layout_programs(layout, schedule)
    assert synchronized["summary"]["programConflictCount"] == 1
    assert synchronized["summary"]["scheduleComplete"] is False


def test_missing_timing_prevents_complete_schedule():
    candidate = {
        "convergence": {
            "inputs": [{"sourceRole": "feed", "sourceMechanismHash": "f"}],
            "samples": [{"inputs": [{"sourceRole": "feed", "sourceMechanismHash": "f", "relativeTimings": []}]}],
        },
        "branches": [[]],
        "tail": [],
    }
    schedule = materialize_assembly_schedule(candidate)
    assert schedule["summary"]["scheduleComplete"] is False
    assert schedule["summary"]["missingTimingCount"] == 1


def test_passive_chain_fragments_use_zero_delta_baseline_for_repair():
    candidate = {
        "nodes": [
            {"role": "feed", "canonicalMechanismHash": "f"},
            {"role": "bonding", "canonicalMechanismHash": "b"},
        ],
        "steps": [{
            "relativeTimings": {
                "preferred": {"frame": "source-fragment-program-start", "programStartDelta": None}
            }
        }],
    }
    schedule = materialize_fragment_chain_schedule(candidate)
    assert schedule["summary"]["scheduleComplete"] is True
    assert schedule["summary"]["defaultedTimingCount"] == 1
    assert schedule["instanceStartCycles"] == {"chain-0": 0, "chain-1": 0}
