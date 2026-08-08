from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.fixed_layout import LayoutBounds
from packages.opus_solver.fixed_layout_batch import solve_fixed_layout_batch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--puzzle', required=True, type=Path)
    ap.add_argument('--layout', required=True, type=Path)
    ap.add_argument('--center-q', type=int, required=True)
    ap.add_argument('--center-r', type=int, required=True)
    ap.add_argument('--radius', type=int, required=True)
    ap.add_argument('--motion-radius', type=int)
    ap.add_argument('--period', type=int, default=7)
    ap.add_argument('--offset', type=int, default=0)
    ap.add_argument('--limit', type=int, default=1)
    ap.add_argument('--max-active-arms', type=int, default=4)
    ap.add_argument('--max-atoms', type=int, default=24)
    ap.add_argument('--max-states-per-depth', type=int, default=10000)
    ap.add_argument('--verification-periods', type=int, default=5)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()

    raw = base64.b64decode(args.puzzle.read_text(encoding='utf-8').strip()) if args.puzzle.suffix == '.b64' else args.puzzle.read_bytes()
    puzzle = parse_puzzle(raw)
    layout = json.loads(args.layout.read_text(encoding='utf-8'))
    bounds = LayoutBounds(
        center=(args.center_q, args.center_r), radius=args.radius,
        motion_radius=args.motion_radius, period=args.period,
        max_active_arms=args.max_active_arms, max_atoms=args.max_atoms,
        max_start_configs=0, max_states_per_depth=args.max_states_per_depth,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    progress_path = args.out / 'progress.jsonl'
    checkpoint_path = args.out / 'checkpoint.json'

    def progress(payload: dict) -> None:
        line = json.dumps(payload, separators=(',', ':'))
        print(line, flush=True)
        with progress_path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')
        if payload.get('event') == 'checkpoint':
            checkpoint_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    result = solve_fixed_layout_batch(
        puzzle, layout, bounds, offset=args.offset, limit=args.limit,
        verification_periods=args.verification_periods,
        progress=progress,
    )
    payload = result.to_dict()
    (args.out / 'results.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2), flush=True)
    if result.solution is not None:
        write_solution(result.solution.candidate_solution, args.out / 'best.solution')
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
