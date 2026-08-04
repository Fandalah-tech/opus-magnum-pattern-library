from __future__ import annotations

from dataclasses import dataclass, field

from .builder import DIRECTIONS, add_hex
from .model import Hex


def branch_offsets(part_type: str) -> tuple[int, ...]:
    return tuple(range(6)) if part_type == "arm6" else (0,)


@dataclass(slots=True)
class ArmState:
    id: str
    part_type: str
    origin: Hex
    rotation: int
    length: int = 1
    base_origin: Hex | None = None
    base_rotation: int | None = None
    base_length: int | None = None
    grabbing: bool = False
    held_atoms: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rotation %= 6
        self.length = max(1, self.length)
        self.base_origin = self.origin if self.base_origin is None else self.base_origin
        self.base_rotation = self.rotation if self.base_rotation is None else self.base_rotation % 6
        self.base_length = self.length if self.base_length is None else max(1, self.base_length)

    @property
    def branches(self) -> tuple[int, ...]:
        return branch_offsets(self.part_type)

    def tip(self, branch: int = 0) -> Hex:
        direction = DIRECTIONS[(self.rotation + self.branches[branch]) % 6]
        return add_hex(self.origin, (direction[0] * self.length, direction[1] * self.length))

    def tips(self) -> dict[int, Hex]:
        return {branch: self.tip(branch) for branch in range(len(self.branches))}

    def snapshot(self) -> dict:
        return {
            "partId": self.id,
            "partType": self.part_type,
            "origin": list(self.origin),
            "rotation": self.rotation,
            "length": self.length,
            "branchCount": len(self.branches),
            "tips": [
                {"branchIndex": branch, "position": list(position)}
                for branch, position in self.tips().items()
            ],
            "grabbing": self.grabbing,
            "heldAtoms": [
                {"branchIndex": branch, "atomId": atom_id}
                for branch, atom_id in sorted(self.held_atoms.items())
            ],
        }
