from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator

from .reaction_placement import (
    METAL_ORDER,
    apply_purification_placement,
    apply_purification_unbond_repair,
    purification_opportunities,
)
from .solver import validate_generated_solution


def _purification_profile_from_replay(replay: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    cycles: dict[str, list[int]] = {}
    for frame in replay.get("frames", []) or []:
        frame_cycle = int(frame.get("cycle") or 0)
        for event in frame.get("events", []) or []:
            if str(event.get("kind") or "") != "atom-purified":
                continue
            element = str(event.get("element") or event.get("toElement") or "")
            if element not in METAL_ORDER:
                continue
            counts[element] += 1
            cycles.setdefault(element, []).append(int(event.get("cycle", frame_cycle) or frame_cycle))
    frontier_index = max((METAL_ORDER.index(element) for element in counts), default=-1)
    return {
        "count": sum(counts.values()),
        "countsByElement": {element: int(counts.get(element, 0)) for element in METAL_ORDER if counts.get(element)},
        "cyclesByElement": {element: values for element, values in cycles.items()},
        "frontierIndex": frontier_index,
        "frontierElement": METAL_ORDER[frontier_index] if frontier_index >= 0 else None,
        "goldReached": int(counts.get("gold", 0)) > 0,
    }


def purification_profile(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int,
) -> dict[str, Any]:
    horizon = max(1, int(max_cycles))
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    profile = _purification_profile_from_replay(replay)
    profile.update({
        "completedCycles": int((replay.get("summary") or {}).get("completedCycles") or 0),
        "terminatedWithError": bool((replay.get("summary") or {}).get("terminatedWithError")),
    })
    return profile


def _solution_signature(solution: dict[str, Any]) -> str:
    parts = [
        {
            "type": str(part.get("type") or ""),
            "position": [int(value) for value in (part.get("position") or (0, 0))],
            "rotation": int(part.get("rotation") or 0) % 6,
            "length": int(part.get("length") or 1),
            "which": int(part.get("which") or 0),
            "program": [
                (int(item.get("cycle") or 0), str(item.get("instruction") or ""))
                for item in (part.get("program") or [])
            ],
        }
        for part in solution.get("parts", []) or []
    ]
    return json.dumps(parts, sort_keys=True, separators=(",", ":"))


def _opportunity_key(item: dict[str, Any], *, frontier_index: int) -> tuple[Any, ...]:
    produced = str(item.get("producedElement") or "")
    produced_index = METAL_ORDER.index(produced) if produced in METAL_ORDER else -1
    advances_frontier = produced_index > frontier_index
    replenishes_frontier = produced_index == frontier_index
    return (
        -int(advances_frontier),
        -int(replenishes_frontier),
        -produced_index,
        int(item.get("minimumBlockerCount") or 0),
        -int(bool(item.get("unbondCandidates"))),
        -int(item.get("readyObservationCount") or 0),
        -int(item.get("observationCount") or 0),
        int(item.get("firstCycle") or 0),
        tuple(item.get("origin") or (0, 0)),
        int(item.get("rotation") or 0),
    )


def _record_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    validation = record.get("validation") or {}
    profile = record.get("purificationProfile") or {}
    opportunity = record.get("opportunity") or {}
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        int(profile.get("frontierIndex") or -1),
        int(profile.get("count") or 0),
        int(profile.get("countsByElement", {}).get("gold", 0)),
        int(profile.get("countsByElement", {}).get("silver", 0)),
        int(profile.get("countsByElement", {}).get("copper", 0)),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        -int(opportunity.get("minimumBlockerCount") or 0),
        int(opportunity.get("observationCount") or 0),
    )


def search_next_purification_step(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 256,
    opportunity_limit: int = 60,
    variant_limit: int = 120,
    result_limit: int = 12,
) -> dict[str, Any]:
    """Find a new static purification station that advances an existing blind machine.

    A candidate is retained only when replay proves strictly more purification
    events than the input machine.  This lets the search accumulate several
    fixed unbonder/purifier stations without consulting target solution bytes.
    """

    horizon = max(1, int(max_cycles))
    baseline_validation = validate_generated_solution(puzzle, solution, max_cycles=horizon)
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    frontier_index = int(baseline_profile.get("frontierIndex") or -1)

    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    opportunities = purification_opportunities(replay, include_blocked=True)
    opportunities.sort(key=lambda item: _opportunity_key(item, frontier_index=frontier_index))
    opportunities = opportunities[:max(0, int(opportunity_limit))]

    purifier_count = sum(
        str(part.get("type") or "") == "glyph-purification"
        for part in solution.get("parts", []) or []
    )
    unbonder_count = sum(
        str(part.get("type") or "") == "unbonder"
        for part in solution.get("parts", []) or []
    )

    records: list[dict[str, Any]] = []
    budget = max(0, int(variant_limit))

    def evaluate(
        candidate: dict[str, Any],
        *,
        repair_mode: str,
        purifier_index: int,
        opportunity: dict[str, Any],
        unbonder_index: int | None = None,
        unbond_candidate: dict[str, Any] | None = None,
    ) -> None:
        validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
        purified = int((validation.get("eventCounts") or {}).get("atom-purified") or 0)
        if purified <= int(baseline_profile.get("count") or 0):
            return
        profile = purification_profile(puzzle, candidate, max_cycles=horizon)
        if int(profile.get("count") or 0) <= int(baseline_profile.get("count") or 0):
            return
        records.append({
            "repairMode": repair_mode,
            "purifierIndex": int(purifier_index),
            "unbonderIndex": int(unbonder_index) if unbonder_index is not None else None,
            "opportunity": deepcopy(opportunity),
            "unbondCandidate": deepcopy(unbond_candidate) if unbond_candidate is not None else None,
            "purificationDelta": int(profile.get("count") or 0) - int(baseline_profile.get("count") or 0),
            "purificationProfile": profile,
            "validation": validation,
            "solution": candidate,
        })

    attempted = 0
    for opportunity in opportunities:
        if attempted >= budget:
            break
        blocker_count = int(opportunity.get("minimumBlockerCount") or 0)
        unbond_candidates = list(opportunity.get("unbondCandidates") or [])

        if blocker_count == 0:
            for purifier_index in range(purifier_count):
                if attempted >= budget:
                    break
                attempted += 1
                evaluate(
                    apply_purification_placement(
                        solution,
                        purifier_index=purifier_index,
                        opportunity=opportunity,
                    ),
                    repair_mode="purify-only",
                    purifier_index=purifier_index,
                    opportunity=opportunity,
                )
            continue

        # Current blind GEN249 evidence is dominated by exactly one residual
        # bond blocker.  Couple one inherited unbonder to that blocker and keep
        # the search bounded; held/output blockers require a different repair
        # family and are not blindly papered over here.
        if blocker_count != 1 or not unbond_candidates or unbonder_count <= 0:
            continue
        for unbond_candidate in unbond_candidates:
            for unbonder_index in range(unbonder_count):
                for purifier_index in range(purifier_count):
                    if attempted >= budget:
                        break
                    attempted += 1
                    evaluate(
                        apply_purification_unbond_repair(
                            solution,
                            purifier_index=purifier_index,
                            unbonder_index=unbonder_index,
                            opportunity=opportunity,
                            unbond_candidate=unbond_candidate,
                        ),
                        repair_mode="unbond+purify",
                        purifier_index=purifier_index,
                        unbonder_index=unbonder_index,
                        opportunity=opportunity,
                        unbond_candidate=unbond_candidate,
                    )
                if attempted >= budget:
                    break
            if attempted >= budget:
                break

    records.sort(key=_record_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-next-purification-step",
        "summary": {
            "maxCycles": horizon,
            "baselinePurificationCount": int(baseline_profile.get("count") or 0),
            "baselineFrontierElement": baseline_profile.get("frontierElement"),
            "opportunityCount": len(opportunities),
            "attemptedVariantCount": attempted,
            "advancingVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "bestFrontierElement": (selected[0].get("purificationProfile") or {}).get("frontierElement") if selected else baseline_profile.get("frontierElement"),
            "targetSolutionBytesUsed": 0,
        },
        "baselineValidation": baseline_validation,
        "baselinePurificationProfile": baseline_profile,
        "opportunities": opportunities,
        "variants": selected,
    }


def search_purification_chain(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 256,
    depth: int = 4,
    beam_width: int = 3,
    opportunity_limit: int = 60,
    variant_limit: int = 120,
    result_limit: int = 10,
) -> dict[str, Any]:
    """Iteratively accumulate target-free purification stations.

    Each generation must increase the replayed purification count.  Beam states
    are deduplicated by their physical part poses/programs, and the search stops
    early if a gold purification event is observed.
    """

    horizon = max(1, int(max_cycles))
    initial_validation = validate_generated_solution(puzzle, solution, max_cycles=horizon)
    initial_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    beam = [{
        "solution": deepcopy(solution),
        "validation": initial_validation,
        "purificationProfile": initial_profile,
        "steps": [],
    }]
    generations: list[dict[str, Any]] = []

    for generation in range(max(0, int(depth))):
        candidates: list[dict[str, Any]] = []
        for parent_index, state in enumerate(beam):
            step_search = search_next_purification_step(
                puzzle,
                state["solution"],
                max_cycles=horizon,
                opportunity_limit=opportunity_limit,
                variant_limit=variant_limit,
                result_limit=max(result_limit, beam_width * 3),
            )
            for variant in step_search.get("variants", []) or []:
                step = {
                    "generation": generation + 1,
                    "parentIndex": parent_index,
                    "repairMode": variant.get("repairMode"),
                    "purifierIndex": variant.get("purifierIndex"),
                    "unbonderIndex": variant.get("unbonderIndex"),
                    "producedElement": (variant.get("opportunity") or {}).get("producedElement"),
                    "purificationDelta": variant.get("purificationDelta"),
                    "opportunity": deepcopy(variant.get("opportunity") or {}),
                    "unbondCandidate": deepcopy(variant.get("unbondCandidate")),
                }
                candidates.append({
                    "solution": variant["solution"],
                    "validation": variant["validation"],
                    "purificationProfile": variant["purificationProfile"],
                    "steps": [*state.get("steps", []), step],
                })

        deduped: dict[str, dict[str, Any]] = {}
        for state in candidates:
            signature = _solution_signature(state["solution"])
            existing = deduped.get(signature)
            ranked = {
                "validation": state["validation"],
                "purificationProfile": state["purificationProfile"],
                "opportunity": (state.get("steps") or [{}])[-1].get("opportunity", {}),
            }
            if existing is None:
                deduped[signature] = state
                continue
            existing_ranked = {
                "validation": existing["validation"],
                "purificationProfile": existing["purificationProfile"],
                "opportunity": (existing.get("steps") or [{}])[-1].get("opportunity", {}),
            }
            if _record_rank(ranked) > _record_rank(existing_ranked):
                deduped[signature] = state

        ordered = sorted(
            deduped.values(),
            key=lambda state: _record_rank({
                "validation": state["validation"],
                "purificationProfile": state["purificationProfile"],
                "opportunity": (state.get("steps") or [{}])[-1].get("opportunity", {}),
            }),
            reverse=True,
        )
        beam = ordered[:max(1, int(beam_width))]
        generations.append({
            "generation": generation + 1,
            "candidateCount": len(candidates),
            "dedupedCandidateCount": len(deduped),
            "beamCount": len(beam),
            "bestPurificationProfile": deepcopy((beam[0].get("purificationProfile") if beam else initial_profile)),
            "bestStepCount": len(beam[0].get("steps", [])) if beam else 0,
        })
        if not beam or not candidates:
            break
        if bool((beam[0].get("purificationProfile") or {}).get("goldReached")):
            break

    ordered_final = sorted(
        beam,
        key=lambda state: _record_rank({
            "validation": state["validation"],
            "purificationProfile": state["purificationProfile"],
            "opportunity": (state.get("steps") or [{}])[-1].get("opportunity", {}),
        }),
        reverse=True,
    )
    best = ordered_final[0] if ordered_final else {
        "solution": deepcopy(solution),
        "validation": initial_validation,
        "purificationProfile": initial_profile,
        "steps": [],
    }
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-purification-chain-search",
        "summary": {
            "maxCycles": horizon,
            "requestedDepth": max(0, int(depth)),
            "beamWidth": max(1, int(beam_width)),
            "generationCount": len(generations),
            "initialPurificationCount": int(initial_profile.get("count") or 0),
            "initialFrontierElement": initial_profile.get("frontierElement"),
            "bestPurificationCount": int((best.get("purificationProfile") or {}).get("count") or 0),
            "bestFrontierElement": (best.get("purificationProfile") or {}).get("frontierElement"),
            "goldReached": bool((best.get("purificationProfile") or {}).get("goldReached")),
            "stepCount": len(best.get("steps", [])),
            "targetSolutionBytesUsed": 0,
        },
        "initialPurificationProfile": initial_profile,
        "generations": generations,
        "best": best,
    }


__all__ = [
    "purification_profile",
    "search_next_purification_step",
    "search_purification_chain",
]
