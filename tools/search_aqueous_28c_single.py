from __future__ import annotations

import argparse
import base64
import copy
import json
from itertools import combinations
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes

DIRECTIONS = ((1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1))


def load_reference(path: Path) -> dict:
    raw = base64.b64decode(path.read_text().strip())
    return parse_solution_bytes(raw, source_name="aqueous-dagger-28c-single-reference.solution")


def clean(solution: dict, name: str) -> dict:
    c = copy.deepcopy(solution)
    c["metrics"] = {}
    c["unknownMetrics"] = []
    c["name"] = name
    return c


def legal_program(program: list[dict]) -> bool:
    cycles = [int(x.get("cycle", 0)) for x in program]
    return min(cycles, default=0) >= 0 and len(cycles) == len(set(cycles))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger-28c-single-reference.solution.b64")
    ap.add_argument("--out", default="reports/aqueous-28c-single-search")
    args = ap.parse_args()

    ref = load_reference(Path(args.fixture))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    variants: list[tuple[dict,dict]] = []
    seen: set[bytes] = set()

    arm_indices = [i for i,p in enumerate(ref["parts"]) if str(p.get("type","")).startswith("arm") or p.get("type") in {"piston","baron"}]
    functional_indices = [i for i,p in enumerate(ref["parts"]) if p.get("type") in {"bonder","bonder-speed","out-std"}]

    def add(c: dict|None, meta: dict):
        if c is None: return
        b = write_solution_bytes(c)
        if b in seen: return
        seen.add(b); variants.append((c,meta))

    # Timing compression: one instruction, suffix, and paired pulls.
    legal_ticks: list[tuple[int,int]] = []
    for pi in arm_indices:
        prog = ref["parts"][pi].get("program") or []
        for ii,item in enumerate(prog):
            if int(item.get("cycle",0)) <= 0: continue
            c = clean(ref, f"single28 tick p{pi} i{ii}")
            c["parts"][pi]["program"][ii]["cycle"] -= 1
            if legal_program(c["parts"][pi]["program"]):
                legal_ticks.append((pi,ii)); add(c,{"kind":"tick-earlier","part":pi,"instruction":ii})
        for start in range(len(prog)):
            c = clean(ref, f"single28 suffix p{pi} s{start}")
            for item in c["parts"][pi]["program"][start:]: item["cycle"] -= 1
            if legal_program(c["parts"][pi]["program"]): add(c,{"kind":"suffix-earlier","part":pi,"start":start})

    for a,b in combinations(legal_ticks,2):
        c = clean(ref,"single28 paired timing")
        ok = True
        for pi,ii in (a,b):
            c["parts"][pi]["program"][ii]["cycle"] -= 1
            ok &= legal_program(c["parts"][pi]["program"])
        if ok: add(c,{"kind":"paired-ticks","mutations":[list(a),list(b)]})

    # Rotate/pivot substitutions, alone and with one timing pull.
    repl={"rotate_cw":"pivot_cw","rotate_ccw":"pivot_ccw","pivot_cw":"rotate_cw","pivot_ccw":"rotate_ccw"}
    substitutions=[]
    for pi in arm_indices:
        for ii,item in enumerate(ref["parts"][pi].get("program") or []):
            old=str(item.get("instruction") or "")
            if old in repl:
                substitutions.append((pi,ii,old,repl[old]))
                c=clean(ref,f"single28 {old}->{repl[old]}")
                c["parts"][pi]["program"][ii]["instruction"]=repl[old]
                add(c,{"kind":"rotate-pivot","part":pi,"instruction":ii,"from":old,"to":repl[old]})
    for pi,ii,old,new in substitutions:
        for tpi,tii in legal_ticks:
            if tpi != pi: continue
            c=clean(ref,"single28 timing+pivot")
            c["parts"][pi]["program"][ii]["instruction"]=new
            c["parts"][tpi]["program"][tii]["cycle"] -= 1
            if legal_program(c["parts"][pi]["program"]): add(c,{"kind":"timing-plus-pivot","part":pi,"action":ii,"timing":tii})

    # Functional geometry: move/rotate each bonder and output by one hex.
    for pi in functional_indices:
        p=ref["parts"][pi]
        pos=tuple(p.get("position") or (0,0))
        for rot in range(6):
            c=clean(ref,f"single28 rotate functional p{pi}")
            c["parts"][pi]["rotation"]=rot
            add(c,{"kind":"functional-rotate","part":pi,"type":p.get("type"),"rotation":rot})
        for dq,dr in DIRECTIONS:
            for rot in range(6):
                c=clean(ref,f"single28 move functional p{pi}")
                c["parts"][pi]["position"]=[pos[0]+dq,pos[1]+dr]
                c["parts"][pi]["rotation"]=rot
                add(c,{"kind":"functional-move","part":pi,"type":p.get("type"),"position":[pos[0]+dq,pos[1]+dr],"rotation":rot})

    # Add an extra bonder near each existing bonder: intended to enable before/after-motion double bonding.
    bonders=[p for p in ref["parts"] if p.get("type")=="bonder"]
    for anchor in bonders:
        q,r=anchor.get("position") or (0,0)
        for dq,dr in DIRECTIONS:
            for rot in range(6):
                c=clean(ref,"single28 add adjacent bonder")
                c["parts"].append({"id":f"codex-extra-bonder-{q+dq}-{r+dr}-{rot}","type":"bonder","enabled":True,"position":[q+dq,r+dr],"length":1,"rotation":rot,"which":0,"armNumber":0,"program":[]})
                add(c,{"kind":"add-adjacent-bonder","position":[q+dq,r+dr],"rotation":rot})

    manifest=[]
    for n,(c,meta) in enumerate(variants):
        fn=f"variant-{n:05d}.solution"
        (out/fn).write_bytes(write_solution_bytes(c)); manifest.append({"file":fn,**meta})
    (out/"manifest.json").write_text(json.dumps({"candidateCount":len(manifest),"armIndices":arm_indices,"functionalIndices":functional_indices,"variants":manifest},indent=2))
    print(json.dumps({"candidateCount":len(manifest),"armIndices":arm_indices,"functionalIndices":functional_indices}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
