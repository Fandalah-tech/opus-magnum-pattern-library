from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import issue_signature, validate


def api_put_file(repo: str, branch: str, path: str, token: str, data: bytes, message: str) -> None:
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    api = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "opus-magnum-codex-evolution",
    }
    sha = None
    try:
        req = urllib.request.Request(f"{api}?ref={urllib.parse.quote(branch, safe='')}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            sha = json.loads(response.read().decode("utf-8")).get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            print(f"DASHBOARD WARN read {path}: HTTP {exc.code}", flush=True)
            return
    body = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    request = urllib.request.Request(
        api,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=25):
            pass
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"DASHBOARD WARN write {path}: HTTP {exc.code} {detail}", flush=True)
    except Exception as exc:
        print(f"DASHBOARD WARN write {path}: {exc}", flush=True)


def score(metrics: dict) -> tuple[int, int, int, int]:
    huge = 10**9
    return (
        int(metrics.get("cycles", huge)),
        int(metrics.get("cost", huge)),
        int(metrics.get("area", huge)),
        int(metrics.get("instructions", huge)),
    )


def solution_id(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_solution_id(path: Path) -> str:
    """Hash the actual mechanism/program, ignoring the human-readable solution name.

    The mutation generator gives each candidate a different name, so raw file hashes
    can differ even when two candidates are functionally identical in Opus Magnum.
    """
    try:
        model = parse_solution_bytes(path.read_bytes(), source_name=path.name)
        model["name"] = ""
        model["metrics"] = {}
        model["unknownMetrics"] = []
        canonical = write_solution_bytes(model)
        return hashlib.sha256(canonical).hexdigest()
    except Exception:
        return solution_id(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validator-url", required=True)
    ap.add_argument("--puzzle", default="reports/aqueous-dagger.puzzle")
    ap.add_argument("--seed", default="reports/single27.solution")
    ap.add_argument("--work", default="reports/aqueous-evolution")
    ap.add_argument("--generations", type=int, default=10)
    ap.add_argument("--elites", type=int, default=3)
    ap.add_argument("--target-cycles", type=int, default=26)
    ap.add_argument("--stagnation", type=int, default=8)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--progress-every", type=int, default=10)
    ap.add_argument("--watchdog-seconds", type=int, default=35)
    ap.add_argument("--heartbeat-seconds", type=int, default=5)
    ap.add_argument("--live-repo")
    ap.add_argument("--live-branch", default="aqueous-dashboard-live")
    ap.add_argument("--live-dir", default="aqueous-dashboard")
    ap.add_argument("--live-token-env", default="GITHUB_TOKEN")
    args = ap.parse_args()

    generations = max(1, args.generations)
    elite_count = max(1, min(8, args.elites))
    worker_count = max(1, min(12, args.workers))
    watchdog_seconds = max(15, args.watchdog_seconds)
    heartbeat_seconds = max(1, args.heartbeat_seconds)
    root = Path(args.work)
    root.mkdir(parents=True, exist_ok=True)
    puzzle = Path(args.puzzle)
    seed = Path(args.seed)
    token = os.environ.get(args.live_token_env)
    run_url = None
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
        run_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

    print(
        f"UNATTENDED workers={worker_count} watchdog={watchdog_seconds}s heartbeat={heartbeat_seconds}s",
        flush=True,
    )

    seed_validation = validate(args.validator_url, puzzle, seed)
    if not seed_validation.get("valid"):
        raise SystemExit(f"Seed is invalid: {seed_validation}")
    seed_metrics = seed_validation.get("metrics") or {}
    seed_cycles = int(seed_metrics.get("cycles", 10**9))

    elite_dir = root / "elites"
    elite_dir.mkdir(exist_ok=True)
    seed_copy = elite_dir / "seed.solution"
    shutil.copy2(seed, seed_copy)
    seed_semantic = semantic_solution_id(seed_copy)
    seed_raw = solution_id(seed_copy)
    elites = [{
        "path": seed_copy,
        "metrics": seed_metrics,
        "kind": "seed",
        "generation": 0,
        "sha256": seed_raw,
        "semanticId": seed_semantic,
    }]

    # Hall is keyed by semantic identity, not raw bytes. This prevents three
    # differently named copies of the same mechanism from occupying all elites.
    hall: dict[str, dict] = {seed_semantic: dict(elites[0])}
    cumulative_tested = 0
    cumulative_valid = 0
    cumulative_timeouts = 0
    best_cycles = seed_cycles
    best_generation = 0
    stagnant = 0
    history = [{"generation": 0, "bestCycles": best_cycles, "tested": 0, "valid": 1, "timeouts": 0}]

    generation = 0
    generation_tested = 0
    generation_total = 0
    generation_valid = 0
    generation_timeouts = 0
    state = "preparing"

    def ranked_hall(limit: int | None = None) -> list[dict]:
        ranked = sorted(
            hall.values(),
            key=lambda x: (score(x.get("metrics") or {}), x.get("semanticId", ""), x.get("sha256", "")),
        )
        return ranked if limit is None else ranked[:limit]

    def top3() -> list[dict]:
        result = []
        for rank, item in enumerate(ranked_hall(3), 1):
            metrics = item.get("metrics") or {}
            result.append({
                "rank": rank,
                "cycles": metrics.get("cycles"),
                "cost": metrics.get("cost"),
                "area": metrics.get("area"),
                "instructions": metrics.get("instructions"),
                "mutation": item.get("kind", "candidate"),
                "generation": item.get("generation", 0),
                "sha256": item.get("sha256"),
                "semanticId": item.get("semanticId"),
                "downloadUrl": f"https://raw.githubusercontent.com/{args.live_repo}/{args.live_branch}/{args.live_dir}/top-{rank}.solution" if args.live_repo else None,
            })
        return result

    def checkpoint(current_state: str) -> None:
        payload = {
            "state": current_state,
            "generation": generation,
            "maxGenerations": generations,
            "bestCycles": best_cycles,
            "bestGeneration": best_generation,
            "stagnation": stagnant,
            "tested": cumulative_tested,
            "valid": cumulative_valid,
            "timeouts": cumulative_timeouts,
            "workers": worker_count,
            "watchdogSeconds": watchdog_seconds,
            "history": history,
            "top": top3(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        tmp = root / "checkpoint.json.tmp"
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(root / "checkpoint.json")

    def publish(current_state: str, *, publish_files: bool = False) -> None:
        if not args.live_repo or not token:
            return
        ranked = ranked_hall(3)
        if publish_files:
            for rank, item in enumerate(ranked, 1):
                api_put_file(
                    args.live_repo,
                    args.live_branch,
                    f"{args.live_dir}/top-{rank}.solution",
                    token,
                    Path(item["path"]).read_bytes(),
                    f"Publish Aqueous top {rank} solution",
                )
        payload = {
            "puzzle": "Aqueous Dagger",
            "state": current_state,
            "seedCycles": seed_cycles,
            "targetCycles": args.target_cycles,
            "generation": generation,
            "maxGenerations": generations,
            "generationTested": generation_tested,
            "generationTotal": generation_total,
            "generationValid": generation_valid,
            "generationTimeouts": generation_timeouts,
            "tested": cumulative_tested,
            "valid": cumulative_valid,
            "timeouts": cumulative_timeouts,
            "bestCycles": best_cycles,
            "bestGeneration": best_generation,
            "bestMutation": top3()[0]["mutation"] if top3() else "seed",
            "eliteCount": len(ranked_hall(elite_count)),
            "stagnation": stagnant,
            "stagnationLimit": args.stagnation,
            "workers": worker_count,
            "watchdogSeconds": watchdog_seconds,
            "topSolutions": top3(),
            "history": history[-30:],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "runUrl": run_url,
        }
        api_put_file(
            args.live_repo,
            args.live_branch,
            f"{args.live_dir}/status.json",
            token,
            (json.dumps(payload, indent=2) + "\n").encode("utf-8"),
            "Update Aqueous evolution dashboard",
        )

    checkpoint("preparing")
    publish("preparing", publish_files=True)

    for gen in range(1, generations + 1):
        generation = gen
        gen_dir = root / f"generation-{gen:03d}"
        if gen_dir.exists():
            shutil.rmtree(gen_dir)
        gen_dir.mkdir(parents=True)
        variants_dir = gen_dir / "variants"
        variants_dir.mkdir()

        candidate_meta: dict[str, dict] = {}
        seen_semantic: set[str] = set()
        serial = 0
        for parent_index, parent in enumerate(elites):
            fixture = gen_dir / f"parent-{parent_index}.solution.b64"
            fixture.write_text(base64.b64encode(Path(parent["path"]).read_bytes()).decode("ascii"))
            out = gen_dir / f"parent-{parent_index}-variants"
            command = [
                "python", "tools/search_aqueous_28c_single.py",
                "--fixture", str(fixture),
                "--out", str(out),
            ]
            subprocess.run(command, check=True)
            manifest = json.loads((out / "manifest.json").read_text())
            for meta in manifest.get("variants", []):
                src = out / meta["file"]
                semantic_id = semantic_solution_id(src)
                if semantic_id in seen_semantic or semantic_id in hall:
                    continue
                seen_semantic.add(semantic_id)
                name = f"variant-{serial:06d}.solution"
                serial += 1
                dst = variants_dir / name
                shutil.copy2(src, dst)
                candidate_meta[name] = {
                    **meta,
                    "semanticId": semantic_id,
                    "parentRank": parent_index + 1,
                    "parentCycles": (parent.get("metrics") or {}).get("cycles"),
                }

        generation_tested = 0
        generation_valid = 0
        generation_timeouts = 0
        generation_total = len(candidate_meta)
        print(
            f"GENERATION {gen}/{generations} candidates={generation_total} parents={len(elites)} workers={worker_count}",
            flush=True,
        )
        publish("running")

        valid_this_generation: list[dict] = []
        pool = ThreadPoolExecutor(max_workers=worker_count)
        futures = {
            pool.submit(validate, args.validator_url, puzzle, variants_dir / name): name
            for name in candidate_meta
        }
        pending = set(futures)
        last_result_at = time.monotonic()
        last_heartbeat_at = last_result_at
        watchdog_fired = False

        while pending:
            done, _ = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            now_mono = time.monotonic()
            if done:
                for future in done:
                    pending.discard(future)
                    name = futures[future]
                    generation_tested += 1
                    cumulative_tested += 1
                    try:
                        validation = future.result()
                    except Exception as exc:
                        validation = {"valid": False, "issues": [{"message": str(exc)}]}
                    if validation.get("valid") is True:
                        generation_valid += 1
                        cumulative_valid += 1
                        metrics = validation.get("metrics") or {}
                        path = variants_dir / name
                        semantic_id = candidate_meta[name]["semanticId"]
                        raw_id = solution_id(path)
                        record = {
                            **candidate_meta[name],
                            "path": path,
                            "metrics": metrics,
                            "kind": candidate_meta[name].get("kind", "candidate"),
                            "generation": gen,
                            "sha256": raw_id,
                            "semanticId": semantic_id,
                        }
                        # Same semantic mechanism can arrive through several mutation paths.
                        # Keep only its best-scoring representation.
                        previous = hall.get(semantic_id)
                        if previous is None or score(metrics) < score(previous.get("metrics") or {}):
                            hall[semantic_id] = record
                        valid_this_generation.append(record)
                        cycles = int(metrics.get("cycles", 10**9))
                        if cycles < best_cycles:
                            best_cycles = cycles
                            best_generation = gen
                            stagnant = 0
                            print(
                                "NEW GLOBAL BEST",
                                json.dumps({"generation": gen, "metrics": metrics, "kind": record["kind"]}, sort_keys=True),
                                flush=True,
                            )
                            publish("target_reached" if best_cycles <= args.target_cycles else "running", publish_files=True)
                    else:
                        _ = issue_signature(validation)

                last_result_at = now_mono

                if generation_tested % max(1, args.progress_every) == 0 or generation_tested == generation_total:
                    print(
                        f"PROGRESS generation={gen}/{generations} tested={generation_tested}/{generation_total} cumulative={cumulative_tested} valid={generation_valid} best={best_cycles} cumulativeValid={cumulative_valid} timeouts={generation_timeouts}",
                        flush=True,
                    )
                    publish("target_reached" if best_cycles <= args.target_cycles else "running")

            if now_mono - last_heartbeat_at >= heartbeat_seconds:
                idle = now_mono - last_result_at
                print(
                    f"HEARTBEAT generation={gen}/{generations} tested={generation_tested}/{generation_total} pending={len(pending)} idle={idle:.1f}s timeouts={generation_timeouts}",
                    flush=True,
                )
                last_heartbeat_at = now_mono

            if pending and now_mono - last_result_at >= watchdog_seconds:
                watchdog_fired = True
                timed_out = len(pending)
                generation_timeouts += timed_out
                cumulative_timeouts += timed_out
                generation_tested += timed_out
                cumulative_tested += timed_out
                print(
                    f"WATCHDOG generation={gen}/{generations} no-result-for={now_mono-last_result_at:.1f}s abandoning={timed_out}",
                    flush=True,
                )
                for future in pending:
                    future.cancel()
                pending.clear()
                publish("running")
                break

        # Do not allow straggler validator threads to hold the generation open.
        pool.shutdown(wait=False, cancel_futures=True)

        previous_best = history[-1]["bestCycles"]
        ranked_all = ranked_hall()
        elites = []
        for rank, item in enumerate(ranked_all[:elite_count]):
            elite_path = elite_dir / f"g{gen:03d}-elite-{rank+1}.solution"
            shutil.copy2(Path(item["path"]), elite_path)
            elites.append({**item, "path": elite_path})

        if best_cycles >= previous_best:
            stagnant += 1
        else:
            stagnant = 0
        history.append({
            "generation": gen,
            "bestCycles": best_cycles,
            "tested": generation_tested,
            "valid": generation_valid,
            "timeouts": generation_timeouts,
            "watchdog": watchdog_fired,
            "distinctElites": len(elites),
        })
        checkpoint("target_reached" if best_cycles <= args.target_cycles else "running")
        publish("target_reached" if best_cycles <= args.target_cycles else "running", publish_files=True)

        print(
            f"CHECKPOINT generation={gen} best={best_cycles} elites={len(elites)} valid={generation_valid} timeouts={generation_timeouts}",
            flush=True,
        )

        if best_cycles <= args.target_cycles:
            state = "target_reached"
            print(f"TARGET REACHED: {best_cycles}c in generation {gen}", flush=True)
            break
        if args.stagnation > 0 and stagnant >= args.stagnation:
            state = "stagnated"
            print(f"STOP: stagnation limit {args.stagnation} reached", flush=True)
            break
    else:
        state = "completed"

    ranked_final = ranked_hall(10)
    report = {
        "state": state,
        "generationsCompleted": generation,
        "maxGenerations": generations,
        "tested": cumulative_tested,
        "valid": cumulative_valid,
        "timeouts": cumulative_timeouts,
        "bestCycles": best_cycles,
        "workers": worker_count,
        "watchdogSeconds": watchdog_seconds,
        "history": history,
        "top": [
            {
                "metrics": item.get("metrics"),
                "kind": item.get("kind"),
                "generation": item.get("generation"),
                "sha256": item.get("sha256"),
                "semanticId": item.get("semanticId"),
            }
            for item in ranked_final
        ],
    }
    (root / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for rank, item in enumerate(ranked_final[:3], 1):
        shutil.copy2(Path(item["path"]), root / f"top-{rank}.solution")
    checkpoint(state)
    publish(state, publish_files=True)
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
