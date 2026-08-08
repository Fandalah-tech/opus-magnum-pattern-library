from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.fixed_layout import LayoutBounds
from packages.opus_solver.pipeline_enumerator import search_short_pipelines


def main() -> int:
    ap = argparse.ArgumentParser(description='Enumerate 5c@1, 6c@1 and prove 7c@2 candidates on a fixed layout.')
    ap.add_argument('--puzzle', required=True, type=Path)
    ap.add_argument('--layout', required=True, type=Path)
    ap.add_argument('--center-q', required=True, type=int)
    ap.add_argument('--center-r', required=True, type=int)
    ap.add_argument('--radius', required=True, type=int)
    ap.add_argument('--motion-radius', type=int)
    ap.add_argument('--offset', type=int, default=0)
    ap.add_argument('--limit', type=int, default=1)
    ap.add_argument('--max-active-arms', type=int, default=4)
    ap.add_argument('--max-atoms', type=int, default=24)
    ap.add_argument('--max-states-per-depth', type=int, default=10000)
    ap.add_argument('--catalog-limit', type=int, default=5000)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()

    raw = base64.b64decode(args.puzzle.read_text(encoding='utf-8').strip()) if args.puzzle.suffix == '.b64' else args.puzzle.read_bytes()
    puzzle = parse_puzzle(raw)
    layout = json.loads(args.layout.read_text(encoding='utf-8'))
    bounds = LayoutBounds(
        center=(args.center_q, args.center_r),
        radius=args.radius,
        motion_radius=args.motion_radius,
        period=7,
        max_active_arms=args.max_active_arms,
        max_atoms=args.max_atoms,
        max_start_configs=0,
        max_states_per_depth=args.max_states_per_depth,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    progress_path = args.out / 'progress.jsonl'

    def progress(event: dict) -> None:
        line = json.dumps(event, separators=(',', ':'))
        print(line, flush=True)
        with progress_path.open('a', encoding='utf-8') as fh:
            fh.write(line + '\n')
        if event.get('event') in {'depth', 'configuration_end'}:
            (args.out / 'checkpoint.json').write_text(json.dumps(event, indent=2), encoding='utf-8')

    result = search_short_pipelines(
        puzzle,
        layout,
        bounds,
        offset=args.offset,
        limit=args.limit,
        catalog_limit=args.catalog_limit,
        progress=progress,
    )
    payload = result.to_dict()
    (args.out / 'results.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')

    # Persist directly proven 2-by-7 candidates as real .solution files.
    if result.two_by_7:
        from copy import deepcopy
        from packages.opus_solver.fixed_layout import enumerate_start_configurations
        configs = {c.index: c for c in enumerate_start_configurations(puzzle, layout, bounds)}
        for i, candidate in enumerate(result.two_by_7[:10]):
            start = configs[candidate.start_configuration]
            solved = deepcopy(start.solution)
            by_id = {
                str(part.get('id')): part
                for part in solved.get('parts', [])
                if str(part.get('type') or '').startswith('arm') or part.get('type') in {'piston', 'baron'}
            }
            for part in by_id.values():
                part['program'] = []
            for cycle, row in enumerate(candidate.program):
                for arm_id, action in row.items():
                    if action is not None:
                        by_id[arm_id]['program'].append({'cycle': cycle, 'instruction': action})
            solved['name'] = f'proven 2-by-7 config {candidate.start_configuration}'
            solved['metrics'] = {}
            solved['unknownMetrics'] = []
            write_solution(solved, args.out / f'two-by-7-{i:02d}.solution')

    print(json.dumps({
        'foundTwoBy7': result.found_two_by_7,
        'oneBy5': len(result.one_by_5),
        'oneBy6': len(result.one_by_6),
        'twoBy7': len(result.two_by_7),
        'matchGroups': len(result.match_groups),
        'stats': result.stats.to_dict(),
    }, indent=2), flush=True)
    return 0 if result.found_two_by_7 else 2


if __name__ == '__main__':
    raise SystemExit(main())
