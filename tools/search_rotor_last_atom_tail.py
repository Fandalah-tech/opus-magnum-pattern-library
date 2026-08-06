from __future__ import annotations

import base64
import json
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes
from packages.opus_solver.beam_explorer import explore_simulator_beam
from tools.github_live_status import GitHubLiveStatusPublisher

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-last-isolated-atom-prefix.solution.b64")
HEARTBEAT = Path("reports/rotor-tail-search-heartbeat.json")
BEST_CANDIDATE = Path("reports/rotor-tail-best-candidate.json")
MAX_DEPTH = 40
BEAM_WIDTH = 1_200
MAX_STATES = 500_000
TIME_LIMIT_SECONDS = 7_200
PUBLISHER = GitHubLiveStatusPublisher(min_interval_seconds=60.0)

HEX_DIRECTIONS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def ordinary_atoms(simulator: Simulator):
    return [atom for atom in simulator.world.atoms.values() if not simulator._is_wheel_atom_id(atom.id)]


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    aq, ar = a
    bq, br = b
    return (abs(aq - bq) + abs(ar - br) + abs((aq + ar) - (bq + br))) // 2


def molecular_components(simulator: Simulator) -> list[set[str]]:
    atom_ids = {atom.id for atom in ordinary_atoms(simulator)}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for atom_id in atom_ids:
        adjacency[atom_id]
    for bond in simulator.world.bonds.values():
        if bond.a in atom_ids and bond.b in atom_ids:
            adjacency[bond.a].add(bond.b)
            adjacency[bond.b].add(bond.a)
    seen: set[str] = set()
    components: list[set[str]] = []
    for atom_id in atom_ids:
        if atom_id in seen:
            continue
        queue = deque([atom_id])
        component: set[str] = set()
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            component.add(current)
            queue.extend(adjacency[current] - seen)
        components.append(component)
    return components


def output_score(simulator: Simulator) -> int:
    _, _, expected_atoms, expected_bonds = simulator.output_patterns[0]
    expected = dict(expected_atoms)
    atoms = ordinary_atoms(simulator)
    atoms_by_pos: dict[tuple[int, int], list] = defaultdict(list)
    atoms_by_element: dict[str, list] = defaultdict(list)
    for atom in atoms:
        atoms_by_pos[atom.position].append(atom)
        atoms_by_element[atom.element].append(atom)

    score = 0
    # Exact placement remains the strongest signal.
    for position, element in expected.items():
        candidates = atoms_by_pos.get(position, [])
        if len(candidates) == 1:
            score += 20
            if candidates[0].element == element:
                score += 100
            if not candidates[0].held_by:
                score += 5

    # Add a smooth distance signal so near-correct states do not tie with remote ones.
    for element in {value for value in expected.values()}:
        target_positions = [position for position, target_element in expected.items() if target_element == element]
        available = list(atoms_by_element.get(element, []))
        remaining = set(range(len(available)))
        for target in target_positions:
            if not remaining:
                score -= 35
                continue
            best_index = min(remaining, key=lambda index: hex_distance(available[index].position, target))
            distance = hex_distance(available[best_index].position, target)
            score += max(-30, 42 - 12 * distance)
            remaining.remove(best_index)

    expected_bond_set = {(kind, tuple(sorted((a, b)))) for kind, a, b in expected_bonds}
    correct_bonds = 0
    incorrect_bonds = 0
    for bond in simulator.world.bonds.values():
        if simulator._is_wheel_atom_id(bond.a) or simulator._is_wheel_atom_id(bond.b):
            continue
        a = simulator.world.atoms[bond.a].position
        b = simulator.world.atoms[bond.b].position
        signature = (bond.kind, tuple(sorted((a, b))))
        if signature in expected_bond_set:
            correct_bonds += 1
            score += 115
        else:
            incorrect_bonds += 1
            score -= 45

    # The product must become one connected molecule. Reward progress toward that topology
    # and strongly reject states that leave several isolated atoms at the end.
    components = molecular_components(simulator)
    largest_component = max((len(component) for component in components), default=0)
    isolated_count = sum(1 for component in components if len(component) == 1)
    score += largest_component * 38
    score -= max(0, len(components) - 1) * 42
    score -= isolated_count * 28
    if len(components) == 1 and len(atoms) == len(expected):
        score += 260

    central = atoms_by_pos.get((3, -2), [])
    if len(central) == 1 and central[0].element == "salt":
        score += 170

    output_cells = set(expected)
    score -= 4 * sum(1 for atom in atoms if atom.position not in output_cells)
    score += correct_bonds * 20
    score -= incorrect_bonds * 10
    return score


def snapshot(simulator: Simulator):
    atoms = [
        {"id": atom.id, "element": atom.element, "position": list(atom.position), "heldBy": sorted(atom.held_by)}
        for atom in ordinary_atoms(simulator)
    ]
    bonds = [
        {
            "a": bond.a,
            "b": bond.b,
            "kind": bond.kind,
            "aPosition": list(simulator.world.atoms[bond.a].position),
            "bPosition": list(simulator.world.atoms[bond.b].position),
        }
        for bond in simulator.world.bonds.values()
        if not simulator._is_wheel_atom_id(bond.a) and not simulator._is_wheel_atom_id(bond.b)
    ]
    return {
        "cycle": simulator.world.cycle,
        "score": output_score(simulator),
        "delivered": dict(simulator.delivered_products),
        "atoms": sorted(atoms, key=lambda item: item["id"]),
        "bonds": sorted(bonds, key=lambda item: (item["a"], item["b"])),
        "arms": {arm_id: arm.snapshot() for arm_id, arm in simulator.arms.items()},
        "componentCount": len(molecular_components(simulator)),
    }


def report_progress(progress: dict, *, force_publish: bool = False, status: str = "running") -> None:
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "stage": "tail-search-v2",
        "maxDepth": MAX_DEPTH,
        "beamWidth": BEAM_WIDTH,
        "maxStates": MAX_STATES,
        "timeLimitSeconds": TIME_LIMIT_SECONDS,
        "heuristicVersion": 2,
        **progress,
    }
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"heartbeat": payload}), file=sys.stderr, flush=True)
    PUBLISHER.publish(payload, force=force_publish)


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")))
    simulator = Simulator.from_models(puzzle, solution)
    for row in build_program_timeline(solution).get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", [])}
        simulator.step(instructions)

    output_id = simulator.output_patterns[0][0]
    action_options = {}
    for arm_id, arm in sorted(simulator.arms.items()):
        if arm.part_type == "piston":
            action_options[arm_id] = (None, "grab", "drop", "rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw", "extend", "retract", "track_plus", "track_minus")
        elif arm.part_type == "baron":
            action_options[arm_id] = (None, "rotate_cw", "rotate_ccw", "drop")

    report_progress({
        "message": "Préfixe rejoué. Initialisation de la recherche v2 avec priorité à la connectivité moléculaire.",
        "depth": 0,
        "elapsedSeconds": 0,
        "visitedStates": 1,
        "expandedStates": 0,
        "frontierSize": 1,
        "bestScore": output_score(simulator),
    }, force_publish=True)

    result = explore_simulator_beam(
        simulator,
        action_options,
        lambda state: state.delivered_products.get(output_id, 0) > 0,
        output_score,
        max_depth=MAX_DEPTH,
        beam_width=BEAM_WIDTH,
        max_states=MAX_STATES,
        max_active_arms=3,
        include_idle=False,
        time_limit_seconds=TIME_LIMIT_SECONDS,
        progress_callback=report_progress,
        progress_interval_seconds=15.0,
    )
    report_progress({
        "message": "Recherche terminée.",
        "depth": result.depth,
        "visitedStates": result.visited_states,
        "expandedStates": result.expanded_states,
        "bestScore": result.best_score,
        "stoppedReason": result.stopped_reason,
        "found": result.found,
    }, force_publish=True, status="completed" if result.found else "stopped")

    payload = {
        "schemaVersion": 2,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "search": {
            "maxDepth": MAX_DEPTH,
            "beamWidth": BEAM_WIDTH,
            "maxStates": MAX_STATES,
            "timeLimitSeconds": TIME_LIMIT_SECONDS,
            "maxActiveArms": 3,
            "heuristicVersion": 2,
        },
        "start": snapshot(simulator),
        "result": {
            "found": result.found,
            "actions": result.actions,
            "visitedStates": result.visited_states,
            "expandedStates": result.expanded_states,
            "depth": result.depth,
            "stoppedReason": result.stopped_reason,
            "bestScore": result.best_score,
            "best": snapshot(result.simulator) if result.simulator is not None else None,
        },
    }
    BEST_CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    BEST_CANDIDATE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
