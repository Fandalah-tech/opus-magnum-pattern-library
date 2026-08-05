from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator


@dataclass(frozen=True, slots=True)
class RotorPrefixCheckpoint:
    completed_cycles: int
    terminated_with_error: bool
    event_counts: tuple[tuple[str, int], ...]
    final_frame: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_locked_prefix_simulator(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    settle_cycles: int = 1,
) -> Simulator:
    """Replay a trusted partial program and return its live terminal simulator."""
    if settle_cycles < 0:
        raise ValueError("settle_cycles must be non-negative")

    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    cycles = list(timeline.get("cycles", []))
    start = len(cycles)
    cycles.extend(
        {"cycle": start + offset, "activeArms": 0, "events": []}
        for offset in range(settle_cycles)
    )
    simulator.run_timeline({**timeline, "cycles": cycles})
    return simulator


def replay_locked_prefix(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    settle_cycles: int = 1,
) -> RotorPrefixCheckpoint:
    """Replay a human-supplied partial program and freeze its terminal state.

    One idle settling cycle is included by default. Opus Magnum glyph effects
    are resolved after arm movement, so a partial tape ending on the placement
    instruction may need the following idle cycle for its final bond or glyph
    event to become observable.
    """
    simulator = build_locked_prefix_simulator(
        puzzle,
        solution,
        settle_cycles=settle_cycles,
    )
    frames = simulator.frames
    final_frame = dict(frames[-1]) if frames else {}

    counts: dict[str, int] = {}
    for frame in frames:
        for event in frame.get("events", []):
            kind = str(event.get("kind") or "")
            if kind:
                counts[kind] = counts.get(kind, 0) + 1

    return RotorPrefixCheckpoint(
        completed_cycles=max(0, len(frames) - 1),
        terminated_with_error=bool(frames and frames[-1].get("phase") == "error"),
        event_counts=tuple(sorted(counts.items())),
        final_frame=final_frame,
    )
