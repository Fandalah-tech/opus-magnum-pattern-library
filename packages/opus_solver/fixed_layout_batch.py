from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from packages.opus_engine import SimulationError, Simulator

from .fixed_layout import (
    LayoutBounds,
    PeriodSolution,
    SearchStats,
    StartConfiguration,
    _compile_solution,
    _locked_actions,
    _runtime_bounded,
    delivered_total,
    enumerate_start_configurations,
    iter_joint_actions,
    physical_state_key,
)


@dataclass(slots=True)
class BatchSearchResult:
    found: bool
    solution: PeriodSolution | None
    stats: SearchStats
    config_offset: int
    config_limit: int
    total_configurations: int
    tested_indices: list[int]
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "found": self.found,
            "reason": self.reason,
            "configOffset": self.config_offset,
            "configLimit": self.config_limit,
            "totalConfigurations": self.total_configurations,
            "testedIndices": self.tested_indices,
            "stats": self.stats.to_dict(),
        }
        if self.solution is not None:
            payload["solution"] = {
                "startConfiguration": self.solution.start_configuration.index,
                "deliveredPerPeriod": self.solution.delivered_per_period,
                "program": [dict(row) for row in self.solution.program],
            }
        return payload


def _run_program_period(simulator: Simulator, program: tuple[dict[str, str | None], ...], bounds: LayoutBounds) -> bool:
    for row in program:
        try:
            simulator.step(row)
        except SimulationError:
            return False
        if not _runtime_bounded(simulator, bounds):
            return False
    return True


def verify_periodic_program(
    puzzle: dict[str, Any],
    start: StartConfiguration,
    program: tuple[dict[str, str | None], ...],
    bounds: LayoutBounds,
    *,
    max_periods: int = 5,
) -> int:
    """Prove a steady repeated P-period loop, allowing a startup transient."""
    simulator = Simulator.from_models(puzzle, start.solution)
    previous_key = physical_state_key(simulator)
    previous_delivered = delivered_total(simulator)
    for _ in range(max_periods):
        if not _run_program_period(simulator, program, bounds):
            return 0
        key = physical_state_key(simulator)
        delivered = delivered_total(simulator)
        delta = delivered - previous_delivered
        if key == previous_key and delta > 0:
            return delta
        previous_key = key
        previous_delivered = delivered
    return 0


def brute_force_configuration_steady(
    puzzle: dict[str, Any],
    start: StartConfiguration,
    bounds: LayoutBounds,
    stats: SearchStats,
    *,
    verification_periods: int = 5,
) -> PeriodSolution | None:
    initial = Simulator.from_models(puzzle, start.solution)
    locked = _locked_actions(start.solution, bounds.period)
    frontier: list[tuple[Simulator, tuple[dict[str, str | None], ...]]] = [(initial, ())]

    for depth in range(bounds.period):
        phase = depth % bounds.period
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
                key = physical_state_key(trial)
                new_path = path + (row,)
                dedupe_key = (key, delivered_total(trial))
                if dedupe_key in next_by_key:
                    stats.deduplicated += 1
                    continue
                next_by_key[dedupe_key] = (trial, new_path)

        frontier = list(next_by_key.values())
        if bounds.max_states_per_depth and len(frontier) > bounds.max_states_per_depth:
            frontier = frontier[:bounds.max_states_per_depth]
        stats.peak_frontier = max(stats.peak_frontier, len(frontier))
        if not frontier:
            return None

    for _, path in frontier:
        delta = verify_periodic_program(
            puzzle, start, path, bounds, max_periods=verification_periods,
        )
        if delta > 0:
            return PeriodSolution(start, path, delta, _compile_solution(start, path))
    return None


def solve_fixed_layout_batch(
    puzzle: dict[str, Any],
    layout: dict[str, Any],
    bounds: LayoutBounds,
    *,
    offset: int = 0,
    limit: int = 64,
    verification_periods: int = 5,
) -> BatchSearchResult:
    enum_bounds = LayoutBounds(
        center=bounds.center,
        radius=bounds.radius,
        period=bounds.period,
        motion_radius=bounds.motion_radius,
        max_active_arms=bounds.max_active_arms,
        max_atoms=bounds.max_atoms,
        max_start_configs=0,
        max_states_per_depth=bounds.max_states_per_depth,
    )
    configurations = enumerate_start_configurations(puzzle, layout, enum_bounds)
    total = len(configurations)
    selected = configurations[max(0, offset): max(0, offset) + max(0, limit)]
    stats = SearchStats(start_configurations=total)
    tested: list[int] = []
    for configuration in selected:
        tested.append(configuration.index)
        stats.tested_configurations += 1
        result = brute_force_configuration_steady(
            puzzle,
            configuration,
            bounds,
            stats,
            verification_periods=verification_periods,
        )
        if result is not None:
            return BatchSearchResult(True, result, stats, offset, limit, total, tested)
    return BatchSearchResult(
        False, None, stats, offset, limit, total, tested,
        reason="batch exhausted without proven periodic solution",
    )
