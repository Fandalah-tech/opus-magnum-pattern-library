from packages.opus_analysis import solution_architecture_signature, specialization_axes


def _part(kind, program=None):
    return {"type": kind, "program": program or []}


def test_architecture_signature_separates_single_arm_and_parallel_factory():
    sequential = {"parts": [_part("piston", [{"cycle": 2, "instruction": "grab"}]), _part("track")]}
    parallel = {"parts": [_part("arm1") for _ in range(12)] + [_part("bonder") for _ in range(12)]}

    left = solution_architecture_signature(sequential)
    right = solution_architecture_signature(parallel)

    assert left["archetype"] == "single-arm-sequential"
    assert left["pistonCount"] == 1
    assert left["programSpan"] == 1
    assert right["archetype"] == "parallel-throughput"


def test_periodic_pipeline_is_identified_from_repeat_programming():
    solution = {"parts": [
        _part("arm1", [{"cycle": 4, "instruction": "repeat"}]),
        _part("arm1", [{"cycle": 1, "instruction": "grab"}]),
    ]}
    signature = solution_architecture_signature(solution)
    assert signature["archetype"] == "periodic-pipeline"
    assert signature["programSpan"] == 4


def test_specialization_axes_select_independent_winners():
    records = [
        {"name": "cheap", "metrics": {"cost": 50, "area": 100, "cycles": 90, "instructions": 30}},
        {"name": "small", "metrics": {"cost": 90, "area": 25, "cycles": 120, "instructions": 20}},
        {"name": "short", "metrics": {"cost": 120, "area": 80, "cycles": 50, "instructions": 15}},
    ]
    winners = specialization_axes(records)
    assert winners["cost"]["name"] == "cheap"
    assert winners["area"]["name"] == "small"
    assert winners["cycles"]["name"] == "short"
    assert winners["instructions"]["name"] == "short"
