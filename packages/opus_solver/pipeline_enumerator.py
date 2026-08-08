from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.opus_engine import SimulationError, Simulator

from .fixed_layout import (
    LayoutBounds,
    StartConfiguration,
    _locked_actions,
    _runtime_bounded,
    delivered_total,
    enumerate_start_configurations,
    iter_joint_actions,
    physical_state_key,
)


@dataclass(slots=True)
class PipelineCandidate:
    start_configuration: int
    depth: int
    delivered: int
    program: tuple[dict[str, str | None], ...]
    exact_state_key: tuple
    match_key: tuple
    rotation_parity: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "startConfiguration": self.start_configuration,
            "depth": self.depth,
            "delivered": self.delivered,
            "program": [dict(row) for row in self.program],
            "rotationParity": list(self.rotation_parity),
            "matchKey": repr(self.match_key),
        }


@dataclass(slots=True)
class PipelineStats:
    start_configurations: int = 0
    tested_configurations: int = 0
    expanded_states: int = 0
    generated_transitions: int = 0
    collisions: int = 0
    pruned_bounds: int = 0
    deduplicated: int = 0
    peak_frontier: int = 0
    depth_frontiers: dict[int, int] = field(default_factory=dict)
    one_by_5: int = 0
    one_by_6: int = 0
    two_by_7: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "startConfigurations": self.start_configurations,
            "testedConfigurations": self.tested_configurations,
            "expandedStates": self.expanded_states,
            "generatedTransitions": self.generated_transitions,
            "collisions": self.collisions,
            "prunedBounds": self.pruned_bounds,
            "deduplicated": self.deduplicated,
            "peakFrontier": self.peak_frontier,
            "depthFrontiers": {str(k): v for k, v in sorted(self.depth_frontiers.items())},
            "oneBy5": self.one_by_5,
            "oneBy6": self.one_by_6,
            "twoBy7": self.two_by_7,
        }


@dataclass(slots=True)
class PipelineSearchResult:
    one_by_5: list[PipelineCandidate]
    one_by_6: list[PipelineCandidate]
    two_by_7: list[PipelineCandidate]
    match_groups: list[dict[str, Any]]
    stats: PipelineStats

    @property
    def found_two_by_7(self) -> bool:
        return bool(self.two_by_7)

    def to_dict(self) -> dict[str, Any]:
        return {
            "foundTwoBy7": self.found_two_by_7,
            "stats": self.stats.to_dict(),
            "oneBy5": [x.to_dict() for x in self.one_by_5],
            "oneBy6": [x.to_dict() for x in self.one_by_6],
            "twoBy7": [x.to_dict() for x in self.two_by_7],
            "matchGroups": self.match_groups,
        }


def _rotation_parity(simulator: Simulator) -> tuple[int, ...]:
    """Coarse parity class used only for pipeline compatibility ranking.

    This is deliberately not a proof of mergeability.  It captures the even/odd
    rotation class of each manipulator at the pipeline boundary, which is useful
    for triangle-isomorphism matching while the exact simulator remains the final
    authority for any 2-by-7 claim.
    """
    return tuple(int(arm.rotation) % 2 for _, arm in sorted(simulator.arms.items()))


def _match_key(simulator: Simulator) -> tuple:
    """Coarse residual-state key for grouping potentially compatible pipelines.

    Exact arm rotations are reduced to parity, but origin/length/track/grab state
    and the molecular world remain exact.  This can identify promising +0/+1
    pairings without claiming that the pair is executable when overlapped.
    """
    exact = physical_state_key(simulator)
    atoms, bonds, arms, floating = exact
    coarse_arms = tuple(
        (arm_id, part_type, origin, rotation % 2, length, track_index, grabbing, held)
        for arm_id, part_type, origin, rotation, length, track_index, grabbing, held in arms
    )
    return atoms, bonds, coarse_arms, floating


def _candidate(start: StartConfiguration, depth: int, simulator: Simulator, path: tuple[dict[str, str | None], ...]) -> PipelineCandidate:
    return PipelineCandidate(
        start_configuration=start.index,
        depth=depth,
        delivered=delivered_total(simulator),
        program=path,
        exact_state_key=physical_state_key(simulator),
        match_key=_match_key(simulator),
        rotation_parity=_rotation_parity(simulator),
    )


def _catalog_unique(catalog: list[PipelineCandidate], seen: set[tuple], item: PipelineCandidate, limit: int) -> None:
    key = (item.start_configuration, item.depth, item.exact_state_key, item.delivered)
    if key in seen:
        return
    seen.add(key)
    if limit <= 0 or len(catalog) < limit:
        catalog.append(item)


def enumerate_short_pipelines_for_configuration(
    puzzle: dict[str, Any],
    start: StartConfiguration,
    bounds: LayoutBounds,
    stats: PipelineStats,
    *,
    max_depth: int = 7,
    catalog_limit: int = 5000,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[PipelineCandidate], list[PipelineCandidate], list[PipelineCandidate]]:
    initial = Simulator.from_models(puzzle, start.solution)
    initial_delivered = delivered_total(initial)
    locked = _locked_actions(start.solution, max_depth)
    frontier: list[tuple[Simulator, tuple[dict[str, str | None], ...]]] = [(initial, ())]
    one5: list[PipelineCandidate] = []
    one6: list[PipelineCandidate] = []
    two7: list[PipelineCandidate] = []
    seen5: set[tuple] = set()
    seen6: set[tuple] = set()
    seen7: set[tuple] = set()

    for depth in range(max_depth):
        phase = depth
        next_by_key: dict[tuple, tuple[Simulator, tuple[dict[str, str | None], ...]]] = {}
        for simulator, path in frontier:
            stats.expanded_states += 1
            for row in iter_joint_actions(simulator, phase, bounds, locked):
                stats.generated_transitions += 1
                trial = deepcopy(simulator)
                try:
                    trial.step(row)
                except SimulationError:
                    stats.collisions += 1
                    continue
                if not _runtime_bounded(trial, bounds):
                    stats.pruned_bounds += 1
                    continue
                new_path = path + (row,)
                delta = delivered_total(trial) - initial_delivered
                exact = physical_state_key(trial)
                dedupe_key = (exact, delta)
                if dedupe_key in next_by_key:
                    stats.deduplicated += 1
                    continue
                next_by_key[dedupe_key] = (trial, new_path)

        frontier = list(next_by_key.values())
        if bounds.max_states_per_depth and len(frontier) > bounds.max_states_per_depth:
            frontier = frontier[: bounds.max_states_per_depth]
        level = depth + 1
        stats.depth_frontiers[level] = stats.depth_frontiers.get(level, 0) + len(frontier)
        stats.peak_frontier = max(stats.peak_frontier, len(frontier))

        if level in (5, 6, 7):
            for simulator, path in frontier:
                delta = delivered_total(simulator) - initial_delivered
                if level == 5 and delta >= 1:
                    _catalog_unique(one5, seen5, _candidate(start, level, simulator, path), catalog_limit)
                elif level == 6 and delta >= 1:
                    _catalog_unique(one6, seen6, _candidate(start, level, simulator, path), catalog_limit)
                elif level == 7 and delta >= 2:
                    _catalog_unique(two7, seen7, _candidate(start, level, simulator, path), catalog_limit)

        if progress is not None:
            progress({
                "event": "depth",
                "config": start.index,
                "depth": level,
                "frontier": len(frontier),
                "oneBy5": len(one5),
                "oneBy6": len(one6),
                "twoBy7": len(two7),
                "stats": stats.to_dict(),
            })
        if not frontier:
            break

    stats.one_by_5 += len(one5)
    stats.one_by_6 += len(one6)
    stats.two_by_7 += len(two7)
    return one5, one6, two7


def _build_match_groups(one5: list[PipelineCandidate], one6: list[PipelineCandidate], *, max_groups: int = 500) -> list[dict[str, Any]]:
    buckets5: dict[tuple, list[PipelineCandidate]] = {}
    buckets6: dict[tuple, list[PipelineCandidate]] = {}
    for item in one5:
        buckets5.setdefault((item.match_key, item.rotation_parity), []).append(item)
    for item in one6:
        buckets6.setdefault((item.match_key, item.rotation_parity), []).append(item)

    groups: list[dict[str, Any]] = []
    for key in sorted(set(buckets5).intersection(buckets6), key=repr):
        a = buckets5[key]
        b = buckets6[key]
        groups.append({
            "rotationParity": list(key[1]),
            "fiveCycleCount": len(a),
            "sixCycleCount": len(b),
            "fiveCycleConfigs": sorted({x.start_configuration for x in a}),
            "sixCycleConfigs": sorted({x.start_configuration for x in b}),
            "matchKey": repr(key[0]),
        })
        if len(groups) >= max_groups:
            break
    return groups


def search_short_pipelines(
    puzzle: dict[str, Any],
    layout: dict[str, Any],
    bounds: LayoutBounds,
    *,
    offset: int = 0,
    limit: int = 1,
    catalog_limit: int = 5000,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> PipelineSearchResult:
    configurations = enumerate_start_configurations(puzzle, layout, bounds)
    selected = configurations[max(0, offset): max(0, offset) + max(0, limit)]
    stats = PipelineStats(start_configurations=len(configurations))
    all5: list[PipelineCandidate] = []
    all6: list[PipelineCandidate] = []
    all7: list[PipelineCandidate] = []

    for start in selected:
        stats.tested_configurations += 1
        if progress is not None:
            progress({"event": "configuration_start", "config": start.index, "stats": stats.to_dict()})
        one5, one6, two7 = enumerate_short_pipelines_for_configuration(
            puzzle,
            start,
            bounds,
            stats,
            max_depth=7,
            catalog_limit=catalog_limit,
            progress=progress,
        )
        all5.extend(one5)
        all6.extend(one6)
        all7.extend(two7)
        if progress is not None:
            progress({
                "event": "configuration_end",
                "config": start.index,
                "oneBy5": len(one5),
                "oneBy6": len(one6),
                "twoBy7": len(two7),
                "stats": stats.to_dict(),
            })

    return PipelineSearchResult(
        one_by_5=all5,
        one_by_6=all6,
        two_by_7=all7,
        match_groups=_build_match_groups(all5, all6),
        stats=stats,
    )
