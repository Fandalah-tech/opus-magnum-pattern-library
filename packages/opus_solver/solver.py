from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex
from packages.opus_parser import write_solution

from .manufacturing import AtomFlow, ManufacturingPlan, build_manufacturing_plan

STANDARD_PRODUCT_TARGET = 6


class UnsupportedPuzzleError(ValueError):
    """Raised when no current solver strategy can handle the puzzle."""


class GeneratedSolutionError(RuntimeError):
    """Raised when a generated candidate fails its own engine validation."""


@dataclass(slots=True)
class SolveResult:
    puzzle_name: str
    strategy: str
    plan: ManufacturingPlan
    solution: dict[str, Any]
    validation: dict[str, Any]

    def write(self, destination: str | Path) -> Path:
        return write_solution(self.solution, destination)

    def to_dict(self, *, include_solution: bool = True) -> dict[str, Any]:
        result = {
            "puzzleName": self.puzzle_name,
            "strategy": self.strategy,
            "plan": self.plan.to_dict(),
            "validation": self.validation,
        }
        if include_solution:
            result["solution"] = self.solution
        return result


def _add(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    return first[0] + second[0], first[1] + second[1]


def _sub(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    return first[0] - second[0], first[1] - second[1]


def _transform_position(
    position: tuple[int, int],
    rotation: int,
    translation: tuple[int, int],
) -> list[int]:
    return list(_add(rotate_hex(position, rotation), translation))


def _part(
    part_id: str,
    part_type: str,
    position: tuple[int, int],
    *,
    global_rotation: int,
    translation: tuple[int, int],
    rotation: int = 0,
    length: int = 1,
    which: int = 0,
    program: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": part_id,
        "type": part_type,
        "enabled": True,
        "position": _transform_position(position, global_rotation, translation),
        "length": length,
        "rotation": (rotation + global_rotation) % 6,
        "which": which,
        "armNumber": 0,
        "program": list(program or []),
    }


def _rotation_mapping(source_delta: tuple[int, int], target_delta: tuple[int, int]) -> int:
    for rotation in range(6):
        if rotate_hex(source_delta, rotation) == target_delta:
            return rotation
    raise UnsupportedPuzzleError(
        f"Product atoms are not hex-adjacent: cannot map {source_delta} to {target_delta}"
    )


def _flow_by_transformation(plan: ManufacturingPlan, transformation: str | None) -> AtomFlow:
    matches = [flow for flow in plan.atom_flows if flow.transformation == transformation]
    if len(matches) != 1:
        raise UnsupportedPuzzleError(
            f"Strategy {plan.strategy} expected one flow with transformation {transformation!r}"
        )
    return matches[0]


def _puzzle_file_id(puzzle: dict[str, Any]) -> str:
    source_name = str((puzzle.get("source") or {}).get("name") or "")
    if source_name:
        return Path(source_name).stem
    return str(puzzle.get("id") or puzzle.get("name") or "generated-puzzle")


def _generate_bonded_pair_solution(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
) -> dict[str, Any]:
    calcified = _flow_by_transformation(plan, "calcification")
    direct = _flow_by_transformation(plan, None)

    # The pattern is expressed in its own local frame, then rotated and
    # translated as a whole. This deliberately produces a fresh layout rather
    # than replaying a campaign reference solution.
    global_rotation = 2
    translation = (4, 3)

    template_salt_position = (0, -1)
    product_delta = _sub(direct.product_position, calcified.product_position)
    output_rotation = _rotation_mapping(product_delta, (1, 0))
    transformed_salt_local = rotate_hex(calcified.product_position, output_rotation)
    output_origin = _sub(template_salt_position, transformed_salt_local)

    arm_program = [
        {"cycle": 0, "instruction": "grab"},
        {"cycle": 1, "instruction": "rotate_cw"},
        {"cycle": 2, "instruction": "rotate_cw"},
        {"cycle": 3, "instruction": "drop"},
        {"cycle": 4, "instruction": "rotate_cw"},
        {"cycle": 5, "instruction": "rotate_cw"},
        {"cycle": 6, "instruction": "grab"},
        {"cycle": 7, "instruction": "rotate_ccw"},
        {"cycle": 8, "instruction": "rotate_ccw"},
        {"cycle": 9, "instruction": "pivot_cw"},
        {"cycle": 10, "instruction": "rotate_ccw"},
        {"cycle": 11, "instruction": "reset"},
    ]

    parts = [
        _part(
            "part-0",
            "out-std",
            output_origin,
            global_rotation=global_rotation,
            translation=translation,
            rotation=output_rotation,
            which=0,
        ),
        _part(
            "part-1",
            "arm1",
            (2, -2),
            global_rotation=global_rotation,
            translation=translation,
            rotation=3,
            program=arm_program,
        ),
        _part(
            "part-2",
            "glyph-calcification",
            (1, 0),
            global_rotation=global_rotation,
            translation=translation,
        ),
        _part(
            "part-3",
            "bonder",
            (2, -1),
            global_rotation=global_rotation,
            translation=translation,
            rotation=5,
        ),
        _part(
            "part-4",
            "input",
            (3, -3),
            global_rotation=global_rotation,
            translation=translation,
            which=calcified.reagent_index,
        ),
        _part(
            "part-5",
            "input",
            (1, -2),
            global_rotation=global_rotation,
            translation=translation,
            which=direct.reagent_index,
        ),
    ]

    return {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {"name": None, "generator": "opus_solver/bonded-pair-v1"},
        "puzzleFile": _puzzle_file_id(puzzle),
        "name": "Opus Solver MVP - bonded pair v1",
        "metrics": {
            "cycles": 77,
            "cost": 40,
            "area": 9,
            "instructions": 13,
        },
        "unknownMetrics": [],
        "parts": parts,
        "trailingBytes": 0,
    }


def _first_simulation_error(replay: dict[str, Any]) -> dict[str, Any] | None:
    for frame in replay.get("frames", []):
        for event in frame.get("events", []):
            if str(event.get("kind") or "") != "simulation-error":
                continue
            return {
                "cycle": event.get("cycle", frame.get("cycle")),
                "message": str(event.get("message") or "Simulation error"),
            }
    return None


def validate_generated_solution(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    target: int = STANDARD_PRODUCT_TARGET,
) -> dict[str, Any]:
    timeline = build_program_timeline(solution)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(timeline)
    standard_outputs = [
        str(part.get("id"))
        for part in solution.get("parts", [])
        if part.get("type") == "out-std"
    ]
    delivered = dict(simulator.delivered_products)
    terminated = bool(replay.get("summary", {}).get("terminatedWithError"))
    error = _first_simulation_error(replay)
    deficits = {
        output_id: max(0, int(target) - int(delivered.get(output_id, 0)))
        for output_id in standard_outputs
    }
    complete = (
        not terminated
        and bool(standard_outputs)
        and all(value == 0 for value in deficits.values())
    )
    if complete:
        failure_mode = None
    elif terminated:
        failure_mode = "simulation-error"
    elif not standard_outputs:
        failure_mode = "missing-standard-output"
    elif not any(int(value) for value in delivered.values()):
        failure_mode = "no-product-delivered"
    else:
        failure_mode = "insufficient-product-delivery"

    return {
        "complete": complete,
        "failureMode": failure_mode,
        "targetPerOutput": target,
        "standardOutputs": standard_outputs,
        "deliveredProducts": delivered,
        "outputDeficits": deficits,
        "totalDelivered": sum(int(value) for value in delivered.values()),
        "totalDeficit": sum(deficits.values()),
        "requestedCycles": len(timeline.get("cycles", [])),
        "completedCycles": replay.get("summary", {}).get("completedCycles"),
        "terminatedWithError": terminated,
        "firstError": error,
    }


def solve_puzzle(puzzle: dict[str, Any]) -> SolveResult:
    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        raise UnsupportedPuzzleError(plan.reason or "Puzzle is not supported by the current solver")
    if plan.strategy != "bonded-pair-v1":
        raise UnsupportedPuzzleError(f"No generator is registered for strategy {plan.strategy}")

    solution = _generate_bonded_pair_solution(puzzle, plan)
    validation = validate_generated_solution(puzzle, solution)
    if not validation["complete"]:
        raise GeneratedSolutionError(
            f"Generated candidate failed validation: {validation}"
        )
    return SolveResult(
        puzzle_name=str(puzzle.get("name") or _puzzle_file_id(puzzle)),
        strategy=plan.strategy,
        plan=plan,
        solution=solution,
        validation=validation,
    )
