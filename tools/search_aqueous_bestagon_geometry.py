from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import validate

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


def hexdist(a: tuple[int,int], b: tuple[int,int]) -> int:
    dq=a[0]-b[0]; dr=a[1]-b[1]
    return max(abs(dq), abs(dr), abs(dq+dr))


def hex_cells(center: tuple[int,int], radius: int) -> list[tuple[int,int]]:
    q0,r0=center
    out=[]
    for dq in range(-radius,radius+1):
        for dr in range(-radius,radius+1):
            if max(abs(dq),abs(dr),abs(dq+dr))<=radius:
                out.append((q0+dq,r0+dr))
    return out


def score(m: dict) -> tuple[int,int,int,int]:
    huge=10**9
    return (int(m.get('cycles',huge)), int(m.get('cost',huge)), int(m.get('area',huge)), int(m.get('instructions',huge)))


def arm_signature(solution: dict) -> str:
    parts=[]
    for p in solution.get('parts') or []:
        item={
            'type':p.get('type'),
            'position':list(p.get('position') or [0,0]),
            'rotation':int(p.get('rotation') or 0)%6,
            'length':int(p.get('length') or 1),
            'program':[(int(i.get('cycle',0)),str(i.get('instruction') or '')) for i in (p.get('program') or [])],
        }
        if p.get('type')=='track':
            item['track']=p.get('track') or p.get('trackHexes') or p.get('positions') or []
        parts.append(item)
    # arm numbering and part serialization order are irrelevant for identity
    parts.sort(key=lambda x: json.dumps(x,sort_keys=True,separators=(',',':')))
    raw=json.dumps(parts,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--validator-url',required=True)
    ap.add_argument('--puzzle',required=True)
    ap.add_argument('--seed',required=True)
    ap.add_argument('--skeleton',required=True)
    ap.add_argument('--work',required=True)
    ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--radius',type=int,default=3)
    ap.add_argument('--target-cycles',type=int,default=44)
    args=ap.parse_args()

    puzzle=Path(args.puzzle); seed_path=Path(args.seed); skeleton_path=Path(args.skeleton)
    root=Path(args.work); root.mkdir(parents=True,exist_ok=True)
    variants=root/'variants'; variants.mkdir(exist_ok=True)

    seed=parse_solution_bytes(seed_path.read_bytes(),source_name=seed_path.name)
    skeleton=parse_solution_bytes(skeleton_path.read_bytes(),source_name=skeleton_path.name)
    seed_val=validate(args.validator_url,puzzle,seed_path)
    if not seed_val.get('valid'): raise SystemExit(f'Seed invalid: {seed_val}')
    best_metrics=seed_val.get('metrics') or {}
    best_path=root/'best.solution'; shutil.copy2(seed_path,best_path)

    markers=[tuple(p.get('position') or [0,0]) for p in (skeleton.get('parts') or []) if p.get('type')=='glyph-marker']
    if not markers: raise SystemExit('Skeleton has no glyph-marker boundary')
    # Radius-3 ring is centrally symmetric; arithmetic mean is its center.
    center_s=(round(sum(q for q,_ in markers)/len(markers)),round(sum(r for _,r in markers)/len(markers)))
    sk_out=next(p for p in skeleton['parts'] if p.get('type')=='out-std')
    seed_out=next(p for p in seed['parts'] if p.get('type')=='out-std')
    rel_center=(center_s[0]-sk_out['position'][0], center_s[1]-sk_out['position'][1])
    center=(seed_out['position'][0]+rel_center[0], seed_out['position'][1]+rel_center[1])
    zone=hex_cells(center,args.radius)

    arm_indices=[i for i,p in enumerate(seed.get('parts') or []) if p.get('type') in ARM_TYPES]
    if len(arm_indices)!=2:
        raise SystemExit(f'Expected two arms in period-8 seed, got {arm_indices}')
    static_positions={tuple(p.get('position') or [0,0]) for i,p in enumerate(seed['parts']) if i not in arm_indices and p.get('type')!='track'}

    # Prioritize cells near the original arms, but exhaust the entire R3 zone.
    orig=[tuple(seed['parts'][i].get('position') or [0,0]) for i in arm_indices]
    cells1=sorted(zone,key=lambda c:(hexdist(c,orig[0]),c))
    cells2=sorted(zone,key=lambda c:(hexdist(c,orig[1]),c))

    seen=set(); paths=[]; generated=0
    for p1 in cells1:
        if p1 in static_positions: continue
        for r1 in range(6):
            for p2 in cells2:
                if p2==p1 or p2 in static_positions: continue
                for r2 in range(6):
                    cand=copy.deepcopy(seed)
                    cand['name']='Bestagon R3 geometry enumeration'
                    cand['metrics']={}; cand['unknownMetrics']=[]
                    cand['parts'][arm_indices[0]]['position']=list(p1)
                    cand['parts'][arm_indices[0]]['rotation']=r1
                    cand['parts'][arm_indices[1]]['position']=list(p2)
                    cand['parts'][arm_indices[1]]['rotation']=r2
                    sig=arm_signature(cand)
                    if sig in seen: continue
                    seen.add(sig)
                    path=variants/f'candidate-{len(paths):06d}.solution'
                    path.write_bytes(write_solution_bytes(cand))
                    paths.append(path); generated+=1

    print(json.dumps({'center':center,'radius':args.radius,'zoneCells':len(zone),'armIndices':arm_indices,'staticBaseCells':len(static_positions),'generated':generated,'seedMetrics':best_metrics},sort_keys=True),flush=True)

    workers=max(1,min(8,args.workers)); it=iter(paths); active={}; tested=0; valid=0; improved=0; target=False
    pool=ThreadPoolExecutor(max_workers=workers)
    started=time.monotonic(); lastlog=started

    def submit_one():
        try:p=next(it)
        except StopIteration:return False
        active[pool.submit(validate,args.validator_url,puzzle,p)]=p; return True

    for _ in range(min(workers,len(paths))): submit_one()
    while active:
        done,_=wait(set(active),timeout=1.0,return_when=FIRST_COMPLETED)
        for fut in done:
            path=active.pop(fut); tested+=1
            try:res=fut.result()
            except Exception as exc:res={'valid':False,'issues':[{'message':str(exc)}]}
            if res.get('valid') is True:
                valid+=1; m=res.get('metrics') or {}
                if score(m)<score(best_metrics):
                    best_metrics=m; improved+=1; shutil.copy2(path,best_path)
                    print('NEW BEST '+json.dumps(m,sort_keys=True),flush=True)
                if int(m.get('cycles',10**9))<=args.target_cycles:
                    target=True; shutil.copy2(path,root/f"target-{m.get('cycles')}c.solution")
                    print('TARGET FOUND '+json.dumps(m,sort_keys=True),flush=True)
            if not target: submit_one()
        now=time.monotonic()
        if now-lastlog>=5:
            print(f'PROGRESS tested={tested}/{len(paths)} valid={valid} bestCycles={best_metrics.get("cycles")} elapsed={now-started:.1f}s',flush=True); lastlog=now
        if target:
            for f in active: f.cancel()
            break
    pool.shutdown(wait=False,cancel_futures=True)

    result={'state':'target-found' if target else 'complete','seedMetrics':seed_val.get('metrics') or {},'bestMetrics':best_metrics,'center':center,'radius':args.radius,'zoneCells':len(zone),'generated':generated,'tested':tested,'valid':valid,'improved':improved,'targetCycles':args.target_cycles,'foundTarget':target,'elapsedSeconds':round(time.monotonic()-started,3)}
    (root/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('RESULT '+json.dumps(result,sort_keys=True),flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
