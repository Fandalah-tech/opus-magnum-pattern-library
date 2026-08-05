from __future__ import annotations

from copy import deepcopy
from typing import Any

from .replay import (
    _add,
    _apply_instruction,
    _detach_consumed,
    _expected_product,
    _frame,
    _initial_arm_state,
    _input_templates,
    _process_consumers,
    _respawn_inputs,
    _rotate_vector,
    _signature,
    _spawn_molecule,
    _track_cells,
)

METAL_ORDER = ("lead", "tin", "iron", "copper", "silver", "gold")
CALCIFIABLE = {"air", "earth", "fire", "water"}


def _transform(local: list[int] | tuple[int, int], part: dict[str, Any]) -> list[int]:
    origin = list(part.get("position") or [0, 0])
    rotation = int(part.get("rotation") or 0)
    return _add(origin, _rotate_vector(list(local), rotation))


def _atom_at(molecules: list[dict[str, Any]], position: list[int]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for molecule in molecules:
        for atom in molecule.get("atoms", []):
            if atom.get("position") == position:
                return molecule, atom
    return None


def _bond_exists(molecule: dict[str, Any], first: list[int], second: list[int]) -> bool:
    target = {tuple(first), tuple(second)}
    return any(
        {tuple(bond.get("from") or [0, 0]), tuple(bond.get("to") or [0, 0])} == target
        for bond in molecule.get("bonds", [])
    )


def _replace_held_molecule_id(
    states: dict[str, dict[str, Any]], old_id: str, new_id: str,
) -> None:
    for state in states.values():
        state["heldMoleculeIds"] = [
            new_id if molecule_id == old_id else molecule_id
            for molecule_id in state.get("heldMoleculeIds", [])
        ]
        state["heldMoleculeIds"] = list(dict.fromkeys(state["heldMoleculeIds"]))
        for attachment in state.get("heldAttachments", []):
            if attachment.get("moleculeId") == old_id:
                attachment["moleculeId"] = new_id


def _merge_molecules(
    molecules: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    if first is second:
        return first
    first["atoms"].extend(second.get("atoms", []))
    first["bonds"].extend(second.get("bonds", []))
    holders = first.setdefault("heldBy", [])
    for holder in second.get("heldBy", []):
        if holder not in holders:
            holders.append(holder)
    _replace_held_molecule_id(states, str(second["id"]), str(first["id"]))
    molecules.remove(second)
    return first


def _process_bonders(
    solution: dict[str, Any], molecules: list[dict[str, Any]], states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in solution.get("parts", []):
        if part.get("type") != "bonder":
            continue
        first_pos = _transform((0, 0), part)
        second_pos = _transform((1, 0), part)
        first_hit = _atom_at(molecules, first_pos)
        second_hit = _atom_at(molecules, second_pos)
        if first_hit is None or second_hit is None:
            continue
        first_molecule, first_atom = first_hit
        second_molecule, second_atom = second_hit
        if first_atom.get("id") == second_atom.get("id"):
            continue
        merged = _merge_molecules(molecules, states, first_molecule, second_molecule)
        if _bond_exists(merged, first_pos, second_pos):
            continue
        bond_id = f"{part.get('id')}-bond-{len(merged.get('bonds', []))}"
        merged.setdefault("bonds", []).append({
            "id": bond_id,
            "type": "normal",
            "from": list(first_pos),
            "to": list(second_pos),
        })
        events.append({
            "kind": "bond-created",
            "glyphPartId": part.get("id"),
            "fromAtomId": first_atom.get("id"),
            "toAtomId": second_atom.get("id"),
            "type": "normal",
        })
    return events


def _process_calcification(solution: dict[str, Any], molecules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in solution.get("parts", []):
        if part.get("type") != "glyph-calcification":
            continue
        position = _transform((0, 0), part)
        hit = _atom_at(molecules, position)
        if hit is None:
            continue
        _, atom = hit
        previous = atom.get("element")
        if previous not in CALCIFIABLE:
            continue
        atom["element"] = "salt"
        events.append({
            "kind": "atom-calcified",
            "glyphPartId": part.get("id"),
            "atomId": atom.get("id"),
            "fromElement": previous,
            "toElement": "salt",
            "position": list(position),
        })
    return events


def _remove_atom_from_molecule(
    molecules: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    molecule: dict[str, Any],
    atom: dict[str, Any],
) -> None:
    position = tuple(atom.get("position") or [0, 0])
    molecule["atoms"] = [item for item in molecule.get("atoms", []) if item.get("id") != atom.get("id")]
    molecule["bonds"] = [
        bond for bond in molecule.get("bonds", [])
        if tuple(bond.get("from") or [0, 0]) != position
        and tuple(bond.get("to") or [0, 0]) != position
    ]
    if molecule["atoms"]:
        return
    _detach_consumed(str(molecule["id"]), states)
    molecules.remove(molecule)


def _process_projection(
    solution: dict[str, Any], molecules: list[dict[str, Any]], states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in solution.get("parts", []):
        if part.get("type") != "glyph-projection":
            continue
        first_pos = _transform((0, 0), part)
        second_pos = _transform((1, 0), part)
        first_hit = _atom_at(molecules, first_pos)
        second_hit = _atom_at(molecules, second_pos)
        if first_hit is None or second_hit is None:
            continue
        first_molecule, first_atom = first_hit
        second_molecule, second_atom = second_hit
        if first_atom.get("element") == "quicksilver":
            quick_molecule, quicksilver = first_molecule, first_atom
            metal = second_atom
        elif second_atom.get("element") == "quicksilver":
            quick_molecule, quicksilver = second_molecule, second_atom
            metal = first_atom
        else:
            continue
        try:
            metal_index = METAL_ORDER.index(str(metal.get("element")))
        except ValueError:
            continue
        if metal_index >= len(METAL_ORDER) - 1:
            continue
        previous = str(metal.get("element"))
        produced = METAL_ORDER[metal_index + 1]
        _remove_atom_from_molecule(molecules, states, quick_molecule, quicksilver)
        metal["element"] = produced
        events.append({
            "kind": "atom-projected",
            "glyphPartId": part.get("id"),
            "consumedAtomId": quicksilver.get("id"),
            "transformedAtomId": metal.get("id"),
            "fromElement": previous,
            "toElement": produced,
            "position": list(metal.get("position") or [0, 0]),
        })
    return events


def _process_supported_glyphs(
    solution: dict[str, Any], molecules: list[dict[str, Any]], states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    events = _process_bonders(solution, molecules, states)
    events.extend(_process_calcification(solution, molecules))
    events.extend(_process_projection(solution, molecules, states))
    return events


def build_chemical_replay_trace(
    puzzle: dict[str, Any], solution: dict[str, Any], timeline: dict[str, Any],
) -> dict[str, Any]:
    parts = {part["id"]: part for part in solution.get("parts", [])}
    track = _track_cells(solution)
    arm_parts = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    states = {part["id"]: _initial_arm_state(part, track) for part in arm_parts}
    templates = _input_templates(puzzle, solution)
    molecules = [_spawn_molecule(template) for template in templates]
    total_delivered: dict[str, int] = {}
    frames = [_frame(
        cycle=-1, display_cycle=0, phase=0, phase_label="initial", events=[],
        states=states, molecules=molecules, active_arm_count=0,
    )]

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

        events.extend(_process_supported_glyphs(solution, molecules, states))
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
        "traceType": "independent-chemical-replay",
        "source": "opus-analysis",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": timeline.get("summary", {}).get("horizon", max(0, len(frames) - 1)),
            "remainingMoleculeCount": len(molecules),
            "deliveredProducts": total_delivered,
        },
        "capabilities": {
            "physicalArmAnimation": True,
            "inputRespawn": True,
            "outputDelivery": True,
            "glyphSimulation": True,
            "supportedGlyphs": ["bonder", "glyph-calcification", "glyph-projection"],
        },
        "frames": frames,
    }
