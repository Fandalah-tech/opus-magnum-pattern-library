from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def multipart(puzzle: Path, solution: Path) -> tuple[bytes, str]:
    boundary = "----opus-codex-regression"
    chunks: list[bytes] = []
    for field, path in (("puzzle", puzzle), ("solution", solution)):
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            path.read_bytes(),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def post_pair(url: str, endpoint: str, puzzle: Path, solution: Path) -> dict:
    body, boundary = multipart(puzzle, solution)
    request = urllib.request.Request(
        f"{url.rstrip('/')}{endpoint}",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{endpoint} returned HTTP {exc.code}: {payload}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--validator-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = []
    failed = False
    classifications: Counter[str] = Counter()

    for pair in manifest["pairs"]:
        puzzle_meta = pair["puzzle"]
        solution_meta = pair["solution"]
        puzzle_path = args.fixtures / puzzle_meta["file"]
        solution_path = args.fixtures / solution_meta["file"]
        errors: list[str] = []
        local = None
        remote = None
        engine = None

        for path, expected in ((puzzle_path, puzzle_meta), (solution_path, solution_meta)):
            if not path.exists():
                errors.append(f"missing file: {path.name}")
                continue
            if path.stat().st_size != expected["size"]:
                errors.append(f"size mismatch: {path.name}")
            if sha256(path) != expected["sha256"]:
                errors.append(f"sha256 mismatch: {path.name}")

        if not errors:
            puzzle = parse_puzzle(puzzle_path)
            solution = parse_solution(solution_path)
            local = {
                "puzzleName": puzzle["name"],
                "puzzleTrailingBytes": puzzle["trailingBytes"],
                "solutionTrailingBytes": solution["trailingBytes"],
                "puzzleFile": solution["puzzleFile"],
                "metrics": solution["metrics"],
            }
            if puzzle["name"] != puzzle_meta["name"]:
                errors.append("puzzle name mismatch")
            if solution["puzzleFile"] != solution_meta["puzzleFile"]:
                errors.append("solution puzzle reference mismatch")
            if solution["metrics"] != solution_meta["metrics"]:
                errors.append("embedded metric mismatch")
            if puzzle["trailingBytes"] != pair["parserChecks"]["puzzleTrailingBytes"]:
                errors.append("puzzle trailing-byte mismatch")
            if solution["trailingBytes"] != pair["parserChecks"]["solutionTrailingBytes"]:
                errors.append("solution trailing-byte mismatch")

        if not errors:
            try:
                remote = post_pair(args.validator_url, "/validate", puzzle_path, solution_path)
                if not remote.get("valid"):
                    errors.append("omsim rejected solution")
                remote_metrics = remote.get("metrics", {})
                for key, expected in solution_meta["metrics"].items():
                    actual = remote_metrics.get(key)
                    if actual is not None and actual != expected:
                        errors.append(f"remote metric mismatch for {key}: {actual} != {expected}")
            except Exception as exc:
                errors.append(str(exc))

        if not errors:
            try:
                engine = post_pair(args.validator_url, "/api/v1/engine/compare", puzzle_path, solution_path)
                status = str(engine.get("status") or "unknown")
                if status == "diverged":
                    classification = engine.get("firstDivergence", {}).get("classification", {})
                    classifications[str(classification.get("subsystem") or "unclassified")] += 1
                elif status == "engine-error":
                    classifications["engine-error"] += 1
                elif status == "match":
                    classifications["match"] += 1
                else:
                    classifications["unknown"] += 1
            except Exception as exc:
                errors.append(f"engine comparison failed: {exc}")

        if errors:
            failed = True
        results.append({
            "puzzle": puzzle_meta["file"],
            "solution": solution_meta["file"],
            "passed": not errors,
            "errors": errors,
            "local": local,
            "remote": remote,
            "engineComparison": engine,
        })

    report = {
        "schemaVersion": "0.2.0",
        "manifest": manifest["id"],
        "validatorUrl": args.validator_url,
        "summary": {
            "total": len(results),
            "passed": sum(1 for item in results if item["passed"]),
            "failed": sum(1 for item in results if not item["passed"]),
            "engineClassifications": dict(sorted(classifications.items())),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
