from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.opus_parser import parse_solution, write_solution


def score(omsim: Path, puzzle: Path, solution: dict, path: Path) -> dict | None:
    candidate = deepcopy(solution)
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    write_solution(candidate, path)
    try:
        run = subprocess.run(
            [str(omsim), "--puzzle-file", str(puzzle), str(path)],
            capture_output=True,
            text=True,
            timeout=0.06,
        )
    except subprocess.TimeoutExpired:
        return None
    text = (run.stdout + run.stderr).strip()
    if run.returncode != 0 or "@V" not in text:
        return None
    # 145g/19i@0 95c/84a@V
    left, right = text.split(" ", 1)
    cost, instructions = left.split("@", 1)[0].split("/")
    cycles, area = right.split("@", 1)[0].split("/")
    return {
        "cost": int(cost[:-1]),
        "instructions": int(instructions[:-1]),
        "cycles": int(cycles[:-1]),
        "area": int(area[:-1]),
        "raw": text,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("solution", type=Path)
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = parse_solution(args.solution)
    scratch = args.output.with_suffix(".candidate.solution")
    results: list[dict] = []

    arms = [part for part in base["parts"] if part["type"].startswith("arm")]
    # Scan one arm at a time first; this keeps the oracle search bounded while
    # still exposing idle prefixes and harmless global phase changes.
    shift_vectors = {(0,) * len(arms)}
    for arm_index, arm in enumerate(arms):
        cycles = [int(item["cycle"]) for item in arm["program"]]
        minimum = min(cycles) if cycles else 0
        for shift in range(-minimum, 9):
            vector = [0] * len(arms)
            vector[arm_index] = shift
            shift_vectors.add(tuple(vector))
    last_index = len(arms) - 1
    last_minimum = min(int(item["cycle"]) for item in arms[last_index]["program"])
    for arm_index, arm in enumerate(arms[:-1]):
        minimum = min(int(item["cycle"]) for item in arm["program"])
        for shift in range(-minimum, 9):
            for last_shift in range(-last_minimum, 1):
                vector = [0] * len(arms)
                vector[arm_index] = shift
                vector[last_index] = last_shift
                shift_vectors.add(tuple(vector))
    for shifts in sorted(shift_vectors):
        candidate = deepcopy(base)
        candidate_arms = [part for part in candidate["parts"] if part["type"].startswith("arm")]
        for arm, shift in zip(candidate_arms, shifts):
            for item in arm["program"]:
                item["cycle"] = int(item["cycle"]) + shift
        metrics = score(args.omsim, args.puzzle, candidate, scratch)
        if metrics:
            results.append({"kind": "phase", "shifts": shifts, "metrics": metrics, "solution": candidate})

    # Greedy deletion from the best phase candidates. Repeating from only the
    # accepted child prevents an exponential enumeration of equivalent tapes.
    seeds = sorted(results, key=lambda record: (record["metrics"]["cycles"], record["metrics"]["instructions"]))[:5]
    for seed in seeds:
        current = seed
        while True:
            children = []
            candidate = current["solution"]
            for part_index, part in enumerate(candidate["parts"]):
                if not part["type"].startswith("arm"):
                    continue
                for instruction_index in range(len(part["program"])):
                    child = deepcopy(candidate)
                    removed = child["parts"][part_index]["program"].pop(instruction_index)
                    metrics = score(args.omsim, args.puzzle, child, scratch)
                    if metrics:
                        children.append({"kind": "remove", "parent": seed.get("shifts"), "removed": [part_index, removed], "metrics": metrics, "solution": child})
            if not children:
                break
            current = min(children, key=lambda record: (record["metrics"]["instructions"], record["metrics"]["cycles"], record["metrics"]["area"]))
            results.extend(children)

    def keys(record: dict) -> dict:
        m = record["metrics"]
        return {
            "cost": (m["cost"], m["area"], m["cycles"], m["instructions"]),
            "area": (m["area"], m["cost"], m["cycles"], m["instructions"]),
            "cycles": (m["cycles"], m["cost"], m["area"], m["instructions"]),
            "instructions": (m["instructions"], m["cost"], m["area"], m["cycles"]),
            "costarea": (m["cost"] * m["area"], m["cost"], m["area"], m["cycles"], m["instructions"]),
            "sum4": (sum(m[k] for k in ("cost", "cycles", "area", "instructions")), m["cost"], m["cycles"], m["area"], m["instructions"]),
        }

    args.output.mkdir(parents=True, exist_ok=True)
    summary = {}
    for metric in ("cost", "area", "cycles", "instructions", "costarea", "sum4"):
        best = min(results, key=lambda record: keys(record)[metric])
        destination = args.output / f"best-{metric}.solution"
        write_solution(best["solution"], destination)
        summary[metric] = {"metrics": best["metrics"], "key": keys(best)[metric], "path": str(destination), "shifts": best.get("shifts"), "kind": best["kind"]}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
