from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
GLYPH_PREFIXES = ("glyph-",)


def solution_architecture_signature(solution: dict[str, Any]) -> dict[str, Any]:
    """Describe a solution in terms useful to mechanism retrieval.

    This intentionally avoids puzzle-specific coordinates.  It captures the
    resource allocation and scheduling shape that distinguishes compact
    single-arm walkers, parallel throughput factories, and balanced cells.
    """

    parts = list(solution.get("parts", []))
    types = Counter(str(part.get("type") or "") for part in parts)
    arms = [part for part in parts if str(part.get("type")) in ARM_TYPES]
    programs = [item for part in arms for item in part.get("program", [])]
    cycles = [int(item.get("cycle") or 0) for item in programs]
    instruction_types = Counter(str(item.get("instruction") or "unknown") for item in programs)
    programmed_arms = sum(bool(part.get("program")) for part in arms)
    period_overrides = instruction_types.get("period_override", 0)
    repeat_markers = instruction_types.get("repeat", 0)

    if len(arms) == 1:
        archetype = "single-arm-sequential"
    elif len(arms) >= 12 or types.get("bonder", 0) + types.get("unbonder", 0) >= 12:
        archetype = "parallel-throughput"
    elif period_overrides or repeat_markers:
        archetype = "periodic-pipeline"
    else:
        archetype = "balanced-cell"

    return {
        "archetype": archetype,
        "partCount": len(parts),
        "armCount": len(arms),
        "programmedArmCount": programmed_arms,
        "trackCount": types.get("track", 0),
        "pistonCount": types.get("piston", 0),
        "inputCount": types.get("input", 0),
        "outputCount": types.get("out-std", 0) + types.get("out-rep", 0),
        "glyphCount": sum(count for name, count in types.items() if name.startswith(GLYPH_PREFIXES)),
        "bonderCount": types.get("bonder", 0) + types.get("bonder-speed", 0),
        "unbonderCount": types.get("unbonder", 0),
        "programEntryCount": len(programs),
        "programSpan": (max(cycles) - min(cycles) + 1) if cycles else 0,
        "periodOverrideCount": period_overrides,
        "repeatMarkerCount": repeat_markers,
        "partTypes": dict(sorted(types.items())),
        "instructionTypes": dict(sorted(instruction_types.items())),
    }


def specialization_axes(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Select the best portfolio member on each standard scalar metric."""

    items = list(records)
    result: dict[str, dict[str, Any]] = {}
    for metric in ("cost", "area", "cycles", "instructions"):
        candidates = [item for item in items if isinstance(item.get("metrics", {}).get(metric), int)]
        if candidates:
            result[metric] = min(
                candidates,
                key=lambda item: (
                    item["metrics"][metric],
                    item.get("metrics", {}).get("cost", 10**12),
                    str(item.get("name") or ""),
                ),
            )
    return result
