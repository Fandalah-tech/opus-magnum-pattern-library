import json
from pathlib import Path

import tools.run_rotor_a41_remote_cached as cached
from tools.run_rotor_a41_remote_cached import load_generated_best, load_learned_ranks, reorder_shifts


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
