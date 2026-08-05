from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_continuation import search_compact_continuation
from packages.opus_solver.rotor_prefix import build_locked_prefix_simulator


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
PREFIX = Path("fixtures/solutions/van-berlos-rotor-area42-corrected-prefix.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    simulator = build_locked_prefix_simulator(_load(PUZZLE), _load(PREFIX))
    result = search_compact_continuation(
        simulator,
        max_depth=5,
        max_states=2_000,
        max_active_arms=1,
    )
    print(json.dumps({
        "found": result.found,
        "actions": result.actions,
        "visitedStates": result.visited_states,
        "expandedStates": result.expanded_states,
        "depth": result.depth,
        "stoppedReason": result.stopped_reason,
    }, indent=2))


if __name__ == "__main__":
    main()
