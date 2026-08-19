from __future__ import annotations

import math
from typing import Any

from .timeline import build_program_timeline as _raw_build_program_timeline

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
TRACK_INSTRUCTIONS = {"track_plus", "track_minus"}
STANDARD_PRODUCT_TARGET = 6
MAX_GENERATED_TRACK_VALIDATION_CYCLES = 20_000


def _track_cells(part: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    """Return serialized track cells in world coordinates.

    `trackHexes` are offsets from the part anchor. The anchor itself is not an
    implicit rail cell; it is included only when `[0, 0]` is explicitly present
    in the serialized offsets. This matches the physical timeline semantics.
    """
    if str(part.get("type") or "") != "track":
        return ()
    origin = tuple(int(value) for value in (part.get("position") or (0, 0)))
    offsets = list(part.get("trackHexes") or [])
    if not offsets:
        return (origin,)
    return tuple(
        (origin[0] + int(offset[0]), origin[1] + int(offset[1]))
        for offset in offsets
    )


def _generated_solver_solution(solution: dict[str, Any]) -> bool:
    source = solution.get("source") or {}
    generator = str(source.get("generator") or "")
    return generator.startswith("opus_solver/")


def generated_track_validation_hint(
    solution: dict[str, Any],
    *,
    target: int = STANDARD_PRODUCT_TARGET,
    max_cycles: int = MAX_GENERATED_TRACK_VALIDATION_CYCLES,
) -> dict[str, Any] | None:
    """Estimate enough replay for sparse periodic machines that traverse tracks.

    A machine can legitimately have a three-cell tape (`grab`, `track_plus`,
    `drop`) while requiring thousands of cycles to walk a long production rail.
    The normal six-period validation heuristic therefore under-runs such learned
    mechanisms. This hint is intentionally conservative and bounded: estimate one
    full rail traversal, multiply it by the number of non-transport workstations
    and the requested output count, and cap the diagnostic replay.

    Imported scored solutions keep their declared cycle metric and are not
    modified. Only solver-generated, metric-free candidates receive this hint.
    """
    if not _generated_solver_solution(solution):
        return None
    metric_cycles = (solution.get("metrics") or {}).get("cycles")
    if isinstance(metric_cycles, int) and metric_cycles > 0:
        return None

    source = solution.get("source") or {}
    existing = source.get("validationCycleHint")
    if isinstance(existing, int) and existing > 0:
        return {
            "hint": existing,
            "source": str(source.get("validationCycleHintSource") or "explicit-source-hint"),
            "existing": True,
        }

    tracks = [part for part in solution.get("parts", []) if str(part.get("type") or "") == "track"]
    if not tracks:
        return None
    track_cells = {str(part.get("id") or ""): _track_cells(part) for part in tracks}

    base_timeline = _raw_build_program_timeline(solution)
    global_period = max(1, int((base_timeline.get("summary") or {}).get("globalPeriod") or 1))
    arm_timeline = {
        str(item.get("partId") or ""): item
        for item in base_timeline.get("arms", [])
    }

    traversal_hints: list[dict[str, Any]] = []
    for arm in solution.get("parts", []):
        arm_id = str(arm.get("id") or "")
        if str(arm.get("type") or "") not in ARM_TYPES:
            continue
        program = list(arm.get("program") or [])
        if not any(str(item.get("instruction") or "") in TRACK_INSTRUCTIONS for item in program):
            continue
        base = tuple(int(value) for value in (arm.get("position") or (0, 0)))
        owned = [
            (track_id, cells)
            for track_id, cells in track_cells.items()
            if base in cells
        ]
        if not owned:
            continue
        timeline_arm = arm_timeline.get(arm_id) or {}
        histogram = timeline_arm.get("histogram") or {}
        moves_per_period = sum(int(histogram.get(instruction) or 0) for instruction in TRACK_INSTRUCTIONS)
        if moves_per_period <= 0:
            moves_per_period = sum(
                str(item.get("instruction") or "") in TRACK_INSTRUCTIONS
                for item in program
            )
        moves_per_period = max(1, int(moves_per_period))
        for track_id, cells in owned:
            rail_steps = max(1, len(cells) - 1)
            traversal_periods = max(1, math.ceil(rail_steps / moves_per_period))
            traversal_hints.append({
                "armId": arm_id,
                "trackId": track_id,
                "trackCellCount": len(cells),
                "movesPerPeriod": moves_per_period,
                "globalPeriod": global_period,
                "traversalCycles": traversal_periods * global_period,
            })

    if not traversal_hints:
        return None

    # Inputs, outputs, and glyphs are durable workstations along a learned rail.
    # Using them as a workload proxy is intentionally broader than counting only
    # source glyphs because a transported molecule may need several transforms
    # before one finished product can be emitted.
    workstation_count = sum(
        str(part.get("type") or "") not in ARM_TYPES | {"track"}
        for part in solution.get("parts", [])
    )
    work_units = max(1, workstation_count) * max(1, int(target))
    longest_traversal = max(int(item["traversalCycles"]) for item in traversal_hints)
    raw_hint = longest_traversal * work_units
    hint = max(global_period, min(max(1, int(max_cycles)), raw_hint))
    return {
        "hint": int(hint),
        "source": "generated-track-workload-v1",
        "existing": False,
        "globalPeriod": global_period,
        "workstationCount": workstation_count,
        "targetProducts": max(1, int(target)),
        "workUnits": work_units,
        "longestTraversalCycles": longest_traversal,
        "uncappedHint": raw_hint,
        "cap": max(1, int(max_cycles)),
        "tracks": traversal_hints,
    }


def ensure_generated_track_validation_hint(solution: dict[str, Any]) -> dict[str, Any] | None:
    """Attach a non-serialized validation hint to a generated track candidate."""
    details = generated_track_validation_hint(solution)
    if details is None or details.get("existing"):
        return details
    source = solution.setdefault("source", {})
    source["validationCycleHint"] = int(details["hint"])
    source["validationCycleHintSource"] = str(details["source"])
    source["validationCycleHintDetails"] = {
        key: value
        for key, value in details.items()
        if key not in {"hint", "source", "existing"}
    }
    return details


__all__ = [
    "MAX_GENERATED_TRACK_VALIDATION_CYCLES",
    "ensure_generated_track_validation_hint",
    "generated_track_validation_hint",
]
