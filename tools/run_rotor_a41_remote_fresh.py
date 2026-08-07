from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import tools.run_rotor_a41_remote_cached as cached

ARCHIVE = Path("reports/rotor-a41-cycle-checkpoint.previous.json")
GENERATION = Path("reports/rotor-a41-campaign-generation.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def best_cycles_before_generation() -> int:
    data = _read_json(cached.campaign.BEST_PARSED)
    metrics = data.get("metrics") if isinstance(data, dict) and isinstance(data.get("metrics"), dict) else {}
    try:
        cycles = int(metrics.get("cycles"))
        area = int(metrics.get("area"))
    except (TypeError, ValueError):
        return int(cached.campaign.REFERENCE_METRICS["cycles"])
    if area == 41 and cycles < int(cached.campaign.REFERENCE_METRICS["cycles"]):
        return cycles
    return int(cached.campaign.REFERENCE_METRICS["cycles"])


def best_cycles_after_generation(fallback: int) -> int:
    analysis = _read_json(cached.campaign.ANALYSIS)
    if isinstance(analysis, dict):
        try:
            return int(analysis.get("bestCycles"))
        except (TypeError, ValueError):
            pass
    data = _read_json(cached.campaign.BEST_PARSED)
    metrics = data.get("metrics") if isinstance(data, dict) and isinstance(data.get("metrics"), dict) else {}
    try:
        cycles = int(metrics.get("cycles"))
        area = int(metrics.get("area"))
    except (TypeError, ValueError):
        return fallback
    return cycles if area == 41 else fallback


def archive_checkpoint() -> bool:
    checkpoint = cached.campaign.CHECKPOINT
    if not checkpoint.is_file():
        return False
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checkpoint, ARCHIVE)
    checkpoint.unlink()
    return True


def write_generation_report(*, archived: bool, start_cycles: int, final_cycles: int | None,
                            exit_code: int | None, status: str) -> None:
    improved = final_cycles is not None and final_cycles < start_cycles
    payload = {
        "schemaVersion": 2,
        "mode": "fresh-generation",
        "status": status,
        "checkpointArchived": archived,
        "checkpointArchive": str(ARCHIVE) if archived else None,
        "searchStrategy": cached.SEARCH_STRATEGY,
        "maxIdleJump": cached.MAX_IDLE_JUMP,
        "startCycles": start_cycles,
        "finalCycles": final_cycles,
        "cycleGain": (start_cycles - final_cycles) if improved else 0,
        "improved": improved,
        "recommendedNextGeneration": bool(exit_code == 0 and improved),
        "exitCode": exit_code,
    }
    GENERATION.parent.mkdir(parents=True, exist_ok=True)
    GENERATION.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    start_cycles = best_cycles_before_generation()
    archived = archive_checkpoint()
    write_generation_report(
        archived=archived,
        start_cycles=start_cycles,
        final_cycles=None,
        exit_code=None,
        status="running",
    )
    exit_code = cached.main()
    final_cycles = best_cycles_after_generation(start_cycles)
    write_generation_report(
        archived=archived,
        start_cycles=start_cycles,
        final_cycles=final_cycles,
        exit_code=exit_code,
        status="completed" if exit_code == 0 else "failed",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
