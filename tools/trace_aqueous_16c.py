from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle_bytes, parse_solution_bytes


def load_b64(path: str) -> bytes:
    return base64.b64decode(Path(path).read_text().strip())


def _right_atoms(frame: dict) -> list[dict]:
    atoms = (frame.get("world") or {}).get("atoms") or []
    # The third right-hand product is assembled from right input spawns 4 and 5.
    prefixes = ("part-14-spawn-4-", "part-14-spawn-5-")
    return [atom for atom in atoms if str(atom.get("id") or "").startswith(prefixes)]


def _interesting_arms(frame: dict) -> list[dict]:
    keep = {"part-11", "part-12", "part-15", "part-16"}
    return [arm for arm in frame.get("arms", []) if arm.get("id") in keep]


def main() -> int:
    puzzle = parse_puzzle_bytes(
        load_b64("fixtures/weeklies2026/aqueous-dagger.puzzle.b64"),
        source_name="weeklies2026_aqueous-dagger.puzzle",
    )
    solution = parse_solution_bytes(
        load_b64("fixtures/weeklies2026/aqueous-dagger-16c-reference.solution.b64"),
        source_name="aqueous-16c.solution",
    )
    timeline = build_program_timeline(solution, max_cycles=20)
    simulator = Simulator.from_models(puzzle, solution)

    print("GLOBAL PERIOD", timeline["summary"]["globalPeriod"])
    for arm in timeline["arms"]:
        print("ARM", json.dumps({
            "id": arm["partId"], "number": arm["armNumber"],
            "first": arm["firstActionCycle"], "period": arm["period"],
        }, sort_keys=True))

    previous = dict(simulator.delivered_products)
    for cycle in timeline["cycles"]:
        instructions = {
            event["partId"]: event["instruction"]
            for event in cycle["events"]
        }
        simulator.step(instructions)
        current = dict(simulator.delivered_products)
        changed = current != previous
        frame = simulator.frames[-1]
        noteworthy = [
            event for event in frame.get("events", [])
            if event.get("kind") in {"product-delivered", "simulation-error", "bond-created", "atom-transmuted"}
        ]
        payload = {
            "instructions": instructions,
            "delivered": current,
            "events": noteworthy,
        }
        if 11 <= cycle["cycle"] <= 14:
            payload["rightAtoms"] = _right_atoms(frame)
            payload["rightArms"] = _interesting_arms(frame)
        if changed or noteworthy or cycle["cycle"] >= 11:
            print("CYCLE", cycle["cycle"], json.dumps(payload, sort_keys=True, default=str))
        previous = current
        if frame.get("terminatedWithError"):
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
