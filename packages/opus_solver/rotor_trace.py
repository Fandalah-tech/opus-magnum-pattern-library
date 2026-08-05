from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator


MILESTONE_KINDS = {
    "atom-calcified",
    "atom-duplicated",
    "bond-created",
    "bond-removed",
    "floating-bond-created",
    "floating-bond-settled",
    "floating-bond-dissolved",
    "product-delivered",
}


@dataclass(frozen=True, slots=True)
class TraceMilestone:
    cycle: int
    kind: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RotorTrace:
    completed_cycles: int
    terminated_with_error: bool
    milestones: tuple[TraceMilestone, ...]
    delivered_products: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def trace_solution_milestones(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    milestone_kinds: set[str] | None = None,
) -> RotorTrace:
    """Replay a solution and extract chemistry/assembly milestones.

    The raw engine frames remain the source of truth. This compact trace is the
    intermediate representation used to learn macro-operations from a known
    solution without copying its arm program verbatim.
    """
    selected = milestone_kinds or MILESTONE_KINDS
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution))
    milestones: list[TraceMilestone] = []
    for frame in replay.get("frames", []):
        cycle = int(frame.get("cycle") or 0)
        for event in frame.get("events", []):
            kind = str(event.get("kind") or "")
            if kind not in selected:
                continue
            payload = {key: value for key, value in event.items() if key not in {"kind", "cycle"}}
            milestones.append(TraceMilestone(cycle, kind, payload))

    summary = replay.get("summary", {})
    return RotorTrace(
        completed_cycles=int(summary.get("completedCycles") or 0),
        terminated_with_error=bool(summary.get("terminatedWithError")),
        milestones=tuple(milestones),
        delivered_products=tuple(sorted(
            (str(output_id), int(count))
            for output_id, count in simulator.delivered_products.items()
        )),
    )
