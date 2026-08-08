from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from tools.solution_identity import mechanical_id, raw_id, translation_class_id
from tools.validate_aqueous_offsets import validate


def score(metrics: dict) -> tuple[int, int, int, int]:
    huge = 10**9
    return (
        int(metrics.get("cycles", huge)),
        int(metrics.get("cost", huge)),
        int(metrics.get("area", huge)),
        int(metrics.get("instructions", huge)),
    )


def compact_score(metrics: dict) -> tuple[int, int, int, int]:
    huge = 10**9
    return (
        int(metrics.get("area", huge)),
        int(metrics.get("instructions", huge)),
        int(metrics.get("cycles", huge)),
        int(metrics.get("cost", huge)),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validator-url", required=True)
    ap.add_argument("--puzzle", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--generations", type=int, default=100)
    ap.add_argument("--elites", type=int, default=4)
    ap.add_argument("--target-cycles", type=int, default=26)
    ap.add_argument("--stagnation", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--progress-every", type=int, default=10)
    ap.add_argument("--watchdog-seconds", type=int, default=35)
    ap.add_argument("--generation-seconds", type=int, default=120)
    ap.add_argument("--heartbeat-seconds", type=int, default=5)
    args = ap.parse_args()

    generations = max(1, args.generations)
    parent_batch = max(1, min(8, args.elites))
    workers = max(1, min(8, args.workers))
    watchdog = max(15, args.watchdog_seconds)
    generation_budget = max(watchdog + 10, args.generation_seconds)
    heartbeat = max(1, args.heartbeat_seconds)

    puzzle = Path(args.puzzle)
    seed = Path(args.seed)
    root = Path(args.work)
    root.mkdir(parents=True, exist_ok=True)
    elite_dir = root / "elites"
    elite_dir.mkdir(exist_ok=True)

    seed_validation = validate(args.validator_url, puzzle, seed)
    if not seed_validation.get("valid"):
        raise SystemExit(f"Seed is invalid: {seed_validation}")

    seed_path = elite_dir / "seed.solution"
    shutil.copy2(seed, seed_path)
    seed_mid = mechanical_id(seed_path)
    seed_tid = translation_class_id(seed_path)
    seed_metrics = seed_validation.get("metrics") or {}

    hall: dict[str, dict] = {
        seed_mid: {
            "path": seed_path,
            "metrics": seed_metrics,
            "kind": "seed",
            "generation": 0,
            "mechanicalId": seed_mid,
            "translationClass": seed_tid,
            "sha256": raw_id(seed_path),
        }
    }
    attempted: set[str] = {seed_mid}
    expanded: set[str] = set()
    retryable: set[str] = set()
    submit_counts: Counter[str] = Counter()
    cumulative_tested = 0
    cumulative_valid = 1
    cumulative_timeouts = 0
    cumulative_retries = 0
    best_cycles = int(seed_metrics.get("cycles", 10**9))
    best_generation = 0
    history: list[dict] = [{"generation": 0, "bestCycles": best_cycles, "tested": 0, "valid": 1}]
    state = "running"

    def ranked_hall() -> list[dict]:
        return sorted(
            hall.values(),
            key=lambda item: (score(item.get("metrics") or {}), item.get("mechanicalId", "")),
        )

    def frontier_items() -> list[dict]:
        return [item for item in ranked_hall() if item["mechanicalId"] not in expanded]

    def select_parents(frontier: list[dict], generation: int) -> list[dict]:
        """Mix exploitation with structural exploration.

        The v5 run accumulated >50k valid unexpanded states while expanding only
        the score-leading fringe.  Four selectors keep one best-cycle parent but
        also walk recent chains, compact layouts and underexplored mutation kinds.
        """
        if not frontier:
            return []
        chosen: list[dict] = []
        chosen_ids: set[str] = set()

        def add(item: dict | None) -> None:
            if item is None:
                return
            mid = item["mechanicalId"]
            if mid in chosen_ids:
                return
            chosen_ids.add(mid)
            chosen.append(item)

        add(frontier[0])

        newest = max(
            frontier,
            key=lambda item: (
                int(item.get("generation") or 0),
                -score(item.get("metrics") or {})[0],
                item.get("mechanicalId", ""),
            ),
        )
        add(newest)

        add(min(frontier, key=lambda item: (compact_score(item.get("metrics") or {}), score(item.get("metrics") or {}))))

        expanded_kind_counts: Counter[str] = Counter(
            str(hall[mid].get("kind") or "unknown")
            for mid in expanded
            if mid in hall
        )
        add(min(
            frontier,
            key=lambda item: (
                expanded_kind_counts[str(item.get("kind") or "unknown")],
                -int(item.get("generation") or 0),
                score(item.get("metrics") or {}),
                item.get("mechanicalId", ""),
            ),
        ))

        # If selectors collide, fill from spaced positions instead of taking the
        # first N score-sorted states again.
        if len(chosen) < parent_batch:
            step = max(1, len(frontier) // max(1, parent_batch - len(chosen) + 1))
            offset = generation % step
            for index in range(offset, len(frontier), step):
                add(frontier[index])
                if len(chosen) >= parent_batch:
                    break
        for item in frontier:
            add(item)
            if len(chosen) >= parent_batch:
                break
        return chosen[:parent_batch]

    def distinct_top(limit: int = 3) -> list[dict]:
        # Translation class is display-only.  The archive and attempted registry
        # always use absolute-board mechanical identity.
        out: list[dict] = []
        seen_translation: set[str] = set()
        for item in ranked_hall():
            tc = item.get("translationClass") or item.get("mechanicalId")
            if tc in seen_translation:
                continue
            seen_translation.add(tc)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def save_checkpoint(gen: int, current_state: str, *, note: str = "") -> None:
        frontier = frontier_items()
        payload = {
            "schemaVersion": 6,
            "state": current_state,
            "generation": gen,
            "maxGenerations": generations,
            "bestCycles": best_cycles,
            "bestGeneration": best_generation,
            "tested": cumulative_tested,
            "valid": cumulative_valid,
            "timeouts": cumulative_timeouts,
            "retries": cumulative_retries,
            "attemptedMechanisms": len(attempted),
            "validMechanisms": len(hall),
            "expandedParents": len(expanded),
            "frontier": len(frontier),
            "retryable": len(retryable),
            "workers": workers,
            "watchdogSeconds": watchdog,
            "generationSeconds": generation_budget,
            "history": history,
            "top": [
                {
                    "metrics": x.get("metrics"),
                    "kind": x.get("kind"),
                    "generation": x.get("generation"),
                    "mechanicalId": x.get("mechanicalId"),
                    "translationClass": x.get("translationClass"),
                    "sha256": x.get("sha256"),
                }
                for x in distinct_top(3)
            ],
            "note": note,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        tmp = root / "checkpoint.json.tmp"
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(root / "checkpoint.json")
        (root / "attempted.txt").write_text("\n".join(sorted(attempted)) + "\n", encoding="utf-8")
        (root / "expanded.txt").write_text("\n".join(sorted(expanded)) + "\n", encoding="utf-8")
        (root / "retryable.txt").write_text("\n".join(sorted(retryable)) + "\n", encoding="utf-8")
        for rank, item in enumerate(distinct_top(3), 1):
            shutil.copy2(Path(item["path"]), root / f"top-{rank}.solution")

    print(
        f"V6 STRUCTURAL workers={workers} watchdog={watchdog}s generationBudget={generation_budget}s",
        flush=True,
    )

    for gen in range(1, generations + 1):
        frontier = frontier_items()
        if not frontier:
            state = "exhausted"
            print(f"SEARCH EXHAUSTED generation={gen} attempted={len(attempted)} valid={len(hall)} best={best_cycles}", flush=True)
            break

        parents = select_parents(frontier, gen)
        parent_ids = [parent["mechanicalId"] for parent in parents]
        print(
            "PARENTS " + json.dumps([
                {
                    "kind": p.get("kind"), "generation": p.get("generation"),
                    "cycles": (p.get("metrics") or {}).get("cycles"),
                    "cost": (p.get("metrics") or {}).get("cost"),
                    "area": (p.get("metrics") or {}).get("area"),
                    "mechanicalId": p.get("mechanicalId"),
                }
                for p in parents
            ], sort_keys=True),
            flush=True,
        )

        gen_dir = root / f"generation-{gen:03d}"
        if gen_dir.exists():
            shutil.rmtree(gen_dir)
        variants_dir = gen_dir / "variants"
        variants_dir.mkdir(parents=True)

        candidate_meta: dict[str, dict] = {}
        seen_generation: set[str] = set()
        translation_classes: set[str] = set()
        generated_raw = 0
        duplicate_within = 0
        duplicate_attempted = 0
        retry_candidates = 0
        serial = 0

        for parent_index, parent in enumerate(parents):
            fixture = gen_dir / f"parent-{parent_index}.solution.b64"
            fixture.write_text(base64.b64encode(Path(parent["path"]).read_bytes()).decode("ascii"), encoding="utf-8")
            out = gen_dir / f"parent-{parent_index}-variants"
            subprocess.run(
                ["python", "tools/search_aqueous_structural.py", "--fixture", str(fixture), "--out", str(out)],
                check=True,
            )
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            for meta in manifest.get("variants", []):
                generated_raw += 1
                src = out / meta["file"]
                mid = mechanical_id(src)
                tid = translation_class_id(src)
                translation_classes.add(tid)
                if mid in seen_generation:
                    duplicate_within += 1
                    continue
                seen_generation.add(mid)
                is_retry = mid in retryable
                if mid in attempted and not is_retry:
                    duplicate_attempted += 1
                    continue
                if is_retry:
                    retry_candidates += 1
                name = f"variant-{serial:06d}.solution"
                serial += 1
                dst = variants_dir / name
                shutil.copy2(src, dst)
                candidate_meta[name] = {
                    **meta,
                    "mechanicalId": mid,
                    "translationClass": tid,
                    "isRetry": is_retry,
                    "parentMechanicalId": parent["mechanicalId"],
                    "parentRank": parent_index + 1,
                    "parentCycles": (parent.get("metrics") or {}).get("cycles"),
                }

        total = len(candidate_meta)
        print(
            "DIVERSITY "
            f"generation={gen}/{generations} parents={len(parents)} generated={generated_raw} "
            f"new={total-retry_candidates} retries={retry_candidates} repeatPrior={duplicate_attempted} "
            f"duplicateWithin={duplicate_within} translationClasses={len(translation_classes)} "
            f"attemptedBefore={len(attempted)} validArchive={len(hall)} frontierBefore={len(frontier)}",
            flush=True,
        )

        if total == 0:
            expanded.update(parent_ids)
            history.append({
                "generation": gen, "bestCycles": best_cycles, "tested": 0, "valid": 0,
                "new": 0, "retries": 0, "repeatPrior": duplicate_attempted,
                "duplicateWithin": duplicate_within, "translationClasses": len(translation_classes),
                "frontier": len(frontier_items()),
            })
            save_checkpoint(gen, "running", note="No new neighbors; parents marked expanded")
            continue

        names = iter(candidate_meta)
        active: dict[Future, str] = {}
        tested = 0
        valid_count = 0
        timeouts = 0
        retries_used = 0
        started_at = time.monotonic()
        last_result = started_at
        last_heartbeat = started_at
        aborted = False
        pool = ThreadPoolExecutor(max_workers=workers)

        def submit_one() -> bool:
            nonlocal retries_used, cumulative_retries
            try:
                name = next(names)
            except StopIteration:
                return False
            meta = candidate_meta[name]
            mid = meta["mechanicalId"]
            if meta.get("isRetry"):
                retries_used += 1
                cumulative_retries += 1
                retryable.discard(mid)
            attempted.add(mid)
            submit_counts[mid] += 1
            fut = pool.submit(validate, args.validator_url, puzzle, variants_dir / name)
            active[fut] = name
            return True

        for _ in range(min(workers, total)):
            submit_one()

        while active:
            done, _ = wait(set(active), timeout=1.0, return_when=FIRST_COMPLETED)
            now = time.monotonic()
            if done:
                for fut in done:
                    name = active.pop(fut)
                    tested += 1
                    cumulative_tested += 1
                    try:
                        validation = fut.result()
                    except Exception as exc:
                        validation = {"valid": False, "issues": [{"message": str(exc)}]}
                    if validation.get("valid") is True:
                        valid_count += 1
                        cumulative_valid += 1
                        metrics = validation.get("metrics") or {}
                        path = variants_dir / name
                        meta = candidate_meta[name]
                        mid = meta["mechanicalId"]
                        record = {
                            **meta,
                            "path": path,
                            "metrics": metrics,
                            "kind": meta.get("kind", "candidate"),
                            "generation": gen,
                            "sha256": raw_id(path),
                        }
                        previous = hall.get(mid)
                        if previous is None or score(metrics) < score(previous.get("metrics") or {}):
                            hall[mid] = record
                        cycles = int(metrics.get("cycles", 10**9))
                        if cycles < best_cycles:
                            best_cycles = cycles
                            best_generation = gen
                            print(
                                "NEW GLOBAL BEST " + json.dumps(
                                    {"generation": gen, "metrics": metrics, "kind": record["kind"], "mechanicalId": mid},
                                    sort_keys=True,
                                ),
                                flush=True,
                            )
                    submit_one()
                last_result = now

                if tested % max(1, args.progress_every) == 0 or tested == total:
                    print(
                        f"PROGRESS generation={gen}/{generations} tested={tested}/{total} cumulative={cumulative_tested} "
                        f"valid={valid_count} best={best_cycles} attempted={len(attempted)} archive={len(hall)} retries={retries_used}",
                        flush=True,
                    )

            if now - last_heartbeat >= heartbeat:
                print(
                    f"HEARTBEAT generation={gen}/{generations} tested={tested}/{total} active={len(active)} "
                    f"idle={now-last_result:.1f}s elapsed={now-started_at:.1f}s timeouts={timeouts}",
                    flush=True,
                )
                last_heartbeat = now

            idle_timeout = now - last_result >= watchdog
            wall_timeout = now - started_at >= generation_budget
            if active and (idle_timeout or wall_timeout):
                aborted = True
                reason = "idle" if idle_timeout else "wall"
                abandoned_names = list(active.values())
                timeouts += len(abandoned_names)
                cumulative_timeouts += len(abandoned_names)
                for fut in active:
                    fut.cancel()
                # One bounded retry.  Parents stay unexpanded after an abort, so
                # these neighbors can be regenerated on the next pass.
                for name in abandoned_names:
                    mid = candidate_meta[name]["mechanicalId"]
                    if submit_counts[mid] < 2:
                        retryable.add(mid)
                print(
                    f"WATCHDOG generation={gen}/{generations} reason={reason} idle={now-last_result:.1f}s "
                    f"elapsed={now-started_at:.1f}s abandoningActive={len(abandoned_names)} "
                    f"retryable={len(retryable)} tested={tested}/{total}",
                    flush=True,
                )
                active.clear()
                break

        pool.shutdown(wait=False, cancel_futures=True)

        if not aborted and tested >= total:
            expanded.update(parent_ids)

        history.append({
            "generation": gen,
            "bestCycles": best_cycles,
            "tested": tested,
            "valid": valid_count,
            "new": total - retry_candidates,
            "retries": retries_used,
            "repeatPrior": duplicate_attempted,
            "duplicateWithin": duplicate_within,
            "translationClasses": len(translation_classes),
            "timeouts": timeouts,
            "aborted": aborted,
            "attempted": len(attempted),
            "validArchive": len(hall),
            "expanded": len(expanded),
            "frontier": len(frontier_items()),
        })
        save_checkpoint(gen, "target_reached" if best_cycles <= args.target_cycles else "running")
        print(
            f"CHECKPOINT generation={gen} best={best_cycles} distinctTop={len(distinct_top())} "
            f"attempted={len(attempted)} validArchive={len(hall)} expanded={len(expanded)} "
            f"frontier={len(frontier_items())} retryable={len(retryable)} aborted={int(aborted)}",
            flush=True,
        )

        if best_cycles <= args.target_cycles:
            state = "target_reached"
            print(f"TARGET REACHED: {best_cycles}c in generation {gen}", flush=True)
            break
    else:
        state = "generation_limit"

    ranked = ranked_hall()
    report = {
        "schemaVersion": 6,
        "state": state,
        "generationsCompleted": history[-1]["generation"],
        "maxGenerations": generations,
        "tested": cumulative_tested,
        "valid": cumulative_valid,
        "timeouts": cumulative_timeouts,
        "retries": cumulative_retries,
        "attemptedMechanisms": len(attempted),
        "validMechanisms": len(hall),
        "expandedParents": len(expanded),
        "frontier": len(frontier_items()),
        "retryable": len(retryable),
        "bestCycles": best_cycles,
        "bestGeneration": best_generation,
        "history": history,
        "top": [
            {
                "metrics": item.get("metrics"),
                "kind": item.get("kind"),
                "generation": item.get("generation"),
                "mechanicalId": item.get("mechanicalId"),
                "translationClass": item.get("translationClass"),
                "sha256": item.get("sha256"),
            }
            for item in ranked[:10]
        ],
    }
    (root / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    save_checkpoint(history[-1]["generation"], state)
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
