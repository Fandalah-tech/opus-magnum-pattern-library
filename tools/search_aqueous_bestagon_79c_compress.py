from __future__ import annotations

import argparse
import copy
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import validate


def normalize_metrics(solution: dict) -> None:
    solution['metrics'] = {}
    solution['unknownMetrics'] = []


def compress_once(base: dict, part_idx: int, inst_idx: int, delta: int) -> dict | None:
    cand = copy.deepcopy(base)
    prog = cand['parts'][part_idx].get('program') or []
    if not (0 <= inst_idx < len(prog)):
        return None
    new_cycle = int(prog[inst_idx]['cycle']) + delta
    if new_cycle < 0:
        return None
    prog[inst_idx]['cycle'] = new_cycle
    prog.sort(key=lambda x: int(x['cycle']))
    cycles = [int(x['cycle']) for x in prog]
    if len(cycles) != len(set(cycles)):
        return None
    normalize_metrics(cand)
    return cand


def shift_suffix(base: dict, part_idx: int, start_inst: int, delta: int) -> dict | None:
    cand = copy.deepcopy(base)
    prog = cand['parts'][part_idx].get('program') or []
    if not (0 <= start_inst < len(prog)):
        return None
    for i in range(start_inst, len(prog)):
        nc = int(prog[i]['cycle']) + delta
        if nc < 0:
            return None
        prog[i]['cycle'] = nc
    prog.sort(key=lambda x: int(x['cycle']))
    cycles = [int(x['cycle']) for x in prog]
    if len(cycles) != len(set(cycles)):
        return None
    normalize_metrics(cand)
    return cand


def delete_reset(base: dict, part_idx: int, inst_idx: int) -> dict | None:
    cand = copy.deepcopy(base)
    prog = cand['parts'][part_idx].get('program') or []
    if not (0 <= inst_idx < len(prog)):
        return None
    if prog[inst_idx].get('instruction') != 'reset':
        return None
    del prog[inst_idx]
    normalize_metrics(cand)
    return cand


def candidate_key(sol: dict) -> str:
    items=[]
    for p in sol['parts']:
        prog=tuple((int(x['cycle']),x['instruction']) for x in p.get('program') or [])
        items.append((p['type'],tuple(p['position']),int(p.get('length',1)),int(p.get('rotation',0)),prog))
    return repr(tuple(items))


def score_metrics(m: dict | None):
    m=m or {}
    return (int(m.get('cycles') or 10**9), int(m.get('instructions') or 10**9), int(m.get('cost') or 10**9), int(m.get('area') or 10**9))


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--validator-url',required=True)
    ap.add_argument('--puzzle',required=True)
    ap.add_argument('--seed',required=True)
    ap.add_argument('--out',required=True)
    ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--rounds',type=int,default=20)
    args=ap.parse_args()
    puzzle=Path(args.puzzle); seed=Path(args.seed); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    current=parse_solution_bytes(seed.read_bytes(),source_name=seed.name)
    seed_validation=validate(args.validator_url,puzzle,seed)
    if not seed_validation.get('valid'):
        raise SystemExit('79c seed failed validation: '+json.dumps(seed_validation))
    best_metrics=seed_validation.get('metrics') or {}
    (out/'best.solution').write_bytes(seed.read_bytes())
    history=[{'round':0,'metrics':best_metrics,'move':'seed'}]
    seen={candidate_key(current)}

    for rnd in range(1,args.rounds+1):
        jobs=[]; serial=0
        for pi,p in enumerate(current['parts']):
            prog=p.get('program') or []
            for ii,_ in enumerate(prog):
                for delta in (-1,-2):
                    c=compress_once(current,pi,ii,delta)
                    if c is not None:
                        k=candidate_key(c)
                        if k not in seen:
                            seen.add(k); jobs.append((serial,{'kind':'single','part':pi,'inst':ii,'delta':delta},c)); serial+=1
                for delta in (-1,-2):
                    c=shift_suffix(current,pi,ii,delta)
                    if c is not None:
                        k=candidate_key(c)
                        if k not in seen:
                            seen.add(k); jobs.append((serial,{'kind':'suffix','part':pi,'inst':ii,'delta':delta},c)); serial+=1
                c=delete_reset(current,pi,ii)
                if c is not None:
                    k=candidate_key(c)
                    if k not in seen:
                        seen.add(k); jobs.append((serial,{'kind':'delete_reset','part':pi,'inst':ii},c)); serial+=1

        paths=[]
        for serial,meta,c in jobs:
            c['name']=f'B3 79c compress r{rnd} #{serial}'
            path=out/f'r{rnd:02d}-{serial:04d}.solution'
            path.write_bytes(write_solution_bytes(c))
            paths.append((serial,meta,c,path))

        valids=[]
        with ThreadPoolExecutor(max_workers=max(1,min(args.workers,8))) as pool:
            futs={pool.submit(validate,args.validator_url,puzzle,path):(serial,meta,c,path) for serial,meta,c,path in paths}
            for n,fut in enumerate(as_completed(futs),1):
                serial,meta,c,path=futs[fut]
                try:r=fut.result()
                except Exception as exc:r={'valid':False,'issues':[{'message':str(exc)}]}
                if r.get('valid'):
                    valids.append((score_metrics(r.get('metrics')),meta,c,path,r))
                if n%50==0 or n==len(futs):
                    print(f'ROUND {rnd} PROGRESS {n}/{len(futs)} valid={len(valids)}',flush=True)
        if not valids:
            history.append({'round':rnd,'metrics':best_metrics,'move':'no-valid-neighbor','tested':len(jobs)})
            print(json.dumps({'round':rnd,'status':'local-minimum','best':best_metrics,'tested':len(jobs)}),flush=True)
            break
        valids.sort(key=lambda x:x[0])
        best=valids[0]
        if best[0] >= score_metrics(best_metrics):
            history.append({'round':rnd,'metrics':best_metrics,'move':'no-improvement','tested':len(jobs),'bestNeighbor':best[4].get('metrics')})
            print(json.dumps({'round':rnd,'status':'no-improvement','best':best_metrics,'neighbor':best[4].get('metrics')}),flush=True)
            break
        _,meta,current,path,r=best
        best_metrics=r.get('metrics') or {}
        (out/'best.solution').write_bytes(path.read_bytes())
        history.append({'round':rnd,'metrics':best_metrics,'move':meta,'tested':len(jobs)})
        print('IMPROVED '+json.dumps(history[-1],sort_keys=True),flush=True)

    (out/'results.json').write_text(json.dumps({'seedMetrics':seed_validation.get('metrics'),'bestMetrics':best_metrics,'history':history,'seenCandidates':len(seen)},indent=2),encoding='utf-8')
    print(json.dumps({'bestMetrics':best_metrics,'rounds':len(history)-1,'seenCandidates':len(seen)}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
