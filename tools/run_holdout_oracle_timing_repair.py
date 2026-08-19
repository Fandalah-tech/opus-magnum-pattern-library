from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import purification_profile
from tools.run_holdout_oracle_base_repair import run_omsim

_ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


def _counts(profile: dict[str, Any]) -> dict[str, int]:
    return {str(k): int(v) for k, v in (profile.get("countsByElement") or {}).items()}


def _precursor_preserved(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    before = _counts(baseline)
    after = _counts(candidate)
    if int(before.get("gold", 0)) > 0:
        return int(after.get("gold", 0)) >= int(before.get("gold", 0)) or int(after.get("silver", 0)) >= 2
    if int(before.get("silver", 0)) >= 2:
        return int(after.get("silver", 0)) >= 2
    frontier = int(baseline.get("frontierIndex") if baseline.get("frontierIndex") is not None else -1)
    new_frontier = int(candidate.get("frontierIndex") if candidate.get("frontierIndex") is not None else -1)
    return new_frontier >= frontier


def _program_signature(solution: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(part.get("id") or ""),
            tuple((int(item.get("cycle") or 0), str(item.get("instruction") or "")) for item in (part.get("program") or [])),
        )
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "") in _ARM_TYPES
    )


def _valid_program(program: list[dict[str, Any]]) -> bool:
    cycles = [int(item.get("cycle") or 0) for item in program]
    return all(cycle >= 0 for cycle in cycles) and len(set(cycles)) == len(cycles)


def _physical_nearby_program_indices(
    solution: dict[str, Any],
    *,
    collision_cycle: int,
    window: int,
) -> dict[str, set[int]]:
    """Map a late official collision back to source tape instructions.

    Raw solution cycles are tape coordinates, not necessarily absolute physical
    cycles.  Once a short tape repeats, a collision hundreds of cycles later can
    be caused by an instruction whose source index is near zero.  Use our
    OMSim-compatible expanded timeline to identify which arm/action phases are
    actually active around the official collision, then map those events back to
    source program entries.  If repeat expansion does not retain sourceCycle,
    matching the instruction kind is a conservative fallback.
    """

    horizon = max(1, int(collision_cycle) + int(window) + 2)
    timeline = build_program_timeline(solution, max_cycles=horizon)
    start = max(0, int(collision_cycle) - int(window) - 1)
    end = int(collision_cycle) + int(window) + 1
    evidence: dict[str, list[dict[str, Any]]] = {}
    for frame in timeline.get("cycles", []) or []:
        cycle = int(frame.get("cycle") or 0)
        if cycle < start or cycle > end:
            continue
        for event in frame.get("events", []) or []:
            part_id = str(event.get("partId") or "")
            if not part_id:
                continue
            evidence.setdefault(part_id, []).append(event)

    result: dict[str, set[int]] = {}
    for part in solution.get("parts", []) or []:
        part_id = str(part.get("id") or "")
        events = evidence.get(part_id) or []
        if not events:
            continue
        program = list(part.get("program") or [])
        selected: set[int] = set()
        for event in events:
            source_cycle = event.get("sourceCycle")
            if source_cycle is not None:
                for index, item in enumerate(program):
                    if int(item.get("cycle") or 0) == int(source_cycle):
                        selected.add(index)
            instruction = str(event.get("instruction") or "")
            if instruction:
                matches = [
                    index for index, item in enumerate(program)
                    if str(item.get("instruction") or "") == instruction
                ]
                # Unique action kinds map exactly.  Repeated action kinds are all
                # retained because any occurrence can be the repeated tape cell.
                selected.update(matches)
        if selected:
            result[part_id] = selected
    return result


def timing_variants(
    solution: dict[str, Any],
    *,
    collision_cycle: int,
    window: int = 8,
    max_delay: int = 8,
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = {_program_signature(solution)}
    physical_nearby = _physical_nearby_program_indices(
        solution,
        collision_cycle=collision_cycle,
        window=window,
    )
    for part_index, part in enumerate(solution.get("parts", []) or []):
        if str(part.get("type") or "") not in _ARM_TYPES:
            continue
        program = list(part.get("program") or [])
        if not program:
            continue
        part_id = str(part.get("id") or f"part-{part_index}")
        nearby = sorted(physical_nearby.get(part_id) or set())
        # Keep the old raw-cycle path for first-period collisions and union it
        # with physical phase evidence for late repeated collisions.
        nearby = sorted(set(nearby) | {
            index for index, item in enumerate(program)
            if abs(int(item.get("cycle") or 0) - int(collision_cycle)) <= int(window)
        })
        if not nearby:
            continue

        # Shift the entire local action block. This preserves the mechanism's
        # internal phase while changing its relation to input spawning/other arms.
        for delta in range(-3, max(0, int(max_delay)) + 1):
            if delta == 0:
                continue
            candidate = deepcopy(solution)
            target = candidate["parts"][part_index]
            shifted = [dict(item, cycle=int(item.get("cycle") or 0) + delta) for item in target.get("program", []) or []]
            if not _valid_program(shifted):
                continue
            target["program"] = shifted
            signature = _program_signature(candidate)
            if signature in seen:
                continue
            seen.add(signature)
            variants.append({
                "mode": "shift-arm-program",
                "armPartId": part_id,
                "physicalCollisionCycle": int(collision_cycle),
                "sourceInstructionIndices": nearby,
                "delta": delta,
                "solution": candidate,
            })

        # Shift one physically implicated source instruction while preserving
        # unique tape cells. This can change a repeated grab/move/drop phase
        # without unnecessarily delaying the rest of the mechanism.
        for instruction_index in nearby:
            for delta in range(-2, max(0, int(max_delay)) + 1):
                if delta == 0:
                    continue
                candidate = deepcopy(solution)
                target = candidate["parts"][part_index]
                shifted = [dict(item) for item in target.get("program", []) or []]
                shifted[instruction_index]["cycle"] = int(shifted[instruction_index].get("cycle") or 0) + delta
                if not _valid_program(shifted):
                    continue
                target["program"] = shifted
                signature = _program_signature(candidate)
                if signature in seen:
                    continue
                seen.add(signature)
                variants.append({
                    "mode": "shift-single-instruction",
                    "armPartId": part_id,
                    "instructionIndex": instruction_index,
                    "instruction": str(program[instruction_index].get("instruction") or ""),
                    "oldCycle": int(program[instruction_index].get("cycle") or 0),
                    "newCycle": int(shifted[instruction_index].get("cycle") or 0),
                    "physicalCollisionCycle": int(collision_cycle),
                    "delta": delta,
                    "solution": candidate,
                })
    return variants


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    max_cycles: int = 500,
    window: int = 8,
    max_delay: int = 8,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    baseline_solution = parse_solution(baseline_path)
    baseline_file = output_dir / "baseline.solution"
    write_solution(baseline_solution, baseline_file)
    baseline_oracle = run_omsim(omsim, puzzle_path, baseline_file)
    baseline_profile = purification_profile(puzzle, baseline_solution, max_cycles=max_cycles)
    collision_cycle = baseline_oracle.get("collisionCycle")
    if collision_cycle is None:
        return {
            "schemaVersion": "0.2.0", "kind": "strict-heldout-oracle-timing-repair-search",
            "targetSolutionBytesUsed": 0, "baselineOMSim": baseline_oracle,
            "baselinePurificationProfile": baseline_profile, "searchedVariantCount": 0,
            "precursorPreservingCount": 0, "oracleAdvancingCount": 0,
            "best": None, "acceptedProductOne": int(baseline_oracle.get("exitCode") or 0) == 0,
        }

    records: list[dict[str, Any]] = []
    variants = timing_variants(
        baseline_solution, collision_cycle=int(collision_cycle), window=window, max_delay=max_delay,
    )
    for index, variant in enumerate(variants):
        path = output_dir / f"candidate-{index:03d}.solution"
        write_solution(variant["solution"], path)
        oracle = run_omsim(omsim, puzzle_path, path)
        profile = purification_profile(puzzle, variant["solution"], max_cycles=max_cycles)
        preserved = _precursor_preserved(baseline_profile, profile)
        advancing = int(oracle.get("progressCycle") or 0) > int(baseline_oracle.get("progressCycle") or 0)
        records.append({
            **{k: v for k, v in variant.items() if k != "solution"},
            "solutionPath": str(path), "omsim": oracle, "purificationProfile": profile,
            "precursorPreserved": preserved, "oracleAdvance": advancing,
        })

    records.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int(bool(item.get("precursorPreserved"))),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((_counts(item.get("purificationProfile") or {})).get("gold", 0)),
            int((_counts(item.get("purificationProfile") or {})).get("silver", 0)),
        ),
        reverse=True,
    )
    acceptable = [item for item in records if item.get("precursorPreserved") and item.get("oracleAdvance")]
    accepted = next((item for item in records if int((item.get("omsim") or {}).get("exitCode") or 0) == 0), None)
    best = accepted or (acceptable[0] if acceptable else (records[0] if records else None))
    best_output = None
    if best is not None:
        best_output = output_dir / "GEN249-best-oracle-timing.solution"
        best_output.write_bytes(Path(best["solutionPath"]).read_bytes())
    return {
        "schemaVersion": "0.2.0", "kind": "strict-heldout-oracle-timing-repair-search",
        "targetSolutionBytesUsed": 0,
        "request": {"maxCycles": int(max_cycles), "window": int(window), "maxDelay": int(max_delay)},
        "baselineOMSim": baseline_oracle, "baselinePurificationProfile": baseline_profile,
        "physicalPhaseProgramIndices": {
            key: sorted(value) for key, value in _physical_nearby_program_indices(
                baseline_solution, collision_cycle=int(collision_cycle), window=window,
            ).items()
        },
        "searchedVariantCount": len(records),
        "precursorPreservingCount": sum(bool(item.get("precursorPreserved")) for item in records),
        "oracleAdvancingCount": sum(bool(item.get("precursorPreserved")) and bool(item.get("oracleAdvance")) for item in records),
        "topVariants": records[:30], "best": best,
        "bestSolution": str(best_output) if best_output is not None else None,
        "acceptedProductOne": accepted is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair a blind OMSim frontier by perturbing source instructions active near the physical collision phase.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--window", type=int, default=8)
    parser.add_argument("--max-delay", type=int, default=8)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim, puzzle_path=args.puzzle, baseline_path=args.baseline,
        output_dir=args.output_dir, max_cycles=args.max_cycles, window=args.window, max_delay=args.max_delay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"], "physicalPhaseProgramIndices": report.get("physicalPhaseProgramIndices"),
        "searchedVariantCount": report["searchedVariantCount"],
        "precursorPreservingCount": report["precursorPreservingCount"], "oracleAdvancingCount": report["oracleAdvancingCount"],
        "best": report["best"], "acceptedProductOne": report["acceptedProductOne"], "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
