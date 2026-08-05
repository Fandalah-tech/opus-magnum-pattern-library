from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_macros import learn_rotor_macros


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SOLUTION = Path("fixtures/solutions/van-berlos-rotor-sum465.parsed.json")


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = json.loads(SOLUTION.read_text(encoding="utf-8"))
    program = learn_rotor_macros(puzzle, solution)
    payload = {
        "startupMilestones": len(program.startup),
        "productCount": len(program.products),
        "deliveryCycles": [product.delivery_cycle for product in program.products],
        "durations": [product.duration for product in program.products],
        "steadyStatePeriod": program.steady_state_period,
        "stableFromProduct": program.stable_from_product,
        "commonEventSignature": dict(program.event_signature),
        "productEventCounts": [dict(product.event_counts) for product in program.products],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
