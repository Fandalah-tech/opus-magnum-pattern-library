from __future__ import annotations

import argparse
import base64
import itertools
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import validate

ACTIONS = ("grab", "drop", "rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw", "extend", "retract")


def axial_radius(q: int, r: int, cq: int, cr: int) -> int:
    dq, dr = q - cq, r - cr
    return max(abs(dq), abs(dr), abs(dq + dr))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--validator-url', required=True)
    ap.add_argument('--puzzle', required=True)
    ap.add_argument('--seed', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()

    seed_path = Path(args.seed)
    puzzle = Path(args.puzzle)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seed_bytes = seed_path.read_bytes()
    base = parse_solution_bytes(seed_bytes, source_name=seed_path.name)

    outputs = [p for p in base['parts'] if p.get('type') == 'out-std']
    if not outputs:
        raise SystemExit('No output found')
    cq, cr = outputs[0]['position']

    occupied = {tuple(p['position']) for p in base['parts'] if p.get('type') != 'track'}
    cells = []
    for q in range(cq - 3, cq + 4):
        for r in range(cr - 3, cr + 4):
            if axial_radius(q, r, cq, cr) <= 3 and (q, r) not in occupied:
                cells.append((q, r))

    # Keep the proven C0-C4 manufacturing prefix untouched. Add only a transfer manipulator.
    # Search short suffixes beginning at C5; first pass is intentionally small and exhaustive.
    specs = []
    serial = 0
    for part_type in ('arm1', 'piston'):
        lengths = (1, 2, 3) if part_type == 'piston' else (1, 2, 3)
        for pos in cells:
            for length in lengths:
                for rot in range(6):
                    for grab_cycle in (4, 5, 6):
                        # 2-4 actions after grab; include a mandatory drop.
                        tail_actions = ('drop', 'rotate_cw', 'rotate_ccw', 'pivot_cw', 'pivot_ccw', 'extend', 'retract')
                        for n_tail in (1, 2, 3):
                            for tail in itertools.product(tail_actions, repeat=n_tail):
                                if 'drop' not in tail:
                                    continue
                                prog = [{'cycle': grab_cycle, 'instruction': 'grab', 'rawCode': 'G'}]
                                for i, act in enumerate(tail, start=1):
                                    raw = {'drop':'g','rotate_cw':'R','rotate_ccw':'r','pivot_cw':'P','pivot_ccw':'p','extend':'E','retract':'e'}[act]
                                    prog.append({'cycle': grab_cycle + i, 'instruction': act, 'rawCode': raw})
                                specs.append((serial, part_type, pos, length, rot, prog))
                                serial += 1

    # Hard cap first pass to avoid an accidental combinatorial explosion; deterministic prefix of canonical ordering.
    specs = specs[:12000]
    jobs = []
    for serial, part_type, pos, length, rot, prog in specs:
        candidate = parse_solution_bytes(seed_bytes, source_name=seed_path.name)
        candidate['name'] = f'B3 exit arm #{serial}'
        candidate['metrics'] = {}
        candidate['unknownMetrics'] = []
        candidate['parts'].append({
            'id': f'added-{serial}', 'type': part_type, 'enabled': True,
            'position': [pos[0], pos[1]], 'length': length, 'rotation': rot,
            'which': 0, 'armNumber': 90, 'program': prog,
        })
        path = out / f'candidate-{serial:05d}.solution'
        path.write_bytes(write_solution_bytes(candidate))
        jobs.append((serial, part_type, pos, length, rot, prog, path))

    valid = []
    closest = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futs = {pool.submit(validate, args.validator_url, puzzle, x[-1]): x for x in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            serial, part_type, pos, length, rot, prog, path = futs[fut]
            try:
                result = fut.result()
            except Exception as exc:
                result = {'valid': False, 'issues': [{'message': str(exc)}], 'rawOutput': str(exc)}
            rec = {'serial': serial, 'type': part_type, 'position': pos, 'length': length, 'rotation': rot,
                   'program': [(x['cycle'], x['instruction']) for x in prog], 'metrics': result.get('metrics'),
                   'file': path.name, 'rawOutput': result.get('rawOutput')}
            if result.get('valid'):
                valid.append(rec)
                print('VALID ' + json.dumps(rec, default=str), flush=True)
            else:
                raw = result.get('rawOutput') or ''
                cycle = -1
                import re
                m = re.search(r'cycle (\d+)', raw)
                if m:
                    cycle = int(m.group(1))
                closest.append((cycle, rec))
            if n % 250 == 0 or n == len(jobs):
                print(f'PROGRESS {n}/{len(jobs)} valid={len(valid)}', flush=True)

    valid.sort(key=lambda x: ((x.get('metrics') or {}).get('cycles', 10**9), (x.get('metrics') or {}).get('cost', 10**9)))
    closest.sort(key=lambda x: x[0], reverse=True)
    payload = {'candidateCount': len(jobs), 'validCount': len(valid), 'results': valid[:50], 'closestInvalid': [r for _, r in closest[:20]]}
    (out / 'results.json').write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
    if valid:
        (out / 'best.solution').write_bytes((out / valid[0]['file']).read_bytes())
    print(json.dumps({'candidateCount': len(jobs), 'validCount': len(valid), 'best': valid[:5], 'closest': payload['closestInvalid'][:5]}, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
