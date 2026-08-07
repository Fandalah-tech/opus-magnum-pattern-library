from __future__ import annotations

import argparse
import json
import subprocess
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator-url", required=True)
    parser.add_argument("--puzzle", default="reports/aqueous-dagger.puzzle")
    parser.add_argument("--variants", default="reports/aqueous-offset-search")
    args = parser.parse_args()

    root = Path(args.variants)
    manifest = json.loads((root / "manifest.json").read_text())
    variant_meta = {item["file"]: item for item in manifest["variants"]}
    best = None
    valid_results = []

    for solution in sorted(root.glob("variant-*.solution")):
        validation = validate(args.validator_url, Path(args.puzzle), solution)
        metrics = validation.get("metrics") or {}
        if validation.get("valid") is True:
            record = {
                **variant_meta[solution.name],
                "metrics": metrics,
            }
            valid_results.append(record)
            cycles = metrics.get("cycles")
            if cycles is not None and (best is None or cycles < best["metrics"]["cycles"]):
                best = record
                print("NEW BEST", json.dumps(best, sort_keys=True))
            if cycles is not None and cycles <= 15:
                break

    report = {
        "candidateCount": manifest["candidateCount"],
        "tested": len(valid_results),
        "valid": valid_results,
        "best": best,
    }
    Path("reports/aqueous-offset-results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"best": best, "validCount": len(valid_results)}, indent=2))
    if best is None:
        raise SystemExit("no valid one-cycle offset variant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
