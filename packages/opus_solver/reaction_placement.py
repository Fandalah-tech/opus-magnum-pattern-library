from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex

from .solver import validate_generated_solution


METAL_ORDER = ("lead", "tin", "iron", "copper", "silver", "gold")


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def purification_opportunities(replay: dict[str, Any]) -> list[dict[str, Any]]:
    """Find trace-observed placements where a purification glyph could fire.

    A purification glyph consumes two equal metal atoms on the two outer cells
    of a three-cell line and creates the next metal on the empty center cell.
    The opportunities are inferred exclusively from a generated candidate's
    local engine trace.  They therefore provide a target-solution-free bridge
    from inherited transport geometry to target chemistry.
    """

    observations: defaultdict[
        tuple[str, tuple[int, int], int],
        dict[str, Any],
    ] = defaultdict(dict)

    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        atoms = list((frame.get("world") or {}).get("atoms") or [])
        by_position: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for atom in atoms:
            by_position[_position(atom.get("position"))].append(atom)
        occupied = set(by_position)

        for first in atoms:
            element = str(first.get("element") or "")
            if element not in METAL_ORDER[:-1]:
                continue
            first_pos = _position(first.get("position"))
            first_id = str(first.get("id") or "")
            for rotation in range(6):
                direction = rotate_hex((1, 0), rotation)
                center = (first_pos[0] + direction[0], first_pos[1] + direction[1])
                second_pos = (center[0] + direction[0], center[1] + direction[1])
                if center in occupied:
                    continue
                matches = [
                    atom
                    for atom in by_position.get(second_pos, [])
                    if str(atom.get("element") or "") == element
                ]
                if not matches:
                    continue
                second = min(matches, key=lambda atom: str(atom.get("id") or ""))
                second_id = str(second.get("id") or "")
                # The reverse orientation sees the same physical glyph pose.
                # Keep one canonical atom ordering while retaining the correct
                # origin/rotation for the surviving direction.
                if first_id and second_id and first_id > second_id:
                    continue

                key = (element, first_pos, rotation)
                payload = observations.get(key)
                if not payload:
                    produced = METAL_ORDER[METAL_ORDER.index(element) + 1]
                    payload = {
                        "element": element,
                        "producedElement": produced,
                        "origin": [first_pos[0], first_pos[1]],
                        "rotation": rotation,
                        "center": [center[0], center[1]],
                        "second": [second_pos[0], second_pos[1]],
                        "firstAtomId": first_id,
                        "secondAtomId": second_id,
                        "firstCycle": cycle,
                        "lastCycle": cycle,
                        "observationCount": 0,
                    }
                    observations[key] = payload
                payload["observationCount"] = int(payload["observationCount"]) + 1
                payload["firstCycle"] = min(int(payload["firstCycle"]), cycle)
                payload["lastCycle"] = max(int(payload["lastCycle"]), cycle)

    return sorted(
        observations.values(),
        key=lambda item: (
            -int(item.get("observationCount") or 0),
            int(item.get("firstCycle") or 0),
            METAL_ORDER.index(str(item.get("element") or "lead")),
            tuple(item.get("origin") or (0, 0)),
            int(item.get("rotation") or 0),
        ),
    )


def apply_purification_placement(
    solution: dict[str, Any],
    *,
    purifier_index: int,
    opportunity: dict[str, Any],
) -> dict[str, Any]:
    """Move one existing purification glyph onto a trace-derived opportunity."""

    result = deepcopy(solution)
    purifiers = [
        part
        for part in result.get("parts", [])
        if str(part.get("type") or "") == "glyph-purification"
    ]
    if not 0 <= int(purifier_index) < len(purifiers):
        raise IndexError(f"purifier_index {purifier_index} outside {len(purifiers)} purification glyphs")
    purifier = purifiers[int(purifier_index)]
    purifier["position"] = [int(value) for value in opportunity.get("origin", (0, 0))]
    purifier["rotation"] = int(opportunity.get("rotation") or 0) % 6
    result.setdefault("source", {})["reactionPlacementRepair"] = {
        "kind": "trace-guided-purification-v1",
        "purifierIndex": int(purifier_index),
        "purifierPartId": str(purifier.get("id") or ""),
        "opportunity": deepcopy(opportunity),
        "targetSolutionBytesUsed": 0,
    }
    return result


def _variant_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    validation = record.get("validation") or {}
    events = validation.get("eventCounts") or {}
    purified = int(events.get("atom-purified") or 0)
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        purified,
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        int(validation.get("distinctChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        int(validation.get("manipulationEventCount") or 0),
        int(record.get("opportunity", {}).get("observationCount") or 0),
        -int(record.get("purifierIndex") or 0),
    )


def search_purification_placements(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 256,
    opportunity_limit: int = 80,
    variant_limit: int = 240,
    result_limit: int = 20,
) -> dict[str, Any]:
    """Search trace-derived purification poses on an inherited blind candidate."""

    horizon = max(1, int(max_cycles))
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    opportunities = purification_opportunities(replay)[:max(0, int(opportunity_limit))]
    purifier_count = sum(
        str(part.get("type") or "") == "glyph-purification"
        for part in solution.get("parts", [])
    )

    records: list[dict[str, Any]] = []
    if purifier_count > 0:
        for opportunity in opportunities:
            for purifier_index in range(purifier_count):
                if len(records) >= max(0, int(variant_limit)):
                    break
                candidate = apply_purification_placement(
                    solution,
                    purifier_index=purifier_index,
                    opportunity=opportunity,
                )
                validation = validate_generated_solution(
                    puzzle,
                    candidate,
                    max_cycles=horizon,
                )
                records.append({
                    "purifierIndex": purifier_index,
                    "opportunity": deepcopy(opportunity),
                    "validation": validation,
                    "solution": candidate,
                })
            if len(records) >= max(0, int(variant_limit)):
                break

    records.sort(key=_variant_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-purification-placement-search",
        "summary": {
            "maxCycles": horizon,
            "purifierCount": purifier_count,
            "opportunityCount": len(opportunities),
            "searchedVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "purificationReachedCount": sum(
                int((record.get("validation") or {}).get("eventCounts", {}).get("atom-purified") or 0) > 0
                for record in records
            ),
            "hasPurification": any(
                int((record.get("validation") or {}).get("eventCounts", {}).get("atom-purified") or 0) > 0
                for record in records
            ),
            "targetSolutionBytesUsed": 0,
        },
        "baseline": {
            "completedCycles": int((replay.get("summary") or {}).get("completedCycles") or 0),
            "terminatedWithError": bool((replay.get("summary") or {}).get("terminatedWithError")),
        },
        "opportunities": opportunities,
        "variants": selected,
    }


__all__ = [
    "apply_purification_placement",
    "purification_opportunities",
    "search_purification_placements",
]
