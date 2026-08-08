from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import validate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--validator-url', required=True)
    ap.add_argument('--puzzle', required=True)
    ap.add_argument('--seed', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()

    puzzle = Path(args.puzzle)
    seed_path = Path(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = parse_solution_bytes(seed_path.read_bytes(), source_name=seed_path.name)
    pistons = [i for i,p in enumerate(base['parts']) if p.get('type') == 'piston']
    if len(pistons) != 2:
        raise SystemExit(f'Expected 2 pistons, found {len(pistons)}')
    a,b = pistons
    prog_a = base['parts'][a]['program']
    prog_b = base['parts'][b]['program']
    actions_a = [x['instruction'] for x in prog_a]
    actions_b = [x['instruction'] for x in prog_b]

    jobs=[]
    serial=0
    for period in (5,6,7):
        for ca in combinations(range(period), len(actions_a)):
            for cb in combinations(range(period), len(actions_b)):
                candidate = parse_solution_bytes(seed_path.read_bytes(), source_name=seed_path.name)
                candidate['name'] = f'B3 piston P{period} #{serial}'
                candidate['metrics'] = {}
                candidate['unknownMetrics'] = []
                candidate['parts'][a]['program'] = [
                    {'cycle': cyc, 'instruction': inst, 'rawCode': prog_a[i].get('rawCode')}
                    for i,(cyc,inst) in enumerate(zip(ca, actions_a))
                ]
                candidate['parts'][b]['program'] = [
                    {'cycle': cyc, 'instruction': inst, 'rawCode': prog_b[i].get('rawCode')}
                    for i,(cyc,inst) in enumerate(zip(cb, actions_b))
                ]
                path=out/f'candidate-{serial:05d}.solution'
                path.write_bytes(write_solution_bytes(candidate))
                jobs.append((serial,period,ca,cb,path))
                serial+=1

    results=[]
    with ThreadPoolExecutor(max_workers=max(1,min(8,args.workers))) as pool:
        futs={pool.submit(validate,args.validator_url,puzzle,path):(serial,period,ca,cb,path) for serial,period,ca,cb,path in jobs}
        for n,fut in enumerate(as_completed(futs),1):
            serial,period,ca,cb,path=futs[fut]
            try:
                r=fut.result()
            except Exception as exc:
                r={'valid':False,'issues':[{'message':str(exc)}]}
            if r.get('valid'):
                record={'serial':serial,'period':period,'cyclesA':ca,'cyclesB':cb,'metrics':r.get('metrics'),'file':path.name}
                results.append(record)
                print('VALID '+json.dumps(record,sort_keys=True),flush=True)
            if n%100==0 or n==len(jobs):
                print(f'PROGRESS {n}/{len(jobs)} valid={len(results)}',flush=True)

    results.sort(key=lambda x:(x['period'], (x.get('metrics') or {}).get('cycles',10**9), (x.get('metrics') or {}).get('cost',10**9)))
    payload={'candidateCount':len(jobs),'validCount':len(results),'results':results}
    (out/'results.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    if results:
        best=out/results[0]['file']
        (out/'best.solution').write_bytes(best.read_bytes())
    print(json.dumps({'candidateCount':len(jobs),'validCount':len(results),'best':results[:10]},default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
