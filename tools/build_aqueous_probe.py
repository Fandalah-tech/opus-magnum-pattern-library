from __future__ import annotations

import argparse
import base64
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle_bytes, write_solution


def _program(entries):
    return [{"cycle": cycle, "instruction": instruction} for cycle, instruction in entries]


def _part(part_id, part_type, position, *, rotation=0, length=1, which=0, program=None):
    return {
        "id": part_id,
        "type": part_type,
        "enabled": True,
        "position": list(position),
        "rotation": rotation,
        "length": length,
        "which": which,
        "armNumber": 0,
        "program": list(program or []),
    }


def build_probe_solution() -> dict:
    return {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {"name": None, "generator": "opus_solver/aqueous-probe-v1"},
        "puzzleFile": "weeklies2026_aqueous-dagger",
        "name": "Codex Aqueous Dagger probe",
        "metrics": {},
        "unknownMetrics": [],
        "parts": [
            _part("out", "out-std", (1, 0), rotation=0, which=0),
            _part("a-salt-arm", "arm1", (-2, 0), rotation=4, length=2,
                  program=_program([(0, "grab"), (1, "rotate_ccw"), (2, "rotate_ccw"),
                                    (3, "drop"), (4, "rotate_cw"), (5, "rotate_cw")])),
            _part("b-water-arm", "arm1", (2, -2), rotation=0,
                  program=_program([(0, "grab"), (3, "rotate_ccw"), (4, "drop"), (5, "rotate_cw")])),
            # Length two keeps the arm base clear of both the incoming water
            # triangle and the completed product. The explicit drop at cycle 6
            # releases the completed molecule before the next 7-cycle feed.
            _part("z-pivot-arm", "arm1", (3, 0), rotation=3, length=2,
                  program=_program([(4, "grab"), (5, "pivot_ccw"), (6, "drop")])),
            _part("salt-input", "input", (-2, -2), rotation=3, which=0),
            _part("water-input", "input", (3, -2), rotation=4, which=1),
            _part("calc-0", "glyph-calcification", (0, -2)),
            _part("calc-1", "glyph-calcification", (1, -2)),
            _part("calc-2", "glyph-calcification", (0, -1)),
            _part("bond", "bonder", (0, 0), rotation=0),
        ],
        "trailingBytes": 0,
    }


def load_official_puzzle(fixture: Path) -> tuple[bytes, dict]:
    data = base64.b64decode(fixture.read_text().strip())
    return data, parse_puzzle_bytes(data, source_name="weeklies2026_aqueous-dagger.puzzle")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger.puzzle.b64")
    parser.add_argument("--puzzle-out", default="reports/aqueous-dagger.puzzle")
    parser.add_argument("--solution-out", default="reports/aqueous-dagger-probe.solution")
    args = parser.parse_args()

    puzzle_bytes, puzzle = load_official_puzzle(Path(args.fixture))
    solution = build_probe_solution()
    Path(args.puzzle_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.puzzle_out).write_bytes(puzzle_bytes)
    write_solution(solution, args.solution_out)

    timeline = build_program_timeline(solution, max_cycles=43)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(timeline)
    if replay["summary"]["terminatedWithError"]:
        raise SystemExit("internal engine rejected Aqueous probe")
    if simulator.delivered_products != {"out": 6}:
        raise SystemExit(f"expected six products, got {simulator.delivered_products}")
    print(
        f"internal-engine products=6 period={timeline['summary']['globalPeriod']} "
        f"completedCycles={replay['summary']['completedCycles']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
