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


def replay_locked_prefix(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
) -> RotorPrefixCheckpoint:
    """Replay a human-supplied partial program and freeze its terminal state.

    This checkpoint is the handoff between a trusted compact opening and the
    autonomous local search. The complete final frame is retained so later
    search code can reconstruct atom, arm, bond and molecule state without
    replaying or modifying the locked prefix.
    """
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution))
    frames = replay.get("frames", [])
    final_frame = dict(frames[-1]) if frames else {}

    counts: dict[str, int] = {}
    for frame in frames:
        for event in frame.get("events", []):
            kind = str(event.get("kind") or "")
            if kind:
                counts[kind] = counts.get(kind, 0) + 1

    summary = replay.get("summary", {})
    return RotorPrefixCheckpoint(
        completed_cycles=int(summary.get("completedCycles") or 0),
        terminated_with_error=bool(summary.get("terminatedWithError")),
        event_counts=tuple(sorted(counts.items())),
        final_frame=final_frame,
    )
