from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.intermediate_convergence import search_intermediate_convergence
from packages.opus_solver.product_delivery import search_singleton_product_delivery
from packages.opus_solver.purification_chain import purification_profile

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def _run_omsim(omsim: Path, puzzle: Path, solution: Path) -> dict[str, Any]:
    process = subprocess.run(
        [str(omsim), "--puzzle-file", str(puzzle), "--metric", "product 1 cycles", str(solution)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = ((process.stdout or "") + (process.stderr or "")).strip()
    match = _COLLISION_RE.search(output)
    if process.returncode == 0:
        progress = 1_000_000_000
    elif match:
        progress = int(match.group(1))
    elif "cycle limit" in output.lower():
        progress = 999_999_999
    else:
        progress = 0
    return {
        "exitCode": int(process.returncode),
        "output": output,
        "progressCycle": progress,
        "collisionCycle": int(match.group(1)) if match else None,
        "collisionLocation": [int(match.group(2)), int(match.group(3))] if match else None,
    }


def _counts(profile: dict[str, Any]) -> dict[str, int]:
    return {
        key: int(value)
        for key, value in (profile.get("countsByElement") or {}).items()
    }


def _resolve_artifact_solution(root: Path, recorded_path: str) -> Path:
    name = Path(recorded_path).name
    matches = list(root.rglob(name))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected exactly one artifact solution named {name}, found {matches}")
    return matches[0]


def _seed_candidates(report: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for generation in report.get("history", []) or []:
        baseline_progress = int((generation.get("baseline") or {}).get("progressCycle") or 0)
        for variant in generation.get("variants", []) or []:
            profile = variant.get("purificationProfile") or {}
            counts = _counts(profile)
            silver = int(counts.get("silver", 0))
            gold = int(counts.get("gold", 0))
            progress = int((variant.get("omsim") or {}).get("progressCycle") or 0)
            if silver < 2 or gold > 0:
                continue
            records.append({
                "generation": int(generation.get("generation") or 0),
                "solutionPath": str(variant.get("solutionPath") or ""),
                "omsim": variant.get("omsim") or {},
                "purificationProfile": profile,
                "oracleAdvance": progress > baseline_progress,
                "advanceDelta": progress - baseline_progress,
            })
    records.sort(
        key=lambda item: (
            int(bool(item.get("oracleAdvance"))),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((_counts(item.get("purificationProfile") or {})).get("silver", 0)),
            int((item.get("purificationProfile") or {}).get("count") or 0),
        ),
        reverse=True,
    )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in records:
        path = str(item.get("solutionPath") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        deduped.append(item)
    return deduped


def _compact_validation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(value.get("complete")),
        "failureMode": value.get("failureMode"),
        "totalDelivered": int(value.get("totalDelivered") or 0),
        "completedCycles": int(value.get("completedCycles") or 0),
        "terminatedWithError": bool(value.get("terminatedWithError")),
        "eventCounts": dict(value.get("eventCounts") or {}),
    }


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    oracle_report_path: Path,
    oracle_artifact_root: Path,
    output_dir: Path,
    seed_limit: int = 6,
    convergence_limit: int = 12,
    preflight_limit: int = 8,
    delivery_limit: int = 8,
    max_cycles: int = 500,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    oracle_report = json.loads(oracle_report_path.read_text(encoding="utf-8"))
    if int(oracle_report.get("targetSolutionBytesUsed") or 0) != 0:
        raise ValueError("Oracle repair report is not target-free")

    seeds = _seed_candidates(oracle_report)[:max(1, int(seed_limit))]
    convergence_records: list[dict[str, Any]] = []

    for seed_index, seed in enumerate(seeds):
        seed_path = _resolve_artifact_solution(oracle_artifact_root, seed["solutionPath"])
        seed_solution = parse_solution(seed_path)
        result = search_intermediate_convergence(
            puzzle,
            seed_solution,
            element="silver",
            max_cycles=max_cycles,
            observation_limit=120,
            result_limit=convergence_limit,
        )
        seed_record = {
            **seed,
            "artifactSolution": str(seed_path),
            "convergenceSummary": result.get("summary") or {},
        }
        seed["searchSummary"] = seed_record["convergenceSummary"]
        for candidate_index, candidate in enumerate(result.get("variants", []) or []):
            path = output_dir / "convergence" / f"seed-{seed_index:02d}-candidate-{candidate_index:02d}.solution"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_solution(candidate["solution"], path)
            oracle = _run_omsim(omsim, puzzle_path, path)
            convergence_records.append({
                "seedIndex": seed_index,
                "candidateIndex": candidate_index,
                "solution": str(path),
                "omsim": oracle,
                "purificationProfile": candidate.get("purificationProfile") or {},
                "validation": _compact_validation(candidate.get("validation") or {}),
                "observation": candidate.get("observation"),
                "move": candidate.get("move"),
                "purifierPose": candidate.get("purifierPose"),
            })

    convergence_records.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int(not bool((item.get("validation") or {}).get("terminatedWithError"))),
            int((item.get("validation") or {}).get("completedCycles") or 0),
        ),
        reverse=True,
    )

    accepted = next(
        (item for item in convergence_records if int((item.get("omsim") or {}).get("exitCode") or 0) == 0),
        None,
    )
    delivery_records: list[dict[str, Any]] = []

    if accepted is None:
        for preflight_index, convergence in enumerate(convergence_records[:max(1, int(preflight_limit))]):
            baseline = parse_solution(convergence["solution"])
            delivery = search_singleton_product_delivery(
                puzzle,
                baseline,
                max_cycles=max_cycles,
                opportunity_limit=80,
                result_limit=delivery_limit,
            )
            for delivery_index, candidate in enumerate(delivery.get("variants", []) or []):
                path = output_dir / "delivery" / f"preflight-{preflight_index:02d}-candidate-{delivery_index:02d}.solution"
                path.parent.mkdir(parents=True, exist_ok=True)
                write_solution(candidate["solution"], path)
                oracle = _run_omsim(omsim, puzzle_path, path)
                record = {
                    "preflightIndex": preflight_index,
                    "deliveryIndex": delivery_index,
                    "parentConvergenceSolution": convergence["solution"],
                    "solution": str(path),
                    "omsim": oracle,
                    "summary": candidate.get("summary") or {},
                    "validation": _compact_validation(candidate.get("validation") or {}),
                }
                delivery_records.append(record)
                if int(oracle.get("exitCode") or 0) == 0:
                    accepted = record
                    break
            if accepted is not None:
                break

    delivery_records.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((item.get("summary") or {}).get("productDeliveredCount") or 0),
        ),
        reverse=True,
    )

    best = accepted
    if best is None:
        if delivery_records:
            best = delivery_records[0]
        elif convergence_records:
            best = convergence_records[0]

    accepted_solution = None
    if accepted is not None:
        accepted_solution = output_dir / "GEN249-omsim-product1.solution"
        accepted_solution.write_bytes(Path(accepted["solution"]).read_bytes())

    best_oracle = (best or {}).get("omsim") or {}
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-frontier-rebuild-search",
        "targetSolutionBytesUsed": 0,
        "request": {
            "seedLimit": int(seed_limit),
            "convergenceLimit": int(convergence_limit),
            "preflightLimit": int(preflight_limit),
            "deliveryLimit": int(delivery_limit),
            "maxCycles": int(max_cycles),
        },
        "oracleRepairRunId": oracle_report.get("runId"),
        "seedCount": len(seeds),
        "seeds": seeds,
        "convergenceCandidateCount": len(convergence_records),
        "convergenceCandidates": convergence_records,
        "deliveryCandidateCount": len(delivery_records),
        "deliveryCandidates": delivery_records,
        "bestOMSim": best_oracle,
        "acceptedProductOne": bool(accepted is not None),
        "acceptedSolution": str(accepted_solution) if accepted_solution is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild a lost chemistry frontier after an OMSim mechanical advance.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--oracle-report", type=Path, required=True)
    parser.add_argument("--oracle-artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-limit", type=int, default=6)
    parser.add_argument("--convergence-limit", type=int, default=12)
    parser.add_argument("--preflight-limit", type=int, default=8)
    parser.add_argument("--delivery-limit", type=int, default=8)
    parser.add_argument("--max-cycles", type=int, default=500)
    args = parser.parse_args()

    report = search(
        omsim=args.omsim,
        puzzle_path=args.puzzle,
        oracle_report_path=args.oracle_report,
        oracle_artifact_root=args.oracle_artifact_root,
        output_dir=args.output_dir,
        seed_limit=args.seed_limit,
        convergence_limit=args.convergence_limit,
        preflight_limit=args.preflight_limit,
        delivery_limit=args.delivery_limit,
        max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "seedCount": report["seedCount"],
        "convergenceCandidateCount": report["convergenceCandidateCount"],
        "deliveryCandidateCount": report["deliveryCandidateCount"],
        "bestOMSim": report["bestOMSim"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
