from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import product
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import validate

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


def canonical_program_signature(solution: dict) -> str:
    """Identity for the fixed-geometry timing search.

    Ignores solution name/metrics and arm numbering, but preserves part geometry,
    instruction sequence and instruction cycles.  This prevents retesting the same
    timing state under different generated names.
    """
    parts = []
    for part in solution.get("parts") or []:
        item = {
            "type": part.get("type"),
            "position": list(part.get("position") or [0, 0]),
            "rotation": int(part.get("rotation") or 0) % 6,
            "length": int(part.get("length") or 1),
            "program": [
                (int(i.get("cycle", 0)), str(i.get("instruction") or ""))
                for i in (part.get("program") or [])
            ],
        }
        # Track geometry is relevant when present.
        if part.get("type") == "track":
            item["track"] = part.get("track") or part.get("trackHexes") or part.get("positions") or []
        parts.append(item)
    parts.sort(key=lambda p: json.dumps(p, sort_keys=True, separators=(",", ":")))
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def legal_program(program: list[dict]) -> bool:
    cycles = [int(item.get("cycle", 0)) for item in program]
    return min(cycles, default=0) >= 0 and len(cycles) == len(set(cycles))


def score(metrics: dict) -> tuple[int, int, int, int]:
    huge = 10**9
    return (
        int(metrics.get("cycles", huge)),
        int(metrics.get("cost", huge)),
        int(metrics.get("area", huge)),
        int(metrics.get("instructions", huge)),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validator-url", required=True)
    ap.add_argument("--puzzle", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--target-cycles", type=int, default=44,
                    help="Approximate period-7 target for the supplied 49c period-8 seed")
    ap.add_argument("--max-shift", type=int, default=1)
    args = ap.parse_args()

    puzzle = Path(args.puzzle)
    seed_path = Path(args.seed)
    root = Path(args.work)
    root.mkdir(parents=True, exist_ok=True)
    variants_dir = root / "variants"
    variants_dir.mkdir(exist_ok=True)

    seed_bytes = seed_path.read_bytes()
    seed = parse_solution_bytes(seed_bytes, source_name=seed_path.name)
    seed_validation = validate(args.validator_url, puzzle, seed_path)
    if not seed_validation.get("valid"):
        raise SystemExit(f"Seed invalid: {seed_validation}")
    seed_metrics = seed_validation.get("metrics") or {}
    best_metrics = seed_metrics
    best_path = root / "best.solution"
    shutil.copy2(seed_path, best_path)

    arms = [i for i, p in enumerate(seed.get("parts") or []) if p.get("type") in ARM_TYPES]
    instruction_slots: list[tuple[int, int]] = []
    for pi in arms:
        for ii, _ in enumerate(seed["parts"][pi].get("program") or []):
            instruction_slots.append((pi, ii))

    # Exhaustive fixed-order compression: each instruction may stay put or move
    # one cycle earlier.  For the supplied seed this is intentionally small enough
    # to exhaust (2^N), and directly asks whether period 8 can be compressed to 7
    # without changing the already-good R3 geometry.
    values = tuple(range(0, args.max_shift + 1))
    seen: set[str] = set()
    candidates: list[Path] = []
    generated = 0
    rejected_program = 0

    for choice in product(values, repeat=len(instruction_slots)):
        if not any(choice):
            continue
        candidate = copy.deepcopy(seed)
        candidate["name"] = "Bestagon R3 timing compression"
        candidate["metrics"] = {}
        candidate["unknownMetrics"] = []
        for shift, (pi, ii) in zip(choice, instruction_slots):
            candidate["parts"][pi]["program"][ii]["cycle"] -= shift
        if not all(legal_program(candidate["parts"][pi].get("program") or []) for pi in arms):
            rejected_program += 1
            continue
        sig = canonical_program_signature(candidate)
        if sig in seen:
            continue
        seen.add(sig)
        path = variants_dir / f"candidate-{len(candidates):06d}.solution"
        path.write_bytes(write_solution_bytes(candidate))
        candidates.append(path)
        generated += 1

    print(json.dumps({
        "seedMetrics": seed_metrics,
        "arms": arms,
        "instructionSlots": len(instruction_slots),
        "generated": generated,
        "rejectedProgram": rejected_program,
        "targetCycles": args.target_cycles,
    }, sort_keys=True), flush=True)

    tested = 0
    valid = 0
    improved = 0
    found_target = False
    workers = max(1, min(8, args.workers))
    iterator = iter(candidates)
    active = {}
    pool = ThreadPoolExecutor(max_workers=workers)

    def submit_one() -> bool:
        try:
            path = next(iterator)
        except StopIteration:
            return False
        active[pool.submit(validate, args.validator_url, puzzle, path)] = path
        return True

    for _ in range(min(workers, len(candidates))):
        submit_one()

    started = time.monotonic()
    last_log = started
    while active:
        done, _ = wait(set(active), timeout=1.0, return_when=FIRST_COMPLETED)
        for fut in done:
            path = active.pop(fut)
            tested += 1
            try:
                result = fut.result()
            except Exception as exc:
                result = {"valid": False, "issues": [{"message": str(exc)}]}
            if result.get("valid") is True:
                valid += 1
                metrics = result.get("metrics") or {}
                if score(metrics) < score(best_metrics):
                    improved += 1
                    best_metrics = metrics
                    shutil.copy2(path, best_path)
                    print("NEW BEST " + json.dumps(metrics, sort_keys=True), flush=True)
                cycles = int(metrics.get("cycles", 10**9))
                if cycles <= args.target_cycles:
                    found_target = True
                    target = root / f"target-{cycles}c.solution"
                    shutil.copy2(path, target)
                    print("TARGET FOUND " + json.dumps(metrics, sort_keys=True), flush=True)
                    # Keep searching the already-launched jobs, but do not need to
                    # submit the rest once period-7-or-better has been demonstrated.
                if not found_target:
                    submit_one()
            else:
                if not found_target:
                    submit_one()

        now = time.monotonic()
        if now - last_log >= 5:
            print(f"PROGRESS tested={tested}/{len(candidates)} valid={valid} bestCycles={best_metrics.get('cycles')} elapsed={now-started:.1f}s", flush=True)
            last_log = now
        if found_target and not done and time.monotonic() - last_log > 10:
            break

    pool.shutdown(wait=False, cancel_futures=True)

    result = {
        "state": "target-found" if found_target else "complete",
        "seedMetrics": seed_metrics,
        "bestMetrics": best_metrics,
        "generated": generated,
        "tested": tested,
        "valid": valid,
        "improved": improved,
        "targetCycles": args.target_cycles,
        "foundTarget": found_target,
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }
    (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("RESULT " + json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
