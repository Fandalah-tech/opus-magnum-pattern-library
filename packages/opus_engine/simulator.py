from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .arm import ArmState
from .builder import DIRECTIONS, InputSource, build_input_sources, rotate_hex
from .model import Hex
from .world import World, WorldEvent

ROTATE_CW = {"rotate_cw", "rotate-clockwise"}
ROTATE_CCW = {"rotate_ccw", "rotate-counterclockwise"}
PIVOT_CW = {"pivot_cw", "pivot-clockwise"}
PIVOT_CCW = {"pivot_ccw", "pivot-counterclockwise"}
EXTEND = {"extend", "extend_piston"}
RETRACT = {"retract", "retract_piston"}
TRACK_PLUS = {"track_plus"}
TRACK_MINUS = {"track_minus"}
GRAB = {"grab"}
DROP = {"drop"}
RESET = {"reset"}


class SimulationError(RuntimeError):
    pass


@dataclass(slots=True)
class MotionProposal:
    arm_id: str
    atom_ids: set[str]
    destinations: dict[str, Hex]
    instruction: str


@dataclass(slots=True)
class ArmMutation:
    arm: ArmState
    rotation: int | None = None
    length: int | None = None
    origin: Hex | None = None
    track_index: int | None = None

    def apply(self) -> None:
        if self.rotation is not None:
            self.arm.rotation = self.rotation % 6
        if self.length is not None:
            self.arm.length = self.length
        if self.origin is not None:
            self.arm.origin = self.origin
        if self.track_index is not None:
            self.arm.track_index = self.track_index


@dataclass(slots=True)
class Simulator:
    world: World
    arms: dict[str, ArmState]
    inputs: list[InputSource] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.frames:
            self.frames.append(self.snapshot("initial"))

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        world = World()
        inputs = build_input_sources(puzzle, solution)
        for source in inputs:
            source.spawn(world)
        world.events = []

        track_cells: tuple[Hex, ...] = tuple(
            tuple(cell)
            for part in solution.get("parts", [])
            if part.get("type") == "track"
            for cell in (part.get("trackHexes") or [])
        )
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
                track_cells=track_cells,
            )
        return cls(world=world, arms=arms, inputs=inputs)

    def molecule_atom_ids(self, atom_id: str) -> set[str]:
        for molecule in self.world.molecules():
            if atom_id in molecule.atom_ids:
                return set(molecule.atom_ids)
        return {atom_id}

    def _grab(self, arm: ArmState) -> None:
        # OMSim treats grab on an arm that is already grabbing as a complete
        # no-op; free branches cannot acquire atoms on a later repeated grab.
        if arm.grabbing:
            return
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

    def _held_atom_ids(self, arm: ArmState) -> set[str]:
        result: set[str] = set()
        for root in set(arm.held_atoms.values()):
            result.update(self.molecule_atom_ids(root))
        return result

    def _rotate_proposal(self, arm: ArmState, center: Hex, steps: int, instruction: str) -> MotionProposal | None:
        atom_ids = self._held_atom_ids(arm)
        if not atom_ids:
            return None
        destinations: dict[str, Hex] = {}
        for atom_id in atom_ids:
            atom = self.world.atoms[atom_id]
            relative = (atom.position[0] - center[0], atom.position[1] - center[1])
            rotated = rotate_hex(relative, steps)
            destinations[atom_id] = (center[0] + rotated[0], center[1] + rotated[1])
        return MotionProposal(arm.id, atom_ids, destinations, instruction)

    def _pivot_proposals(self, arm: ArmState, steps: int, instruction: str) -> list[MotionProposal]:
        proposals: list[MotionProposal] = []
        handled: set[frozenset[str]] = set()
        for branch, root in arm.held_atoms.items():
            atom_ids = self.molecule_atom_ids(root)
            key = frozenset(atom_ids)
            if key in handled:
                continue
            handled.add(key)
            center = arm.tip(branch)
            destinations: dict[str, Hex] = {}
            for atom_id in atom_ids:
                atom = self.world.atoms[atom_id]
                relative = (atom.position[0] - center[0], atom.position[1] - center[1])
                rotated = rotate_hex(relative, steps)
                destinations[atom_id] = (center[0] + rotated[0], center[1] + rotated[1])
            proposals.append(MotionProposal(arm.id, atom_ids, destinations, instruction))
        return proposals

    def _translate_proposal(self, arm: ArmState, delta: Hex, instruction: str) -> MotionProposal | None:
        atom_ids = self._held_atom_ids(arm)
        if not atom_ids:
            return None
        return MotionProposal(
            arm.id,
            atom_ids,
            {
                atom_id: (
                    self.world.atoms[atom_id].position[0] + delta[0],
                    self.world.atoms[atom_id].position[1] + delta[1],
                )
                for atom_id in atom_ids
            },
            instruction,
        )

    def _validate_and_apply(self, proposals: list[MotionProposal]) -> None:
        destination_owner: dict[Hex, str] = {}
        moving_atoms = {atom_id for proposal in proposals for atom_id in proposal.atom_ids}
        proposed_for_atom: dict[str, Hex] = {}
        proposal_signatures: dict[str, tuple] = {}

        def signature(proposal: MotionProposal) -> tuple:
            arm = self.arms[proposal.arm_id]
            instruction = proposal.instruction
            if instruction in ROTATE_CW | ROTATE_CCW:
                return ("rotation", arm.origin, -1 if instruction in ROTATE_CW else 1)
            if instruction in PIVOT_CW | PIVOT_CCW:
                fixed = sorted(
                    self.world.atoms[atom_id].position
                    for atom_id, destination in proposal.destinations.items()
                    if self.world.atoms[atom_id].position == destination
                )
                return ("pivot", tuple(fixed), -1 if instruction in PIVOT_CW else 1)
            deltas = {
                (destination[0] - self.world.atoms[atom_id].position[0],
                 destination[1] - self.world.atoms[atom_id].position[1])
                for atom_id, destination in proposal.destinations.items()
            }
            return ("translation", tuple(sorted(deltas)))

        for proposal in proposals:
            current_signature = signature(proposal)
            for atom_id, destination in proposal.destinations.items():
                previous = proposed_for_atom.get(atom_id)
                if previous is not None and previous != destination:
                    raise SimulationError(f"Conflicting motions for atom {atom_id}")
                previous_signature = proposal_signatures.get(atom_id)
                if previous_signature is not None and previous_signature != current_signature:
                    raise SimulationError(f"Incompatible shared motions for atom {atom_id}")
                proposed_for_atom[atom_id] = destination
                proposal_signatures[atom_id] = current_signature
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

    def _plan_motion(self, arm: ArmState, instruction: str) -> tuple[list[MotionProposal], ArmMutation | None]:
        if instruction in ROTATE_CW or instruction in ROTATE_CCW:
            steps = -1 if instruction in ROTATE_CW else 1
            proposal = self._rotate_proposal(arm, arm.origin, steps, instruction)
            return ([proposal] if proposal else []), ArmMutation(arm, rotation=arm.rotation + steps)

        if instruction in PIVOT_CW or instruction in PIVOT_CCW:
            steps = -1 if instruction in PIVOT_CW else 1
            return self._pivot_proposals(arm, steps, instruction), None

        if instruction in EXTEND or instruction in RETRACT:
            if not arm.is_piston:
                return [], None
            next_length = min(3, arm.length + 1) if instruction in EXTEND else max(arm.base_length or 1, arm.length - 1)
            direction = DIRECTIONS[arm.rotation % 6]
            delta_units = next_length - arm.length
            delta = (direction[0] * delta_units, direction[1] * delta_units)
            proposal = self._translate_proposal(arm, delta, instruction)
            return ([proposal] if proposal else []), ArmMutation(arm, length=next_length)

        if instruction in TRACK_PLUS or instruction in TRACK_MINUS:
            if not arm.track_cells:
                return [], None
            step = 1 if instruction in TRACK_PLUS else -1
            next_index = arm.track_index + step
            if next_index < 0 or next_index >= len(arm.track_cells):
                raise SimulationError(f"Arm {arm.id} cannot move beyond its track")
            next_origin = arm.track_cells[next_index]
            delta = (next_origin[0] - arm.origin[0], next_origin[1] - arm.origin[1])
            proposal = self._translate_proposal(arm, delta, instruction)
            return ([proposal] if proposal else []), ArmMutation(
                arm, origin=next_origin, track_index=next_index,
            )

        if instruction in RESET:
            delta = (
                int(arm.base_origin[0]) - arm.origin[0],
                int(arm.base_origin[1]) - arm.origin[1],
            )
            proposals: list[MotionProposal] = []
            proposal = self._translate_proposal(arm, delta, instruction)
            if proposal:
                proposals.append(proposal)
            return proposals, ArmMutation(
                arm,
                origin=arm.base_origin,
                rotation=arm.base_rotation,
                length=arm.base_length,
                track_index=arm.base_track_index,
            )

        return [], None

    def _before_motion(self) -> None:
        """First-half hook, after grab/drop but before physical motion."""

    def _respawn_inputs(self) -> None:
        for source in self.inputs:
            source.spawn(self.world)

    def step(self, instructions: dict[str, str | None]) -> dict[str, Any]:
        self.world.events = []

        for arm_id in sorted(self.arms):
            instruction = instructions.get(arm_id)
            arm = self.arms[arm_id]
            if instruction in GRAB:
                self._grab(arm)
            elif instruction in DROP:
                self._drop(arm)

        self._before_motion()

        proposals: list[MotionProposal] = []
        mutations: list[ArmMutation] = []
        for arm_id in sorted(self.arms):
            instruction = instructions.get(arm_id)
            if not instruction:
                continue
            planned, mutation = self._plan_motion(self.arms[arm_id], str(instruction))
            proposals.extend(planned)
            if mutation:
                mutations.append(mutation)

        self._validate_and_apply(proposals)
        for mutation in mutations:
            mutation.apply()

        self._respawn_inputs()

        for arm_id, instruction in instructions.items():
            if instruction:
                self.world.events.append(WorldEvent("arm-instruction", self.world.cycle, {
                    "armId": arm_id, "instruction": instruction,
                }))

        self.world.cycle += 1
        frame = self.snapshot("after-instructions")
        self.frames.append(frame)
        return frame

    def run_timeline(self, timeline: dict[str, Any]) -> dict[str, Any]:
        for row in timeline.get("cycles", []):
            instructions = {
                str(event.get("partId")): event.get("instruction")
                for event in row.get("events", [])
            }
            try:
                self.step(instructions)
            except SimulationError as error:
                self.world.events.append(WorldEvent("simulation-error", self.world.cycle, {
                    "message": str(error),
                }))
                self.frames.append(self.snapshot("error"))
                break
        return {
            "schemaVersion": "0.2.0",
            "traceType": "opus-engine-experimental",
            "summary": {
                "frameCount": len(self.frames),
                "completedCycles": max(0, len(self.frames) - 1),
                "requestedCycles": len(timeline.get("cycles", [])),
                "terminatedWithError": self.frames[-1].get("phase") == "error",
            },
            "capabilities": {
                "rotation": True,
                "pivot": True,
                "piston": True,
                "track": True,
                "grabDrop": True,
                "inputRespawn": True,
                "transactionalCollisionCheck": True,
                "glyphs": False,
            },
            "frames": self.frames,
        }

    def snapshot(self, phase: str) -> dict[str, Any]:
        return {
            "cycle": self.world.cycle,
            "phase": phase,
            "arms": [arm.snapshot() for arm in sorted(self.arms.values(), key=lambda item: item.id)],
            "inputs": [
                {
                    "inputId": source.id,
                    "spawnCount": source.spawn_count,
                    "footprint": [list(position) for position in source.footprint],
                }
                for source in self.inputs
            ],
            "world": self.world.snapshot(),
            "events": [
                {"kind": event.kind, "cycle": event.cycle, **event.data}
                for event in self.world.events
            ],
        }
