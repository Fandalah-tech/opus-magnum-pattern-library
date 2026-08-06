from __future__ import annotations

from typing import Any

from .builder import DIRECTIONS, rotate_hex
from .complete_simulator import Simulator as CompleteSimulator
from .model import Atom, Bond
from .simulator import (
    ArmMutation,
    MotionProposal,
    RESET,
    ROTATE_CCW,
    ROTATE_CW,
    SimulationError,
    Simulator as BaseSimulator,
)
from .world import WorldEvent

VAN_BERLO_ELEMENTS = ("salt", "water", "air", "salt", "fire", "earth")


class Simulator(CompleteSimulator):
    """Campaign-complete simulator surface."""

    def __post_init__(self) -> None:
        self.van_berlo_arms = []
        self.completed_repeating_outputs = set()
        self.floating_bond_roots: dict[tuple[str, str, str], str] = {}
        self.pending_floating_pairs: dict[frozenset[str], str] = {}
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        simulator.van_berlo_arms = [arm for arm in simulator.arms.values() if arm.part_type == "baron"]
        for arm in simulator.van_berlo_arms:
            arm.grabbing = True
            for branch, element in enumerate(VAN_BERLO_ELEMENTS):
                atom_id = f"{arm.id}-wheel-{branch}"
                atom = Atom(atom_id, element, arm.tip(branch))
                atom.held_by.add(arm.id)
                simulator.world.atoms[atom_id] = atom
                arm.held_atoms[branch] = atom_id
        if simulator.van_berlo_arms:
            simulator.frames[0] = simulator.snapshot("initial")
        return simulator

    @staticmethod
    def _is_wheel_atom_id(atom_id: str) -> bool:
        return "-wheel-" in atom_id

    def _atoms_at(self, position):
        return [atom for atom in self.world.atoms.values() if atom.position == position]

    def molecule_atom_ids(self, atom_id: str) -> set[str]:
        if atom_id not in self.world.atoms:
            return {atom_id}
        adjacency: dict[str, set[str]] = {item: set() for item in self.world.atoms}
        for key, bond in self.world.bonds.items():
            root = self.floating_bond_roots.get(key)
            if root is None:
                adjacency[bond.a].add(bond.b)
                adjacency[bond.b].add(bond.a)
                continue
            payload = bond.b if bond.a == root else bond.a
            adjacency[root].add(payload)
        component = {atom_id}
        stack = [atom_id]
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, ()):
                if neighbor not in component:
                    component.add(neighbor)
                    stack.append(neighbor)
        return component

    def _baron_attached_atom_ids(self, arm) -> set[str]:
        atom_ids = self._held_atom_ids(arm)
        for branch in range(6):
            tip = arm.tip(branch)
            for atom in self._atoms_at(tip):
                if self._is_wheel_atom_id(atom.id):
                    continue
                atom_ids.update(self.molecule_atom_ids(atom.id))
        return atom_ids

    def _baron_rotation_proposal(self, arm, instruction):
        steps = -1 if instruction in ROTATE_CW else 1
        atom_ids = self._baron_attached_atom_ids(arm)
        destinations = {}
        for atom_id in atom_ids:
            atom = self.world.atoms[atom_id]
            relative = (atom.position[0] - arm.origin[0], atom.position[1] - arm.origin[1])
            rotated = rotate_hex(relative, steps)
            destinations[atom_id] = (arm.origin[0] + rotated[0], arm.origin[1] + rotated[1])
        proposal = MotionProposal(arm.id, atom_ids, destinations, instruction) if atom_ids else None
        return ([proposal] if proposal else []), ArmMutation(arm, rotation=arm.rotation + steps)

    def _plan_motion(self, arm, instruction):
        if arm.part_type == "baron" and instruction in ROTATE_CW | ROTATE_CCW:
            return self._baron_rotation_proposal(arm, instruction)
        if arm.part_type == "baron" and instruction in RESET:
            atom_ids = self._baron_attached_atom_ids(arm)
            destinations = {}
            rotation_steps = int(arm.base_rotation) - arm.rotation
            target_origin = arm.base_origin
            for atom_id in atom_ids:
                atom = self.world.atoms[atom_id]
                relative = (atom.position[0] - arm.origin[0], atom.position[1] - arm.origin[1])
                rotated = rotate_hex(relative, rotation_steps)
                destinations[atom_id] = (int(target_origin[0]) + rotated[0], int(target_origin[1]) + rotated[1])
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
        triplex_pairs = {tuple(sorted((start, end))) for kind, start, end in bonds if kind == "triplex"}
        normalized = tuple(
            bond for bond in bonds
            if not (bond[0] == "normal" and tuple(sorted((bond[1], bond[2]))) in triplex_pairs)
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
                self.world.events.append(WorldEvent("repeating-product-completed", self.world.cycle, {"consumerPartId": output_id, "repetitions": 3}))

    @staticmethod
    def _adjacent_positions(first, second) -> bool:
        delta = (second[0] - first[0], second[1] - first[1])
        return delta in set(DIRECTIONS)

    def _settle_floating_bonds(self) -> None:
        for key, root_id in list(self.floating_bond_roots.items()):
            bond = self.world.bonds.get(key)
            if bond is None:
                self.floating_bond_roots.pop(key, None)
                continue
            first = self.world.atoms.get(bond.a)
            second = self.world.atoms.get(bond.b)
            if first is None or second is None:
                self.floating_bond_roots.pop(key, None)
                continue
            if not first.held_by and not second.held_by and self._adjacent_positions(first.position, second.position):
                self.floating_bond_roots.pop(key, None)
                self.world.events.append(WorldEvent("floating-bond-settled", self.world.cycle, {"fromAtomId": bond.a, "toAtomId": bond.b, "rootAtomId": root_id, "type": bond.kind}))

    def _translate_stationary_component(self, stationary_id, occupied_pos, free_pos, moving_atoms):
        dq = free_pos[0] - occupied_pos[0]
        dr = free_pos[1] - occupied_pos[1]
        queued = [stationary_id]
        components: list[set[str]] = []
        selected: set[str] = set()
        while queued:
            root = queued.pop()
            if root in selected:
                continue
            component = self.molecule_atom_ids(root)
            if component & moving_atoms:
                return False
            components.append(component)
            selected.update(component)
            targets = {
                (self.world.atoms[atom_id].position[0] + dq, self.world.atoms[atom_id].position[1] + dr)
                for atom_id in component
            }
            for atom in self.world.atoms.values():
                if atom.id in selected or atom.id in moving_atoms or self._is_wheel_atom_id(atom.id):
                    continue
                if atom.position in targets:
                    queued.append(atom.id)
        destinations = {
            atom_id: (
                self.world.atoms[atom_id].position[0] + dq,
                self.world.atoms[atom_id].position[1] + dr,
            )
            for component in components
            for atom_id in component
        }
        if len(set(destinations.values())) != len(destinations):
            return False
        for atom_id, position in destinations.items():
            self.world.atoms[atom_id].position = position
        self.world.events.append(WorldEvent("bonder-chain-shifted", self.world.cycle, {
            "rootAtomId": stationary_id,
            "atomIds": sorted(destinations),
            "delta": [dq, dr],
        }))
        return True

    def _capture_bonder_collisions(self, proposals) -> None:
        moving_atoms = {atom_id for proposal in proposals for atom_id in proposal.atom_ids}
        destinations = {
            destination: atom_id
            for proposal in proposals
            for atom_id, destination in proposal.destinations.items()
            if not self._is_wheel_atom_id(atom_id)
        }
        for first_pos, second_pos, part_id in self.bonder_pairs:
            for occupied_pos, free_pos in ((first_pos, second_pos), (second_pos, first_pos)):
                moving_atom_id = destinations.get(occupied_pos)
                if moving_atom_id is None:
                    continue
                stationary = next((atom for atom in self._atoms_at(occupied_pos) if not self._is_wheel_atom_id(atom.id)), None)
                if stationary is None or stationary.id in moving_atoms:
                    continue
                free_occupied = any(not self._is_wheel_atom_id(atom.id) for atom in self._atoms_at(free_pos))
                if free_occupied:
                    if not self._translate_stationary_component(stationary.id, occupied_pos, free_pos, moving_atoms):
                        continue
                    self.world.events.append(WorldEvent("bonder-payload-shifted", self.world.cycle, {
                        "glyphPartId": part_id,
                        "rootAtomId": stationary.id,
                        "from": list(occupied_pos),
                        "toward": list(free_pos),
                    }))
                    continue
                stationary.position = free_pos
                pair = frozenset((moving_atom_id, stationary.id))
                self.pending_floating_pairs[pair] = stationary.id
                self.world.events.append(WorldEvent("atom-bonder-displaced", self.world.cycle, {"glyphPartId": part_id, "atomId": stationary.id, "from": list(occupied_pos), "to": list(free_pos)}))

    def _mark_pending_floating_bonds(self) -> None:
        for pair, root_id in list(self.pending_floating_pairs.items()):
            if len(pair) != 2:
                self.pending_floating_pairs.pop(pair, None)
                continue
            first, second = tuple(pair)
            key = Bond(first, second, "normal").key
            if key in self.world.bonds:
                self.floating_bond_roots[key] = root_id
                self.pending_floating_pairs.pop(pair, None)
                self.world.events.append(WorldEvent("floating-bond-created", self.world.cycle, {"fromAtomId": first, "toAtomId": second, "rootAtomId": root_id, "type": "normal"}))

    def _apply_without_wheel_colliders(self, proposals) -> None:
        wheel_atoms = {atom_id: atom for atom_id, atom in list(self.world.atoms.items()) if self._is_wheel_atom_id(atom_id)}
        wheel_destinations = {atom_id: destination for proposal in proposals for atom_id, destination in proposal.destinations.items() if atom_id in wheel_atoms}
        ordinary_proposals = []
        for proposal in proposals:
            atom_ids = {atom_id for atom_id in proposal.atom_ids if atom_id not in wheel_atoms}
            if not atom_ids:
                continue
            ordinary_proposals.append(MotionProposal(proposal.arm_id, atom_ids, {atom_id: destination for atom_id, destination in proposal.destinations.items() if atom_id in atom_ids}, proposal.instruction))
        for atom_id in wheel_atoms:
            self.world.atoms.pop(atom_id, None)
        try:
            super()._validate_and_apply(ordinary_proposals)
        finally:
            for atom_id, atom in wheel_atoms.items():
                atom.position = wheel_destinations.get(atom_id, atom.position)
                self.world.atoms[atom_id] = atom

    def _validate_and_apply(self, proposals) -> None:
        self._capture_bonder_collisions(proposals)
        try:
            self._apply_without_wheel_colliders(proposals)
        except SimulationError as error:
            output_cells = {position for _, _, expected_atoms, _ in self.output_patterns for position, _ in expected_atoms}
            candidates = []
            for molecule in self.world.molecules():
                if not any(self.world.atoms[atom_id].position in output_cells for atom_id in molecule.atom_ids):
                    continue
                atoms, bonds = self._molecule_signature(set(molecule.atom_ids))
                candidates.append({"atomIds": sorted(molecule.atom_ids), "atoms": list(atoms), "bonds": list(bonds), "heldBy": {atom_id: sorted(self.world.atoms[atom_id].held_by) for atom_id in sorted(molecule.atom_ids) if self.world.atoms[atom_id].held_by}})
            motion_state = [{"armId": proposal.arm_id, "instruction": proposal.instruction, "sources": {atom_id: list(self.world.atoms[atom_id].position) for atom_id in sorted(proposal.atom_ids)}, "destinations": {atom_id: list(destination) for atom_id, destination in sorted(proposal.destinations.items())}, "arm": self.arms[proposal.arm_id].snapshot()} for proposal in proposals]
            raise SimulationError(f"{error}; motionState={motion_state}; outputCandidates={candidates}") from error

    def _disjoint_output_atom_ids(self, expected_atoms, expected_bonds):
        expected_by_position = dict(expected_atoms)
        selected = {}
        for position, element in expected_by_position.items():
            candidates = [
                atom for atom in self._atoms_at(position)
                if not self._is_wheel_atom_id(atom.id)
            ]
            if len(candidates) != 1 or candidates[0].element != element:
                return None
            atom = candidates[0]
            if atom.held_by:
                return None
            selected[position] = atom
        selected_ids = {atom.id for atom in selected.values()}
        expected = {
            (kind, tuple(sorted((start, end))))
            for kind, start, end in expected_bonds
        }
        actual = set()
        for bond in self.world.bonds.values():
            touches = bond.a in selected_ids or bond.b in selected_ids
            if not touches:
                continue
            if bond.a not in selected_ids or bond.b not in selected_ids:
                return None
            first = self.world.atoms[bond.a].position
            second = self.world.atoms[bond.b].position
            actual.add((bond.kind, tuple(sorted((first, second)))))
        if actual != expected:
            return None
        return selected_ids

    def _process_consumers(self) -> None:
        delivered_ids = set()
        for output_id, product_index, expected_atoms, expected_bonds in self.output_patterns:
            atom_ids = self._disjoint_output_atom_ids(expected_atoms, expected_bonds)
            if not atom_ids:
                continue
            delivered_ids.update(atom_ids)
            self.delivered_products[output_id] = self.delivered_products.get(output_id, 0) + 1
            self.world.events.append(WorldEvent("product-delivered", self.world.cycle, {
                "consumerType": "output",
                "consumerPartId": output_id,
                "productIndex": product_index,
                "atomIds": sorted(atom_ids),
                "disjoint": True,
            }))
        if delivered_ids:
            self._remove_molecule(delivered_ids)
        super()._process_consumers()

    def _before_motion(self) -> None:
        self._settle_floating_bonds()
        self._process_basic_glyphs()
        self._mark_pending_floating_bonds()

    def _respawn_inputs(self) -> None:
        BaseSimulator._respawn_inputs(self)
        self._process_calcification()
        self._process_duplication()
        self._process_animismus()
        self._process_basic_glyphs()
        self._mark_pending_floating_bonds()
        self._process_projection()
        self._process_purification()
        self._latch_repeating_outputs()
        self._process_consumers()
