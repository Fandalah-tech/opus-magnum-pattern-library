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
    """Find trace-observed faithful purification placements that could fire.

    OMSim's purification glyph takes two equal, free metal atoms on local cells
    ``(0, 0)`` and ``(1, 0)`` and creates the next metal on local ``(0, 1)``.
    Both inputs must be unheld and unbonded.  Opportunities are inferred only
    from a generated candidate's local engine trace, never from a target
    solution.
    """

    observations: defaultdict[
        tuple[str, tuple[int, int], int],
        dict[str, Any],
    ] = defaultdict(dict)

    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        world = frame.get("world") or {}
        atoms = list(world.get("atoms") or [])
        bonded_ids = {
            str(bond.get(key) or "")
            for bond in (world.get("bonds") or [])
            for key in ("fromAtomId", "toAtomId")
            if bond.get(key)
        }
        by_position: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for atom in atoms:
            by_position[_position(atom.get("position"))].append(atom)
        occupied = set(by_position)

        def free_conversion_atom(atom: dict[str, Any]) -> bool:
            atom_id = str(atom.get("id") or "")
            return not (atom.get("heldBy") or []) and atom_id not in bonded_ids

        for first in atoms:
            element = str(first.get("element") or "")
            if element not in METAL_ORDER[:-1] or not free_conversion_atom(first):
                continue
            first_pos = _position(first.get("position"))
            first_id = str(first.get("id") or "")
            for rotation in range(6):
                input_delta = rotate_hex((1, 0), rotation)
                output_delta = rotate_hex((0, 1), rotation)
                second_pos = (first_pos[0] + input_delta[0], first_pos[1] + input_delta[1])
                output_pos = (first_pos[0] + output_delta[0], first_pos[1] + output_delta[1])
                if output_pos in occupied:
                    continue
                matches = [
                    atom
                    for atom in by_position.get(second_pos, [])
                    if str(atom.get("element") or "") == element
                    and free_conversion_atom(atom)
                ]
                if not matches:
                    continue
                second = min(matches, key=lambda atom: str(atom.get("id") or ""))
                second_id = str(second.get("id") or "")
                # Reverse orientations represent the same two physical inputs;
                # retain one deterministic atom ordering.
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
                        "second": [second_pos[0], second_pos[1]],
                        "output": [output_pos[0], output_pos[1]],
                        "firstAtomId": first_id,
                        "secondAtomId": second_id,
                        "firstCycle": cycle,
                        "lastCycle": cycle,
                        "observationCount": 0,
                        "geometryEvidence": "faithful-purification-local-cells-0,0-1,0-to-0,1",
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
    source = result.setdefault("source", {})
    # Parsed artifact binaries do not retain non-serialized generator metadata.
    # Re-establish solver provenance so the generic track validation-horizon
    # estimator can replay sparse transport machines long enough to reach the
    # trace-derived reaction pose.
    source["generator"] = "opus_solver/trace-guided-purification-v1"
    source["reactionPlacementRepair"] = {
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
        "schemaVersion": "0.2.0",
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
