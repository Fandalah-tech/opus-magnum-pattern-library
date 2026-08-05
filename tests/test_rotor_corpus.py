from packages.opus_solver.rotor_corpus import rank_seed_candidates, summarize_solution


def _solution(name: str, arm_types: list[str], instruction_count: int) -> dict:
    parts = [
        {"type": "out-std", "program": []},
        {"type": "input", "program": []},
        {"type": "input", "program": []},
        {"type": "baron", "program": []},
        {"type": "bonder", "program": []},
        {"type": "unbonder", "program": []},
        {"type": "track", "program": []},
    ]
    per_arm = max(1, instruction_count // max(1, len(arm_types)))
    parts.extend(
        {"type": arm_type, "program": [{"cycle": i, "instruction": "grab"} for i in range(per_arm)]}
        for arm_type in arm_types
    )
    return {
        "name": name,
        "metrics": {"cycles": None, "cost": None, "area": None, "instructions": None},
        "source": {"sha256": name},
        "parts": parts,
    }


def test_infers_metrics_from_working_solution_name() -> None:
    entry = summarize_solution(_solution("A47 - C574", ["piston", "piston"], 160), "area.solution")

    assert entry.inferred_metrics["area"] == 47
    assert entry.inferred_metrics["cycles"] == 574
    assert entry.family == "area-piston-track"
    assert entry.likely_complete is True


def test_sum_architecture_is_classified_without_embedded_metrics() -> None:
    entry = summarize_solution(_solution("SUM465", ["arm6", "arm1", "arm1"], 77), "sum.solution")

    assert entry.inferred_metrics["sum"] == 465
    assert entry.family == "sum-arm6-track"
    assert entry.active_arm_count == 3
    assert entry.likely_complete is True


def test_setup_and_experimental_files_are_not_seed_candidates() -> None:
    complete = summarize_solution(_solution("SUM465", ["arm6", "arm1", "arm1"], 77), "complete.solution")
    setup = summarize_solution(_solution("43 SETUP", ["piston"], 80), "setup.solution")
    experimental = summarize_solution(_solution("SUM465 - EXPERIMENTAL", ["arm6", "arm1", "arm1"], 77), "experimental.solution")

    ranked = rank_seed_candidates([setup, experimental, complete])

    assert [entry.filename for entry in ranked] == ["complete.solution"]


def test_sum_family_ranks_before_larger_area_machine() -> None:
    area = summarize_solution(_solution("A47 - C574", ["piston", "piston"], 160), "area.solution")
    sum_entry = summarize_solution(_solution("SUM480", ["arm6", "arm1", "arm1"], 73), "sum.solution")

    ranked = rank_seed_candidates([area, sum_entry])

    assert [entry.filename for entry in ranked] == ["sum.solution", "area.solution"]
