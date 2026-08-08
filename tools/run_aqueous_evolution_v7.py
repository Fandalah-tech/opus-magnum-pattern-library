from __future__ import annotations

import argparse, base64, json, shutil, subprocess, time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from tools.solution_identity import mechanical_id, raw_id, translation_class_id
from tools.validate_aqueous_offsets import validate


def score(m):
    h=10**9
    return (int(m.get('cycles',h)),int(m.get('cost',h)),int(m.get('area',h)),int(m.get('instructions',h)))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--validator-url',required=True); ap.add_argument('--puzzle',required=True); ap.add_argument('--seed',required=True)
    ap.add_argument('--work',required=True); ap.add_argument('--generations',type=int,default=300); ap.add_argument('--target-cycles',type=int,default=26)
    ap.add_argument('--workers',type=int,default=8); ap.add_argument('--watchdog-seconds',type=int,default=25); ap.add_argument('--generation-seconds',type=int,default=600)
    args=ap.parse_args()
    root=Path(args.work); root.mkdir(parents=True,exist_ok=True); archive=root/'archive'; archive.mkdir(exist_ok=True)
    puzzle=Path(args.puzzle); seed=Path(args.seed); workers=max(1,min(8,args.workers))
    state_path=root/'state-v7.json'
    attempted=set((root/'attempted.txt').read_text().split()) if (root/'attempted.txt').exists() else set()
    expanded=set((root/'expanded.txt').read_text().split()) if (root/'expanded.txt').exists() else set()
    retryable=set((root/'retryable.txt').read_text().split()) if (root/'retryable.txt').exists() else set()
    submit_counts=Counter(); hall={}; history=[]; cumulative_tested=0; cumulative_valid=0; cumulative_timeouts=0; cumulative_retries=0

    def add_existing(path, kind='resume', generation=0, metrics=None):
        if not path.exists(): return
        mid=mechanical_id(path); dst=archive/f'{mid}.solution'
        if not dst.exists(): shutil.copy2(path,dst)
        hall[mid]={'path':str(dst),'metrics':metrics or {},'kind':kind,'generation':generation,'mechanicalId':mid,'translationClass':translation_class_id(path),'sha256':raw_id(path)}

    if state_path.exists():
        old=json.loads(state_path.read_text())
        cumulative_tested=int(old.get('tested',0)); cumulative_valid=int(old.get('valid',0)); cumulative_timeouts=int(old.get('timeouts',0)); cumulative_retries=int(old.get('retries',0)); history=list(old.get('history') or [])
        for rec in old.get('hall') or []:
            p=archive/f"{rec['mechanicalId']}.solution"
            if p.exists():
                x=dict(rec); x['path']=str(p); hall[x['mechanicalId']]=x
    else:
        sv=validate(args.validator_url,puzzle,seed)
        if not sv.get('valid'): raise SystemExit('invalid seed')
        add_existing(seed,'seed',0,sv.get('metrics') or {}); cumulative_valid=1
        for rank in range(1,4):
            p=root/f'top-{rank}.solution'
            if p.exists():
                v=validate(args.validator_url,puzzle,p)
                if v.get('valid'): add_existing(p,'imported-top',0,v.get('metrics') or {})

    # Imported tops are intentionally re-expanded under the broader current generator;
    # attempted identity still prevents revalidation of old neighbors.
    for mid in list(hall): expanded.discard(mid)
    attempted.update(hall)

    def ranked(): return sorted(hall.values(), key=lambda x:(score(x.get('metrics') or {}),-int(x.get('generation',0)),x['mechanicalId']))
    def frontier(): return [x for x in ranked() if x['mechanicalId'] not in expanded]
    def best_cycles(): return min((score(x.get('metrics') or {})[0] for x in hall.values()), default=10**9)
    def choose(fr,g):
        if not fr:return []
        picks=[]; seen=set()
        def add(x):
            if x and x['mechanicalId'] not in seen: seen.add(x['mechanicalId']); picks.append(x)
        add(fr[0]); add(max(fr,key=lambda x:int(x.get('generation',0))))
        kinds=Counter(hall[m].get('kind','') for m in expanded if m in hall)
        add(min(fr,key=lambda x:(kinds[x.get('kind','')],-int(x.get('generation',0)),score(x.get('metrics') or {}))))
        step=max(1,len(fr)//7); add(fr[(g*step)%len(fr)])
        return picks[:4]

    def save(gen,state):
        recs=[]
        for x in hall.values():
            recs.append({k:x.get(k) for k in ('metrics','kind','generation','mechanicalId','translationClass','sha256')})
        payload={'schemaVersion':7,'state':state,'generation':gen,'bestCycles':best_cycles(),'tested':cumulative_tested,'valid':cumulative_valid,'timeouts':cumulative_timeouts,'retries':cumulative_retries,'attemptedMechanisms':len(attempted),'validMechanisms':len(hall),'expandedParents':len(expanded),'frontier':len(frontier()),'retryable':len(retryable),'history':history[-200:],'hall':recs}
        state_path.write_text(json.dumps(payload,indent=2)); (root/'checkpoint.json').write_text(json.dumps(payload,indent=2))
        (root/'attempted.txt').write_text('\n'.join(sorted(attempted))+'\n'); (root/'expanded.txt').write_text('\n'.join(sorted(expanded))+'\n'); (root/'retryable.txt').write_text('\n'.join(sorted(retryable))+'\n')
        for i,x in enumerate(ranked()[:3],1): shutil.copy2(x['path'],root/f'top-{i}.solution')

    start_gen=(history[-1].get('generation',0)+1) if history else 1
    final_state='running'
    for gen in range(start_gen,start_gen+args.generations):
        fr=frontier()
        if not fr: final_state='exhausted'; save(gen,final_state); break
        parents=choose(fr,gen); gen_dir=root/f'generation-{gen:04d}'; shutil.rmtree(gen_dir,ignore_errors=True); gen_dir.mkdir()
        candidates={}; seen=set(); tclasses=set(); generated=dupwithin=repeatprior=retries_gen=0; serial=0
        for pi,parent in enumerate(parents):
            fixture=gen_dir/f'p{pi}.b64'; fixture.write_text(base64.b64encode(Path(parent['path']).read_bytes()).decode())
            out=gen_dir/f'p{pi}-out'; subprocess.run(['python','tools/search_aqueous_structural.py','--fixture',str(fixture),'--out',str(out)],check=True)
            man=json.loads((out/'manifest.json').read_text())
            for meta in man.get('variants',[]):
                generated+=1; src=out/meta['file']; mid=mechanical_id(src); tid=translation_class_id(src); tclasses.add(tid)
                if mid in seen: dupwithin+=1; continue
                seen.add(mid); is_retry=mid in retryable
                if mid in attempted and not is_retry: repeatprior+=1; continue
                if is_retry: retries_gen+=1
                dst=gen_dir/f'v-{serial:06d}.solution'; serial+=1; shutil.copy2(src,dst)
                candidates[str(dst)]={**meta,'mechanicalId':mid,'translationClass':tid,'isRetry':is_retry,'parentMechanicalId':parent['mechanicalId']}
        tested=validc=timeouts=0; aborted=False; started=time.monotonic(); last=started
        names=iter(candidates.items()); active={}; pool=ThreadPoolExecutor(max_workers=workers)
        def submit_one():
            nonlocal cumulative_retries
            try:path,meta=next(names)
            except StopIteration:return False
            mid=meta['mechanicalId']
            if meta['isRetry']: retryable.discard(mid); cumulative_retries+=1
            attempted.add(mid); submit_counts[mid]+=1
            active[pool.submit(validate,args.validator_url,puzzle,Path(path))]=(path,meta); return True
        for _ in range(min(workers,len(candidates))): submit_one()
        while active:
            done,_=wait(set(active),timeout=1,return_when=FIRST_COMPLETED); now=time.monotonic()
            for fut in done:
                path,meta=active.pop(fut); tested+=1; cumulative_tested+=1; last=now
                try:v=fut.result()
                except Exception:v={'valid':False}
                if v.get('valid'):
                    validc+=1; cumulative_valid+=1; mid=meta['mechanicalId']; dst=archive/f'{mid}.solution'
                    if not dst.exists(): shutil.copy2(path,dst)
                    hall[mid]={**meta,'path':str(dst),'metrics':v.get('metrics') or {},'kind':meta.get('kind','candidate'),'generation':gen,'sha256':raw_id(Path(path))}
                    if int((v.get('metrics') or {}).get('cycles',999999))<=args.target_cycles:
                        final_state='target_reached'; save(gen,final_state); pool.shutdown(wait=False,cancel_futures=True); print('TARGET REACHED'); return 0
                submit_one()
            if active and ((now-last)>=args.watchdog_seconds or (now-started)>=args.generation_seconds):
                aborted=True; abandoned=list(active.values()); timeouts+=len(abandoned); cumulative_timeouts+=len(abandoned)
                for _,meta in abandoned:
                    mid=meta['mechanicalId']
                    if submit_counts[mid]<2: retryable.add(mid)
                for f in active:f.cancel()
                active.clear(); break
        pool.shutdown(wait=False,cancel_futures=True)
        if not aborted: expanded.update(p['mechanicalId'] for p in parents)
        history.append({'generation':gen,'bestCycles':best_cycles(),'tested':tested,'valid':validc,'new':len(candidates)-retries_gen,'repeatPrior':repeatprior,'duplicateWithin':dupwithin,'translationClasses':len(tclasses),'attemptedMechanisms':len(attempted),'validMechanisms':len(hall),'expandedParents':len(expanded),'frontier':len(frontier()),'timeouts':timeouts,'retries':retries_gen,'aborted':aborted})
        save(gen,'running')
        print('DIVERSITY',json.dumps(history[-1],sort_keys=True),flush=True)
    save(history[-1]['generation'] if history else 0,final_state)
    (root/'results.json').write_text(state_path.read_text())
    return 0

if __name__=='__main__': raise SystemExit(main())
