from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packages.opus_parser import write_solution_bytes
from tools.validate_aqueous_offsets import validate

ACTIONS = ("grab","drop","rotate_cw","rotate_ccw","pivot_cw","pivot_ccw","extend","retract")


def load_seed(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def arm_by_number(parts, n):
    for i,p in enumerate(parts):
        if p.get("armNumber") == n and p.get("type") in ("arm1","piston","arm2","arm3","arm6"):
            return i
    raise RuntimeError(f"arm {n} not found")


def set_c7_mode(program, action, mode):
    out=[x for x in program if not (x.get("cycle")==7 and x.get("instruction")==action)]
    if mode=="c6":
        if any(x.get("cycle")==6 for x in out):
            return None
        out.append({"cycle":6,"instruction":action})
    return sorted(out,key=lambda x:x["cycle"])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--validator-url",required=True)
    ap.add_argument("--puzzle",required=True)
    ap.add_argument("--seed-json",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--workers",type=int,default=8)
    args=ap.parse_args()
    seed=load_seed(Path(args.seed_json))
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    a1=arm_by_number(seed["parts"],0)
    a2=arm_by_number(seed["parts"],1)
    a3=arm_by_number(seed["parts"],2)
    a4=arm_by_number(seed["parts"],3)

    arm4_programs=[[]]
    cycles=(4,5,6)
    for k in (1,2,3):
        for chosen in itertools.combinations(cycles,k):
            for acts in itertools.product(ACTIONS,repeat=k):
                arm4_programs.append([{"cycle":c,"instruction":a} for c,a in zip(chosen,acts)])

    jobs=[]; serial=0
    for m1,m2,m3 in itertools.product(("remove","c6"), repeat=3):
        p1=set_c7_mode(seed["parts"][a1]["program"],"grab",m1)
        p2=set_c7_mode(seed["parts"][a2]["program"],"rotate_ccw",m2)
        p3=set_c7_mode(seed["parts"][a3]["program"],"drop",m3)
        if p1 is None or p2 is None or p3 is None:
            continue
        for p4 in arm4_programs:
            cand=json.loads(json.dumps(seed))
            cand["name"]=f"50C P7 redistribute #{serial}"
            cand["metrics"]={}
            cand["unknownMetrics"]=[]
            cand["parts"][a1]["program"]=p1
            cand["parts"][a2]["program"]=p2
            cand["parts"][a3]["program"]=p3
            cand["parts"][a4]["program"]=p4
            path=out/f"candidate-{serial:05d}.solution"
            path.write_bytes(write_solution_bytes(cand))
            jobs.append((serial,m1,m2,m3,p4,path)); serial+=1

    valid=[]; closest=[]
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,8))) as pool:
        futs={pool.submit(validate,args.validator_url,Path(args.puzzle),j[-1]):j for j in jobs}
        for n,f in enumerate(as_completed(futs),1):
            serial,m1,m2,m3,p4,path=futs[f]
            try:r=f.result()
            except Exception as e:r={"valid":False,"rawOutput":str(e)}
            rec={"serial":serial,"modes":[m1,m2,m3],"arm4":p4,"metrics":r.get("metrics"),"file":path.name,"rawOutput":r.get("rawOutput")}
            if r.get("valid"):
                valid.append(rec); print("VALID "+json.dumps(rec),flush=True)
            else:
                raw=r.get("rawOutput") or ""; cyc=-1
                import re
                m=re.search(r"cycle (\\d+)",raw)
                if m:cyc=int(m.group(1))
                closest.append((cyc,rec))
            if n%250==0 or n==len(jobs):print(f"PROGRESS {n}/{len(jobs)} valid={len(valid)}",flush=True)

    valid.sort(key=lambda x:((x.get("metrics") or {}).get("cycles",10**9),(x.get("metrics") or {}).get("cost",10**9)))
    closest.sort(key=lambda x:x[0],reverse=True)
    payload={"candidateCount":len(jobs),"validCount":len(valid),"results":valid[:50],"closestInvalid":[r for _,r in closest[:30]]}
    (out/"results.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    if valid:(out/"best.solution").write_bytes((out/valid[0]["file"]).read_bytes())
    print(json.dumps({"candidateCount":len(jobs),"validCount":len(valid),"best":valid[:10],"closest":payload["closestInvalid"][:10]}))

if __name__=="__main__":
    main()
