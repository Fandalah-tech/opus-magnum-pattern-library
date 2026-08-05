from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


Hex = tuple[int, int]


@dataclass(frozen=True, slots=True)
class RotorStation:
    id: str
    kind: str
    position: Hex
    rotation: int = 0
    which: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RotorLayout:
    supported: bool
    reason: str | None
    stations: tuple[RotorStation, ...]
    buffers: tuple[Hex, ...]
    workspace_radius: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_wide_rotor_layout() -> RotorLayout:
    """Return a spacious first-solution layout skeleton.

    This layout intentionally optimizes for debuggability rather than cost or
    area. Inputs, conversion, bonding, buffers, and output are separated into
    independent lanes so choreography can be synthesized station by station.
    """
    stations = (
        RotorStation("input-water", "input", (-10, 0), 0, 0),
        RotorStation("input-salt", "input", (-10, 6), 0, 1),
        RotorStation("split-water", "unbonder", (-5, 0), 0),
        RotorStation("split-salt", "unbonder", (-5, 6), 0),
        RotorStation("rotor", "baron", (0, 3), 0),
        RotorStation("bonder", "bonder", (6, 3), 0),
        RotorStation("output", "out-std", (14, 3), 0, 0),
    )
    buffers = (
        (3, 8), (5, 8), (7, 8),
        (3, -2), (5, -2), (7, -2),
        (10, 3),
    )
    occupied = [station.position for station in stations]
    if len(set(occupied)) != len(occupied):
        return RotorLayout(False, "station origins overlap", (), (), 0)
    if len(set(buffers)) != len(buffers) or set(buffers) & set(occupied):
        return RotorLayout(False, "buffer cells overlap stations", (), (), 0)
    return RotorLayout(True, None, stations, buffers, 18)


def layout_solution_parts(layout: RotorLayout) -> list[dict[str, Any]]:
    if not layout.supported:
        raise ValueError(layout.reason or "unsupported Rotor layout")
    parts: list[dict[str, Any]] = []
    for index, station in enumerate(layout.stations):
        parts.append({
            "id": f"rotor-station-{index}",
            "type": station.kind,
            "enabled": True,
            "position": list(station.position),
            "length": 1,
            "rotation": station.rotation,
            "which": station.which,
            "armNumber": 0,
            "program": [],
        })
    return parts
