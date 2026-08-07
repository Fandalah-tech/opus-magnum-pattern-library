from pathlib import Path

from tools.run_rotor_a41_remote_cached import load_learned_ranks, reorder_shifts


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
