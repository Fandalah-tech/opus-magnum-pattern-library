from __future__ import annotations

from typing import Any

from .builder import rotate_hex
from .complete_simulator import Simulator as CompleteSimulator
from .model import Atom
from .simulator import ArmMutation, MotionProposal, RESET, SimulationError, Simulator as BaseSimulator
from .world import WorldEvent

VAN_BERLO_ELEMENTS = ("salt", "water", "air", "salt", "fire", "earth")


class Simulator(CompleteSimulator):
    """Campaign-complete simulator surface."""

    def __post_init__(self) -> None:
        self.van_berlo_arms = []
        self.completed_repeating_outputs = set()
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        simulator.van_berlo_arms = [
            arm for arm in simulator.arms.values() if arm.part_type == "baron"
        ]
        for arm in simulator.van_berlo_arms:
            arm.grabbing = True
            for branch, element in enumerate(VAN_BERLO_ELEMENTS):
                atom_id = f"{arm.id}-wheel-{branch}"
                atom = Atom(atom_id, element, arm.tip(branch))
                atom.held_by.add(arm.id)
                simulator.world.add_atom(atom)
                arm.held_atoms[branch] = atom_id
        if simulator.van_berlo_arms:
            simulator.frames[0] = simulator.snapshot("initial")
        return simulator

    def _plan_motion(self, arm, instruction):
        if arm.part_type == "baron" and instruction in RESET:
            atom_ids = self._held_atom_ids(arm)
            destinations = {}
            rotation_steps = int(arm.base_rotation) - arm.rotation
            target_origin = arm.base_origin
            for atom_id in atom_ids:
                atom = self.world.atoms[atom_id]
                relative = (
                    atom.position[0] - arm.origin[0],
                    atom.position[1] - arm.origin[1],
                )
                rotated = rotate_hex(relative, rotation_steps)
                destinations[atom_id] = (
                    int(target_origin[0]) + rotated[0],
                    int(target_origin[1]) + rotated[1],
                )
            proposal = MotionProposal(arm.id, atom_ids, destinations, instruction) if atom_ids else None
            return ([proposal] if proposal else []), ArmMutation(
                arm,
                origin=arm.base_origin,
                rotation=arm.base_rotation,
                length=arm.base_length,
                track_index=arm.base_track_index,
            )
        return super()._plan_motion(arm, instruction)

    def _molecule_signature(self, atom_ids):
        atoms, bonds = super()._molecule_signature(atom_ids)
        triplex_pairs = {
            tuple(sorted((start, end)))
            for kind, start, end in bonds
            if kind == "triplex"
        }
        normalized = tuple(
            bond for bond in bonds
            if not (
                bond[0] == "normal"
                and tuple(sorted((bond[1], bond[2]))) in triplex_pairs
            )
        )
        return atoms, normalized

    def repeating_product_complete(self, output_id: str, repetitions: int = 3) -> bool:
        if output_id in self.completed_repeating_outputs:
            return True
        return super().repeating_product_complete(output_id, repetitions)

    def _latch_repeating_outputs(self) -> None:
        for output_id, *_ in self.repeating_patterns:
            if output_id in self.completed_repeating_outputs:
                continue
            if super().repeating_product_complete(output_id, 3):
                self.completed_repeating_outputs.add(output_id)
                self.world.events.append(WorldEvent("repeating-product-completed", self.world.cycle, {
                    "consumerPartId": output_id,
                    "repetitions": 3,
                }))

    def _capture_bonder_collisions(self, proposals) -> None:
        """Resolve the transient overlap produced at a bonder endpoint.

        During the first half-cycle a moving atom may enter an occupied bonder
        endpoint while the opposite endpoint is free. OMSim displaces the
        stationary atom to that opposite endpoint before the collision phase;
        the regular glyph pass then decides whether a bond can be created.
        """
        moving_atoms = {atom_id for proposal in proposals for atom_id in proposal.atom_ids}
        destinations = {
            destination: atom_id
            for proposal in proposals
            for atom_id, destination in proposal.destinations.items()
        }
        for first_pos, second_pos, part_id in self.bonder_pairs:
            for occupied_pos, free_pos in ((first_pos, second_pos), (second_pos, first_pos)):
                if occupied_pos not in destinations:
                    continue
                stationary = self.world.atom_at(occupied_pos)
                if (
                    stationary is None
                    or stationary.id in moving_atoms
                    or self.world.atom_at(free_pos) is not None
                ):
                    continue
                stationary.position = free_pos
                self.world.events.append(WorldEvent("atom-bonder-displaced", self.world.cycle, {
                    "glyphPartId": part_id,
                    "atomId": stationary.id,
                    "from": list(occupied_pos),
                    "to": list(free_pos),
                }))

    def _validate_and_apply(self, proposals) -> None:
        self._capture_bonder_collisions(proposals)
        try:
            super()._validate_and_apply(proposals)
        except SimulationError as error:
            output_cells = {
                position
                for _, _, expected_atoms, _ in self.output_patterns
                for position, _ in expected_atoms
            }
            candidates = []
            for molecule in self.world.molecules():
                if not any(
                    self.world.atoms[atom_id].position in output_cells
                    for atom_id in molecule.atom_ids
                ):
                    continue
                atoms, bonds = self._molecule_signature(set(molecule.atom_ids))
                candidates.append({
                    "atomIds": sorted(molecule.atom_ids),
                    "atoms": list(atoms),
                    "bonds": list(bonds),
                    "heldBy": {
                        atom_id: sorted(self.world.atoms[atom_id].held_by)
                        for atom_id in sorted(molecule.atom_ids)
                        if self.world.atoms[atom_id].held_by
                    },
                })
            motion_state = [
                {
                    "armId": proposal.arm_id,
                    "instruction": proposal.instruction,
                    "sources": {
                        atom_id: list(self.world.atoms[atom_id].position)
                        for atom_id in sorted(proposal.atom_ids)
                    },
                    "destinations": {
                        atom_id: list(destination)
                        for atom_id, destination in sorted(proposal.destinations.items())
                    },
                    "arm": self.arms[proposal.arm_id].snapshot(),
                }
                for proposal in proposals
            ]
            raise SimulationError(
                f"{error}; motionState={motion_state}; outputCandidates={candidates}"
            ) from error

    def _before_motion(self) -> None:
        self._process_basic_glyphs()

    def _respawn_inputs(self) -> None:
        BaseSimulator._respawn_inputs(self)
        self._process_calcification()
        self._process_duplication()
        self._process_animismus()
        self._process_basic_glyphs()
        self._process_projection()
        self._process_purification()
        self._latch_repeating_outputs()
        self._process_consumers()
