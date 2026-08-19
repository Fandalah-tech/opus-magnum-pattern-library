from __future__ import annotations

import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.opus_parser import parse_solution, write_solution

PUZZLE = ROOT.parent / "upload" / "SOS_Salt_of_Saturn_by_Vinegar (1).puzzle"
OMSIM = Path("/tmp/omsim-src/omsim")
BASE = ROOT / "reports/generated/sos-salt-of-saturn/SOS_Salt_of_Saturn_by_Vinegar (1)-auto.solution"
OUT = ROOT / "reports/generated/sos-salt-of-saturn/blind-optimization"
TMP = OUT / "geometry-candidate.solution"


def evaluate(solution: dict) -> dict | None:
    model = deepcopy(solution)
    model["metrics"] = {}
    model["unknownMetrics"] = []
    write_solution(model, TMP)
    try:
        run = subprocess.run(
            [str(OMSIM), "--puzzle-file", str(PUZZLE), "--output-intervals",
             "--metric", "cost", "--metric", "instructions", "--metric", "cycles", "--metric", "area", str(TMP)],
            capture_output=True, text=True, timeout=.25,
        )
    except subprocess.TimeoutExpired:
        return None
    text = (run.stdout + run.stderr).strip()
    match = re.search(r"cost: (\d+)\ninstructions: (\d+)\ncycles: (\d+)\narea: (\d+)", text)
    if run.returncode or not match:
        return None
    interval = re.search(r"output intervals:.*\[(\d+)\]", text)
    cost, instructions, cycles, area = map(int, match.groups())
    return {"cost": cost, "instructions": instructions, "cycles": cycles, "area": area,
            "rate": int(interval.group(1)) if interval else None, "raw": text}


def translate(solution: dict, indexes: set[int], dq: int, dr: int) -> dict:
    result = deepcopy(solution)
    for index in indexes:
        part = result["parts"][index]
        part["position"] = [part["position"][0] + dq, part["position"][1] + dr]
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = parse_solution(BASE)
    records = []
    groups = {
        "fire-line": {6, 7, 8, 11, 12},
        "lead-salt-line": {0, 1, 2, 3, 4, 5, 9, 10},
        "fire-source": {6, 7, 8},
        "fire-output": {11, 12},
        "lead-source": {0, 1, 2, 3, 4, 5},
        "lead-output": {9, 10},
    }
    for name, indexes in groups.items():
        for dq in range(-8, 9):
            for dr in range(-8, 9):
                if dq == dr == 0:
                    continue
                candidate = translate(base, indexes, dq, dr)
                metrics = evaluate(candidate)
                if metrics:
                    records.append({"kind": "translate", "group": name, "offset": [dq, dr], "metrics": metrics, "solution": candidate})

    # Safe structural probes: delete a part, alter arm length/type, shorten rails.
    for index, part in enumerate(base["parts"]):
        child = deepcopy(base)
        child["parts"].pop(index)
        metrics = evaluate(child)
        if metrics:
            records.append({"kind": "delete", "part": index, "metrics": metrics, "solution": child})
        if part["type"].startswith("arm"):
            for arm_type in ("arm1", "arm2", "arm3", "arm6", "piston"):
                for length in range(1, 4):
                    child = deepcopy(base)
                    child["parts"][index]["type"] = arm_type
                    child["parts"][index]["length"] = length
                    metrics = evaluate(child)
                    if metrics:
                        records.append({"kind": "arm", "part": index, "type": arm_type, "length": length, "metrics": metrics, "solution": child})

    records.append({"kind": "base", "metrics": evaluate(base), "solution": base})
    objectives = {
        "cost": lambda m: (m["cost"], m["area"], m["cycles"]),
        "area": lambda m: (m["area"], m["cost"]),
        "cycles": lambda m: (m["cycles"],),
        "instructions": lambda m: (m["instructions"], m["cost"]),
        "rate": lambda m: (m["rate"] if m["rate"] is not None else 10**9,),
        "sum4": lambda m: (m["cost"] + m["cycles"] + m["area"] + m["instructions"],),
    }
    summary = {}
    for name, key in objectives.items():
        best = min(records, key=lambda r: key(r["metrics"]))
        path = OUT / f"geometry-best-{name}.solution"
        write_solution(best["solution"], path)
        summary[name] = {k: v for k, v in best.items() if k != "solution"} | {"path": str(path), "objective": key(best["metrics"])}
    (OUT / "geometry-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
