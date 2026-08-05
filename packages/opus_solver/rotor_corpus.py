from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import zipfile

from packages.opus_parser import parse_solution_bytes


ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


@dataclass(frozen=True, slots=True)
class RotorCorpusEntry:
    filename: str
    metrics: dict[str, int | None]
    part_count: int
    arm_count: int
    part_types: tuple[tuple[str, int], ...]
    instruction_count: int
    complete_metrics: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_solution(solution: dict[str, Any], filename: str = "") -> RotorCorpusEntry:
    parts = list(solution.get("parts") or [])
    counts = Counter(str(part.get("type") or "") for part in parts)
    metrics = dict(solution.get("metrics") or {})
    return RotorCorpusEntry(
        filename=filename or str((solution.get("source") or {}).get("name") or ""),
        metrics=metrics,
        part_count=len(parts),
        arm_count=sum(counts[item] for item in ARM_TYPES),
        part_types=tuple(sorted(counts.items())),
        instruction_count=sum(len(part.get("program") or []) for part in parts),
        complete_metrics=all(metrics.get(name) is not None for name in ("cycles", "cost", "area", "instructions")),
    )


def analyze_solution_zip(source: str | Path | bytes) -> tuple[RotorCorpusEntry, ...]:
    if isinstance(source, bytes):
        import io
        archive = zipfile.ZipFile(io.BytesIO(source))
    else:
        archive = zipfile.ZipFile(source)
    with archive:
        entries = []
        for name in sorted(archive.namelist()):
            if not name.lower().endswith(".solution"):
                continue
            solution = parse_solution_bytes(archive.read(name), source_name=name)
            entries.append(summarize_solution(solution, name))
    return tuple(entries)


def rank_seed_candidates(entries: Iterable[RotorCorpusEntry]) -> tuple[RotorCorpusEntry, ...]:
    """Rank known-valid candidates for bootstrapping mechanical synthesis.

    Complete solutions with fewer parts and instructions are preferred.  Area,
    cost and cycles break ties.  This ranking is not an optimizer; it selects a
    mechanically simple reference whose topology can be generalized by the
    layout compiler.
    """
    usable = [entry for entry in entries if entry.complete_metrics]
    return tuple(sorted(
        usable,
        key=lambda entry: (
            entry.part_count,
            entry.arm_count,
            entry.instruction_count,
            int(entry.metrics.get("area") or 10**9),
            int(entry.metrics.get("cost") or 10**9),
            int(entry.metrics.get("cycles") or 10**9),
        ),
    ))
