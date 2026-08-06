from __future__ import annotations

import base64
import json
import sys
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
MAX_DEPTH = 28
BEAM_WIDTH = 750
MAX_STATES = 250_000
TIME_LIMIT_SECONDS = 5_400
PUBLISHER = GitHubLiveStatusPublisher(min_interval_seconds=60.0)


def ordinary_atoms(simulator: Simulator):
    return [atom for atom in simulator.world.atoms.values() if not simulator._is_wheel_atom_id(atom.id)]


def output_score(simulator: Simulator) -> int:
    _, _, expected_atoms, expected_bonds = simulator.output_patterns[0]
    expected = dict(expected_atoms)
    atoms_by_pos = {}
    for atom in ordinary_atoms(simulator):
        atoms_by_pos.setdefault(atom.position, []).append(atom)
    score = 0
    for position, element in expected.items():
        candidates = atoms_by_pos.get(position, [])
        if len(candidates) == 1:
            score += 20
            if candidates[0].element == element:
                score += 100
            if not candidates[0].held_by:
                score += 5
    expected_bond_set = {(kind, tuple(sorted((a, b)))) for kind, a, b in expected_bonds}
    for bond in simulator.world.bonds.values():
        if simulator._is_wheel_atom_id(bond.a) or simulator._is_wheel_atom_id(bond.b):
            continue
        a = simulator.world.atoms[bond.a].position
        b = simulator.world.atoms[bond.b].position
        signature = (bond.kind, tuple(sorted((a, b))))
        score += 80 if signature in expected_bond_set else -35
    central = atoms_by_pos.get((3, -2), [])
    if len(central) == 1 and central[0].element == "salt":
        score += 150
    output_cells = set(expected)
    score -= 3 * sum(1 for atom in ordinary_atoms(simulator) if atom.position not in output_cells)
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
    }


def report_progress(progress: dict, *, force_publish: bool = False, status: str = "running") -> None:
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "stage": "tail-search",
        "maxDepth": MAX_DEPTH,
        "beamWidth": BEAM_WIDTH,
        "maxStates": MAX_STATES,
        "timeLimitSeconds": TIME_LIMIT_SECONDS,
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
        "message": "Préfixe rejoué. Initialisation du beam search borné en mémoire.",
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
        max_active_arms=2,
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
        "schemaVersion": 1,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "search": {
            "maxDepth": MAX_DEPTH,
            "beamWidth": BEAM_WIDTH,
            "maxStates": MAX_STATES,
            "timeLimitSeconds": TIME_LIMIT_SECONDS,
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
