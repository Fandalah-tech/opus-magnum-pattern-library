from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def validate(url: str, puzzle: Path, solution: Path) -> dict:
    command = [
        "curl", "--fail-with-body", "-sS",
        "-F", f"puzzle=@{puzzle}",
        "-F", f"solution=@{solution}",
        f"{url}/api/v1/analyze",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return {"httpError": result.stderr.strip(), "valid": False}
    payload = json.loads(result.stdout)
    return payload.get("validation", {})


def issue_signature(validation: dict) -> str:
    issues = validation.get("issues") or []
    if not issues:
        return str(validation.get("status") or "unknown")
    message = str(issues[0].get("message") or issues[0].get("code") or "issue")
    return message.splitlines()[-1][:180]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator-url", required=True)
    parser.add_argument("--puzzle", default="reports/aqueous-dagger.puzzle")
    parser.add_argument("--variants", default="reports/aqueous-offset-search")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    root = Path(args.variants)
    manifest = json.loads((root / "manifest.json").read_text())
    variant_meta = {item["file"]: item for item in manifest["variants"]}
    solutions = sorted(root.glob("variant-*.solution"))
    best = None
    valid_results = []
    failures = Counter()
    tested = 0

    total = len(solutions)
    print(f"SEARCH START candidates={total} workers={max(1, args.workers)}", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(validate, args.validator_url, Path(args.puzzle), solution): solution
            for solution in solutions
        }
        for future in as_completed(futures):
            solution = futures[future]
            tested += 1
            try:
                validation = future.result()
            except Exception as exc:
                validation = {"valid": False, "issues": [{"message": f"validator exception: {exc}"}]}
            metrics = validation.get("metrics") or {}
            if validation.get("valid") is True:
                record = {**variant_meta[solution.name], "metrics": metrics}
                valid_results.append(record)
                cycles = metrics.get("cycles")
                if cycles is not None and (best is None or cycles < best["metrics"]["cycles"]):
                    best = record
                    shutil.copy2(solution, root / "best.solution")
                    print("NEW BEST", json.dumps(best, sort_keys=True), flush=True)
            else:
                failures[issue_signature(validation)] += 1

            if tested % max(1, args.progress_every) == 0 or tested == total:
                best_cycles = None if best is None else best.get("metrics", {}).get("cycles")
                print(
                    f"PROGRESS tested={tested}/{total} valid={len(valid_results)} best_cycles={best_cycles}",
                    flush=True,
                )

    valid_results.sort(key=lambda r: (
        r.get("metrics", {}).get("cycles", 10**9),
        r.get("metrics", {}).get("cost", 10**9),
        r.get("file", ""),
    ))
    report = {
        "candidateCount": manifest["candidateCount"],
        "tested": tested,
        "valid": valid_results,
        "best": best,
        "failureSignatures": failures.most_common(20),
    }
    report_path = root / "results.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps({
        "best": best,
        "validCount": len(valid_results),
        "tested": tested,
        "topValid": valid_results[:10],
        "topFailures": failures.most_common(10),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
