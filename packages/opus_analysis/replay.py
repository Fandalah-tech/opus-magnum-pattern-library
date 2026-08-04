from __future__ import annotations

from copy import deepcopy
from typing import Any

ROTATE_CW = {"rotate_cw", "rotate-clockwise"}
ROTATE_CCW = {"rotate_ccw", "rotate-counterclockwise"}
EXTEND = {"extend", "extend_piston"}
RETRACT = {"retract", "retract_piston"}
GRAB = {"grab"}
DROP = {"drop"}
RESET = {"reset"}
PIVOT_CW = {"pivot_cw", "pivot-clockwise"}
PIVOT_CCW = {"pivot_ccw", "pivot-counterclockwise"}
TRACK_PLUS = {"track_plus"}
TRACK_MINUS = {"track_minus"}

DIRECTIONS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def _add(a: list[int], b: list[int]) -> list[int]:
    return [int(a[0]) + int(b[0]), int(a[1]) + int(b[1])]


def _sub(a: list[int], b: list[int]) -> list[int]:
    return [int(a[0]) - int(b[0]), int(a[1]) - int(b[1])]


def _rotate_vector(vector: list[int], steps: int) -> list[int]:
    q, r = int(vector[0]), int(vector[1])
    if steps >= 0:
        for _ in range(steps % 6):
            q, r = -r, q + r
    else:
        for _ in range((-steps) % 6):
            q, r = q + r, -q
    return [q, r]


def _rotate_point(point: list[int], center: list[int], steps: int) -> list[int]:
    return _add(center, _rotate_vector(_sub(point, center), steps))


def _tip(state: dict[str, Any]) -> list[int]:
    dq, dr = DIRECTIONS[int(state["rotation"]) % 6]
    return [int(state["origin"][0]) + dq * int(state["length"]), int(state["origin"][1]) + dr * int(state["length"])]


def _track_cells(solution: dict[str, Any]) -> list[list[int]]:
    tracks = [part for part in solution.get("parts", []) if part.get("type") == "track"]
    if not tracks:
        return []
    cells = tracks[0].get("trackHexes") or []
    return [list(cell) for cell in cells]


def _initial_arm_state(part: dict[str, Any], track: list[list[int]]) -> dict[str, Any]:
    base_length = max(1, int(part.get("length") or 1))
    origin = list(part.get("position") or [0, 0])
    track_index = next((index for index, cell in enumerate(track) if cell == origin), 0)
    return {
        "partId": part["id"],
        "armNumber": part.get("armNumber"),
        "partType": part.get("type"),
        "origin": origin,
        "baseOrigin": list(origin),
        "rotation": int(part.get("rotation") or 0) % 6,
        "baseRotation": int(part.get("rotation") or 0) % 6,
        "length": base_length,
        "baseLength": base_length,
        "grabbing": False,
        "heldMoleculeId": None,
        "heldRotation": 0,
        "trackIndex": track_index,
        "baseTrackIndex": track_index,
        "lastInstruction": None,
        "stateSource": "kinematic-atom-model",
    }


def _instantiate_inputs(puzzle: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    reagents = puzzle.get("reagents", [])
    molecules: list[dict[str, Any]] = []
    for input_index, part in enumerate(item for item in solution.get("parts", []) if item.get("type") == "input"):
        reagent_index = int(part.get("which") or 0)
        if reagent_index < 0 or reagent_index >= len(reagents):
            continue
        reagent = reagents[reagent_index]
        origin = list(part.get("position") or [0, 0])
        rotation = int(part.get("rotation") or 0)
        atoms = []
        for atom in reagent.get("atoms", []):
            local = _rotate_vector(list(atom.get("position") or [0, 0]), rotation)
            atoms.append({
                "id": f"m{input_index}-{atom.get('id')}",
                "element": atom.get("element"),
                "position": _add(origin, local),
            })
        bonds = []
        for bond_index, bond in enumerate(reagent.get("bonds", [])):
            start = _add(origin, _rotate_vector(list(bond.get("from") or [0, 0]), rotation))
            end = _add(origin, _rotate_vector(list(bond.get("to") or [0, 0]), rotation))
            bonds.append({"id": f"m{input_index}-b{bond_index}", "type": bond.get("type"), "from": start, "to": end})
        molecules.append({
            "id": f"molecule-{input_index}",
            "source": "input",
            "sourcePartId": part.get("id"),
            "reagentIndex": reagent_index,
            "heldBy": None,
            "atoms": atoms,
            "bonds": bonds,
        })
    return molecules


def _translate_molecule(molecule: dict[str, Any], delta: list[int]) -> None:
    for atom in molecule["atoms"]:
        atom["position"] = _add(atom["position"], delta)
    for bond in molecule["bonds"]:
        bond["from"] = _add(bond["from"], delta)
        bond["to"] = _add(bond["to"], delta)


def _rotate_molecule(molecule: dict[str, Any], center: list[int], steps: int) -> None:
    for atom in molecule["atoms"]:
        atom["position"] = _rotate_point(atom["position"], center, steps)
    for bond in molecule["bonds"]:
        bond["from"] = _rotate_point(bond["from"], center, steps)
        bond["to"] = _rotate_point(bond["to"], center, steps)


def _molecule_at(molecules: list[dict[str, Any]], position: list[int]) -> dict[str, Any] | None:
    for molecule in molecules:
        if molecule.get("heldBy") is not None:
            continue
        if any(atom.get("position") == position for atom in molecule.get("atoms", [])):
            return molecule
    return None


def _apply_instruction(
    state: dict[str, Any],
    instruction: str | None,
    molecules: list[dict[str, Any]],
    track: list[list[int]],
) -> None:
    if not instruction:
        return
    state["lastInstruction"] = instruction
    held = next((m for m in molecules if m.get("id") == state.get("heldMoleculeId")), None)
    old_origin = list(state["origin"])
    old_tip = _tip(state)

    if instruction in ROTATE_CW:
        state["rotation"] = (int(state["rotation"]) - 1) % 6
        if held:
            _rotate_molecule(held, old_origin, -1)
    elif instruction in ROTATE_CCW:
        state["rotation"] = (int(state["rotation"]) + 1) % 6
        if held:
            _rotate_molecule(held, old_origin, 1)
    elif instruction in EXTEND and state.get("partType") == "piston":
        state["length"] = min(3, int(state["length"]) + 1)
        if held:
            _translate_molecule(held, _sub(_tip(state), old_tip))
    elif instruction in RETRACT and state.get("partType") == "piston":
        state["length"] = max(int(state["baseLength"]), int(state["length"]) - 1)
        if held:
            _translate_molecule(held, _sub(_tip(state), old_tip))
    elif instruction in TRACK_PLUS and track:
        state["trackIndex"] = min(len(track) - 1, int(state["trackIndex"]) + 1)
        state["origin"] = list(track[int(state["trackIndex"])])
        if held:
            _translate_molecule(held, _sub(state["origin"], old_origin))
    elif instruction in TRACK_MINUS and track:
        state["trackIndex"] = max(0, int(state["trackIndex"]) - 1)
        state["origin"] = list(track[int(state["trackIndex"])])
        if held:
            _translate_molecule(held, _sub(state["origin"], old_origin))
    elif instruction in GRAB:
        molecule = _molecule_at(molecules, old_tip)
        state["grabbing"] = True
        if molecule:
            molecule["heldBy"] = state["partId"]
            state["heldMoleculeId"] = molecule["id"]
    elif instruction in DROP:
        state["grabbing"] = False
        if held:
            held["heldBy"] = None
        state["heldMoleculeId"] = None
    elif instruction in PIVOT_CW:
        state["heldRotation"] = (int(state["heldRotation"]) - 1) % 6
        if held:
            _rotate_molecule(held, old_tip, -1)
    elif instruction in PIVOT_CCW:
        state["heldRotation"] = (int(state["heldRotation"]) + 1) % 6
        if held:
            _rotate_molecule(held, old_tip, 1)
    elif instruction in RESET:
        state["rotation"] = int(state["baseRotation"])
        state["length"] = int(state["baseLength"])
        state["trackIndex"] = int(state["baseTrackIndex"])
        state["origin"] = list(state["baseOrigin"])
        state["grabbing"] = False
        if held:
            held["heldBy"] = None
        state["heldMoleculeId"] = None


def build_replay_trace(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    timeline: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic arm-and-atom replay trace.

    Reagent molecules are instantiated at each input. Arms can grab a molecule
    when their tip overlaps one of its atoms, carry it through rotations,
    pivots, piston and track motion, and release it with drop.
    """
    parts = {part["id"]: part for part in solution.get("parts", [])}
    track = _track_cells(solution)
    arm_parts = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    states = {part["id"]: _initial_arm_state(part, track) for part in arm_parts}
    molecules = _instantiate_inputs(puzzle, solution)
    frames: list[dict[str, Any]] = []

    for row in timeline.get("cycles", []):
        events: list[dict[str, Any]] = []
        for event in row.get("events", []):
            part = parts.get(event.get("partId"), {})
            instruction = event.get("instruction")
            events.append({
                "kind": "arm-instruction",
                "partId": event.get("partId"),
                "armNumber": event.get("armNumber"),
                "partType": event.get("type"),
                "instruction": instruction,
                "rawCode": event.get("rawCode"),
                "tapeCycle": event.get("tapeCycle"),
                "origin": part.get("position"),
                "generatedBy": event.get("generatedBy"),
            })
            state = states.get(event.get("partId"))
            if state is not None:
                _apply_instruction(state, instruction, molecules, track)

        frames.append({
            "cycle": row.get("cycle", 0),
            "phase": 1,
            "phaseLabel": "after-instructions",
            "activeArmCount": row.get("activeArms", 0),
            "events": events,
            "armStates": [deepcopy(state) for state in states.values()],
            "molecules": deepcopy(molecules),
        })

    return {
        "schemaVersion": "0.4.0",
        "traceType": "kinematic-atom-replay",
        "source": "opus-analysis",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": timeline.get("summary", {}).get("horizon", len(frames)),
            "phaseCount": 1,
            "initialMoleculeCount": len(molecules),
            "hasPhysicalArmStates": True,
            "hasMoleculeStates": True,
        },
        "capabilities": {
            "seek": True,
            "playback": True,
            "activeArmHighlight": True,
            "physicalArmAnimation": True,
            "pistonAnimation": True,
            "trackAnimation": bool(track),
            "grabState": True,
            "moleculeAnimation": True,
            "bondRendering": True,
            "glyphSimulation": False,
        },
        "limitations": [
            "Input reagents are instantiated once at cycle zero; repeated reagent spawning is not implemented yet.",
            "Molecules move through arm kinematics, but glyph effects and collision validation are not simulated.",
            "Track branches are followed in stored file order.",
            "Reset releases held molecules and returns directly to the initial arm state.",
        ],
        "frames": frames,
    }
