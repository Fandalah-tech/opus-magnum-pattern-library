from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

METRICS = ("cycles", "cost", "area", "instructions")


def complete_metrics(solution: dict) -> bool:
    metrics = solution.get("metrics") or {}
    return all(isinstance(metrics.get(k), int) for k in METRICS)


def dominates(a: dict, b: dict) -> bool:
    am = a["metrics"]
    bm = b["metrics"]
    return all(am[k] <= bm[k] for k in METRICS) and any(am[k] < bm[k] for k in METRICS)


def pareto_front(items: list[dict]) -> list[dict]:
    # O(n^2), intentionally simple and deterministic; individual event sets are modest.
    return [x for x in items if not any(y is not x and dominates(y, x) for y in items)]


def player_name(solution: dict) -> str | None:
    value = solution.get("submitter") or solution.get("player")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def normalized_distance_to_ideal(solution: dict, items: list[dict]) -> float:
    if not items:
        return float("inf")
    total = 0.0
    for metric in METRICS:
        values = [s["metrics"][metric] for s in items]
        lo, hi = min(values), max(values)
        if hi == lo:
            continue
        z = (solution["metrics"][metric] - lo) / (hi - lo)
        total += z * z
    return sqrt(total)


def representative_archetypes(front: list[dict]) -> dict:
    if not front:
        return {"balanced": None, **{f"{m}Focused": None for m in METRICS}}
    out = {}
    balanced = min(front, key=lambda s: (normalized_distance_to_ideal(s, front), s["id"]))
    out["balanced"] = balanced["id"]
    for metric in METRICS:
        best = min(s["metrics"][metric] for s in front)
        candidates = [s for s in front if s["metrics"][metric] == best]
        chosen = min(candidates, key=lambda s: (normalized_distance_to_ideal(s, front), s["id"]))
        out[f"{metric}Focused"] = chosen["id"]
    return out


def build(manifest: dict) -> dict:
    puzzles = {p["id"]: p for p in manifest.get("puzzles", [])}
    by_puzzle: dict[str, list[dict]] = defaultdict(list)
    for s in manifest.get("solutions", []):
        by_puzzle[s.get("puzzleId")].append(s)

    puzzle_reports = []
    player_stats: dict[str, dict] = defaultdict(lambda: {
        "solutions": 0,
        "completeMetricSolutions": 0,
        "puzzles": set(),
        "paretoSolutions": 0,
        "metricRecords": Counter(),
    })

    for puzzle_id, solutions in by_puzzle.items():
        complete = [s for s in solutions if complete_metrics(s)]
        front = pareto_front(complete)
        front_ids = {s["id"] for s in front}
        records = {}
        ranges = {}
        for metric in METRICS:
            if not complete:
                records[metric] = {"value": None, "solutionIds": []}
                ranges[metric] = {"min": None, "max": None}
                continue
            values = [s["metrics"][metric] for s in complete]
            best = min(values)
            ids = [s["id"] for s in complete if s["metrics"][metric] == best]
            records[metric] = {"value": best, "solutionIds": ids}
            ranges[metric] = {"min": min(values), "max": max(values)}

        for s in solutions:
            player = player_name(s)
            if not player:
                continue
            stat = player_stats[player]
            stat["solutions"] += 1
            stat["puzzles"].add(puzzle_id)
            if complete_metrics(s):
                stat["completeMetricSolutions"] += 1
            if s.get("id") in front_ids:
                stat["paretoSolutions"] += 1
            for metric, record in records.items():
                if s.get("id") in record["solutionIds"]:
                    stat["metricRecords"][metric] += 1

        puzzle = puzzles.get(puzzle_id, {})
        puzzle_reports.append({
            "puzzleId": puzzle_id,
            "name": puzzle.get("name"),
            "eventTitle": puzzle.get("eventTitle"),
            "solutionCount": len(solutions),
            "completeMetricSolutionCount": len(complete),
            "paretoCount": len(front),
            "paretoSolutionIds": sorted(front_ids),
            "records": records,
            "metricRanges": ranges,
            "representatives": representative_archetypes(front),
        })

    players = []
    for name, stat in player_stats.items():
        players.append({
            "player": name,
            "solutionCount": stat["solutions"],
            "completeMetricSolutionCount": stat["completeMetricSolutions"],
            "puzzleCount": len(stat["puzzles"]),
            "paretoSolutionCount": stat["paretoSolutions"],
            "metricRecordCounts": {k: stat["metricRecords"].get(k, 0) for k in METRICS},
        })
    players.sort(key=lambda x: (-x["paretoSolutionCount"], -x["puzzleCount"], -x["solutionCount"], x["player"].casefold()))
    puzzle_reports.sort(key=lambda x: ((x.get("name") or "").casefold(), x["puzzleId"]))

    complete_total = sum(p["completeMetricSolutionCount"] for p in puzzle_reports)
    pareto_total = sum(p["paretoCount"] for p in puzzle_reports)
    return {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceManifest": manifest.get("id"),
        "summary": {
            "puzzleCount": len(puzzle_reports),
            "solutionCount": sum(p["solutionCount"] for p in puzzle_reports),
            "completeMetricSolutionCount": complete_total,
            "paretoSolutionCount": pareto_total,
            "identifiedPlayerCount": len(players),
        },
        "puzzles": puzzle_reports,
        "players": players,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze canonical Critelli metadata for Pareto fronts, records and player profiles.")
    ap.add_argument("--manifest", type=Path, default=Path("database/critelli-public-events.manifest.json"))
    ap.add_argument("--output", type=Path, default=Path("reports/critelli-analysis.json"))
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = build(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
