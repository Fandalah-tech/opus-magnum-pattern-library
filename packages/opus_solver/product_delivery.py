from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
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
    return result


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
    """Deliver a trace-produced singleton without target solution geometry.

    Product shapes come only from the puzzle contract.  The generated replay
    supplies the product molecule pose.  A synthesized arm moves the molecule
    one 60-degree step before a standard output consumes it, avoiding the
    common illegal direct overlap between a conversion glyph and its product
    output cell.
    """

    horizon = max(1, int(max_cycles))
    baseline_full = replay_summary(puzzle, solution, max_cycles=horizon)
    replay = baseline_full.pop("replay")
    baseline = baseline_full
    opportunities = product_output_opportunities(puzzle, replay, require_unheld=True)
    singleton_indices = {
        index
        for index, product in enumerate(puzzle.get("products", []) or [])
        if len(product.get("atoms", []) or []) == 1 and not product.get("bonds")
    }
    opportunities = [
        item for item in opportunities
        if int(item.get("productIndex") or 0) in singleton_indices
    ][:max(0, int(opportunity_limit))]

    baseline_deliveries = int(baseline.get("productDeliveredCount") or 0)
    baseline_purification = int(baseline.get("purificationCount") or 0)
    records: list[dict[str, Any]] = []
    searched = 0

    for opportunity in opportunities:
        first_cycle = int(opportunity.get("firstCycle") or 0)
        # The observation is a start-of-cycle frame.  Search the exact observed
        # cycle and one cycle later; replay rejects stale pickup attempts.
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
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-singleton-product-delivery-search",
        "summary": {
            "maxCycles": horizon,
            "opportunityCount": len(opportunities),
            "searchedVariantCount": searched,
            "deliveringVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "baselineProductDeliveredCount": baseline_deliveries,
            "bestProductDeliveredCount": int((selected[0].get("summary") or {}).get("productDeliveredCount") or baseline_deliveries) if selected else baseline_deliveries,
            "hasDelivery": bool(selected),
            "targetSolutionBytesUsed": 0,
        },
        "baseline": baseline,
        "opportunities": opportunities,
        "variants": selected,
    }


__all__ = [
    "add_singleton_product_extractor",
    "search_singleton_product_delivery",
]
