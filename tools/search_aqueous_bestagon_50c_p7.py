from __future__ import annotations

import argparse
import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packages.opus_parser import write_solution_bytes
from tools.validate_aqueous_offsets import validate


def axial_radius(q: int, r: int, cq: int, cr: int) -> int:
    dq, dr = q - cq, r - cr
    return max(abs(dq), abs(dr), abs(dq + dr))


def inst(cycle: int, action: str) -> dict:
    raw = {
        'grab':'G','drop':'g','rotate_cw':'R','rotate_ccw':'r',
        'pivot_cw':'P','pivot_ccw':'p','extend':'E','retract':'e',
    }[action]
    return {'cycle': cycle, 'instruction': action, 'rawCode': raw}


def max_program_cycle(sol: dict) -> int:
    return max((x['cycle'] for p in sol['parts'] for x in p.get('program', [])), default=-1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--validator-url', required=True)
    ap.add_argument('--puzzle', required=True)
    ap.add_argument('--seed-json', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=120000)
    args = ap.parse_args()

    puzzle = Path(args.puzzle)
    base = json.loads(Path(args.seed_json).read_text(encoding='utf-8'))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Markers are visual scaffolding only and must not constrain Bestagon search.
    base['parts'] = [p for p in base['parts'] if p.get('type') != 'glyph-marker']
    base['metrics'] = {}
    base['unknownMetrics'] = []

    outputs = [p for p in base['parts'] if p.get('type') == 'out-std']
    if len(outputs) != 1:
        raise SystemExit(f'Expected one output, found {len(outputs)}')
    cq, cr = outputs[0]['position']

    arms = [i for i,p in enumerate(base['parts']) if p.get('type') in ('arm1','piston')]
    if len(arms) != 3:
        raise SystemExit(f'Expected three existing manipulators, found {len(arms)}')

    # Confirm the known C7 tail: grab / drop / rotate_ccw in some arm order.
    c7 = []
    for idx in arms:
        for x in base['parts'][idx].get('program', []):
            if x['cycle'] == 7:
                c7.append((idx, x['instruction']))
    if sorted(a for _,a in c7) != sorted(['grab','drop','rotate_ccw']):
        raise SystemExit(f'Unexpected C7 tail: {c7}')

    # Each old C7 action is either deleted or moved to C6. This guarantees max cycle <= 6.
    end_variants = []
    for mask in range(8):
        sol = copy.deepcopy(base)
        meta = []
        for bit,(idx,action) in enumerate(c7):
            prog = [x for x in sol['parts'][idx]['program'] if x['cycle'] != 7]
            mode = 'remove'
            if mask & (1 << bit):
                # Do not put two instructions on the same arm/cycle.
                if not any(x['cycle'] == 6 for x in prog):
                    prog.append(inst(6, action))
                    mode = 'move6'
            prog.sort(key=lambda x:x['cycle'])
            sol['parts'][idx]['program'] = prog
            meta.append((idx, action, mode))
        if max_program_cycle(sol) <= 6:
            end_variants.append((sol, meta))

    occupied = {tuple(p['position']) for p in base['parts'] if p.get('type') != 'track'}
    cells=[]
    for q in range(cq-3,cq+4):
        for r in range(cr-3,cr+4):
            if axial_radius(q,r,cq,cr) <= 3 and (q,r) not in occupied:
                cells.append((q,r))

    templates = [
        ('grab','pivot_cw','drop'), ('grab','pivot_ccw','drop'),
        ('grab','rotate_cw','drop'), ('grab','rotate_ccw','drop'),
        ('grab','extend','drop'), ('grab','retract','drop'),
        ('grab','extend','pivot_cw','drop'), ('grab','extend','pivot_ccw','drop'),
        ('grab','pivot_cw','extend','drop'), ('grab','pivot_ccw','extend','drop'),
        ('grab','rotate_cw','extend','drop'), ('grab','rotate_ccw','extend','drop'),
        ('grab','extend','rotate_cw','drop'), ('grab','extend','rotate_ccw','drop'),
    ]

    jobs=[]
    serial=0
    for end_sol,end_meta in end_variants:
        for part_type in ('arm1','piston'):
            for pos in cells:
                for length in (1,2,3):
                    for rotation in range(6):
                        for actions in templates:
                            # Contiguous short suffix ending exactly at C6.
                            start = 7 - len(actions)
                            if start < 0:
                                continue
                            sol = copy.deepcopy(end_sol)
                            prog=[inst(start+i,a) for i,a in enumerate(actions)]
                            sol['parts'].append({
                                'type':part_type,'enabled':True,'position':[pos[0],pos[1]],
                                'length':length,'rotation':rotation,'which':0,'armNumber':3,
                                'program':prog,
                            })
                            sol['name']=f'B3 P7 candidate {serial}'
                            if max_program_cycle(sol) > 6:
                                raise AssertionError('Generated non-P7 candidate')
                            path=out/f'candidate-{serial:06d}.solution'
                            path.write_bytes(write_solution_bytes(sol))
                            jobs.append((serial,part_type,pos,length,rotation,actions,end_meta,path))
                            serial += 1
                            if len(jobs) >= args.limit:
                                break
                        if len(jobs) >= args.limit: break
                    if len(jobs) >= args.limit: break
                if len(jobs) >= args.limit: break
            if len(jobs) >= args.limit: break
        if len(jobs) >= args.limit: break

    valid=[]
    closest=[]
    issue_counts={}
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,8))) as pool:
        futs={pool.submit(validate,args.validator_url,puzzle,j[-1]):j for j in jobs}
        for n,fut in enumerate(as_completed(futs),1):
            serial,part_type,pos,length,rotation,actions,end_meta,path=futs[fut]
            try:
                r=fut.result()
            except Exception as exc:
                r={'valid':False,'rawOutput':str(exc),'issues':[{'message':str(exc)}]}
            rec={
                'serial':serial,'type':part_type,'position':pos,'length':length,'rotation':rotation,
                'actions':actions,'endTail':end_meta,'metrics':r.get('metrics'),'file':path.name,
                'rawOutput':r.get('rawOutput'),
            }
            if r.get('valid'):
                valid.append(rec)
                print('VALID '+json.dumps(rec,default=str),flush=True)
            else:
                raw=r.get('rawOutput') or ''
                norm=re.sub(r'cycle \d+','cycle N',raw)
                issue_counts[norm]=issue_counts.get(norm,0)+1
                m=re.search(r'cycle (\d+)',raw)
                cyc=int(m.group(1)) if m else -1
                closest.append((cyc,rec))
            if n%500==0 or n==len(jobs):
                print(f'PROGRESS {n}/{len(jobs)} valid={len(valid)}',flush=True)

    valid.sort(key=lambda x:((x.get('metrics') or {}).get('cycles',10**9),(x.get('metrics') or {}).get('cost',10**9),(x.get('metrics') or {}).get('area',10**9)))
    closest.sort(key=lambda x:x[0],reverse=True)
    payload={
        'candidateCount':len(jobs),'validCount':len(valid),'p7GuaranteedByMaxProgramCycle':6,
        'results':valid[:100],'closestInvalid':[x for _,x in closest[:30]],
        'issueCounts':sorted(issue_counts.items(),key=lambda kv:kv[1],reverse=True)[:20],
    }
    (out/'results.json').write_text(json.dumps(payload,indent=2,default=str),encoding='utf-8')
    if valid:
        (out/'best.solution').write_bytes((out/valid[0]['file']).read_bytes())
    print(json.dumps({'candidateCount':len(jobs),'validCount':len(valid),'best':valid[:5],'closest':payload['closestInvalid'][:5]},default=str),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
