from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.fixed_layout import LayoutBounds, solve_fixed_layout


def _load_layout(path: Path) -> dict:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return parse_solution(path)


def _load_puzzle(path: Path) -> dict:
    if path.suffix.lower() == ".b64":
        raw = base64.b64decode(path.read_text(encoding="utf-8").strip())
        return parse_puzzle(raw)
    return parse_puzzle(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Brute-force a fixed Opus Magnum layout by initial pose then instructions.")
    ap.add_argument("--puzzle", required=True, type=Path)
    ap.add_argument("--layout", required=True, type=Path)
    ap.add_argument("--center-q", required=True, type=int)
    ap.add_argument("--center-r", required=True, type=int)
    ap.add_argument("--radius", required=True, type=int)
    ap.add_argument("--period", type=int, default=7)
    ap.add_argument("--max-active-arms", type=int, default=4)
    ap.add_argument("--max-atoms", type=int, default=24)
    ap.add_argument("--max-start-configs", type=int, default=0)
    ap.add_argument("--max-states-per-depth", type=int, default=100000)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    puzzle = _load_puzzle(args.puzzle)
    layout = _load_layout(args.layout)
    bounds = LayoutBounds(
        center=(args.center_q, args.center_r),
        radius=args.radius,
        period=args.period,
        max_active_arms=args.max_active_arms,
        max_atoms=args.max_atoms,
        max_start_configs=args.max_start_configs,
        max_states_per_depth=args.max_states_per_depth,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    result = solve_fixed_layout(puzzle, layout, bounds)
    report = result.to_dict()
    (args.out / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)

    if result.solution is not None:
        write_solution(result.solution.candidate_solution, args.out / "best.solution")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
