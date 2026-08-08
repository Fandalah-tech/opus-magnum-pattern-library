from __future__ import annotations

import argparse
import itertools
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packages.opus_parser import write_solution_bytes
from tools.validate_aqueous_offsets import validate

RAW = {
    'grab': 'G', 'drop': 'g', 'rotate_cw': 'R', 'rotate_ccw': 'r',
}


def axial_radius(q: int, r: int, cq: int, cr: int) -> int:
    dq, dr = q - cq, r - cr
    return max(abs(dq), abs(dr), abs(dq + dr))


def inst(cycle: int, instruction: str) -> dict:
    return {'cycle': cycle, 'instruction': instruction, 'rawCode': RAW[instruction]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--validator-url', required=True)
    ap.add_argument('--puzzle', required=True)
    ap.add_argument('--seed-json', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()

    base = json.loads(Path(args.seed_json).read_text(encoding='utf-8'))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    outputs = [p for p in base['parts'] if p.get('type') == 'out-std']
    if not outputs:
        raise SystemExit('No output')
    cq, cr = outputs[0]['position']

    # Keep factory infrastructure and arms 0/1. Remove current output manipulators
    # (armNumber 2/3) so the rotary arm owns the handoff/output role.
    fixed = []
    for p in base['parts']:
        if p.get('type') == 'glyph-marker':
            continue
        if p.get('armNumber') in (2, 3) and p.get('type') in ('arm1', 'piston', 'arm2', 'arm3', 'arm6', 'baron'):
            continue
        q = dict(p)
        if q.get('armNumber') in (0, 1):
            # Strict P7 first pass: terminal C7 action is either removed or moved to C6.
            q['program'] = [dict(x) for x in q.get('program', []) if int(x.get('cycle', 0)) < 7]
        fixed.append(q)

    occupied = {tuple(p['position']) for p in fixed if p.get('type') not in ('track',)}
    cells = []
    for q in range(cq - 3, cq + 4):
        for r in range(cr - 3, cr + 4):
            if axial_radius(q, r, cq, cr) <= 3 and (q, r) not in occupied:
                cells.append((q, r))

    # Short rotary programs ending by C6. The important family is pickup + 1/2 rotations + drop.
    programs = []
    for grab_cycle in (3, 4, 5):
        for nrot in (1, 2, 3):
            for dirs in itertools.product(('rotate_cw', 'rotate_ccw'), repeat=nrot):
                drop_cycle = grab_cycle + nrot + 1
                if drop_cycle > 6:
                    continue
                prog = [inst(grab_cycle, 'grab')]
                for i, d in enumerate(dirs, 1):
                    prog.append(inst(grab_cycle + i, d))
                prog.append(inst(drop_cycle, 'drop'))
                programs.append(prog)

    # Also test one-cycle hold / direct grab-drop paths.
    for g in (4, 5):
        if g + 1 <= 6:
            programs.append([inst(g, 'grab'), inst(g + 1, 'drop')])

    specs = []
    serial = 0
    for pos in cells:
        for length in (1, 2, 3):
            for rot in range(6):
                for prog in programs:
                    specs.append((serial, pos, length, rot, prog))
                    serial += 1

    jobs = []
    for serial, pos, length, rot, prog in specs:
        cand = dict(base)
        cand['name'] = f'arm6 rotary P7 #{serial}'
        cand['metrics'] = {}
        cand['unknownMetrics'] = []
        cand['parts'] = [dict(p) for p in fixed]
        cand['parts'].append({
            'id': f'rotary-{serial}', 'type': 'arm6', 'enabled': True,
            'position': [pos[0], pos[1]], 'length': length, 'rotation': rot,
            'which': 0, 'armNumber': 4, 'program': prog,
        })
        path = out / f'candidate-{serial:05d}.solution'
        path.write_bytes(write_solution_bytes(cand))
        jobs.append((serial, pos, length, rot, prog, path))

    valid = []
    closest = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futs = {pool.submit(validate, args.validator_url, Path(args.puzzle), x[-1]): x for x in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            serial, pos, length, rot, prog, path = futs[fut]
            try:
                result = fut.result()
            except Exception as exc:
                result = {'valid': False, 'rawOutput': str(exc)}
            rec = {
                'serial': serial, 'position': pos, 'length': length, 'rotation': rot,
                'program': [(x['cycle'], x['instruction']) for x in prog],
                'metrics': result.get('metrics'), 'file': path.name,
                'rawOutput': result.get('rawOutput') or '',
            }
            if result.get('valid'):
                valid.append(rec)
                print('VALID ' + json.dumps(rec, default=str), flush=True)
            else:
                raw = rec['rawOutput']
                m = re.search(r'cycle (\d+)', raw)
                cycle = int(m.group(1)) if m else -1
                closest.append((cycle, rec))
            if n % 250 == 0 or n == len(jobs):
                print(f'PROGRESS {n}/{len(jobs)} valid={len(valid)}', flush=True)

    valid.sort(key=lambda x: ((x.get('metrics') or {}).get('cycles', 10**9), (x.get('metrics') or {}).get('cost', 10**9)))
    closest.sort(key=lambda x: x[0], reverse=True)
    payload = {
        'candidateCount': len(jobs), 'validCount': len(valid),
        'results': valid[:50], 'closestInvalid': [x[1] for x in closest[:30]],
    }
    (out / 'results.json').write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
    if valid:
        (out / 'best.solution').write_bytes((out / valid[0]['file']).read_bytes())
    print(json.dumps({'candidateCount': len(jobs), 'validCount': len(valid), 'best': valid[:5], 'closest': payload['closestInvalid'][:5]}, default=str), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
