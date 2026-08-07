from __future__ import annotations

import argparse
import base64
import copy
import json
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes


def load_reference(path: Path) -> dict:
    return parse_solution_bytes(
        base64.b64decode(path.read_text().strip()),
        source_name="aqueous-dagger-16c-reference.solution",
    )


def hex_disk(radius: int):
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= radius:
                yield q, r


def part(part_type: str, position, rotation: int, serial: int) -> dict:
    return {
        "id": f"search-glyph-{serial}",
        "type": part_type,
        "enabled": True,
        "position": list(position),
        "rotation": rotation,
        "length": 1,
        "which": 0,
        "armNumber": 0,
        "program": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger-16c-reference.solution.b64")
    parser.add_argument("--out", default="reports/aqueous-right-bonder-search")
    parser.add_argument("--radius", type=int, default=3)
    args = parser.parse_args()

    reference = load_reference(Path(args.fixture))
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    serial = 0

    # Existing right bonder is at (4,-3), rot1. Search additions/replacements locally.
    center = (4, -3)
    original_index = next(
        i for i, p in enumerate(reference["parts"])
        if p.get("type") == "bonder" and tuple(p.get("position") or ()) == center
    )

    for dq, dr in hex_disk(args.radius):
        pos = (center[0] + dq, center[1] + dr)
        for rotation in range(6):
            # Add a second standard bonder while keeping the original.
            candidate = copy.deepcopy(reference)
            candidate["metrics"] = {}
            candidate["unknownMetrics"] = []
            candidate["name"] = "Codex Aqueous extra right bonder"
            candidate["parts"].append(part("bonder", pos, rotation, serial))
            name = f"variant-{serial:04d}.solution"
            (root / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name, "kind": "add-bonder",
                "position": list(pos), "rotation": rotation,
            })
            serial += 1

            # Replace the original with a standard bonder elsewhere.
            candidate = copy.deepcopy(reference)
            candidate["metrics"] = {}
            candidate["unknownMetrics"] = []
            candidate["name"] = "Codex Aqueous move right bonder"
            candidate["parts"][original_index]["position"] = list(pos)
            candidate["parts"][original_index]["rotation"] = rotation
            name = f"variant-{serial:04d}.solution"
            (root / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name, "kind": "move-bonder",
                "position": list(pos), "rotation": rotation,
            })
            serial += 1

            # Replace original standard bonder with multibonder at each local pose.
            candidate = copy.deepcopy(reference)
            candidate["metrics"] = {}
            candidate["unknownMetrics"] = []
            candidate["name"] = "Codex Aqueous right multibonder"
            candidate["parts"][original_index]["type"] = "bonder-speed"
            candidate["parts"][original_index]["position"] = list(pos)
            candidate["parts"][original_index]["rotation"] = rotation
            name = f"variant-{serial:04d}.solution"
            (root / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name, "kind": "replace-multibonder",
                "position": list(pos), "rotation": rotation,
            })
            serial += 1

            # Add a multibonder as an extra glyph while retaining original.
            candidate = copy.deepcopy(reference)
            candidate["metrics"] = {}
            candidate["unknownMetrics"] = []
            candidate["name"] = "Codex Aqueous extra right multibonder"
            candidate["parts"].append(part("bonder-speed", pos, rotation, serial))
            name = f"variant-{serial:04d}.solution"
            (root / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name, "kind": "add-multibonder",
                "position": list(pos), "rotation": rotation,
            })
            serial += 1

    (root / "manifest.json").write_text(json.dumps({
        "referenceMetrics": reference.get("metrics"),
        "originalBonderIndex": original_index,
        "candidateCount": serial,
        "variants": manifest,
    }, indent=2))
    print(f"generated {serial} right-bonder variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
