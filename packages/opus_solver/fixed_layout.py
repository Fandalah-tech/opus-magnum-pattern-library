from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from typing import Any, Iterator

from packages.opus_engine import SimulationError, Simulator

ACTIONS = (
    "grab", "drop", "rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw",
    "extend", "retract", "track_plus", "track_minus",
)


@dataclass(slots=True, frozen=True)
class LayoutBounds:
    center: tuple[int, int]
    radius: int
    period: int = 7
    motion_radius: int | None = None
    max_active_arms: int = 4
    max_atoms: int = 24
    max_start_configs: int = 0
    max_states_per_depth: int = 100_000


@dataclass(slots=True)
class StartConfiguration:
    index: int
    solution: dict[str, Any]
    signature: tuple


@dataclass(slots=True)
class SearchStats:
    start_configurations: int = 0
    tested_configurations: int = 0
    expanded_states: int = 0
    generated_transitions: int = 0
    collisions: int = 0
    pruned_bounds: int = 0
    deduplicated: int = 0
    peak_frontier: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "startConfigurations": self.start_configurations,
            "testedConfigurations": self.tested_configurations,
            "expandedStates": self.expanded_states,
            "generatedTransitions": self.generated_transitions,
            "collisions": self.collisions,
            "prunedBounds": self.pruned_bounds,
            "deduplicated": self.deduplicated,
            "peakFrontier": self.peak_frontier,
        }


@dataclass(slots=True)
class PeriodSolution:
    start_configuration: StartConfiguration
    program: tuple[dict[str, str | None], ...]
    delivered_per_period: int
    candidate_solution: dict[str, Any]


@dataclass(slots=True)
class SearchResult:
    found: bool
    solution: PeriodSolution | None
    stats: SearchStats
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "found": self.found,
            "reason": self.reason,
            "stats": self.stats.to_dict(),
        }
        if self.solution is not None:
            payload["solution"] = {
                "startConfiguration": self.solution.start_configuration.index,
                "deliveredPerPeriod": self.solution.delivered_per_period,
                "program": [dict(row) for row in self.solution.program],
            }
        return payload


def _axial_radius(position: tuple[int, int], center: tuple[int, int]) -> int:
    q = position[0] - center[0]
    r = position[1] - center[1]
    return max(abs(q), abs(r), abs(q + r))


def _absolute_tracks(solution: dict[str, Any]) -> list[tuple[tuple[int, int], ...]]:
    tracks = []
    for part in solution.get("parts", []):
        if part.get("type") != "track" or not part.get("trackHexes"):
            continue
        origin = tuple(part.get("position") or (0, 0))
        tracks.append(tuple(
            (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
            for cell in part.get("trackHexes", [])
        ))
    return tracks


def _owned_track(part: dict[str, Any], tracks: list[tuple[tuple[int, int], ...]]) -> tuple[tuple[int, int], ...]:
    origin = tuple(part.get("position") or (0, 0))
    return next((track for track in tracks if origin in track), ())


def _is_arm(part: dict[str, Any]) -> bool:
    kind = str(part.get("type") or "")
    return kind.startswith("arm") or kind in {"piston", "baron"}


def _pose_domain(part: dict[str, Any], tracks: list[tuple[tuple[int, int], ...]]) -> tuple[tuple, ...]:
    rotations = range(6)
    lengths = range(1, 4) if part.get("type") == "piston" else (max(1, int(part.get("length") or 1)),)
    track = _owned_track(part, tracks)
    positions = track if track else (tuple(part.get("position") or (0, 0)),)
    return tuple((tuple(pos), int(length), int(rotation)) for pos in positions for length in lengths for rotation in rotations)


def _layout_pose_bounded(simulator: Simulator, bounds: LayoutBounds) -> bool:
    for arm in simulator.arms.values():
        if _axial_radius(tuple(arm.origin), bounds.center) > bounds.radius:
            return False
        if any(_axial_radius(tuple(tip), bounds.center) > bounds.radius for tip in arm.tips().values()):
            return False
    return True


def _runtime_bounded(simulator: Simulator, bounds: LayoutBounds) -> bool:
    if len(simulator.world.atoms) > bounds.max_atoms:
        return False
    if bounds.motion_radius is None:
        return True
    return all(
        _axial_radius(tuple(atom.position), bounds.center) <= bounds.motion_radius
        for atom in simulator.world.atoms.values()
        if "-wheel-" not in str(atom.id)
    )


def enumerate_start_configurations(
    puzzle: dict[str, Any],
    layout: dict[str, Any],
    bounds: LayoutBounds,
) -> list[StartConfiguration]:
    """Phase A: enumerate unique editor-encodable initial manipulator poses."""
    tracks = _absolute_tracks(layout)
    arms = [part for part in layout.get("parts", []) if _is_arm(part)]
    domains = [_pose_domain(part, tracks) for part in arms]
    seen: set[tuple] = set()
    results: list[StartConfiguration] = []

    for poses in product(*domains):
        candidate = deepcopy(layout)
        by_id = {str(part.get("id")): part for part in candidate.get("parts", [])}
        for source, (position, length, rotation) in zip(arms, poses):
            part = by_id[str(source.get("id"))]
            part["position"] = [int(position[0]), int(position[1])]
            part["length"] = int(length)
            part["rotation"] = int(rotation)
        try:
            simulator = Simulator.from_models(puzzle, candidate)
        except Exception:
            continue
        if not _layout_pose_bounded(simulator, bounds):
            continue
        signature = physical_state_key(simulator)
        if signature in seen:
            continue
        seen.add(signature)
        results.append(StartConfiguration(len(results), candidate, signature))
        if bounds.max_start_configs and len(results) >= bounds.max_start_configs:
            break
    return results


def physical_state_key(simulator: Simulator) -> tuple:
    atom_desc = {
        atom_id: (tuple(atom.position), str(atom.element), tuple(sorted(str(x) for x in atom.held_by)))
        for atom_id, atom in simulator.world.atoms.items()
    }
    atoms = tuple(sorted(atom_desc.values()))
    bonds = []
    for bond in simulator.world.bonds.values():
        a, b = atom_desc.get(bond.a), atom_desc.get(bond.b)
        if a is not None and b is not None:
            bonds.append((str(bond.kind), *sorted((a, b))))
    arms = []
    for arm_id, arm in sorted(simulator.arms.items()):
        held = tuple(sorted(
            (int(branch), atom_desc.get(atom_id, ("missing", atom_id)))
            for branch, atom_id in arm.held_atoms.items()
        ))
        arms.append((
            str(arm_id), str(arm.part_type), tuple(arm.origin), int(arm.rotation) % 6,
            int(arm.length), int(arm.track_index), bool(arm.grabbing), held,
        ))
    floating = []
    for key, root_id in (getattr(simulator, "floating_bond_roots", {}) or {}).items():
        bond = simulator.world.bonds.get(key)
        if bond is None:
            continue
        a, b = atom_desc.get(bond.a), atom_desc.get(bond.b)
        if a is not None and b is not None:
            floating.append((str(bond.kind), *sorted((a, b)), atom_desc.get(root_id)))
    return atoms, tuple(sorted(bonds)), tuple(arms), tuple(sorted(floating))


def delivered_total(simulator: Simulator) -> int:
    return sum(int(value) for value in (getattr(simulator, "delivered_products", {}) or {}).values())


def _adjacent(first: tuple[int, int], second: tuple[int, int]) -> bool:
    delta = second[0] - first[0], second[1] - first[1]
    return delta in {(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)}


def legal_actions(simulator: Simulator, arm_id: str) -> tuple[str | None, ...]:
    arm = simulator.arms[arm_id]
    result: list[str | None] = [None]
    if not arm.grabbing and any(simulator.world.atom_at(tip) is not None for tip in arm.tips().values()):
        result.append("grab")
    if arm.held_atoms:
        result.extend(("drop", "pivot_cw", "pivot_ccw"))
    result.extend(("rotate_cw", "rotate_ccw"))
    if arm.part_type == "piston":
        if arm.length < 3:
            result.append("extend")
        if arm.length > int(arm.base_length or 1):
            result.append("retract")
    if arm.track_cells:
        loop = len(arm.track_cells) >= 3 and _adjacent(arm.track_cells[-1], arm.track_cells[0])
        if loop or arm.track_index < len(arm.track_cells) - 1:
            result.append("track_plus")
        if loop or arm.track_index > 0:
            result.append("track_minus")
    return tuple(dict.fromkeys(result))


def _locked_actions(layout: dict[str, Any], period: int) -> dict[tuple[str, int], str]:
    locked: dict[tuple[str, int], str] = {}
    for part in layout.get("parts", []):
        if not _is_arm(part):
            continue
        arm_id = str(part.get("id"))
        for row in part.get("program", []):
            action = str(row.get("instruction") or "")
            cycle = int(row.get("cycle", -1))
            if action in ACTIONS and 0 <= cycle < period:
                locked[(arm_id, cycle)] = action
    return locked


def iter_joint_actions(
    simulator: Simulator,
    phase: int,
    bounds: LayoutBounds,
    locked: dict[tuple[str, int], str],
) -> Iterator[dict[str, str | None]]:
    arm_ids = tuple(sorted(simulator.arms))
    domains = []
    for arm_id in arm_ids:
        forced = locked.get((arm_id, phase))
        domain = legal_actions(simulator, arm_id)
        if forced is not None:
            if forced not in domain:
                return
            domain = (forced,)
        domains.append(domain)
    for values in product(*domains):
        if sum(value is not None for value in values) <= bounds.max_active_arms:
            yield dict(zip(arm_ids, values))


def _compile_solution(start: StartConfiguration, program: tuple[dict[str, str | None], ...]) -> dict[str, Any]:
    candidate = deepcopy(start.solution)
    by_id = {str(part.get("id")): part for part in candidate.get("parts", []) if _is_arm(part)}
    for part in by_id.values():
        part["program"] = []
    for cycle, row in enumerate(program):
        for arm_id, action in row.items():
            if action is not None:
                by_id[arm_id]["program"].append({"cycle": cycle, "instruction": action})
    candidate["name"] = f"fixed-layout P{len(program)} config {start.index}"
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    return candidate


def brute_force_configuration(
    puzzle: dict[str, Any],
    start: StartConfiguration,
    bounds: LayoutBounds,
    stats: SearchStats,
) -> PeriodSolution | None:
    initial = Simulator.from_models(puzzle, start.solution)
    initial_key = physical_state_key(initial)
    initial_delivered = delivered_total(initial)
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
                if depth + 1 == bounds.period:
                    delta = delivered_total(trial) - initial_delivered
                    if key == initial_key and delta > 0:
                        return PeriodSolution(start, new_path, delta, _compile_solution(start, new_path))
                dedupe_key = (key, delivered_total(trial) - initial_delivered)
                if dedupe_key in next_by_key:
                    stats.deduplicated += 1
                    continue
                next_by_key[dedupe_key] = (trial, new_path)
        frontier = list(next_by_key.values())
        if bounds.max_states_per_depth and len(frontier) > bounds.max_states_per_depth:
            frontier = frontier[:bounds.max_states_per_depth]
        stats.peak_frontier = max(stats.peak_frontier, len(frontier))
        if not frontier:
            break
    return None


def solve_fixed_layout(
    puzzle: dict[str, Any],
    layout: dict[str, Any],
    bounds: LayoutBounds,
) -> SearchResult:
    stats = SearchStats()
    configurations = enumerate_start_configurations(puzzle, layout, bounds)
    stats.start_configurations = len(configurations)
    for configuration in configurations:
        stats.tested_configurations += 1
        result = brute_force_configuration(puzzle, configuration, bounds, stats)
        if result is not None:
            return SearchResult(True, result, stats)
    exhaustive = bounds.max_states_per_depth == 0 and bounds.max_start_configs == 0
    reason = "bounded state space exhausted" if exhaustive else "configured search bounds exhausted"
    return SearchResult(False, None, stats, reason)
