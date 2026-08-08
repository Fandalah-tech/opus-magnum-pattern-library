from __future__ import annotations

import hashlib
from pathlib import Path

from .binary import BinaryReader, ParseError, read_bytes

METRIC_IDS = {0: "cycles", 1: "cost", 2: "area", 3: "instructions"}
INSTRUCTION_CODES = {
    ord("p"): "pivot_ccw", ord("E"): "extend", ord("P"): "pivot_cw",
    ord("g"): "drop", ord("a"): "track_minus", ord("r"): "rotate_ccw",
    ord("e"): "retract", ord("R"): "rotate_cw", ord("G"): "grab",
    ord("A"): "track_plus", ord("O"): "period_override", ord("X"): "reset",
    ord("C"): "repeat",
}


def _count(reader: BinaryReader, label: str, limit: int = 1_000_000) -> int:
    value = reader.int32()
    if value < 0 or value > limit:
        raise ParseError(f"Invalid {label}: {value}")
    return value


def parse_solution_bytes(data: bytes, *, source_name: str | None = None) -> dict:
    reader = BinaryReader(data)
    version = reader.int32()
    if version not in (6, 7):
        raise ParseError(f"Unsupported solution version {version}; expected 6 or 7")

    puzzle_file = reader.string()
    name = reader.string()
    metric_marker = _count(reader, "metric marker", 64)
    metrics = {name: None for name in METRIC_IDS.values()}
    unknown_metrics = []

    # OM solution v7 uses this field as a solved marker: 0 means unsolved,
    # any non-zero value is followed by the canonical four metric pairs.
    # Older v6 files are kept on the historical count-based interpretation.
    metric_count = (4 if metric_marker else 0) if version == 7 else metric_marker
    for _ in range(metric_count):
        metric_id = reader.int32()
        value = reader.int32()
        metric_name = METRIC_IDS.get(metric_id)
        if metric_name:
            metrics[metric_name] = value
        else:
            unknown_metrics.append({"id": metric_id, "value": value})

    part_count = _count(reader, "part count", 100_000)
    parts = []
    for part_index in range(part_count):
        part_type = reader.string()
        enabled = reader.byte()
        position = [reader.int32(), reader.int32()]
        length = reader.int32()
        rotation = reader.int32()
        which = reader.int32()

        instruction_count = _count(reader, f"instruction count for part {part_index}")
        program = []
        for _ in range(instruction_count):
            cycle = reader.int32()
            code = reader.byte()
            program.append({
                "cycle": cycle,
                "instruction": INSTRUCTION_CODES.get(code, "unknown"),
                "rawCode": chr(code) if 32 <= code <= 126 else code,
            })

        track_hexes = []
        if part_type == "track":
            track_count = _count(reader, f"track cell count for part {part_index}")
            track_hexes = [[reader.int32(), reader.int32()] for _ in range(track_count)]

        arm_number = reader.int32()
        part = {
            "id": f"part-{part_index}",
            "type": part_type,
            "enabled": enabled != 0,
            "position": position,
            "length": length,
            "rotation": rotation,
            "which": which,
            "armNumber": arm_number,
            "program": program,
        }
        if track_hexes:
            part["trackHexes"] = track_hexes
        parts.append(part)

    return {
        "schemaVersion": "0.1.0",
        "format": {"kind": "solution", "version": version},
        "source": {
            "name": source_name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        },
        "puzzleFile": puzzle_file,
        "name": name,
        "metrics": metrics,
        "unknownMetrics": unknown_metrics,
        "parts": parts,
        "trailingBytes": reader.remaining(),
    }


def parse_solution(source: str | Path | bytes | bytearray) -> dict:
    data = read_bytes(source)
    name = None if isinstance(source, (bytes, bytearray)) else Path(source).name
    return parse_solution_bytes(data, source_name=name)
