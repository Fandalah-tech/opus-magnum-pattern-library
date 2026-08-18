from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_engine.builder import DIRECTIONS, rotate_hex

from .input_footprint_repair import replay_summary
from .output_placement import add_standard_output, product_output_opportunities
from .solver import validate_generated_solution


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _next_arm_number(solution: dict[str, Any]) -> int:
    return 1 + max(
        (
            int(part.get("armNumber") or 0)
            for part in solution.get("parts", []) or []
            if str(part.get("type") or "").startswith("arm")
            or str(part.get("type") or "") in {"piston", "baron"}
        ),
        default=0,
    )


def _singleton_world_position(product: dict[str, Any], opportunity: dict[str, Any]) -> tuple[int, int] | None:
    atoms = list(product.get("atoms", []) or [])
    if len(atoms) != 1 or product.get("bonds"):
        return None
    origin = _position(opportunity.get("origin"))
    rotation = int(opportunity.get("rotation") or 0) % 6
    local = _position(atoms[0].get("position"))
    rotated = rotate_hex(local, rotation)
    return origin[0] + rotated[0], origin[1] + rotated[1]


def _dedupe_observed_products(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the earliest pose per physical molecule and target product."""

    selected: dict[tuple[int, tuple[str, ...]], dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for item in opportunities:
        atom_ids = tuple(sorted(str(value) for value in item.get("atomIds", []) or []))
        if not atom_ids:
            anonymous.append(item)
            continue
        key = (int(item.get("productIndex") or 0), atom_ids)
        previous = selected.get(key)
        if previous is None or int(item.get("firstCycle") or 0) < int(previous.get("firstCycle") or 0):
            selected[key] = item
    result = [*selected.values(), *anonymous]
    return sorted(
        result,
        key=lambda item: (
            int(item.get("firstCycle") or 0),
            int(item.get("productIndex") or 0),
            tuple(item.get("origin") or (0, 0)),
            int(item.get("rotation") or 0),
        ),
    )


def _layout_extent(solution: dict[str, Any]) -> tuple[int, int]:
    """Return a conservative positive edge including explicit track/pipe cells."""

    cells: list[tuple[int, int]] = []
    for part in solution.get("parts", []) or []:
        origin = _position(part.get("position"))
        cells.append(origin)
        for key in ("trackHexes", "pipeHexes"):
            for local in part.get(key, []) or []:
                cells.append((origin[0] + int(local[0]), origin[1] + int(local[1])))
    if not cells:
        return 0, 0
    return max(cell[0] for cell in cells), max(cell[1] for cell in cells)


def ensure_all_standard_outputs(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    reserve_margin: int = 8,
) -> dict[str, Any]:
    """Place one legal output part for every puzzle product contract.

    OMSim refuses to evaluate product metrics until every puzzle product has at
    least one corresponding output part. Missing outputs are therefore placed
    in a conservative reserve area outside the inherited mechanism. These are
    completeness placeholders, not target-solution geometry: the first-product
    transport search still derives its active output from generated replay.
    """

    result = deepcopy(solution)
    products = list(puzzle.get("products", []) or [])
    present = {
        int(part.get("which") or 0)
        for part in result.get("parts", []) or []
        if str(part.get("type") or "").startswith("out-")
    }
    missing = [index for index in range(len(products)) if index not in present]
    if not missing:
        return result

    max_u, max_v = _layout_extent(result)
    max_span = 1
    for product in products:
        positions = [_position(atom.get("position")) for atom in product.get("atoms", []) or []]
        if positions:
            span_u = max(p[0] for p in positions) - min(p[0] for p in positions) + 1
            span_v = max(p[1] for p in positions) - min(p[1] for p in positions) + 1
            max_span = max(max_span, span_u, span_v)
    spacing = max(4, max_span + 3)
    start = (max_u + int(reserve_margin), max_v + int(reserve_margin))

    for ordinal, product_index in enumerate(missing):
        origin = (start[0] + ordinal * spacing, start[1])
        result = add_standard_output(
            result,
            {
                "productIndex": product_index,
                "origin": [origin[0], origin[1]],
                "rotation": 0,
                "firstCycle": None,
                "lastCycle": None,
                "observationCount": 0,
                "atomIds": [],
                "held": False,
                "evidence": "solver-reserved-product-output",
            },
        )
        result.setdefault("source", {}).setdefault("productDeliveryRepairs", []).append({
            "mode": "reserved-output-completeness",
            "productIndex": product_index,
            "origin": [origin[0], origin[1]],
            "targetSolutionBytesUsed": 0,
        })
    return result


def add_singleton_product_extractor(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    opportunity: dict[str, Any],
    *,
    base_rotation: int,
    motion_instruction: str,
    grab_cycle: int | None = None,
) -> dict[str, Any]:
    """Move an observed singleton product one arm rotation into an output."""

    products = list(puzzle.get("products", []) or [])
    product_index = int(opportunity.get("productIndex") or 0)
    if not 0 <= product_index < len(products):
        raise IndexError(f"productIndex {product_index} outside {len(products)} products")
    source_position = _singleton_world_position(products[product_index], opportunity)
    if source_position is None:
        raise ValueError("singleton product extractor requires a one-atom unbonded product")

    direction_index = int(base_rotation) % 6
    tip_direction = DIRECTIONS[direction_index]
    base = (source_position[0] - tip_direction[0], source_position[1] - tip_direction[1])
    steps = -1 if str(motion_instruction) == "rotate_cw" else 1
    relative = (source_position[0] - base[0], source_position[1] - base[1])
    moved = rotate_hex(relative, steps)
    destination = (base[0] + moved[0], base[1] + moved[1])

    output_opportunity = {
        "productIndex": product_index,
        "origin": [destination[0], destination[1]],
        "rotation": 0,
        "firstCycle": int(opportunity.get("firstCycle") or 0) + 2,
        "lastCycle": int(opportunity.get("lastCycle") or opportunity.get("firstCycle") or 0) + 2,
        "observationCount": 1,
        "atomIds": list(opportunity.get("atomIds") or []),
        "held": False,
        "evidence": "generated-replay-singleton-extraction-target",
    }
    result = add_standard_output(solution, output_opportunity)

    existing_ids = {str(part.get("id") or "") for part in result.get("parts", []) or []}
    serial = 0
    while f"product-extractor-arm-{serial}" in existing_ids:
        serial += 1
    part_id = f"product-extractor-arm-{serial}"
    resolved_grab_cycle = int(opportunity.get("firstCycle") or 0) if grab_cycle is None else int(grab_cycle)
    result.setdefault("parts", []).append({
        "id": part_id,
        "type": "arm1",
        "enabled": True,
        "position": [base[0], base[1]],
        "length": 1,
        "rotation": direction_index,
        "which": 0,
        "armNumber": _next_arm_number(result),
        "program": [
            {"cycle": resolved_grab_cycle, "instruction": "grab"},
            {"cycle": resolved_grab_cycle + 1, "instruction": str(motion_instruction)},
            {"cycle": resolved_grab_cycle + 2, "instruction": "drop"},
        ],
    })
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/trace-guided-product-delivery-v1"
    source.setdefault("productDeliveryRepairs", []).append({
        "mode": "singleton-one-rotation",
        "productIndex": product_index,
        "observedOpportunity": deepcopy(opportunity),
        "armPartId": part_id,
        "sourcePosition": [source_position[0], source_position[1]],
        "basePosition": [base[0], base[1]],
        "baseRotation": direction_index,
        "motionInstruction": str(motion_instruction),
        "destination": [destination[0], destination[1]],
        "grabCycle": resolved_grab_cycle,
        "motionCycle": resolved_grab_cycle + 1,
        "dropCycle": resolved_grab_cycle + 2,
        "targetSolutionBytesUsed": 0,
    })
    return ensure_all_standard_outputs(puzzle, result)


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    summary = record.get("summary") or {}
    validation = record.get("validation") or {}
    return (
        int(summary.get("productDeliveredCount") or 0),
        int(validation.get("totalDelivered") or 0),
        int(summary.get("purificationCount") or 0),
        int(not bool(summary.get("terminatedWithError"))),
        int(summary.get("completedCycles") or 0),
        -int(record.get("grabDelay") or 0),
    )


def search_singleton_product_delivery(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 500,
    opportunity_limit: int = 60,
    result_limit: int = 20,
) -> dict[str, Any]:
    """Deliver a trace-produced singleton without target solution geometry."""

    horizon = max(1, int(max_cycles))
    baseline_full = replay_summary(puzzle, solution, max_cycles=horizon)
    replay = baseline_full.pop("replay")
    baseline = baseline_full
    raw_opportunities = product_output_opportunities(puzzle, replay, require_unheld=True)
    singleton_indices = {
        index
        for index, product in enumerate(puzzle.get("products", []) or [])
        if len(product.get("atoms", []) or []) == 1 and not product.get("bonds")
    }
    raw_opportunities = [
        item for item in raw_opportunities
        if int(item.get("productIndex") or 0) in singleton_indices
    ]
    opportunities = _dedupe_observed_products(raw_opportunities)[:max(0, int(opportunity_limit))]

    baseline_deliveries = int(baseline.get("productDeliveredCount") or 0)
    baseline_purification = int(baseline.get("purificationCount") or 0)
    records: list[dict[str, Any]] = []
    searched = 0

    for opportunity in opportunities:
        first_cycle = int(opportunity.get("firstCycle") or 0)
        for delay in (0, 1):
            for base_rotation in range(6):
                for instruction in ("rotate_cw", "rotate_ccw"):
                    searched += 1
                    candidate = add_singleton_product_extractor(
                        puzzle,
                        solution,
                        opportunity,
                        base_rotation=base_rotation,
                        motion_instruction=instruction,
                        grab_cycle=first_cycle + delay,
                    )
                    summary = replay_summary(puzzle, candidate, max_cycles=horizon)
                    summary.pop("replay", None)
                    if int(summary.get("productDeliveredCount") or 0) <= baseline_deliveries:
                        continue
                    if int(summary.get("purificationCount") or 0) < baseline_purification:
                        continue
                    validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
                    records.append({
                        "opportunity": deepcopy(opportunity),
                        "grabDelay": delay,
                        "baseRotation": base_rotation,
                        "motionInstruction": instruction,
                        "summary": summary,
                        "validation": validation,
                        "solution": candidate,
                    })

    records.sort(key=_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.3.0",
        "kind": "trace-guided-singleton-product-delivery-search",
        "summary": {
            "maxCycles": horizon,
            "rawOpportunityCount": len(raw_opportunities),
            "opportunityCount": len(opportunities),
            "searchedVariantCount": searched,
            "deliveringVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "baselineProductDeliveredCount": baseline_deliveries,
            "bestProductDeliveredCount": int((selected[0].get("summary") or {}).get("productDeliveredCount") or baseline_deliveries) if selected else baseline_deliveries,
            "hasDelivery": bool(selected),
            "allProductOutputsPlaced": bool(selected) and all(
                index in {
                    int(part.get("which") or 0)
                    for part in (selected[0].get("solution") or {}).get("parts", []) or []
                    if str(part.get("type") or "").startswith("out-")
                }
                for index in range(len(puzzle.get("products", []) or []))
            ),
            "targetSolutionBytesUsed": 0,
        },
        "baseline": baseline,
        "opportunities": opportunities,
        "variants": selected,
    }


__all__ = [
    "add_singleton_product_extractor",
    "ensure_all_standard_outputs",
    "search_singleton_product_delivery",
]
