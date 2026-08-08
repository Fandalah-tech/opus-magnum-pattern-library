from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


def validate(url: str, puzzle: Path, solution: Path) -> dict:
    command = [
        "curl", "--fail-with-body", "-sS",
        "--connect-timeout", "5",
        "--max-time", "20",
        "--retry", "1",
        "--retry-delay", "1",
        "--retry-connrefused",
        "-F", f"puzzle=@{puzzle}",
        "-F", f"solution=@{solution}",
        f"{url}/api/v1/validate",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        return {
            "httpError": "validator timeout after 25s",
            "valid": False,
            "issues": [{"message": "validator timeout"}],
        }
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if result.returncode == 28:
            stderr = stderr or "validator curl timeout"
        return {
            "httpError": stderr,
            "valid": False,
            "issues": [{"message": stderr or f"curl exit {result.returncode}"}],
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "httpError": f"invalid validator JSON: {exc}",
            "issues": [{"message": "invalid validator JSON"}],
        }
    # /api/v1/validate is OMSim-only and returns the validation object directly.
    if isinstance(payload, dict) and "valid" in payload:
        return payload
    # Backward-compatible fallback if a deployment ever wraps the validation.
    if isinstance(payload, dict):
        return payload.get("validation", {})
    return {"valid": False, "issues": [{"message": "unexpected validator payload"}]}


def issue_signature(validation: dict) -> str:
    issues = validation.get("issues") or []
    if not issues:
        return str(validation.get("status") or "unknown")
    message = str(issues[0].get("message") or issues[0].get("code") or "issue")
    return message.splitlines()[-1][:180]


def publish_status(*, repo: str | None, branch: str | None, path: str, token: str | None, payload: dict) -> None:
    if not repo or not branch or not token:
        return
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    api = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "opus-magnum-codex-dashboard",
    }
    sha = None
    try:
        req = urllib.request.Request(f"{api}?ref={urllib.parse.quote(branch, safe='')}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            current = json.loads(response.read().decode("utf-8"))
            sha = current.get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            print(f"DASHBOARD WARN get status failed: HTTP {exc.code}", flush=True)
            return
    body = {
        "message": "Update Aqueous live solver status",
        "content": base64.b64encode((json.dumps(payload, indent=2) + "\n").encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    data = json.dumps(body).encode("utf-8")
    try:
        req = urllib.request.Request(api, data=data, headers={**headers, "Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req, timeout=20):
            pass
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"DASHBOARD WARN publish failed: HTTP {exc.code} {detail}", flush=True)
    except Exception as exc:
        print(f"DASHBOARD WARN publish failed: {exc}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator-url", required=True)
    parser.add_argument("--puzzle", default="reports/aqueous-dagger.puzzle")
    parser.add_argument("--variants", default="reports/aqueous-offset-search")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--live-repo")
    parser.add_argument("--live-branch")
    parser.add_argument("--live-path", default="aqueous-dashboard/status.json")
    parser.add_argument("--live-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--seed-cycles", type=int, default=27)
    parser.add_argument("--target-cycles", type=int, default=26)
    parser.add_argument("--generation", type=int, default=1)
    args = parser.parse_args()

    root = Path(args.variants)
    manifest = json.loads((root / "manifest.json").read_text())
    variant_meta = {item["file"]: item for item in manifest["variants"]}
    solutions = sorted(root.glob("variant-*.solution"))
    best = None
    best_cycles = args.seed_cycles
    valid_results = []
    failures = Counter()
    tested = 0
    total = len(solutions)
    token = os.environ.get(args.live_token_env)
    run_url = None
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
        run_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

    def dashboard(state: str) -> None:
        mutation = "seed" if best is None else str(best.get("kind") or "candidate")
        payload = {
            "puzzle": "Aqueous Dagger",
            "state": state,
            "seedCycles": args.seed_cycles,
            "targetCycles": args.target_cycles,
            "tested": tested,
            "total": total,
            "valid": len(valid_results),
            "bestCycles": best_cycles,
            "bestMutation": mutation,
            "generation": args.generation,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "runUrl": run_url,
        }
        publish_status(
            repo=args.live_repo,
            branch=args.live_branch,
            path=args.live_path,
            token=token,
            payload=payload,
        )

    print(f"SEARCH START candidates={total} workers={max(1, args.workers)} seed={args.seed_cycles} target={args.target_cycles}", flush=True)
    dashboard("running")

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
                if cycles is not None and (best is None or cycles < best_cycles):
                    best = record
                    best_cycles = int(cycles)
                    shutil.copy2(solution, root / "best.solution")
                    print("NEW BEST", json.dumps(best, sort_keys=True), flush=True)
                    dashboard("target_reached" if best_cycles <= args.target_cycles else "running")
            else:
                failures[issue_signature(validation)] += 1

            if tested % max(1, args.progress_every) == 0 or tested == total:
                print(
                    f"PROGRESS tested={tested}/{total} valid={len(valid_results)} best_cycles={best_cycles}",
                    flush=True,
                )
                dashboard("target_reached" if best_cycles <= args.target_cycles else "running")

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
        "bestCycles": best_cycles,
        "failureSignatures": failures.most_common(20),
    }
    report_path = root / "results.json"
    report_path.write_text(json.dumps(report, indent=2))
    dashboard("target_reached" if best_cycles <= args.target_cycles else "completed")
    print(json.dumps({
        "best": best,
        "bestCycles": best_cycles,
        "validCount": len(valid_results),
        "tested": tested,
        "topValid": valid_results[:10],
        "topFailures": failures.most_common(10),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
