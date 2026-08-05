from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_prefix import replay_locked_prefix


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
PREFIX = Path("fixtures/solutions/van-berlos-rotor-area42-corrected-prefix.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_corrected_area42_prefix_replays_and_really_splits_source_pair() -> None:
    checkpoint = replay_locked_prefix(_load(PUZZLE), _load(PREFIX))
    counts = dict(checkpoint.event_counts)

    assert checkpoint.terminated_with_error is False
    assert checkpoint.completed_cycles >= 22
    assert counts.get("bond-removed", 0) >= 1
    assert counts.get("bond-created", 0) >= 1
    assert checkpoint.final_frame
