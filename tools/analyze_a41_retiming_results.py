from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ANALYSIS = Path("reports/rotor-a41-cycle-analysis.json")
CHECKPOINT = Path("reports/rotor-a41-cycle-checkpoint.json")
OUTPUT = Path("reports/rotor-a41-retiming-learning.json")


def _load_source() -> dict[str, Any]:
    for path in (ANALYSIS, CHECKPOINT):
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                return data
    raise FileNotFoundError("No A41 analysis/checkpoint report is available")


def _iter_results(data: dict[str, Any]):
    for round_data in data.get("rounds") or []:
        if not isinstance(round_data, dict):
            continue
        for result in round_data.get("candidates") or []:
            if isinstance(result, dict):
                yield result
    for result in data.get("activeRoundResults") or []:
        if isinstance(result, dict):
            yield result


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    baseline = int(data.get("baselineCycles") or 1112)
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"tested": 0, "valid": 0, "improved": 0, "bestCycles": None, "cycleTotal": 0}
    )
    part_groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"tested": 0, "valid": 0, "improved": 0, "bestCycles": None}
    )
    seen = 0

    for result in _iter_results(data):
        shift = result.get("shift") if isinstance(result.get("shift"), dict) else {}
        part = str(shift.get("part") or "unknown")
        instruction = str(shift.get("instruction") or "unknown")
        cycle = int(shift.get("cycle") or 0)
        valid = bool(result.get("valid"))
        cycles = int(result["cycles"]) if result.get("cycles") is not None else None
        improved = valid and cycles is not None and cycles < baseline

        bucket = groups[(part, instruction)]
        bucket["tested"] += 1
        bucket["valid"] += int(valid)
        bucket["improved"] += int(improved)
        bucket["cycleTotal"] += cycle
        if cycles is not None and (bucket["bestCycles"] is None or cycles < bucket["bestCycles"]):
            bucket["bestCycles"] = cycles

        p = part_groups[part]
        p["tested"] += 1
        p["valid"] += int(valid)
        p["improved"] += int(improved)
        if cycles is not None and (p["bestCycles"] is None or cycles < p["bestCycles"]):
            p["bestCycles"] = cycles
        seen += 1

    by_instruction = []
    for (part, instruction), values in groups.items():
        tested = values["tested"]
        by_instruction.append({
            "part": part,
            "instruction": instruction,
            "tested": tested,
            "valid": values["valid"],
            "improved": values["improved"],
            "validRate": round(values["valid"] / tested, 4) if tested else 0,
            "improvementRate": round(values["improved"] / tested, 4) if tested else 0,
            "averageSourceCycle": round(values["cycleTotal"] / tested, 1) if tested else None,
            "bestCycles": values["bestCycles"],
        })
    by_instruction.sort(key=lambda row: (-row["improved"], -row["validRate"], row["bestCycles"] or 10**9, row["part"], row["instruction"]))

    by_part = []
    for part, values in part_groups.items():
        tested = values["tested"]
        by_part.append({
            "part": part,
            "tested": tested,
            "valid": values["valid"],
            "improved": values["improved"],
            "validRate": round(values["valid"] / tested, 4) if tested else 0,
            "improvementRate": round(values["improved"] / tested, 4) if tested else 0,
            "bestCycles": values["bestCycles"],
        })
    by_part.sort(key=lambda row: (-row["improved"], -row["validRate"], row["bestCycles"] or 10**9, row["part"]))

    return {
        "schemaVersion": 1,
        "baselineCycles": baseline,
        "observations": seen,
        "byPart": by_part,
        "byPartInstruction": by_instruction,
        "recommendation": by_instruction[:8],
    }


def main() -> int:
    data = _load_source()
    output = summarize(data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"observations": output["observations"], "recommendation": output["recommendation"][:3]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
