from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")
WATCH = ("part-9-spawn-0-atom-0", "part-4-spawn-0-atom-0")


def fmt_position(simulator: Simulator, atom_id: str) -> str:
    atom = simulator.world.atoms.get(atom_id)
    if atom is None:
        return "missing"
    holders = "+".join(sorted(atom.held_by)) or "-"
    return f"{atom.position[0]},{atom.position[1]}:{atom.element}:{holders}"


def fmt_arm(simulator: Simulator, arm_id: str) -> str:
    arm = simulator.arms[arm_id]
    held = "+".join(sorted(set(arm.held_atoms.values()))) or "-"
    tip = arm.tip()
    return (
        f"o={arm.origin[0]},{arm.origin[1]};r={arm.rotation};l={arm.length};"
        f"tip={tip[0]},{tip[1]};t={arm.track_index};held={held}"
    )


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    print("cycle|instructions|water0|salt0|p8|p10|events")
    for row in timeline.get("cycles", []):
        if simulator.world.cycle >= 70:
            break
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
            if event.get("instruction")
        }
        simulator.step(instructions)
        relevant = any(part in instructions for part in ("part-8", "part-10", "part-1"))
        meaningful = [event.kind for event in simulator.world.events if event.kind != "arm-instruction"]
        if not relevant and not meaningful:
            continue
        instruction_text = ",".join(f"{part}:{instruction}" for part, instruction in sorted(instructions.items()))
        print("|".join((
            str(simulator.world.cycle),
            instruction_text,
            fmt_position(simulator, WATCH[0]),
            fmt_position(simulator, WATCH[1]),
            fmt_arm(simulator, "part-8"),
            fmt_arm(simulator, "part-10"),
            ",".join(meaningful),
        )))


if __name__ == "__main__":
    main()
