from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any, Iterable
import zipfile

from packages.opus_parser import parse_solution_bytes


ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
ACTIVE_ARM_TYPES = ARM_TYPES - {"baron"}
INCOMPLETE_NAME_MARKERS = (
    "setup",
    "accroche",
    "bloquant",
    "piste",
    "methode",
    "méthode",
    "experimental",
    "je ne sais",
)


@dataclass(frozen=True, slots=True)
class RotorCorpusEntry:
    filename: str
    solution_name: str
    source_sha256: str
    metrics: dict[str, int | None]
    inferred_metrics: dict[str, int | None]
    part_count: int
    arm_count: int
    active_arm_count: int
    part_types: tuple[tuple[str, int], ...]
    instruction_count: int
    architecture_signature: str
    family: str
    likely_complete: bool
    complete_metrics: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _infer_metrics(name: str) -> dict[str, int | None]:
    lowered = name.lower()
    area_match = re.search(r"(?:^|\s)a\s*(\d+)", lowered)
    cycle_match = re.search(r"(?:^|\s)c\s*(\d+)", lowered)
    sum_match = re.search(r"(?:^|\s)sum\s*(\d+)", lowered)
    return {
        "area": int(area_match.group(1)) if area_match else None,
        "cycles": int(cycle_match.group(1)) if cycle_match else None,
        "sum": int(sum_match.group(1)) if sum_match else None,
        "cost": None,
        "instructions": None,
    }


def _architecture_family(counts: Counter[str], active_arm_count: int) -> str:
    has_track = counts["track"] > 0
    has_arm6 = counts["arm6"] > 0
    pistons = counts["piston"]
    if has_arm6 and active_arm_count <= 3:
        return "sum-arm6-track" if has_track else "sum-arm6"
    if pistons >= 2 and has_track:
        return "area-piston-track"
    if pistons >= 4:
        return "wide-piston"
    return "other"


def summarize_solution(solution: dict[str, Any], filename: str = "") -> RotorCorpusEntry:
    parts = list(solution.get("parts") or [])
    counts = Counter(str(part.get("type") or "") for part in parts)
    metrics = dict(solution.get("metrics") or {})
    name = str(solution.get("name") or "")
    inferred = _infer_metrics(name)
    active_arm_count = sum(counts[item] for item in ACTIVE_ARM_TYPES)
    signature_items = [
        f"{part_type}:{counts[part_type]}"
        for part_type in sorted(counts)
        if part_type != "glyph-marker"
    ]
    signature = "|".join(signature_items)
    lower_name = name.lower()
    likely_complete = (
        counts["out-std"] == 1
        and counts["input"] == 2
        and active_arm_count > 0
        and sum(len(part.get("program") or []) for part in parts) >= 60
        and not any(marker in lower_name for marker in INCOMPLETE_NAME_MARKERS)
    )
    return RotorCorpusEntry(
        filename=filename or str((solution.get("source") or {}).get("name") or ""),
        solution_name=name,
        source_sha256=str((solution.get("source") or {}).get("sha256") or ""),
        metrics=metrics,
        inferred_metrics=inferred,
        part_count=len(parts),
        arm_count=sum(counts[item] for item in ARM_TYPES),
        active_arm_count=active_arm_count,
        part_types=tuple(sorted(counts.items())),
        instruction_count=sum(len(part.get("program") or []) for part in parts),
        architecture_signature=signature,
        family=_architecture_family(counts, active_arm_count),
        likely_complete=likely_complete,
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
    """Rank mechanically useful references even when save metrics are absent.

    Weekly work-in-progress files commonly omit embedded metrics.  We therefore
    reject obvious setup/experimental saves, prefer compact architecture
    families, and use metrics inferred from human-readable names only as late
    tie breakers.  Exact engine validation is still required before a seed is
    accepted by the solver.
    """
    usable = [entry for entry in entries if entry.likely_complete]
    family_priority = {
        "sum-arm6-track": 0,
        "sum-arm6": 1,
        "area-piston-track": 2,
        "wide-piston": 3,
        "other": 4,
    }
    return tuple(sorted(
        usable,
        key=lambda entry: (
            family_priority.get(entry.family, 9),
            entry.active_arm_count,
            entry.instruction_count,
            entry.part_count,
            int(entry.inferred_metrics.get("sum") or 10**9),
            int(entry.inferred_metrics.get("area") or 10**9),
            int(entry.inferred_metrics.get("cycles") or 10**9),
            entry.filename,
        ),
    ))
