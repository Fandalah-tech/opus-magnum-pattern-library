from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle, parse_solution


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def probe(
    puzzle_path: Path,
    solution_path: Path,
    *,
    element: str,
    max_cycles: int = 500,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(solution_path)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=max_cycles))

    by_atom: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    cycle_counts: list[dict[str, Any]] = []
    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        matches = []
        for atom in (frame.get("world") or {}).get("atoms", []) or []:
            if str(atom.get("element") or "") != str(element):
                continue
            atom_id = str(atom.get("id") or "")
            record = {
                "cycle": cycle,
                "position": list(_position(atom.get("position"))),
                "heldBy": sorted(str(value) for value in atom.get("heldBy", []) or []),
            }
            by_atom[atom_id].append(record)
            matches.append({"atomId": atom_id, **record})
        if matches:
            cycle_counts.append({
                "cycle": cycle,
                "count": len(matches),
                "unheldCount": sum(not item["heldBy"] for item in matches),
                "atoms": matches,
            })

    atoms = []
    for atom_id, observations in sorted(by_atom.items()):
        positions = []
        held_cycles = []
        unheld_cycles = []
        for item in observations:
            if item["position"] not in positions:
                positions.append(item["position"])
            if item["heldBy"]:
                held_cycles.append(item["cycle"])
            else:
                unheld_cycles.append(item["cycle"])
        atoms.append({
            "atomId": atom_id,
            "firstCycle": observations[0]["cycle"],
            "lastCycle": observations[-1]["cycle"],
            "observationCount": len(observations),
            "positions": positions,
            "heldCycleCount": len(held_cycles),
            "unheldCycleCount": len(unheld_cycles),
            "firstHeldCycle": held_cycles[0] if held_cycles else None,
            "lastHeldCycle": held_cycles[-1] if held_cycles else None,
            "firstUnheldCycle": unheld_cycles[0] if unheld_cycles else None,
            "lastUnheldCycle": unheld_cycles[-1] if unheld_cycles else None,
            "observations": observations,
        })

    max_simultaneous = max((item["count"] for item in cycle_counts), default=0)
    max_unheld = max((item["unheldCount"] for item in cycle_counts), default=0)
    first_two_cycle = next((item["cycle"] for item in cycle_counts if item["count"] >= 2), None)
    first_two_unheld_cycle = next((item["cycle"] for item in cycle_counts if item["unheldCount"] >= 2), None)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-intermediate-lifetime-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {"element": element, "maxCycles": max_cycles},
        "summary": {
            "element": element,
            "atomCount": len(atoms),
            "observedCycleCount": len(cycle_counts),
            "maxSimultaneousCount": max_simultaneous,
            "maxSimultaneousUnheldCount": max_unheld,
            "firstTwoAtomCycle": first_two_cycle,
            "firstTwoUnheldCycle": first_two_unheld_cycle,
            "completedCycles": int((replay.get("summary") or {}).get("completedCycles") or 0),
            "terminatedWithError": bool((replay.get("summary") or {}).get("terminatedWithError")),
            "targetSolutionBytesUsed": 0,
        },
        "atoms": atoms,
        "cycleCounts": cycle_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace generated intermediate atom lifetimes without target solution evidence.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--element", required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.solution,
        element=args.element,
        max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "summary": report["summary"],
        "atoms": [
            {key: item[key] for key in (
                "atomId", "firstCycle", "lastCycle", "heldCycleCount", "unheldCycleCount",
                "firstHeldCycle", "lastHeldCycle", "firstUnheldCycle", "lastUnheldCycle",
            )}
            for item in report["atoms"]
        ],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
