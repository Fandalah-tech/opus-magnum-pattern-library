from __future__ import annotations

import argparse
import base64
import copy
import json
from itertools import combinations
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes


def load_reference(path: Path) -> dict:
    raw = base64.b64decode(path.read_text().strip())
    return parse_solution_bytes(raw, source_name="aqueous-dagger-16c-reference.solution")


def arm_candidates(solution: dict) -> list[int]:
    result = []
    for index, part in enumerate(solution.get("parts") or []):
        program = list(part.get("program") or [])
        if not program:
            continue
        minimum = min(int(item.get("cycle", 0)) for item in program)
        if minimum > 0:
            result.append(index)
    return result


def shifted(solution: dict, selected: set[int]) -> dict:
    candidate = copy.deepcopy(solution)
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    candidate["name"] = "Codex Aqueous 16c offset search"
    for index in selected:
        for item in candidate["parts"][index].get("program") or []:
            item["cycle"] = int(item.get("cycle", 0)) - 1
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger-16c-reference.solution.b64")
    parser.add_argument("--out", default="reports/aqueous-offset-search")
    args = parser.parse_args()

    reference = load_reference(Path(args.fixture))
    movable = arm_candidates(reference)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    manifest = []
    serial = 0
    # Test every non-empty subset of independently-started programs one cycle earlier.
    # The current reference has seven such programs => 127 candidates.
    for size in range(1, len(movable) + 1):
        for combo in combinations(movable, size):
            selected = set(combo)
            candidate = shifted(reference, selected)
            name = f"variant-{serial:03d}.solution"
            (output / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name,
                "shiftedPartIndices": list(combo),
                "shiftedArmNumbers": [candidate["parts"][i].get("armNumber") for i in combo],
            })
            serial += 1

    (output / "manifest.json").write_text(json.dumps({
        "referenceMetrics": reference.get("metrics"),
        "movablePartIndices": movable,
        "candidateCount": serial,
        "variants": manifest,
    }, indent=2))
    print(f"generated {serial} variants from movable parts {movable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
