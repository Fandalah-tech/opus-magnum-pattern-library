from __future__ import annotations

from typing import Any

from .builder import rotate_hex
from .model import Bond
from .runtime_simulator import METAL_ORDER, Simulator as RuntimeSimulator
from .simulator import ArmMutation, TRACK_MINUS, TRACK_PLUS
from .world import WorldEvent


def _absolute_track(part: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    origin = tuple(part.get("position") or (0, 0))
    return tuple(
        (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
        for cell in (part.get("trackHexes") or [])
    )


def _transform(
    position: tuple[int, int],
    origin: tuple[int, int],
    rotation: int,
) -> tuple[int, int]:
    rotated = rotate_hex(position, rotation)
    return origin[0] + rotated[0], origin[1] + rotated[1]


class Simulator(RuntimeSimulator):
    """Runtime simulator with faithful track ownership and safe atom consumption."""

    def __post_init__(self) -> None:
        self.prismatic_bonders = []
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        tracks = [
            _absolute_track(part)
            for part in solution.get("parts", [])
            if part.get("type") == "track" and part.get("trackHexes")
        ]
        for arm in simulator.arms.values():
            owned_track = next((track for track in tracks if arm.origin in track), None)
            if owned_track is None:
                owned_track = tracks[0] if tracks else ()
            arm.track_cells = owned_track
            if owned_track and arm.origin in owned_track:
                arm.track_index = owned_track.index(arm.origin)
            else:
                arm.track_index = 0
            arm.base_track_index = arm.track_index

        for part in solution.get("parts", []):
            if part.get("type") != "bonder-prisma":
                continue
            origin = tuple(part.get("position") or (0, 0))
            rotation = int(part.get("rotation") or 0)
            simulator.prismatic_bonders.append((
                (
                    _transform((0, 0), origin, rotation),
                    _transform((1, 0), origin, rotation),
                    _transform((0, 1), origin, rotation),
                ),
                str(part.get("id") or "bonder-prisma"),
            ))
        return simulator

    def _plan_motion(self, arm, instruction):
        if instruction in TRACK_PLUS or instruction in TRACK_MINUS:
            if not arm.track_cells:
                return [], None
            step = 1 if instruction in TRACK_PLUS else -1
            next_index = max(0, min(len(arm.track_cells) - 1, arm.track_index + step))
            next_origin = arm.track_cells[next_index]
            delta = (next_origin[0] - arm.origin[0], next_origin[1] - arm.origin[1])
            proposal = self._translate_proposal(arm, delta, instruction)
            return ([proposal] if proposal else []), ArmMutation(
                arm,
                origin=next_origin,
                track_index=next_index,
            )
        return super()._plan_motion(arm, instruction)

    def _detach_consumed_atom(self, atom_id: str) -> None:
        atom = self.world.atoms.get(atom_id)
        if atom is not None:
            for arm_id in list(atom.held_by):
                arm = self.arms.get(arm_id)
                if arm is None:
                    continue
                arm.held_atoms = {
                    branch: held_atom_id
                    for branch, held_atom_id in arm.held_atoms.items()
                    if held_atom_id != atom_id
                }
                if not arm.held_atoms:
                    arm.grabbing = False
            atom.held_by.clear()

    def _process_projection(self) -> None:
        for first_pos, second_pos, part_id in self.projection_glyphs:
            first = self.world.atom_at(first_pos)
            second = self.world.atom_at(second_pos)
            if first is None or second is None:
                continue

            if first.element == "quicksilver":
                quicksilver, metal = first, second
            elif second.element == "quicksilver":
                quicksilver, metal = second, first
            else:
                continue

            try:
                index = METAL_ORDER.index(metal.element)
            except ValueError:
                continue
            if index >= len(METAL_ORDER) - 1:
                continue

            previous = metal.element
            produced = METAL_ORDER[index + 1]
            consumed_id = quicksilver.id
            self._detach_consumed_atom(consumed_id)
            self.world.remove_atom(consumed_id)
            self._replace_atom_element(metal.id, produced)
            self.world.events.append(WorldEvent("atom-projected", self.world.cycle, {
                "glyphPartId": part_id,
                "consumedAtomId": consumed_id,
                "transformedAtomId": metal.id,
                "fromElement": previous,
                "toElement": produced,
                "position": list(metal.position),
            }))

    def _process_basic_glyphs(self) -> None:
        super()._process_basic_glyphs()
        for positions, part_id in self.prismatic_bonders:
            atoms = [self.world.atom_at(position) for position in positions]
            if any(atom is None for atom in atoms):
                continue
            for first_index, second_index in ((0, 1), (1, 2), (2, 0)):
                first = atoms[first_index]
                second = atoms[second_index]
                if first is None or second is None or first.id == second.id:
                    continue
                bond = Bond(first.id, second.id, "normal")
                if bond.key in self.world.bonds:
                    continue
                self.world.add_bond(bond)
                self.world.events.append(WorldEvent("bond-created", self.world.cycle, {
                    "glyphPartId": part_id,
                    "fromAtomId": first.id,
                    "toAtomId": second.id,
                    "type": "normal",
                    "prismatic": True,
                }))
