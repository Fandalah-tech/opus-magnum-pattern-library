from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from .replay import (
    _apply_instruction,
    _frame,
    _initial_arm_state,
    _input_templates,
    _process_consumers,
    _respawn_inputs,
    _rotate_vector,
    _spawn_molecule,
    _track_cells,
)

CLASSICAL_ELEMENTS = {"air", "earth", "fire", "water"}
BASIC_GLYPHS = {"bonder", "unbonder", "glyph-calcification"}


def _cell(part: dict[str, Any], offset: list[int]) -> list[int]:
    origin = list(part.get("position") or [0, 0])
    rotated = _rotate_vector(offset, int(part.get("rotation") or 0))
    return [origin[0] + rotated[0], origin[1] + rotated[1]]


def _atom_locations(molecules: list[dict[str, Any]]) -> dict[tuple[int, int], tuple[dict[str, Any], dict[str, Any]]]:
    locations: dict[tuple[int, int], tuple[dict[str, Any], dict[str, Any]]] = {}
    for molecule in molecules:
        for atom in molecule.get("atoms", []):
            position = tuple(atom.get("position") or [0, 0])
            locations[position] = (molecule, atom)
    return locations


def _bond_matches(bond: dict[str, Any], a: list[int], b: list[int]) -> bool:
    left = tuple(bond.get("from") or [0, 0])
    right = tuple(bond.get("to") or [0, 0])
    return {left, right} == {tuple(a), tuple(b)}


def _replace_molecule_reference(states: dict[str, dict[str, Any]], old_id: str, new_id: str) -> None:
    if old_id == new_id:
        return
    for state in states.values():
        state["heldMoleculeIds"] = [new_id if value == old_id else value for value in state.get("heldMoleculeIds", [])]
        state["heldMoleculeIds"] = list(dict.fromkeys(state["heldMoleculeIds"]))
        for attachment in state.get("heldAttachments", []):
            if attachment.get("moleculeId") == old_id:
                attachment["moleculeId"] = new_id


def _merge_molecules(
    molecules: list[dict[str, Any]],
    left: dict[str, Any],
    right: dict[str, Any],
    states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if left is right:
        return left
    keep, remove = sorted((left, right), key=lambda item: str(item.get("id") or ""))
    keep.setdefault("atoms", []).extend(remove.get("atoms", []))
    keep.setdefault("bonds", []).extend(remove.get("bonds", []))
    held_by = list(keep.get("heldBy", [])) + list(remove.get("heldBy", []))
    unique_held = []
    seen = set()
    for value in held_by:
        key = (value.get("partId"), value.get("branchIndex"))
        if key not in seen:
            seen.add(key)
            unique_held.append(value)
    keep["heldBy"] = unique_held
    _replace_molecule_reference(states, str(remove.get("id")), str(keep.get("id")))
    molecules[:] = [item for item in molecules if item is not remove]
    return keep


def _components(molecule: dict[str, Any]) -> list[set[tuple[int, int]]]:
    atoms = {tuple(atom.get("position") or [0, 0]) for atom in molecule.get("atoms", [])}
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    for position in atoms:
        adjacency[position]
    for bond in molecule.get("bonds", []):
        a = tuple(bond.get("from") or [0, 0])
        b = tuple(bond.get("to") or [0, 0])
        if a in atoms and b in atoms:
            adjacency[a].add(b)
            adjacency[b].add(a)
    result = []
    unseen = set(atoms)
    while unseen:
        start = min(unseen)
        stack = [start]
        unseen.remove(start)
        component = {start}
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        result.append(component)
    return sorted(result, key=lambda value: min(value) if value else (0, 0))


def _split_molecule(
    molecules: list[dict[str, Any]],
    molecule: dict[str, Any],
    states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    components = _components(molecule)
    if len(components) <= 1:
        return [molecule]

    original_id = str(molecule.get("id") or "molecule")
    original_atoms = list(molecule.get("atoms", []))
    original_bonds = list(molecule.get("bonds", []))
    original_held = list(molecule.get("heldBy", []))
    replacements = []
    for index, positions in enumerate(components):
        new_id = original_id if index == 0 else f"{original_id}-split-{index}"
        atoms = [atom for atom in original_atoms if tuple(atom.get("position") or [0, 0]) in positions]
        bonds = [
            bond for bond in original_bonds
            if tuple(bond.get("from") or [0, 0]) in positions and tuple(bond.get("to") or [0, 0]) in positions
        ]
        held_by = []
        for held in original_held:
            part_id = held.get("partId")
            state = states.get(part_id)
            if not state:
                continue
            branch = int(held.get("branchIndex") or 0)
            tip = next((tip for tip in state.get("tips", []) if int(tip.get("branchIndex") or 0) == branch), None)
            if tip and tuple(tip.get("position") or [0, 0]) in positions:
                held_by.append(held)
        replacements.append({**molecule, "id": new_id, "atoms": atoms, "bonds": bonds, "heldBy": held_by})

    molecules[:] = [item for item in molecules if item is not molecule] + replacements
    for state in states.values():
        state["heldMoleculeIds"] = [value for value in state.get("heldMoleculeIds", []) if value != original_id]
        state["heldAttachments"] = [value for value in state.get("heldAttachments", []) if value.get("moleculeId") != original_id]
        for replacement in replacements:
            for held in replacement.get("heldBy", []):
                if held.get("partId") == state.get("partId"):
                    state["heldMoleculeIds"].append(replacement["id"])
                    state["heldAttachments"].append({
                        "branchIndex": held.get("branchIndex"),
                        "moleculeId": replacement["id"],
                        "grabPosition": next(
                            (tip.get("position") for tip in state.get("tips", []) if tip.get("branchIndex") == held.get("branchIndex")),
                            None,
                        ),
                    })
        state["heldMoleculeIds"] = list(dict.fromkeys(state["heldMoleculeIds"]))
        state["grabbing"] = bool(state["heldMoleculeIds"])
    return replacements


def process_basic_glyphs(
    solution: dict[str, Any],
    molecules: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply the currently supported passive glyph effects once.

    Effects are evaluated after arm instructions and before disposal/output
    consumers. This intentionally covers only normal bonder, normal unbonder,
    and calcification. Each mutation emits an explicit trace event.
    """
    events: list[dict[str, Any]] = []
    for part in solution.get("parts", []):
        part_type = str(part.get("type") or "")
        if part_type not in BASIC_GLYPHS:
            continue

        if part_type == "glyph-calcification":
            target = _cell(part, [0, 0])
            located = _atom_locations(molecules).get(tuple(target))
            if located:
                molecule, atom = located
                before = str(atom.get("element") or "")
                if before in CLASSICAL_ELEMENTS:
                    atom["element"] = "salt"
                    events.append({
                        "kind": "glyph-effect",
                        "glyphType": part_type,
                        "glyphPartId": part.get("id"),
                        "effect": "calcify",
                        "moleculeId": molecule.get("id"),
                        "position": target,
                        "fromElement": before,
                        "toElement": "salt",
                    })
            continue

        first = _cell(part, [0, 0])
        second = _cell(part, [1, 0])
        locations = _atom_locations(molecules)
        left = locations.get(tuple(first))
        right = locations.get(tuple(second))
        if not left or not right:
            continue
        left_molecule, _ = left
        right_molecule, _ = right

        if part_type == "bonder":
            existing = any(_bond_matches(bond, first, second) for molecule in {id(left_molecule): left_molecule, id(right_molecule): right_molecule}.values() for bond in molecule.get("bonds", []))
            if existing:
                continue
            merged = _merge_molecules(molecules, left_molecule, right_molecule, states)
            bond_id = f"{merged.get('id')}-glyph-bond-{len(merged.get('bonds', []))}"
            merged.setdefault("bonds", []).append({"id": bond_id, "type": "normal", "from": first, "to": second})
            events.append({
                "kind": "glyph-effect",
                "glyphType": part_type,
                "glyphPartId": part.get("id"),
                "effect": "bond-created",
                "moleculeId": merged.get("id"),
                "positions": [first, second],
            })
            continue

        molecule = left_molecule if left_molecule is right_molecule else None
        if molecule is None:
            continue
        before = len(molecule.get("bonds", []))
        molecule["bonds"] = [bond for bond in molecule.get("bonds", []) if not _bond_matches(bond, first, second)]
        if len(molecule["bonds"]) == before:
            continue
        split = _split_molecule(molecules, molecule, states)
        events.append({
            "kind": "glyph-effect",
            "glyphType": part_type,
            "glyphPartId": part.get("id"),
            "effect": "bond-removed",
            "moleculeIds": [item.get("id") for item in split],
            "positions": [first, second],
        })
    return events


def build_replay_trace(puzzle: dict[str, Any], solution: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    """Build the replay trace with the supported passive glyph simulation."""
    parts = {part["id"]: part for part in solution.get("parts", [])}
    track = _track_cells(solution)
    arm_parts = [part for part in solution.get("parts", []) if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}]
    states = {part["id"]: _initial_arm_state(part, track) for part in arm_parts}
    templates = _input_templates(puzzle, solution)
    molecules = [_spawn_molecule(template) for template in templates]
    total_delivered: dict[str, int] = {}
    frames = [_frame(cycle=-1, display_cycle=0, phase=0, phase_label="initial", events=[], states=states, molecules=molecules, active_arm_count=0)]

    glyph_effect_count = 0
    for row in timeline.get("cycles", []):
        events: list[dict[str, Any]] = []
        for event in row.get("events", []):
            part, instruction = parts.get(event.get("partId"), {}), event.get("instruction")
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

        glyph_events = process_basic_glyphs(solution, molecules, states)
        glyph_effect_count += len(glyph_events)
        events.extend(glyph_events)

        consumer_events, delivered_now = _process_consumers(puzzle, solution, molecules, states)
        events.extend(consumer_events)
        for output_id, count in delivered_now.items():
            total_delivered[output_id] = total_delivered.get(output_id, 0) + count
        spawned = _respawn_inputs(templates, molecules)
        frames.append(_frame(
            cycle=int(row.get("cycle", 0)),
            display_cycle=int(row.get("cycle", 0)) + 1,
            phase=1,
            phase_label="after-instructions-glyphs-and-consumers",
            events=events,
            states=states,
            molecules=molecules,
            active_arm_count=int(row.get("activeArms", 0)),
            spawned=spawned,
            delivered=total_delivered,
        ))

    return {
        "schemaVersion": "0.7.0",
        "traceType": "multiarm-atom-basic-glyph-replay",
        "source": "opus-analysis",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": timeline.get("summary", {}).get("horizon", max(0, len(frames) - 1)),
            "phaseCount": 2,
            "initialMoleculeCount": len(templates),
            "remainingMoleculeCount": len(molecules),
            "deliveredProducts": total_delivered,
            "glyphEffectCount": glyph_effect_count,
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
            "disposalSimulation": True,
            "outputDelivery": True,
            "glyphSimulation": True,
            "simulatedGlyphs": sorted(BASIC_GLYPHS),
        },
        "limitations": [
            "Only normal bonder, normal unbonder and calcification are simulated.",
            "Bonder/unbonder activation geometry uses their two occupied hexes and is pending OMSim cross-validation.",
            "Calcification currently converts air/earth/fire/water atoms on its anchor cell to salt.",
            "Multibonder, prismatic bonding, purification, projection, duplication, animismus and other glyphs are not simulated.",
            "Collision validation is not simulated.",
            "Track branches are followed in stored file order.",
        ],
        "frames": frames,
    }
