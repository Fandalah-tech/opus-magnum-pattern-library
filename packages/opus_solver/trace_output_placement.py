from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex

from .solver import validate_generated_solution


def singleton_product_descriptor(puzzle: dict[str, Any], product_index: int) -> dict[str, Any] | None:
    products = list(puzzle.get("products") or [])
    if not 0 <= int(product_index) < len(products):
        return None
    product = products[int(product_index)] or {}
    atoms = list(product.get("atoms") or [])
    bonds = list(product.get("bonds") or [])
    if len(atoms) != 1 or bonds:
        return None
    atom = atoms[0]
    return {
        "productIndex": int(product_index),
        "element": str(atom.get("element") or ""),
        "localPosition": [int(value) for value in (atom.get("position") or (0, 0))],
    }


def singleton_output_opportunities(
    puzzle: dict[str, Any],
    replay: dict[str, Any],
    *,
    product_index: int,
) -> list[dict[str, Any]]:
    descriptor = singleton_product_descriptor(puzzle, product_index)
    if descriptor is None:
        return []
    element = descriptor["element"]
    local = tuple(descriptor["localPosition"])
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        world = frame.get("world") or {}
        bonded: set[str] = set()
        for bond in world.get("bonds", []) or []:
            bonded.add(str(bond.get("fromAtomId") or ""))
            bonded.add(str(bond.get("toAtomId") or ""))
        for atom in world.get("atoms", []) or []:
            if str(atom.get("element") or "") != element:
                continue
            atom_id = str(atom.get("id") or "")
            if not atom_id or atom_id in bonded or atom.get("heldBy"):
                continue
            world_pos = tuple(int(value) for value in (atom.get("position") or (0, 0)))
            for rotation in range(6):
                rotated = rotate_hex(local, rotation)
                output_pos = (world_pos[0] - rotated[0], world_pos[1] - rotated[1])
                key = (atom_id, world_pos, output_pos, rotation)
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "productIndex": int(product_index),
                    "element": element,
                    "atomId": atom_id,
                    "atomPosition": [world_pos[0], world_pos[1]],
                    "outputPosition": [output_pos[0], output_pos[1]],
                    "rotation": rotation,
                    "cycle": cycle,
                    "targetSolutionBytesUsed": 0,
                })
    return sorted(result, key=lambda item: (int(item["cycle"]), tuple(item["outputPosition"]), int(item["rotation"])))


def apply_singleton_output_placement(
    solution: dict[str, Any],
    opportunity: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(solution)
    product_index = int(opportunity.get("productIndex") or 0)
    outputs = [
        part for part in result.get("parts", []) or []
        if str(part.get("type") or "") == "out-std" and int(part.get("which") or 0) == product_index
    ]
    if outputs:
        output = outputs[0]
    else:
        output = {
            "id": f"trace-output-{product_index}",
            "type": "out-std",
            "enabled": True,
            "position": [0, 0],
            "length": 1,
            "rotation": 0,
            "which": product_index,
            "armNumber": 0,
            "program": [],
        }
        result.setdefault("parts", []).append(output)
    output["position"] = [int(value) for value in opportunity.get("outputPosition", (0, 0))]
    output["rotation"] = int(opportunity.get("rotation") or 0) % 6
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/trace-singleton-output-placement-v1"
    source.setdefault("traceOutputPlacements", []).append({
        **deepcopy(opportunity),
        "outputPartId": str(output.get("id") or ""),
        "targetSolutionBytesUsed": 0,
    })
    return result


def search_singleton_output_placement(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    product_index: int,
    max_cycles: int = 500,
    opportunity_limit: int = 120,
    result_limit: int = 20,
) -> dict[str, Any]:
    horizon = max(1, int(max_cycles))
    baseline = validate_generated_solution(puzzle, solution, max_cycles=horizon)
    baseline_delivered = int((baseline.get("deliveredByProduct") or {}).get(str(product_index), 0))
    replay = Simulator.from_models(puzzle, solution).run_timeline(build_program_timeline(solution, max_cycles=horizon))
    opportunities = singleton_output_opportunities(puzzle, replay, product_index=product_index)
    opportunities = opportunities[:max(0, int(opportunity_limit))]
    records: list[dict[str, Any]] = []
    for opportunity in opportunities:
        candidate = apply_singleton_output_placement(solution, opportunity)
        validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
        delivered = int((validation.get("deliveredByProduct") or {}).get(str(product_index), 0))
        if delivered <= baseline_delivered:
            continue
        records.append({
            "opportunity": deepcopy(opportunity),
            "delivered": delivered,
            "validation": validation,
            "solution": candidate,
        })
    records.sort(
        key=lambda item: (
            int(item.get("delivered") or 0),
            int(not bool((item.get("validation") or {}).get("terminatedWithError"))),
            int((item.get("validation") or {}).get("completedCycles") or 0),
            -int((item.get("opportunity") or {}).get("cycle") or 0),
        ),
        reverse=True,
    )
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-singleton-output-placement-search",
        "summary": {
            "maxCycles": horizon,
            "productIndex": int(product_index),
            "baselineDelivered": baseline_delivered,
            "opportunityCount": len(opportunities),
            "deliveringVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "bestDelivered": int(selected[0].get("delivered") or 0) if selected else baseline_delivered,
            "targetSolutionBytesUsed": 0,
        },
        "baselineValidation": baseline,
        "opportunities": opportunities,
        "variants": selected,
    }


__all__ = [
    "apply_singleton_output_placement",
    "search_singleton_output_placement",
    "singleton_output_opportunities",
    "singleton_product_descriptor",
]
