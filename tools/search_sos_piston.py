from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.opus_parser import parse_solution, write_solution

BASE = ROOT / "reports/generated/sos-salt-of-saturn/SOS_Salt_of_Saturn_by_Vinegar (1)-auto.solution"
PUZZLE = ROOT.parent / "upload/SOS_Salt_of_Saturn_by_Vinegar (1).puzzle"
OMSIM = Path("/tmp/omsim-src/omsim")
OUT = ROOT / "reports/generated/sos-salt-of-saturn/blind-optimization"
TMP = OUT / "piston-candidate.solution"


def evaluate(model: dict) -> dict | None:
    model = deepcopy(model); model["metrics"] = {}; model["unknownMetrics"] = []
    write_solution(model, TMP)
    try:
        p = subprocess.run([str(OMSIM), "-p", str(PUZZLE), str(TMP)], capture_output=True, text=True, timeout=.06)
    except subprocess.TimeoutExpired:
        return None
    m = re.search(r"(\d+)g/(\d+)i@\d+ (\d+)c/(\d+)a@V", p.stdout + p.stderr)
    if p.returncode or not m: return None
    c, i, y, a = map(int, m.groups())
    return {"cost": c, "instructions": i, "cycles": y, "area": a}


def main() -> None:
    base = parse_solution(BASE)
    valid = []
    dirs = [(0,0),(1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1)]
    # Remove rail part 5, convert transport arm part 4 to a piston, and map
    # the two-cell rail journey to one extension/retraction pair.
    for keep_plus, keep_minus, length, rotation, delta in itertools.product((2,3), (5,6), (1,2,3), range(6), dirs):
        candidate = deepcopy(base)
        candidate["parts"].pop(5)
        arm = candidate["parts"][4]
        arm["type"] = "piston"
        arm["length"] = length
        arm["rotation"] = rotation
        arm["position"] = [arm["position"][0] + delta[0], arm["position"][1] + delta[1]]
        program = []
        for item in arm["program"]:
            cycle = int(item["cycle"])
            instruction = item["instruction"]
            if instruction == "track_plus":
                if cycle != keep_plus: continue
                instruction = "extend"
            elif instruction == "track_minus":
                if cycle != keep_minus: continue
                instruction = "retract"
            program.append({**item, "instruction": instruction})
        arm["program"] = program
        metrics = evaluate(candidate)
        if metrics:
            valid.append({"keepPlus": keep_plus, "keepMinus": keep_minus, "length": length,
                          "rotation": rotation, "delta": delta, "metrics": metrics, "solution": candidate})
    summary = {"validCandidates": len(valid)}
    if valid:
        best = min(valid, key=lambda r: (r["metrics"]["cost"], r["metrics"]["area"], r["metrics"]["cycles"]))
        path = OUT / "best-cost-piston.solution"
        write_solution(best.pop("solution"), path)
        summary["best"] = best | {"path": str(path)}
    (OUT / "piston-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__": main()
