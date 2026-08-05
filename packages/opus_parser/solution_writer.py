from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import Any

from .solution import METRIC_IDS

_METRIC_CODES = {name: code for code, name in METRIC_IDS.items()}
_INSTRUCTION_CODES = {
    "pivot_ccw": ord("p"),
    "extend": ord("E"),
    "pivot_cw": ord("P"),
    "drop": ord("g"),
    "track_minus": ord("a"),
    "rotate_ccw": ord("r"),
    "retract": ord("e"),
    "rotate_cw": ord("R"),
    "grab": ord("G"),
    "track_plus": ord("A"),
    "period_override": ord("O"),
    "reset": ord("X"),
    "repeat": ord("C"),
}


class SolutionWriteError(ValueError):
    """Raised when a solution model cannot be serialized safely."""


class _BinaryWriter:
    def __init__(self) -> None:
        self.stream = io.BytesIO()

    def int32(self, value: int) -> None:
        self.stream.write(struct.pack("<i", int(value)))

    def byte(self, value: int) -> None:
        if not 0 <= int(value) <= 255:
            raise SolutionWriteError(f"Byte value out of range: {value}")
        self.stream.write(struct.pack("<B", int(value)))

    def seven_bit_int(self, value: int) -> None:
        value = int(value)
        if value < 0:
            raise SolutionWriteError(f"Negative string length: {value}")
        while value >= 0x80:
            self.byte((value & 0x7F) | 0x80)
            value >>= 7
        self.byte(value)

    def string(self, value: str) -> None:
        encoded = str(value).encode("utf-8")
        self.seven_bit_int(len(encoded))
        self.stream.write(encoded)

    def bytes(self) -> bytes:
        return self.stream.getvalue()


def _metric_entries(solution: dict[str, Any]) -> list[tuple[int, int]]:
    metrics = solution.get("metrics") or {}
    entries: list[tuple[int, int]] = []
    for name, code in sorted(_METRIC_CODES.items(), key=lambda item: item[1]):
        value = metrics.get(name)
        if value is not None:
            entries.append((code, int(value)))
    for item in solution.get("unknownMetrics") or []:
        entries.append((int(item["id"]), int(item["value"])))
    return entries


def write_solution_bytes(solution: dict[str, Any], *, version: int | None = None) -> bytes:
    """Serialize a normalized solution model into the game's binary format.

    The writer intentionally accepts the same dictionary shape returned by
    :func:`parse_solution_bytes`, which makes generated solutions round-trip
    through the parser without a second internal representation.
    """
    resolved_version = int(version or (solution.get("format") or {}).get("version") or 7)
    if resolved_version not in (6, 7):
        raise SolutionWriteError(f"Unsupported solution version {resolved_version}; expected 6 or 7")

    writer = _BinaryWriter()
    writer.int32(resolved_version)
    writer.string(str(solution.get("puzzleFile") or ""))
    writer.string(str(solution.get("name") or "Generated solution"))

    metrics = _metric_entries(solution)
    writer.int32(len(metrics))
    for metric_id, value in metrics:
        writer.int32(metric_id)
        writer.int32(value)

    parts = list(solution.get("parts") or [])
    writer.int32(len(parts))
    for index, part in enumerate(parts):
        part_type = str(part.get("type") or "")
        if not part_type:
            raise SolutionWriteError(f"Part {index} has no type")
        position = part.get("position") or (0, 0)
        if len(position) != 2:
            raise SolutionWriteError(f"Part {index} has invalid position {position!r}")

        writer.string(part_type)
        writer.byte(1 if part.get("enabled", True) else 0)
        writer.int32(int(position[0]))
        writer.int32(int(position[1]))
        writer.int32(int(part.get("length") or 1))
        writer.int32(int(part.get("rotation") or 0))
        writer.int32(int(part.get("which") or 0))

        program = sorted(
            list(part.get("program") or []),
            key=lambda item: int(item.get("cycle", 0)),
        )
        writer.int32(len(program))
        for instruction_index, item in enumerate(program):
            instruction = str(item.get("instruction") or "")
            code = _INSTRUCTION_CODES.get(instruction)
            if code is None:
                raw_code = item.get("rawCode")
                if isinstance(raw_code, str) and len(raw_code) == 1:
                    code = ord(raw_code)
                elif isinstance(raw_code, int):
                    code = raw_code
                else:
                    raise SolutionWriteError(
                        f"Part {index} instruction {instruction_index} has unsupported action {instruction!r}"
                    )
            writer.int32(int(item.get("cycle", 0)))
            writer.byte(code)

        if part_type == "track":
            track_hexes = list(part.get("trackHexes") or [])
            writer.int32(len(track_hexes))
            for cell in track_hexes:
                if len(cell) != 2:
                    raise SolutionWriteError(f"Part {index} has invalid track cell {cell!r}")
                writer.int32(int(cell[0]))
                writer.int32(int(cell[1]))

        writer.int32(int(part.get("armNumber") or 0))

    return writer.bytes()


def write_solution(solution: dict[str, Any], destination: str | Path, *, version: int | None = None) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(write_solution_bytes(solution, version=version))
    return path
