from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution


def _summary(document: dict) -> dict:
    kind = document["format"]["kind"]
    if kind == "puzzle":
        return {
            "kind": kind,
            "file": document["source"]["name"],
            "name": document["name"],
            "version": document["format"]["version"],
            "sha256": document["source"]["sha256"],
            "size": document["source"]["size"],
            "reagents": len(document["reagents"]),
            "products": len(document["products"]),
            "production": document["production"],
            "trailingBytes": document["trailingBytes"],
        }

    part_types: dict[str, int] = {}
    serialized_instructions = 0
    for part in document["parts"]:
        part_types[part["type"]] = part_types.get(part["type"], 0) + 1
        serialized_instructions += len(part["program"])

    return {
        "kind": kind,
        "file": document["source"]["name"],
        "name": document["name"],
        "puzzleFile": document["puzzleFile"],
        "version": document["format"]["version"],
        "sha256": document["source"]["sha256"],
        "size": document["source"]["size"],
        "metrics": document["metrics"],
        "parts": len(document["parts"]),
        "partTypes": dict(sorted(part_types.items())),
        "serializedInstructionEntries": serialized_instructions,
        "trailingBytes": document["trailingBytes"],
    }


def inspect(path: Path, full: bool) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".puzzle":
        document = parse_puzzle(path)
    elif suffix == ".solution":
        document = parse_solution(path)
    else:
        raise ValueError(f"Unsupported file extension: {path.suffix}")
    return document if full else _summary(document)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Opus Magnum puzzle and solution files")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--full", action="store_true", help="Emit the complete canonical representation")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    results = []
    failed = False
    for path in args.paths:
        try:
            results.append({"ok": True, "result": inspect(path, args.full)})
        except Exception as exc:  # CLI boundary: preserve all per-file failures in JSON.
            failed = True
            results.append({"ok": False, "file": str(path), "error": str(exc)})

    payload = results[0] if len(results) == 1 else results
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
