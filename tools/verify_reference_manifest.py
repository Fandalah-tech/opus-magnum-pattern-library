from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_file(root: Path, expected: dict, kind: str) -> list[str]:
    path = root / expected["file"]
    errors: list[str] = []
    if not path.exists():
        return [f"missing {kind}: {path}"]
    if path.stat().st_size != expected["size"]:
        errors.append(f"{path.name}: size mismatch")
    if _sha256(path) != expected["sha256"]:
        errors.append(f"{path.name}: SHA-256 mismatch")

    parsed = parse_puzzle(path) if kind == "puzzle" else parse_solution(path)
    if parsed["format"]["version"] != expected["version"]:
        errors.append(f"{path.name}: version mismatch")
    if parsed["trailingBytes"] != 0:
        errors.append(f"{path.name}: {parsed['trailingBytes']} trailing bytes")

    if kind == "puzzle":
        if parsed["name"] != expected["name"]:
            errors.append(f"{path.name}: puzzle name mismatch")
    else:
        if parsed["puzzleFile"] != expected["puzzleFile"]:
            errors.append(f"{path.name}: puzzle reference mismatch")
        for metric, value in expected["metrics"].items():
            if parsed["metrics"].get(metric) != value:
                errors.append(f"{path.name}: metric {metric} mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify locally supplied Opus Magnum fixtures against a metadata-only manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("fixture_directory", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors: list[str] = []
    checked = 0
    for pair in manifest["pairs"]:
        errors.extend(_check_file(args.fixture_directory, pair["puzzle"], "puzzle"))
        errors.extend(_check_file(args.fixture_directory, pair["solution"], "solution"))
        checked += 1

    print(json.dumps({"valid": not errors, "pairsChecked": checked, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
