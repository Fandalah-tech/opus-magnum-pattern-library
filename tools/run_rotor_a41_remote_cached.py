from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.a41_validator_cache import ValidatorCache, solution_fingerprint
import tools.run_rotor_a41_remote_cycle_campaign as campaign

CACHE_PATH = Path("reports/rotor-a41-validator-cache.json")
CACHE_STATS_PATH = Path("reports/rotor-a41-validator-cache-stats.json")
LEARNING_PATH = Path("reports/rotor-a41-retiming-learning.json")
CACHE_NAMESPACE = f"{campaign.VALIDATOR_URL.rstrip('/')}{campaign.ANALYZE_ENDPOINT}"
MAX_IDLE_JUMP = 8
SEARCH_STRATEGY = "a41-adaptive-idle-retiming-v1"


def load_learned_ranks(path: Path = LEARNING_PATH) -> dict[tuple[str, str], int]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = data.get("byPartInstruction") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}
    ranks: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        part = str(row.get("part") or "")
        instruction = str(row.get("instruction") or "")
        if part and instruction:
            ranks.setdefault((part, instruction), index)
    return ranks


def expand_idle_window_shifts(
    solution: dict[str, Any],
    base_shifts: list[dict[str, Any]],
    max_jump: int = MAX_IDLE_JUMP,
) -> list[dict[str, Any]]:
    """Expand one-cycle shifts within the existing idle gap of the same arm.

    No candidate crosses the previous programmed instruction, so instruction
    order is preserved. This exposes multi-cycle compression that a greedy
    one-cycle hill climb can miss when intermediate shifts do not improve the
    final cycle metric.
    """
    if max_jump <= 1:
        return list(base_shifts)

    parts = {str(part.get("id")): part for part in solution.get("parts", [])}
    expanded: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()

    for shift in base_shifts:
        part_id = str(shift.get("part") or "")
        cycle = int(shift.get("cycle") or 0)
        instruction = str(shift.get("instruction") or "")
        part = parts.get(part_id)
        if part is None:
            continue

        program = sorted(part.get("program", []), key=lambda item: int(item["cycle"]))
        previous_cycles = [int(item["cycle"]) for item in program if int(item["cycle"]) < cycle]
        previous_cycle = max(previous_cycles) if previous_cycles else -1
        available_gap = max(0, cycle - previous_cycle - 1)
        limit = min(max_jump, available_gap)

        for jump in range(1, limit + 1):
            candidate = dict(shift)
            candidate["targetCycle"] = cycle - jump
            candidate["jump"] = jump
            key = (part_id, cycle, int(candidate["targetCycle"]), instruction)
            if key not in seen:
                seen.add(key)
                expanded.append(candidate)

    return expanded


def reorder_shifts(shifts: list[dict[str, Any]], ranks: dict[tuple[str, str], int]) -> list[dict[str, Any]]:
    if not ranks:
        return shifts
    fallback = len(ranks) + 1000
    indexed = list(enumerate(shifts))
    indexed.sort(key=lambda item: (
        ranks.get((str(item[1].get("part") or ""), str(item[1].get("instruction") or "")), fallback),
        item[0],
    ))
    return [shift for _, shift in indexed]


def search_space_signature(shifts: list[dict[str, Any]]) -> str:
    payload = {
        "strategy": SEARCH_STRATEGY,
        "maxIdleJump": MAX_IDLE_JUMP,
        "candidates": shifts,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_generated_best() -> tuple[dict[str, Any] | None, str | None, str | None]:
    path = campaign.BEST_PARSED
    if not path.is_file():
        return None, None, None
    try:
        model = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, None
    if not isinstance(model, dict):
        return None, None, None
    metrics = model.get("metrics") if isinstance(model.get("metrics"), dict) else {}
    try:
        cycles = int(metrics.get("cycles"))
        area = int(metrics.get("area"))
    except (TypeError, ValueError):
        return None, None, None
    if area != 41 or cycles >= int(campaign.REFERENCE_METRICS["cycles"]):
        return None, None, None
    return model, campaign.BEST_SOLUTION.name, "validated-omsim-best"


def write_cache_stats(*, entries_before: int, cache: ValidatorCache, hits: int, misses: int) -> None:
    total = hits + misses
    payload = {
        "schemaVersion": 1,
        "namespace": CACHE_NAMESPACE,
        "entriesBefore": entries_before,
        "entriesAfter": len(cache),
        "hits": hits,
        "misses": misses,
        "requests": total,
        "hitRate": round(hits / total, 4) if total else 0,
        "remoteCallsAvoided": hits,
    }
    CACHE_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_STATS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    cache = ValidatorCache(CACHE_PATH, CACHE_NAMESPACE)
    entries_before = len(cache)
    stats = {"hits": 0, "misses": 0}
    original_validate = campaign.validate_remote
    original_candidate_shifts = campaign.candidate_shifts
    original_load_reference = campaign.load_reference
    original_write_checkpoint = campaign.write_checkpoint
    original_load_checkpoint = campaign.load_checkpoint
    learned_ranks = load_learned_ranks()

    def validate_cached(puzzle_path: Path, solution: dict[str, Any], name: str) -> dict[str, Any]:
        fingerprint = solution_fingerprint(campaign.encode_solution(solution))
        cached = cache.get(fingerprint)
        if cached is not None:
            stats["hits"] += 1
            cached["cacheHit"] = True
            cached["fingerprint"] = fingerprint
            return cached

        stats["misses"] += 1
        result = original_validate(puzzle_path, solution, name)
        result["cacheHit"] = False
        result["fingerprint"] = fingerprint
        # Cache deterministic validator answers, including valid=False. Do not
        # cache transport failures/timeouts: those must be retried later.
        if result.get("ok"):
            stored = dict(result)
            stored.pop("cacheHit", None)
            cache.put(fingerprint, stored)
        return result

    def candidate_shifts_learned(solution: dict[str, Any]) -> list[dict[str, Any]]:
        base = original_candidate_shifts(solution)
        expanded = expand_idle_window_shifts(solution, base)
        return reorder_shifts(expanded, learned_ranks)

    def load_reference_prefer_best():
        generated = load_generated_best()
        if generated[0] is not None:
            return generated
        return original_load_reference()

    def write_checkpoint_bound(**kwargs: Any) -> None:
        original_write_checkpoint(**kwargs)
        current = kwargs.get("current")
        if not isinstance(current, dict):
            return
        try:
            data = json.loads(campaign.CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            return
        shifts = candidate_shifts_learned(current)
        data["searchStrategy"] = SEARCH_STRATEGY
        data["maxIdleJump"] = MAX_IDLE_JUMP
        data["candidateCount"] = len(shifts)
        data["searchSpaceSignature"] = search_space_signature(shifts)
        temp = campaign.CHECKPOINT.with_suffix(".json.bound.tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(campaign.CHECKPOINT)

    def load_checkpoint_bound(baseline_cycles: int) -> dict[str, Any] | None:
        data = original_load_checkpoint(baseline_cycles)
        if data is None:
            return None
        current = data.get("current")
        if not isinstance(current, dict):
            return None
        shifts = candidate_shifts_learned(current)
        expected = search_space_signature(shifts)
        if data.get("searchStrategy") != SEARCH_STRATEGY:
            return None
        if int(data.get("maxIdleJump") or -1) != MAX_IDLE_JUMP:
            return None
        if int(data.get("candidateCount") or -1) != len(shifts):
            return None
        if data.get("searchSpaceSignature") != expected:
            return None
        return data

    campaign.validate_remote = validate_cached
    campaign.candidate_shifts = candidate_shifts_learned
    campaign.load_reference = load_reference_prefer_best
    campaign.write_checkpoint = write_checkpoint_bound
    campaign.load_checkpoint = load_checkpoint_bound
    try:
        return campaign.main()
    finally:
        write_cache_stats(
            entries_before=entries_before,
            cache=cache,
            hits=stats["hits"],
            misses=stats["misses"],
        )


if __name__ == "__main__":
    raise SystemExit(main())
