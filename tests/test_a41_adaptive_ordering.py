import json
from pathlib import Path

import tools.run_rotor_a41_remote_cached as cached
from tools.run_rotor_a41_remote_cached import (
    expand_idle_window_shifts,
    load_generated_best,
    load_learned_ranks,
    reorder_shifts,
)


def test_reorder_shifts_uses_learned_group_order_stably():
    shifts = [
        {"part": "part-9", "instruction": "grab", "cycle": 10},
        {"part": "part-1", "instruction": "rotate_cw", "cycle": 20},
        {"part": "part-1", "instruction": "rotate_cw", "cycle": 30},
        {"part": "part-12", "instruction": "drop", "cycle": 40},
    ]
    ranks = {("part-1", "rotate_cw"): 0, ("part-9", "grab"): 1}

    ordered = reorder_shifts(shifts, ranks)

    assert [row["cycle"] for row in ordered] == [20, 30, 10, 40]


def test_expand_idle_window_shifts_never_crosses_previous_instruction():
    solution = {
        "parts": [
            {
                "id": "part-1",
                "program": [
                    {"cycle": 10, "instruction": "grab"},
                    {"cycle": 15, "instruction": "rotate_cw"},
                ],
            }
        ]
    }
    base = [
        {
            "part": "part-1",
            "cycle": 15,
            "targetCycle": 14,
            "instruction": "rotate_cw",
        }
    ]

    expanded = expand_idle_window_shifts(solution, base, max_jump=8)

    assert [row["targetCycle"] for row in expanded] == [14, 13, 12, 11]
    assert [row["jump"] for row in expanded] == [1, 2, 3, 4]


def test_expand_idle_window_shifts_respects_jump_cap():
    solution = {
        "parts": [
            {
                "id": "part-1",
                "program": [
                    {"cycle": 1, "instruction": "grab"},
                    {"cycle": 20, "instruction": "rotate_cw"},
                ],
            }
        ]
    }
    base = [{"part": "part-1", "cycle": 20, "targetCycle": 19, "instruction": "rotate_cw"}]
    expanded = expand_idle_window_shifts(solution, base, max_jump=3)
    assert [row["targetCycle"] for row in expanded] == [19, 18, 17]


def test_real_a41_fixture_expands_search_without_exceeding_campaign_budget():
    solution, _, _ = cached.campaign.load_reference()
    assert solution is not None
    base = cached.campaign.candidate_shifts(solution)
    expanded = expand_idle_window_shifts(solution, base, max_jump=cached.MAX_IDLE_JUMP)
    assert len(base) == 34
    assert len(expanded) > len(base)
    assert len(expanded) <= cached.campaign.MAX_CANDIDATES


def test_load_learned_ranks_ignores_invalid_file(tmp_path: Path):
    path = tmp_path / "learning.json"
    path.write_text("not-json", encoding="utf-8")
    assert load_learned_ranks(path) == {}


def test_generated_best_is_preferred_only_when_it_improves_a41(tmp_path: Path, monkeypatch):
    best = tmp_path / "best.parsed.json"
    solution = tmp_path / "best.solution"
    monkeypatch.setattr(cached.campaign, "BEST_PARSED", best)
    monkeypatch.setattr(cached.campaign, "BEST_SOLUTION", solution)

    best.write_text(json.dumps({"metrics": {"cycles": 1100, "area": 41}}), encoding="utf-8")
    model, name, kind = load_generated_best()
    assert model is not None
    assert name == solution.name
    assert kind == "validated-omsim-best"

    best.write_text(json.dumps({"metrics": {"cycles": 1112, "area": 41}}), encoding="utf-8")
    assert load_generated_best() == (None, None, None)

    best.write_text(json.dumps({"metrics": {"cycles": 1090, "area": 42}}), encoding="utf-8")
    assert load_generated_best() == (None, None, None)
