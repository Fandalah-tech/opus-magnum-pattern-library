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


def _branch_offsets(part_type: str) -> list[int]:
    return list(range(6)) if part_type == "arm6" else [0]


def _tips(state: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for branch_index, offset in enumerate(state["branchOffsets"]):
        rotation = (int(state["rotation"]) + int(offset)) % 6
        dq, dr = DIRECTIONS[rotation]
        result.append({
            "branchIndex": branch_index,
            "rotation": rotation,
            "position": [
                int(state["origin"][0]) + dq * int(state["length"]),
                int(state["origin"][1]) + dr * int(state["length"]),
            ],
        })
    return result


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
    branch_offsets = _branch_offsets(str(part.get("type") or ""))
    state = {
        "partId": part["id"],
        "armNumber": part.get("armNumber"),
        "partType": part.get("type"),
        "origin": origin,
        "baseOrigin": list(origin),
        "rotation": int(part.get("rotation") or 0) % 6,
        "baseRotation": int(part.get("rotation") or 0) % 6,
        "length": base_length,
        "baseLength": base_length,
        "branchOffsets": branch_offsets,
        "branchCount": len(branch_offsets),
        "grabbing": False,
        "heldAttachments": [],
        "heldMoleculeIds": [],
        "heldRotation": 0,
        "trackIndex": track_index,
        "baseTrackIndex": track_index,
        "lastInstruction": None,
        "stateSource": "kinematic-multiarm-atom-model",
    }
    state["tips"] = _tips(state)
    return state


def _input_templates(puzzle: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    reagents = puzzle.get("reagents", [])
    templates: list[dict[str, Any]] = []
    inputs = [item for item in solution.get("parts", []) if item.get("type") == "input"]
    for input_index, part in enumerate(inputs):
        reagent_index = int(part.get("which") or 0)
        if reagent_index < 0 or reagent_index >= len(reagents):
            continue
        reagent = reagents[reagent_index]
        origin = list(part.get("position") or [0, 0])
        rotation = int(part.get("rotation") or 0)
        atoms = []
        for atom in reagent.get("atoms", []):
            local = _rotate_vector(list(atom.get("position") or [0, 0]), rotation)
            atoms.append({"element": atom.get("element"), "position": _add(origin, local)})
        bonds = []
        for bond in reagent.get("bonds", []):
            bonds.append({
                "type": bond.get("type"),
                "from": _add(origin, _rotate_vector(list(bond.get("from") or [0, 0]), rotation)),
                "to": _add(origin, _rotate_vector(list(bond.get("to") or [0, 0]), rotation)),
            })
        templates.append({
            "inputIndex": input_index,
            "sourcePartId": part.get("id"),
            "reagentIndex": reagent_index,
            "atoms": atoms,
            "bonds": bonds,
            "spawnCount": 0,
        })
    return templates


def _spawn_molecule(template: dict[str, Any]) -> dict[str, Any]:
    spawn_index = int(template["spawnCount"])
    template["spawnCount"] = spawn_index + 1
    molecule_id = f"input-{template['inputIndex']}-molecule-{spawn_index}"
    atoms = [
        {
            "id": f"{molecule_id}-a{index}",
            "element": atom.get("element"),
            "position": list(atom.get("position") or [0, 0]),
        }
        for index, atom in enumerate(template.get("atoms", []))
    ]
    bonds = [
        {
            "id": f"{molecule_id}-b{index}",
            "type": bond.get("type"),
            "from": list(bond.get("from") or [0, 0]),
            "to": list(bond.get("to") or [0, 0]),
        }
        for index, bond in enumerate(template.get("bonds", []))
    ]
    return {
        "id": molecule_id,
        "source": "input",
        "sourcePartId": template.get("sourcePartId"),
        "reagentIndex": template.get("reagentIndex"),
        "spawnIndex": spawn_index,
        "heldBy": [],
        "atoms": atoms,
        "bonds": bonds,
    }


def _occupied_positions(molecules: list[dict[str, Any]]) -> set[tuple[int, int]]:
    return {
        tuple(atom.get("position") or [0, 0])
        for molecule in molecules
        for atom in molecule.get("atoms", [])
    }


def _respawn_inputs(templates: list[dict[str, Any]], molecules: list[dict[str, Any]]) -> list[str]:
    occupied = _occupied_positions(molecules)
    spawned: list[str] = []
    for template in templates:
        target = {tuple(atom.get("position") or [0, 0]) for atom in template.get("atoms", [])}
        if target and target.isdisjoint(occupied):
            molecule = _spawn_molecule(template)
            molecules.append(molecule)
            occupied.update(target)
            spawned.append(molecule["id"])
    return spawned


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


def _molecule_at(molecules: list[dict[str, Any]], position: list[int], excluded: set[str]) -> dict[str, Any] | None:
    for molecule in molecules:
        if molecule.get("id") in excluded:
            continue
        if any(atom.get("position") == position for atom in molecule.get("atoms", [])):
            return molecule
    return None


def _held_molecules(state: dict[str, Any], molecules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = set(state.get("heldMoleculeIds") or [])
    return [molecule for molecule in molecules if molecule.get("id") in ids]


def _release_all(state: dict[str, Any], molecules: list[dict[str, Any]]) -> None:
    for molecule in _held_molecules(state, molecules):
        molecule["heldBy"] = [item for item in molecule.get("heldBy", []) if item.get("partId") != state["partId"]]
    state["heldAttachments"] = []
    state["heldMoleculeIds"] = []
    state["grabbing"] = False


def _apply_instruction(
    state: dict[str, Any],
    instruction: str | None,
    molecules: list[dict[str, Any]],
    track: list[list[int]],
) -> None:
    if not instruction:
        return
    state["lastInstruction"] = instruction
    held = _held_molecules(state, molecules)
    old_origin = list(state["origin"])
    old_tips = {item["branchIndex"]: item["position"] for item in _tips(state)}

    if instruction in ROTATE_CW:
        state["rotation"] = (int(state["rotation"]) - 1) % 6
        for molecule in held:
            _rotate_molecule(molecule, old_origin, -1)
    elif instruction in ROTATE_CCW:
        state["rotation"] = (int(state["rotation"]) + 1) % 6
        for molecule in held:
            _rotate_molecule(molecule, old_origin, 1)
    elif instruction in EXTEND and state.get("partType") == "piston":
        state["length"] = min(3, int(state["length"]) + 1)
        new_tips = {item["branchIndex"]: item["position"] for item in _tips(state)}
        for attachment in state.get("heldAttachments", []):
            molecule = next((item for item in held if item["id"] == attachment["moleculeId"]), None)
            if molecule:
                branch = int(attachment["branchIndex"])
                _translate_molecule(molecule, _sub(new_tips[branch], old_tips[branch]))
    elif instruction in RETRACT and state.get("partType") == "piston":
        state["length"] = max(int(state["baseLength"]), int(state["length"]) - 1)
        new_tips = {item["branchIndex"]: item["position"] for item in _tips(state)}
        for attachment in state.get("heldAttachments", []):
            molecule = next((item for item in held if item["id"] == attachment["moleculeId"]), None)
            if molecule:
                branch = int(attachment["branchIndex"])
                _translate_molecule(molecule, _sub(new_tips[branch], old_tips[branch]))
    elif instruction in TRACK_PLUS and track:
        state["trackIndex"] = min(len(track) - 1, int(state["trackIndex"]) + 1)
        state["origin"] = list(track[int(state["trackIndex"])])
        delta = _sub(state["origin"], old_origin)
        for molecule in held:
            _translate_molecule(molecule, delta)
    elif instruction in TRACK_MINUS and track:
        state["trackIndex"] = max(0, int(state["trackIndex"]) - 1)
        state["origin"] = list(track[int(state["trackIndex"])])
        delta = _sub(state["origin"], old_origin)
        for molecule in held:
            _translate_molecule(molecule, delta)
    elif instruction in GRAB:
        state["grabbing"] = True
        excluded = set(state.get("heldMoleculeIds") or [])
        for tip in _tips(state):
            molecule = _molecule_at(molecules, tip["position"], excluded)
            if not molecule:
                continue
            attachment = {
                "branchIndex": tip["branchIndex"],
                "moleculeId": molecule["id"],
                "grabPosition": list(tip["position"]),
            }
            state["heldAttachments"].append(attachment)
            state["heldMoleculeIds"].append(molecule["id"])
            molecule.setdefault("heldBy", []).append({"partId": state["partId"], "branchIndex": tip["branchIndex"]})
            excluded.add(molecule["id"])
    elif instruction in DROP:
        _release_all(state, molecules)
    elif instruction in PIVOT_CW:
        state["heldRotation"] = (int(state["heldRotation"]) - 1) % 6
        handled: set[str] = set()
        for attachment in state.get("heldAttachments", []):
            molecule_id = attachment["moleculeId"]
            if molecule_id in handled:
                continue
            molecule = next((item for item in held if item["id"] == molecule_id), None)
            if molecule:
                center = old_tips[int(attachment["branchIndex"])]
                _rotate_molecule(molecule, center, -1)
                handled.add(molecule_id)
    elif instruction in PIVOT_CCW:
        state["heldRotation"] = (int(state["heldRotation"]) + 1) % 6
        handled: set[str] = set()
        for attachment in state.get("heldAttachments", []):
            molecule_id = attachment["moleculeId"]
            if molecule_id in handled:
                continue
            molecule = next((item for item in held if item["id"] == molecule_id), None)
            if molecule:
                center = old_tips[int(attachment["branchIndex"])]
                _rotate_molecule(molecule, center, 1)
                handled.add(molecule_id)
    elif instruction in RESET:
        _release_all(state, molecules)
        state["rotation"] = int(state["baseRotation"])
        state["length"] = int(state["baseLength"])
        state["trackIndex"] = int(state["baseTrackIndex"])
        state["origin"] = list(state["baseOrigin"])

    state["tips"] = _tips(state)


def _frame(
    *,
    cycle: int,
    display_cycle: int,
    phase: int,
    phase_label: str,
    events: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    molecules: list[dict[str, Any]],
    active_arm_count: int,
    spawned: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "cycle": cycle,
        "displayCycle": display_cycle,
        "phase": phase,
        "phaseLabel": phase_label,
        "activeArmCount": active_arm_count,
        "events": events,
        "spawnedMoleculeIds": spawned or [],
        "armStates": [deepcopy(state) for state in states.values()],
        "molecules": deepcopy(molecules),
    }


def build_replay_trace(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    timeline: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic multi-arm and atom replay trace.

    arm6 exposes six independent gripper branches. Grab can attach one molecule
    per occupied branch, all attached molecules follow arm rotation/translation,
    and inputs regenerate whenever their complete reagent footprint is clear.
    """
    parts = {part["id"]: part for part in solution.get("parts", [])}
    track = _track_cells(solution)
    arm_parts = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    states = {part["id"]: _initial_arm_state(part, track) for part in arm_parts}
    templates = _input_templates(puzzle, solution)
    molecules = [_spawn_molecule(template) for template in templates]
    frames: list[dict[str, Any]] = [
        _frame(
            cycle=-1,
            display_cycle=0,
            phase=0,
            phase_label="initial",
            events=[],
            states=states,
            molecules=molecules,
            active_arm_count=0,
        )
    ]

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

        spawned = _respawn_inputs(templates, molecules)
        frames.append(_frame(
            cycle=int(row.get("cycle", 0)),
            display_cycle=int(row.get("cycle", 0)) + 1,
            phase=1,
            phase_label="after-instructions",
            events=events,
            states=states,
            molecules=molecules,
            active_arm_count=int(row.get("activeArms", 0)),
            spawned=spawned,
        ))

    return {
        "schemaVersion": "0.5.0",
        "traceType": "multiarm-atom-replay",
        "source": "opus-analysis",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": timeline.get("summary", {}).get("horizon", max(0, len(frames) - 1)),
            "phaseCount": 2,
            "initialMoleculeCount": len(templates),
            "hasPhysicalArmStates": True,
            "hasMoleculeStates": True,
            "hasMultiBranchArms": any(state["branchCount"] > 1 for state in states.values()),
        },
        "capabilities": {
            "seek": True,
            "playback": True,
            "activeArmHighlight": True,
            "physicalArmAnimation": True,
            "pistonAnimation": True,
            "trackAnimation": bool(track),
            "grabState": True,
            "multiBranchGrab": True,
            "moleculeAnimation": True,
            "inputRespawn": True,
            "bondRendering": True,
            "glyphSimulation": False,
        },
        "limitations": [
            "The trace exposes an explicit initial frame followed by one post-instruction frame per cycle.",
            "Glyph effects and collision validation are not simulated.",
            "Track branches are followed in stored file order.",
            "Reset releases held molecules and returns directly to the initial arm state.",
            "A molecule is attached to at most one branch of the same arm in this version.",
        ],
        "frames": frames,
    }
