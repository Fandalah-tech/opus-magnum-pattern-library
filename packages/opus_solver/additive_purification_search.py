from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator

from .purification_chain import METAL_ORDER, purification_profile
from .reaction_placement import purification_opportunities
from .reaction_station_synthesis import add_purification_station
from .solver import validate_generated_solution


def _opportunity_rank(
    item: dict[str, Any],
    frontier_index: int,
    *,
    replenish_frontier: bool = False,
    precursor_index: int | None = None,
) -> tuple[Any, ...]:
    produced = str(item.get("producedElement") or "")
    produced_index = METAL_ORDER.index(produced) if produced in METAL_ORDER else -1
    advances = produced_index > frontier_index
    replenishes = bool(replenish_frontier and produced_index == frontier_index)
    supports = bool(
        replenish_frontier
        and precursor_index is not None
        and produced_index == precursor_index
    )
    # A bonded conversion input can require several unbonders. Prefer a true
    # frontier advance, then a chemically necessary second copy of the current
    # frontier metal, then replenishment of its immediate precursor, and only
    # then the smallest exact bond-removal set.
    unbond_count = len(item.get("unbondCandidates") or [])
    return (
        -int(advances),
        -int(replenishes),
        -int(supports),
        -produced_index,
        int(item.get("minimumBlockerCount") or 0),
        unbond_count,
        -int(item.get("readyObservationCount") or 0),
        -int(item.get("observationCount") or 0),
        int(item.get("firstCycle") or 0),
        tuple(item.get("origin") or (0, 0)),
        int(item.get("rotation") or 0),
    )


def _record_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    profile = record.get("purificationProfile") or {}
    validation = record.get("validation") or {}
    return (
        int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1),
        int(profile.get("countsByElement", {}).get("gold", 0)),
        int(profile.get("countsByElement", {}).get("silver", 0)),
        int(profile.get("countsByElement", {}).get("copper", 0)),
        int(profile.get("count") or 0),
        int(validation.get("totalDelivered") or 0),
        int(not bool(profile.get("terminatedWithError"))),
        int(profile.get("completedCycles") or 0),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        -len((record.get("opportunity") or {}).get("unbondCandidates") or []),
        int((record.get("opportunity") or {}).get("observationCount") or 0),
    )


def search_additive_purification_stations(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 400,
    opportunity_limit: int = 160,
    result_limit: int = 20,
) -> dict[str, Any]:
    """Add new reaction stations instead of cannibalizing earlier chemistry.

    Purification consumes two equal metals. Reaching a new frontier once is
    therefore not always enough to advance again. If the current frontier has
    fewer than two copies, the search first prefers producing another frontier
    atom. When that reaction itself lacks enough immediate precursor material,
    it may also replenish the preceding metal in the purification ladder. This
    resource-support step is still replay-derived and target-solution-free; it
    prevents a silver frontier from dead-ending merely because only one copper
    remains available to manufacture the second silver.
    """

    horizon = max(1, int(max_cycles))
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    frontier_index = int(
        baseline_profile.get("frontierIndex")
        if baseline_profile.get("frontierIndex") is not None
        else -1
    )
    frontier_element = (
        METAL_ORDER[frontier_index]
        if 0 <= frontier_index < len(METAL_ORDER)
        else None
    )
    counts_by_element = baseline_profile.get("countsByElement") or {}
    frontier_count = int(
        counts_by_element.get(frontier_element, 0)
        if frontier_element is not None
        else 0
    )
    replenish_frontier = bool(
        frontier_element is not None
        and frontier_element != "gold"
        and frontier_count < 2
    )
    precursor_index = (
        frontier_index - 1
        if replenish_frontier and frontier_index > 0
        else None
    )
    precursor_element = (
        METAL_ORDER[precursor_index]
        if precursor_index is not None and 0 <= precursor_index < len(METAL_ORDER)
        else None
    )
    precursor_count = int(
        counts_by_element.get(precursor_element, 0)
        if precursor_element is not None
        else 0
    )

    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    opportunities = purification_opportunities(replay, include_blocked=True)
    opportunities.sort(
        key=lambda item: _opportunity_rank(
            item,
            frontier_index,
            replenish_frontier=replenish_frontier,
            precursor_index=precursor_index,
        )
    )
    opportunities = opportunities[:max(0, int(opportunity_limit))]

    records: list[dict[str, Any]] = []
    attempted = 0
    skipped_unrepairable = 0
    attempted_advance = 0
    attempted_replenishment = 0
    attempted_precursor_support = 0
    for opportunity in opportunities:
        produced = str(opportunity.get("producedElement") or "")
        produced_index = METAL_ORDER.index(produced) if produced in METAL_ORDER else -1
        advances = produced_index > frontier_index
        replenishes = bool(replenish_frontier and produced_index == frontier_index)
        supports_precursor = bool(
            replenish_frontier
            and precursor_index is not None
            and produced_index == precursor_index
        )
        if not (advances or replenishes or supports_precursor):
            continue
        blockers = opportunity.get("blockersAtBestObservation") or {}
        # Additive static glyphs can solve bond blockers, but cannot force an
        # arm to drop an input or vacate an occupied purification output.
        if blockers.get("firstHeld") or blockers.get("secondHeld") or blockers.get("outputOccupied"):
            skipped_unrepairable += 1
            continue
        unbond_candidates = list(opportunity.get("unbondCandidates") or [])
        if (blockers.get("firstBonded") or blockers.get("secondBonded")) and not unbond_candidates:
            skipped_unrepairable += 1
            continue

        attempted += 1
        attempted_advance += int(advances)
        attempted_replenishment += int(replenishes)
        attempted_precursor_support += int(supports_precursor)
        candidate = add_purification_station(
            solution,
            opportunity,
            unbond_candidates=unbond_candidates,
        )
        profile = purification_profile(puzzle, candidate, max_cycles=horizon)
        if int(profile.get("count") or 0) <= int(baseline_profile.get("count") or 0):
            continue
        if replenishes:
            new_frontier_count = int(
                (profile.get("countsByElement") or {}).get(frontier_element, 0)
            )
            if new_frontier_count <= frontier_count:
                continue
        if supports_precursor:
            new_precursor_count = int(
                (profile.get("countsByElement") or {}).get(precursor_element, 0)
            )
            if new_precursor_count <= precursor_count:
                continue
        validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
        records.append({
            "repairMode": (
                "additive-frontier-replenishment-multi-unbond+purify"
                if replenishes and unbond_candidates
                else "additive-frontier-replenishment-purify"
                if replenishes
                else "additive-precursor-support-multi-unbond+purify"
                if supports_precursor and unbond_candidates
                else "additive-precursor-support-purify"
                if supports_precursor
                else "additive-multi-unbond+purify"
                if unbond_candidates
                else "additive-purify"
            ),
            "frontierAdvance": bool(advances),
            "frontierReplenishment": bool(replenishes),
            "precursorSupport": bool(supports_precursor),
            "opportunity": deepcopy(opportunity),
            "addedUnbonderCount": len(unbond_candidates),
            "purificationDelta": int(profile.get("count") or 0) - int(baseline_profile.get("count") or 0),
            "purificationProfile": profile,
            "validation": validation,
            "solution": candidate,
        })

    records.sort(key=_record_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.3.0",
        "kind": "trace-guided-additive-purification-station-search",
        "summary": {
            "maxCycles": horizon,
            "baselinePurificationCount": int(baseline_profile.get("count") or 0),
            "baselineFrontierElement": baseline_profile.get("frontierElement"),
            "baselineFrontierCount": frontier_count,
            "frontierReplenishmentNeeded": replenish_frontier,
            "supportPrecursorElement": precursor_element,
            "baselineSupportPrecursorCount": precursor_count,
            "opportunityCount": len(opportunities),
            "attemptedAdditiveStationCount": attempted,
            "attemptedFrontierAdvanceCount": attempted_advance,
            "attemptedFrontierReplenishmentCount": attempted_replenishment,
            "attemptedPrecursorSupportCount": attempted_precursor_support,
            "skippedUnrepairableOpportunityCount": skipped_unrepairable,
            "advancingVariantCount": sum(bool(record.get("frontierAdvance")) for record in records),
            "replenishingVariantCount": sum(bool(record.get("frontierReplenishment")) for record in records),
            "precursorSupportingVariantCount": sum(bool(record.get("precursorSupport")) for record in records),
            "returnedVariantCount": len(selected),
            "bestFrontierElement": (selected[0].get("purificationProfile") or {}).get("frontierElement") if selected else baseline_profile.get("frontierElement"),
            "bestFrontierCount": int(
                ((selected[0].get("purificationProfile") or {}).get("countsByElement") or {}).get(
                    (selected[0].get("purificationProfile") or {}).get("frontierElement"),
                    0,
                )
            ) if selected else frontier_count,
            "goldReached": bool((selected[0].get("purificationProfile") or {}).get("goldReached")) if selected else bool(baseline_profile.get("goldReached")),
            "targetSolutionBytesUsed": 0,
        },
        "baselinePurificationProfile": baseline_profile,
        "opportunities": opportunities,
        "variants": selected,
    }


__all__ = ["search_additive_purification_stations"]
