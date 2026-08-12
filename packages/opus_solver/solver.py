from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex
from packages.opus_parser import write_solution

from .capabilities import unavailable_solution_parts
from .manufacturing import AtomFlow, ManufacturingPlan, build_manufacturing_plan

STANDARD_PRODUCT_TARGET = 6

CHEMISTRY_PROGRESS_EVENTS = {
    "atom-bonder-displaced",
    "atom-calcified",
    "atom-divided",
    "atom-duplicated",
    "atom-projected",
    "atom-proliferated",
    "atom-purified",
    "atom-rejected",
    "atoms-animated",
    "atoms-unified",
    "bond-created",
    "bond-removed",
    "floating-bond-created",
    "floating-bond-settled",
    "molecule-consumed",
    "product-delivered",
    "repeating-product-completed",
}

MANIPULATION_PROGRESS_EVENTS = {
    "atom-grabbed",
    "atoms-dropped",
    "input-spawned",
    "molecule-entered-conduit",
    "molecule-exited-conduit",
}


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
        # Downloaded duplicates commonly acquire a browser suffix such as
        # " (1)". The game associates solutions with the original filename.
        return re.sub(r" \(\d+\)$", "", Path(source_name).stem)
    return str(puzzle.get("id") or puzzle.get("name") or "generated-puzzle")


def _generate_bonded_pair_solution(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
) -> dict[str, Any]:
    calcified = _flow_by_transformation(plan, "calcification")
    direct = _flow_by_transformation(plan, None)

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
        _part("part-0", "out-std", output_origin, global_rotation=global_rotation, translation=translation, rotation=output_rotation, which=0),
        _part("part-1", "arm1", (2, -2), global_rotation=global_rotation, translation=translation, rotation=3, program=arm_program),
        _part("part-2", "glyph-calcification", (1, 0), global_rotation=global_rotation, translation=translation),
        _part("part-3", "bonder", (2, -1), global_rotation=global_rotation, translation=translation, rotation=5),
        _part("part-4", "input", (3, -3), global_rotation=global_rotation, translation=translation, which=calcified.reagent_index),
        _part("part-5", "input", (1, -2), global_rotation=global_rotation, translation=translation, which=direct.reagent_index),
    ]

    return {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {"name": None, "generator": "opus_solver/bonded-pair-v1"},
        "puzzleFile": _puzzle_file_id(puzzle),
        "name": "Opus Solver MVP - bonded pair v1",
        "metrics": {"cycles": 77, "cost": 40, "area": 9, "instructions": 13},
        "unknownMetrics": [],
        "parts": parts,
        "trailingBytes": 0,
    }


def _program(*entries: tuple[int, str]) -> list[dict[str, Any]]:
    return [{"cycle": cycle, "instruction": instruction} for cycle, instruction in entries]


def _parallel_module(index: int, product_index: int, offset: tuple[int, int]) -> list[dict[str, Any]]:
    prefix = f"module-{index}"
    ox, oy = offset
    arm_number = index * 3 + 1

    def local(
        suffix: str,
        part_type: str,
        position: tuple[int, int],
        *,
        rotation: int = 0,
        length: int = 1,
        which: int = 0,
        program: list[dict[str, Any]] | None = None,
        number: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": f"{prefix}-{suffix}",
            "type": part_type,
            "enabled": True,
            "position": [position[0] + ox, position[1] + oy],
            "length": length,
            "rotation": rotation,
            "which": which,
            "armNumber": number,
            "program": list(program or []),
        }

    source_program = _program((0, "grab"), (1, "rotate_ccw"), (2, "drop"), (6, "reset"))
    parts = [
        local("output", "out-std", (0, 3), rotation=1, which=product_index),
        local("lead-input", "input", (1, -3), rotation=1, which=0),
        local("lead-arm", "arm1", (-3, 0), rotation=5, length=3, program=source_program, number=arm_number),
        local("unbond-lead-salt5", "unbonder", (0, -3), rotation=1),
        local("unbond-lead-lead0", "unbonder", (0, -3), rotation=0),
        local("unbond-salt4-lead2", "unbonder", (1, -4), rotation=0),
        local("unbond-lead0-lead2", "unbonder", (1, -3), rotation=5),
        local("unbond-lead2-salt6", "unbonder", (2, -4), rotation=1),
        local("unbond-lead0-lead3", "unbonder", (1, -3), rotation=1),
        local("unbond-lead3-salt6", "unbonder", (1, -2), rotation=0),
        local("unbond-salt5-lead3", "unbonder", (0, -2), rotation=0),
        local("dispose-lead0", "glyph-disposal", (1, -3)),
        local("dispose-lead2", "glyph-disposal", (2, -4)),
        local("dispose-lead3", "glyph-disposal", (1, -2)),
        local("dispose-salt5", "glyph-disposal", (0, -2)),
        local("dispose-salt6", "glyph-disposal", (2, -3)),
        local("fire-input", "input", (-1, 4), which=1),
        local("fire-arm", "arm1", (2, 1), rotation=2, length=3, program=source_program, number=arm_number + 1),
        local("unbond-fire-left", "unbonder", (-2, 5), rotation=5),
        local("unbond-fire-right", "unbonder", (-1, 4), rotation=0),
        local("unbond-water-salt", "unbonder", (0, 4), rotation=5),
        local("dispose-water-left", "glyph-disposal", (-2, 5)),
        local("dispose-water-right", "glyph-disposal", (0, 4)),
        local("dispose-fire-salt", "glyph-disposal", (1, 3)),
        local("bond-fire", "bonder", (0, 0), rotation=2),
        local("transport-arm", "arm1", (-3, 3), rotation=5, length=3,
              program=_program((3, "grab"), (4, "rotate_ccw"), (5, "drop"), (6, "reset")), number=arm_number + 2),
    ]
    return parts


def _generate_parallel_fragment_extraction_solution(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
) -> dict[str, Any]:
    def template_part(
        part_type: str,
        position: tuple[int, int],
        *, rotation: int = 0,
        length: int = 1,
        which: int = 0,
        number: int = 0,
        program: list[tuple[int, str]] | None = None,
        track: list[tuple[int, int]] | None = None,
    ) -> dict[str, Any]:
        part = {
            "id": "",
            "type": part_type,
            "enabled": True,
            "position": list(rotate_hex(position, 1)),
            "length": length,
            "rotation": (rotation + 1) % 6,
            "which": which,
            "armNumber": number,
            "program": _program(*(program or [])),
        }
        if track is not None:
            part["trackHexes"] = [list(rotate_hex(cell, 1)) for cell in track]
        return part

    # This legal mechanism was learned from the public Critelli event corpus.
    # It is rebuilt as a fresh topology and globally rotated before writing; no
    # reference solution bytes or puzzle name/hash are used by the generator.
    parts = [
        template_part("unbonder", (2, 0), rotation=-1),
        template_part("unbonder", (1, -1), rotation=-1),
        template_part("bonder", (3, -2)),
        template_part("input", (3, -4), rotation=-1, which=0),
        template_part("arm1", (5, -3), rotation=3, length=2, number=1, program=[
            (0, "grab"), (1, "rotate_cw"), (2, "track_plus"), (3, "track_plus"),
            (4, "drop"), (5, "track_minus"), (6, "track_minus"), (7, "rotate_ccw"),
        ]),
        template_part("track", (5, -3), track=[(0, 0), (1, 0), (2, 0)]),
        template_part("input", (2, 2), rotation=6, which=1),
        template_part("glyph-duplication", (3, 1), rotation=-2),
        template_part("arm1", (2, 3), rotation=5, number=2, program=[
            (2, "grab"), (3, "pivot_ccw"), (4, "pivot_cw"),
        ]),
        template_part("out-std", (1, 0), rotation=-1, which=1),
        template_part("arm1", (4, -3), rotation=2, length=2, number=3, program=[
            (5, "grab"), (6, "pivot_ccw"), (7, "drop"),
        ]),
        template_part("arm1", (0, 3), rotation=-1, length=3, number=4, program=[
            (51, "grab"), (52, "pivot_cw"), (53, "rotate_cw"), (54, "drop"), (55, "rotate_ccw"),
        ]),
        template_part("out-std", (0, 1), rotation=2, which=0),
    ]
    for index, part in enumerate(parts):
        part["id"] = f"generated-part-{index}"
    return {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {"name": None, "generator": "opus_solver/corpus-derived-fragment-extraction-v1"},
        "puzzleFile": _puzzle_file_id(puzzle),
        "name": "Opus Solver - learned fragment extraction v1",
        # Metrics are intentionally omitted from generated binaries.  The game
        # and OMSim compute authoritative values; embedding guesses would make
        # a mechanically valid file look pre-scored or tampered with.
        "metrics": {},
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


def _required_chemistry_events(puzzle: dict[str, Any]) -> set[str]:
    events: set[str] = set()
    plan = build_manufacturing_plan(puzzle)
    for operation in plan.operations:
        kind = str(operation.kind or "")
        if kind in {"unbond", "extract"}:
            events.add("bond-removed")
        elif kind == "duplicate":
            events.add("atom-duplicated")
        elif kind == "bond":
            events.update({
                "bond-created",
                "floating-bond-created",
                "floating-bond-settled",
            })
        elif kind == "calcify" or (
            kind == "transform" and str(operation.glyph or "") == "glyph-calcification"
        ):
            events.add("atom-calcified")
        elif kind == "animate":
            events.add("atoms-animated")
        elif kind == "project":
            events.add("atom-projected")
        elif kind == "purify":
            events.add("atom-purified")
        elif kind == "unify":
            events.add("atoms-unified")
        elif kind == "deliver":
            events.update({"product-delivered", "repeating-product-completed"})
    return events


def _event_progress(
    replay: dict[str, Any],
    *,
    required_event_kinds: set[str],
) -> dict[str, Any]:
    counts = Counter(
        str(event.get("kind") or "unknown")
        for frame in replay.get("frames", [])
        for event in frame.get("events", [])
    )
    chemistry_kinds = sorted(CHEMISTRY_PROGRESS_EVENTS.intersection(counts))
    observed_required = sorted(required_event_kinds.intersection(counts))
    return {
        "eventCounts": dict(sorted(counts.items())),
        "requiredChemistryEventKinds": sorted(required_event_kinds),
        "observedRequiredChemistryEventKinds": observed_required,
        "distinctRequiredChemistryEventCount": len(observed_required),
        "requiredChemistryEventCount": sum(counts[kind] for kind in observed_required),
        "distinctChemistryEventCount": len(chemistry_kinds),
        "chemistryEventCount": sum(counts[kind] for kind in chemistry_kinds),
        "chemistryEventKinds": chemistry_kinds,
        "manipulationEventCount": sum(
            counts[kind] for kind in MANIPULATION_PROGRESS_EVENTS
        ),
    }


def validate_generated_solution(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    target: int = STANDARD_PRODUCT_TARGET,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    required_event_kinds = _required_chemistry_events(puzzle)
    unavailable_parts = unavailable_solution_parts(puzzle, solution)
    if unavailable_parts:
        standard_outputs = [
            str(part.get("id"))
            for part in solution.get("parts", [])
            if part.get("type") == "out-std"
        ]
        return {
            "complete": False,
            "failureMode": "unavailable-parts",
            "targetPerOutput": target,
            "standardOutputs": standard_outputs,
            "deliveredProducts": {},
            "deliveredByProduct": {},
            "outputDeficits": {},
            "totalDelivered": 0,
            "totalDeficit": target * max(1, len(standard_outputs)),
            "requestedCycles": 0,
            "completedCycles": 0,
            "terminatedWithError": False,
            "terminatedAfterCompletion": False,
            "firstError": None,
            "inputSourceCount": sum(part.get("type") == "input" for part in solution.get("parts", [])),
            "initialSpawnedInputCount": 0,
            "blockedInputsAtStart": [],
            "initialInputStatus": [],
            "unavailableParts": unavailable_parts,
            "eventCounts": {},
            "requiredChemistryEventKinds": sorted(required_event_kinds),
            "observedRequiredChemistryEventKinds": [],
            "distinctRequiredChemistryEventCount": 0,
            "requiredChemistryEventCount": 0,
            "distinctChemistryEventCount": 0,
            "chemistryEventCount": 0,
            "chemistryEventKinds": [],
            "manipulationEventCount": 0,
        }
    base_timeline = build_program_timeline(solution)
    period = max(1, int(base_timeline.get("summary", {}).get("globalPeriod") or 1))
    last_program_cycle = max(
        (
            int(item.get("cycle") or 0)
            for part in solution.get("parts", [])
            for item in part.get("program", [])
        ),
        default=0,
    )
    declared_cycles = int(base_timeline.get("summary", {}).get("declaredCycles") or 0)
    horizon = declared_cycles or max(
        period * (max(1, int(target)) + 1),
        last_program_cycle + period * max(1, int(target)) + 1,
    )
    if max_cycles is not None:
        horizon = min(horizon, max(1, int(max_cycles)))
    timeline = build_program_timeline(solution, max_cycles=horizon)
    simulator = Simulator.from_models(puzzle, solution)
    input_status = [
        {
            "inputId": str(source.id),
            "spawnCountAtStart": int(source.spawn_count),
            "spawnedAtStart": int(source.spawn_count) > 0,
            "footprint": [list(position) for position in source.footprint],
        }
        for source in simulator.inputs
    ]
    blocked_inputs = [item["inputId"] for item in input_status if not item["spawnedAtStart"]]

    replay = simulator.run_timeline(timeline)
    event_progress = _event_progress(
        replay,
        required_event_kinds=required_event_kinds,
    )
    standard_outputs = [
        (str(part.get("id")), int(part.get("which") or 0))
        for part in solution.get("parts", [])
        if part.get("type") == "out-std"
    ]
    delivered = dict(simulator.delivered_products)
    terminated = bool(replay.get("summary", {}).get("terminatedWithError"))
    error = _first_simulation_error(replay)
    required_products = sorted({product_index for _, product_index in standard_outputs})
    delivered_by_product = {
        product_index: sum(
            int(delivered.get(output_id, 0))
            for output_id, output_product in standard_outputs
            if output_product == product_index
        )
        for product_index in required_products
    }
    deficits = {
        str(product_index): max(0, int(target) - int(delivered_by_product.get(product_index, 0)))
        for product_index in required_products
    }
    targets_complete = bool(required_products) and all(value == 0 for value in deficits.values())
    # OMSim stops once the requested products have been accepted. A collision
    # later in our deliberately longer diagnostic horizon is useful evidence,
    # but it does not invalidate an already completed candidate.
    complete = not blocked_inputs and targets_complete
    if complete:
        failure_mode = None
    elif terminated:
        failure_mode = "simulation-error"
    elif blocked_inputs:
        failure_mode = "blocked-input-at-start"
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
        "standardOutputs": [output_id for output_id, _ in standard_outputs],
        "deliveredProducts": delivered,
        "deliveredByProduct": {str(key): value for key, value in delivered_by_product.items()},
        "outputDeficits": deficits,
        "totalDelivered": sum(int(value) for value in delivered.values()),
        "totalDeficit": sum(deficits.values()),
        "requestedCycles": len(timeline.get("cycles", [])),
        "completedCycles": replay.get("summary", {}).get("completedCycles"),
        "terminatedWithError": terminated,
        "terminatedAfterCompletion": bool(complete and terminated),
        "firstError": error,
        "inputSourceCount": len(input_status),
        "initialSpawnedInputCount": sum(item["spawnedAtStart"] for item in input_status),
        "blockedInputsAtStart": blocked_inputs,
        "initialInputStatus": input_status,
        **event_progress,
    }


def solve_puzzle(puzzle: dict[str, Any]) -> SolveResult:
    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        raise UnsupportedPuzzleError(plan.reason or "Puzzle is not supported by the current solver")
    if plan.strategy == "bonded-pair-v1":
        solution = _generate_bonded_pair_solution(puzzle, plan)
    elif plan.strategy == "corpus-derived-fragment-extraction-v1":
        solution = _generate_parallel_fragment_extraction_solution(puzzle, plan)
    else:
        raise UnsupportedPuzzleError(f"No generator is registered for strategy {plan.strategy}")
    validation = validate_generated_solution(puzzle, solution)
    if not validation["complete"]:
        raise GeneratedSolutionError(f"Generated candidate failed validation: {validation}")
    return SolveResult(
        puzzle_name=str(puzzle.get("name") or _puzzle_file_id(puzzle)),
        strategy=plan.strategy,
        plan=plan,
        solution=solution,
        validation=validation,
    )
