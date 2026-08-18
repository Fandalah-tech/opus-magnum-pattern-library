from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator

from .purification_chain import METAL_ORDER, purification_profile
from .reaction_placement import purification_opportunities
from .reaction_station_synthesis import add_purification_station
from .solver import validate_generated_solution


def _opportunity_rank(item: dict[str, Any], frontier_index: int) -> tuple[Any, ...]:
    produced = str(item.get("producedElement") or "")
    produced_index = METAL_ORDER.index(produced) if produced in METAL_ORDER else -1
    advances = produced_index > frontier_index
    # A bonded conversion input can require several unbonders.  Prefer the
    # smallest exact bond-removal set after preferring a true frontier advance.
    unbond_count = len(item.get("unbondCandidates") or [])
    return (
        -int(advances),
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

    This is the natural continuation after the first target-free purification:
    the iron->copper station must remain in place while a new copper->silver
    station is synthesized.  Every required bond on a blocked conversion input
    is given its own replay-derived unbonder before the added purifier fires.
    """

    horizon = max(1, int(max_cycles))
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    frontier_index = int(baseline_profile.get("frontierIndex") if baseline_profile.get("frontierIndex") is not None else -1)

    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    opportunities = purification_opportunities(replay, include_blocked=True)
    opportunities.sort(key=lambda item: _opportunity_rank(item, frontier_index))
    opportunities = opportunities[:max(0, int(opportunity_limit))]

    records: list[dict[str, Any]] = []
    attempted = 0
    skipped_unrepairable = 0
    for opportunity in opportunities:
        produced = str(opportunity.get("producedElement") or "")
        produced_index = METAL_ORDER.index(produced) if produced in METAL_ORDER else -1
        if produced_index <= frontier_index:
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
        candidate = add_purification_station(
            solution,
            opportunity,
            unbond_candidates=unbond_candidates,
        )
        profile = purification_profile(puzzle, candidate, max_cycles=horizon)
        if int(profile.get("count") or 0) <= int(baseline_profile.get("count") or 0):
            continue
        validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
        records.append({
            "repairMode": "additive-multi-unbond+purify" if unbond_candidates else "additive-purify",
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
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-additive-purification-station-search",
        "summary": {
            "maxCycles": horizon,
            "baselinePurificationCount": int(baseline_profile.get("count") or 0),
            "baselineFrontierElement": baseline_profile.get("frontierElement"),
            "opportunityCount": len(opportunities),
            "attemptedAdditiveStationCount": attempted,
            "skippedUnrepairableOpportunityCount": skipped_unrepairable,
            "advancingVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "bestFrontierElement": (selected[0].get("purificationProfile") or {}).get("frontierElement") if selected else baseline_profile.get("frontierElement"),
            "goldReached": bool((selected[0].get("purificationProfile") or {}).get("goldReached")) if selected else bool(baseline_profile.get("goldReached")),
            "targetSolutionBytesUsed": 0,
        },
        "baselinePurificationProfile": baseline_profile,
        "opportunities": opportunities,
        "variants": selected,
    }


__all__ = ["search_additive_purification_stations"]
