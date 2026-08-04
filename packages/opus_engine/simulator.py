from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .arm import ArmState
from .builder import rotate_hex
from .model import Hex
from .world import World, WorldEvent

ROTATE_CW = {"rotate_cw", "rotate-clockwise"}
ROTATE_CCW = {"rotate_ccw", "rotate-counterclockwise"}
GRAB = {"grab"}
DROP = {"drop"}


class SimulationError(RuntimeError):
    pass


@dataclass(slots=True)
class MotionProposal:
    arm_id: str
    atom_ids: set[str]
    destinations: dict[str, Hex]
    instruction: str


@dataclass(slots=True)
class Simulator:
    world: World
    arms: dict[str, ArmState]
    frames: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.frames:
            self.frames.append(self.snapshot("initial"))

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        from .builder import build_initial_world

        world = build_initial_world(puzzle, solution)
        arms: dict[str, ArmState] = {}
        for part in solution.get("parts", []):
            part_type = str(part.get("type") or "")
            if not (part_type.startswith("arm") or part_type in {"piston", "baron"}):
                continue
            arms[str(part["id"])] = ArmState(
                id=str(part["id"]),
                part_type=part_type,
                origin=tuple(part.get("position") or (0, 0)),
                rotation=int(part.get("rotation") or 0),
                length=max(1, int(part.get("length") or 1)),
            )
        return cls(world=world, arms=arms)

    def molecule_atom_ids(self, atom_id: str) -> set[str]:
        for molecule in self.world.molecules():
            if atom_id in molecule.atom_ids:
                return set(molecule.atom_ids)
        return {atom_id}

    def _grab(self, arm: ArmState) -> None:
        arm.grabbing = True
        already_held = set(arm.held_atoms.values())
        for branch, tip in arm.tips().items():
            atom = self.world.atom_at(tip)
            if atom is None or atom.id in already_held:
                continue
            arm.held_atoms[branch] = atom.id
            atom.held_by.add(arm.id)
            already_held.add(atom.id)
            self.world.events.append(WorldEvent("atom-grabbed", self.world.cycle, {
                "armId": arm.id, "branchIndex": branch, "atomId": atom.id,
            }))

    def _drop(self, arm: ArmState) -> None:
        for atom_id in arm.held_atoms.values():
            atom = self.world.atoms.get(atom_id)
            if atom is not None:
                atom.held_by.discard(arm.id)
        if arm.held_atoms:
            self.world.events.append(WorldEvent("atoms-dropped", self.world.cycle, {
                "armId": arm.id, "atomIds": sorted(set(arm.held_atoms.values())),
            }))
        arm.held_atoms.clear()
        arm.grabbing = False

    def _rotation_proposal(self, arm: ArmState, steps: int, instruction: str) -> MotionProposal | None:
        held_roots = set(arm.held_atoms.values())
        if not held_roots:
            return None

        atom_ids: set[str] = set()
        for root in held_roots:
            atom_ids.update(self.molecule_atom_ids(root))
        destinations: dict[str, Hex] = {}
        for atom_id in atom_ids:
            atom = self.world.atoms[atom_id]
            relative = (atom.position[0] - arm.origin[0], atom.position[1] - arm.origin[1])
            rotated = rotate_hex(relative, steps)
            destinations[atom_id] = (arm.origin[0] + rotated[0], arm.origin[1] + rotated[1])
        return MotionProposal(arm.id, atom_ids, destinations, instruction)

    def _validate_and_apply(self, proposals: list[MotionProposal]) -> None:
        destination_owner: dict[Hex, str] = {}
        moving_atoms = {atom_id for proposal in proposals for atom_id in proposal.atom_ids}
        proposed_for_atom: dict[str, Hex] = {}

        for proposal in proposals:
            for atom_id, destination in proposal.destinations.items():
                previous = proposed_for_atom.get(atom_id)
                if previous is not None and previous != destination:
                    raise SimulationError(f"Conflicting motions for atom {atom_id}")
                proposed_for_atom[atom_id] = destination
                owner = destination_owner.get(destination)
                if owner is not None and owner != atom_id:
                    raise SimulationError(f"Motion collision at {destination}")
                destination_owner[destination] = atom_id

        stationary = {
            atom.position: atom.id
            for atom in self.world.atoms.values()
            if atom.id not in moving_atoms
        }
        for destination, atom_id in destination_owner.items():
            if destination in stationary:
                raise SimulationError(
                    f"Atom {atom_id} collides with stationary atom {stationary[destination]} at {destination}"
                )

        for atom_id, destination in proposed_for_atom.items():
            self.world.atoms[atom_id].position = destination

    def step(self, instructions: dict[str, str | None]) -> dict[str, Any]:
        self.world.events = []

        for arm_id in sorted(self.arms):
            instruction = instructions.get(arm_id)
            arm = self.arms[arm_id]
            if instruction in GRAB:
                self._grab(arm)
            elif instruction in DROP:
                self._drop(arm)

        proposals: list[MotionProposal] = []
        rotations: list[tuple[ArmState, int]] = []
        for arm_id in sorted(self.arms):
            instruction = instructions.get(arm_id)
            arm = self.arms[arm_id]
            if instruction in ROTATE_CW:
                proposal = self._rotation_proposal(arm, -1, str(instruction))
                if proposal:
                    proposals.append(proposal)
                rotations.append((arm, -1))
            elif instruction in ROTATE_CCW:
                proposal = self._rotation_proposal(arm, 1, str(instruction))
                if proposal:
                    proposals.append(proposal)
                rotations.append((arm, 1))

        self._validate_and_apply(proposals)
        for arm, steps in rotations:
            arm.rotation = (arm.rotation + steps) % 6

        for arm_id, instruction in instructions.items():
            if instruction:
                self.world.events.append(WorldEvent("arm-instruction", self.world.cycle, {
                    "armId": arm_id, "instruction": instruction,
                }))

        self.world.cycle += 1
        frame = self.snapshot("after-instructions")
        self.frames.append(frame)
        return frame

    def snapshot(self, phase: str) -> dict[str, Any]:
        return {
            "cycle": self.world.cycle,
            "phase": phase,
            "arms": [arm.snapshot() for arm in sorted(self.arms.values(), key=lambda item: item.id)],
            "world": self.world.snapshot(),
            "events": [
                {"kind": event.kind, "cycle": event.cycle, **event.data}
                for event in self.world.events
            ],
        }
