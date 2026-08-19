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


def _direction_rotation(delta: tuple[int, int]) -> int | None:
    for rotation in range(6):
        if rotate_hex((1, 0), rotation) == delta:
            return rotation
    return None


def purification_opportunities(
    replay: dict[str, Any],
    *,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    """Find trace-observed faithful purification placements.

    OMSim's purification glyph takes two equal metal atoms on local cells
    ``(0, 0)`` and ``(1, 0)`` and creates the next metal on local ``(0, 1)``.
    A ready opportunity has unheld, unbonded inputs and an empty output cell.

    With ``include_blocked=True`` we also retain geometrically correct pairs
    that are blocked in the end-of-cycle snapshot by holding, bonding, or an
    occupied output.  Those near-opportunities are useful because the faithful
    engine executes basic unbonders before purification in the same first
    half-cycle.  A one-bond blocker can therefore be repaired by relocating an
    inherited unbonder and purifier together.  Every proposed repair is replay-
    validated; a near-opportunity is search evidence, not a claimed success.
    """

    observations: defaultdict[
        tuple[str, tuple[int, int], int],
        dict[str, Any],
    ] = defaultdict(dict)

    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        world = frame.get("world") or {}
        atoms = list(world.get("atoms") or [])
        atoms_by_id = {str(atom.get("id") or ""): atom for atom in atoms}
        bond_neighbors: defaultdict[str, set[str]] = defaultdict(set)
        for bond in world.get("bonds") or []:
            first_id = str(bond.get("fromAtomId") or "")
            second_id = str(bond.get("toAtomId") or "")
            if first_id and second_id:
                bond_neighbors[first_id].add(second_id)
                bond_neighbors[second_id].add(first_id)
        bonded_ids = set(bond_neighbors)
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
                input_delta = rotate_hex((1, 0), rotation)
                output_delta = rotate_hex((0, 1), rotation)
                second_pos = (first_pos[0] + input_delta[0], first_pos[1] + input_delta[1])
                output_pos = (first_pos[0] + output_delta[0], first_pos[1] + output_delta[1])
                matches = [
                    atom
                    for atom in by_position.get(second_pos, [])
                    if str(atom.get("element") or "") == element
                ]
                if not matches:
                    continue
                second = min(matches, key=lambda atom: str(atom.get("id") or ""))
                second_id = str(second.get("id") or "")
                # Reverse orientations represent the same two physical inputs;
                # retain one deterministic atom ordering.
                if first_id and second_id and first_id > second_id:
                    continue

                first_held = bool(first.get("heldBy") or [])
                second_held = bool(second.get("heldBy") or [])
                first_bonded = first_id in bonded_ids
                second_bonded = second_id in bonded_ids
                output_occupied = output_pos in occupied
                blocker_count = sum((
                    first_held,
                    second_held,
                    first_bonded,
                    second_bonded,
                    output_occupied,
                ))
                ready = blocker_count == 0
                if not ready and not include_blocked:
                    continue

                unbond_candidates = []
                for blocked_id in (first_id, second_id):
                    blocked_atom = atoms_by_id.get(blocked_id)
                    if blocked_atom is None:
                        continue
                    blocked_pos = _position(blocked_atom.get("position"))
                    for neighbor_id in sorted(bond_neighbors.get(blocked_id, ())):
                        neighbor = atoms_by_id.get(neighbor_id)
                        if neighbor is None:
                            continue
                        neighbor_pos = _position(neighbor.get("position"))
                        direction = (
                            neighbor_pos[0] - blocked_pos[0],
                            neighbor_pos[1] - blocked_pos[1],
                        )
                        unbond_rotation = _direction_rotation(direction)
                        if unbond_rotation is None:
                            continue
                        unbond_candidates.append({
                            "blockedAtomId": blocked_id,
                            "neighborAtomId": neighbor_id,
                            "origin": [blocked_pos[0], blocked_pos[1]],
                            "rotation": unbond_rotation,
                            "second": [neighbor_pos[0], neighbor_pos[1]],
                            "cycle": cycle,
                        })

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
                        "readyObservationCount": 0,
                        "minimumBlockerCount": blocker_count,
                        "blockersAtBestObservation": {},
                        "unbondCandidates": [],
                        "geometryEvidence": "faithful-purification-local-cells-0,0-1,0-to-0,1",
                    }
                    observations[key] = payload
                payload["observationCount"] = int(payload["observationCount"]) + 1
                payload["readyObservationCount"] = int(payload["readyObservationCount"]) + int(ready)
                payload["firstCycle"] = min(int(payload["firstCycle"]), cycle)
                payload["lastCycle"] = max(int(payload["lastCycle"]), cycle)
                if blocker_count <= int(payload.get("minimumBlockerCount") or blocker_count):
                    payload["minimumBlockerCount"] = blocker_count
                    payload["blockersAtBestObservation"] = {
                        "firstHeld": first_held,
                        "secondHeld": second_held,
                        "firstBonded": first_bonded,
                        "secondBonded": second_bonded,
                        "outputOccupied": output_occupied,
                        "cycle": cycle,
                    }
                    payload["unbondCandidates"] = unbond_candidates

    return sorted(
        observations.values(),
        key=lambda item: (
            int(item.get("minimumBlockerCount") or 0),
            -int(bool(item.get("unbondCandidates"))),
            -int(item.get("readyObservationCount") or 0),
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
    source["generator"] = "opus_solver/trace-guided-purification-v1"
    source["reactionPlacementRepair"] = {
        "kind": "trace-guided-purification-v1",
        "purifierIndex": int(purifier_index),
        "purifierPartId": str(purifier.get("id") or ""),
        "opportunity": deepcopy(opportunity),
        "targetSolutionBytesUsed": 0,
    }
    return result


def apply_purification_unbond_repair(
    solution: dict[str, Any],
    *,
    purifier_index: int,
    unbonder_index: int,
    opportunity: dict[str, Any],
    unbond_candidate: dict[str, Any],
) -> dict[str, Any]:
    """Place an unbonder immediately upstream of a blocked purification pose."""

    result = apply_purification_placement(
        solution,
        purifier_index=purifier_index,
        opportunity=opportunity,
    )
    unbonders = [
        part
        for part in result.get("parts", [])
        if str(part.get("type") or "") == "unbonder"
    ]
    if not 0 <= int(unbonder_index) < len(unbonders):
        raise IndexError(f"unbonder_index {unbonder_index} outside {len(unbonders)} unbonders")
    unbonder = unbonders[int(unbonder_index)]
    unbonder["position"] = [int(value) for value in unbond_candidate.get("origin", (0, 0))]
    unbonder["rotation"] = int(unbond_candidate.get("rotation") or 0) % 6
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/trace-guided-unbond-purification-v1"
    source["reactionPlacementRepair"] = {
        "kind": "trace-guided-unbond-purification-v1",
        "purifierIndex": int(purifier_index),
        "unbonderIndex": int(unbonder_index),
        "purifierPartId": str([
            part for part in result.get("parts", [])
            if str(part.get("type") or "") == "glyph-purification"
        ][int(purifier_index)].get("id") or ""),
        "unbonderPartId": str(unbonder.get("id") or ""),
        "opportunity": deepcopy(opportunity),
        "unbondCandidate": deepcopy(unbond_candidate),
        "targetSolutionBytesUsed": 0,
    }
    return result


def _variant_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    validation = record.get("validation") or {}
    events = validation.get("eventCounts") or {}
    purified = int(events.get("atom-purified") or 0)
    opportunity = record.get("opportunity") or {}
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
        -int(opportunity.get("minimumBlockerCount") or 0),
        int(opportunity.get("readyObservationCount") or 0),
        int(opportunity.get("observationCount") or 0),
        int(record.get("repairMode") == "unbond+purify"),
        -int(record.get("purifierIndex") or 0),
        -int(record.get("unbonderIndex") or 0),
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
    """Search ready and coupled unbond+purification poses on a blind candidate."""

    horizon = max(1, int(max_cycles))
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    all_opportunities = purification_opportunities(replay, include_blocked=True)
    opportunities = all_opportunities[:max(0, int(opportunity_limit))]
    purifier_count = sum(
        str(part.get("type") or "") == "glyph-purification"
        for part in solution.get("parts", [])
    )
    unbonder_count = sum(
        str(part.get("type") or "") == "unbonder"
        for part in solution.get("parts", [])
    )

    records: list[dict[str, Any]] = []

    def add_record(candidate, *, purifier_index, opportunity, repair_mode, unbonder_index=None, unbond_candidate=None):
        validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
        records.append({
            "repairMode": repair_mode,
            "purifierIndex": purifier_index,
            "unbonderIndex": unbonder_index,
            "opportunity": deepcopy(opportunity),
            "unbondCandidate": deepcopy(unbond_candidate) if unbond_candidate is not None else None,
            "validation": validation,
            "solution": candidate,
        })

    if purifier_count > 0:
        for opportunity in opportunities:
            if len(records) >= max(0, int(variant_limit)):
                break
            unbond_candidates = list(opportunity.get("unbondCandidates") or [])
            # For a bond-blocked pose, try the mechanistically relevant coupled
            # repair first so the bounded budget is not consumed by purifier-
            # only placements that cannot satisfy faithful conversion input.
            if unbond_candidates and unbonder_count > 0:
                for unbond_candidate in unbond_candidates:
                    for unbonder_index in range(unbonder_count):
                        for purifier_index in range(purifier_count):
                            if len(records) >= max(0, int(variant_limit)):
                                break
                            candidate = apply_purification_unbond_repair(
                                solution,
                                purifier_index=purifier_index,
                                unbonder_index=unbonder_index,
                                opportunity=opportunity,
                                unbond_candidate=unbond_candidate,
                            )
                            add_record(
                                candidate,
                                purifier_index=purifier_index,
                                unbonder_index=unbonder_index,
                                opportunity=opportunity,
                                unbond_candidate=unbond_candidate,
                                repair_mode="unbond+purify",
                            )
                        if len(records) >= max(0, int(variant_limit)):
                            break
                    if len(records) >= max(0, int(variant_limit)):
                        break
            else:
                for purifier_index in range(purifier_count):
                    if len(records) >= max(0, int(variant_limit)):
                        break
                    candidate = apply_purification_placement(
                        solution,
                        purifier_index=purifier_index,
                        opportunity=opportunity,
                    )
                    add_record(
                        candidate,
                        purifier_index=purifier_index,
                        opportunity=opportunity,
                        repair_mode="purify-only",
                    )

    records.sort(key=_variant_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.4.0",
        "kind": "trace-guided-purification-placement-search",
        "summary": {
            "maxCycles": horizon,
            "purifierCount": purifier_count,
            "unbonderCount": unbonder_count,
            "opportunityCount": len(opportunities),
            "readyOpportunityCount": sum(int(item.get("minimumBlockerCount") or 0) == 0 for item in opportunities),
            "nearOpportunityCount": sum(int(item.get("minimumBlockerCount") or 0) > 0 for item in opportunities),
            "unbondableOpportunityCount": sum(bool(item.get("unbondCandidates")) for item in opportunities),
            "searchedVariantCount": len(records),
            "coupledVariantCount": sum(record.get("repairMode") == "unbond+purify" for record in records),
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
    "apply_purification_unbond_repair",
    "purification_opportunities",
    "search_purification_placements",
]
