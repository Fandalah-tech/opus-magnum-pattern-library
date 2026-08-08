from __future__ import annotations

import argparse
import base64
import copy
import json
from itertools import combinations
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes

CENTRAL_ARMS = (7, 8, 11, 12)
FEED_ARMS = (1, 2, 15, 16)


def load_reference(path: Path) -> dict:
    raw = base64.b64decode(path.read_text().strip())
    return parse_solution_bytes(raw, source_name="aqueous-dagger-16c-reference.solution")


def clean(solution: dict, name: str) -> dict:
    candidate = copy.deepcopy(solution)
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    candidate["name"] = name
    return candidate


def legal_program(program: list[dict]) -> bool:
    cycles = [int(item.get("cycle", 0)) for item in program]
    return min(cycles, default=0) >= 0 and len(cycles) == len(set(cycles))


def shift_suffix(reference: dict, part_index: int, start: int) -> dict | None:
    candidate = clean(reference, f"Codex structural suffix p{part_index} s{start}")
    program = candidate["parts"][part_index].get("program") or []
    for item in program[start:]:
        item["cycle"] = int(item.get("cycle", 0)) - 1
    return candidate if legal_program(program) else None


def shift_instruction(reference: dict, part_index: int, instruction_index: int) -> dict | None:
    candidate = clean(reference, f"Codex structural tick p{part_index} i{instruction_index}")
    program = candidate["parts"][part_index].get("program") or []
    program[instruction_index]["cycle"] = int(program[instruction_index].get("cycle", 0)) - 1
    return candidate if legal_program(program) else None


def substitute(reference: dict, part_index: int, instruction_index: int, action: str) -> dict:
    candidate = clean(reference, f"Codex structural action p{part_index} i{instruction_index} {action}")
    candidate["parts"][part_index]["program"][instruction_index]["instruction"] = action
    return candidate


def mutate_pair(reference: dict, mutations: tuple[tuple[int, int], ...]) -> dict | None:
    candidate = clean(reference, "Codex structural paired ticks")
    for part_index, instruction_index in mutations:
        program = candidate["parts"][part_index].get("program") or []
        program[instruction_index]["cycle"] = int(program[instruction_index].get("cycle", 0)) - 1
    if all(legal_program(candidate["parts"][part].get("program") or []) for part, _ in mutations):
        return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger-16c-reference.solution.b64")
    parser.add_argument("--out", default="reports/aqueous-structural-search")
    args = parser.parse_args()

    reference = load_reference(Path(args.fixture))
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    variants: list[tuple[dict, dict]] = []
    seen: set[bytes] = set()

    def add(candidate: dict | None, meta: dict) -> None:
        if candidate is None:
            return
        encoded = write_solution_bytes(candidate)
        if encoded in seen:
            return
        seen.add(encoded)
        variants.append((candidate, meta))

    # 1) Compress every possible suffix on the four central handoff arms.
    for part_index in CENTRAL_ARMS:
        program = reference["parts"][part_index].get("program") or []
        for start in range(len(program)):
            add(shift_suffix(reference, part_index, start), {
                "kind": "suffix-earlier", "part": part_index, "start": start,
            })

    # 2) Pull individual instructions one cycle earlier on central and feed arms.
    legal_single_ticks: list[tuple[int, int]] = []
    for part_index in CENTRAL_ARMS + FEED_ARMS:
        program = reference["parts"][part_index].get("program") or []
        for instruction_index, item in enumerate(program):
            if int(item.get("cycle", 0)) <= 0:
                continue
            candidate = shift_instruction(reference, part_index, instruction_index)
            if candidate is not None:
                legal_single_ticks.append((part_index, instruction_index))
                add(candidate, {
                    "kind": "tick-earlier", "part": part_index, "instruction": instruction_index,
                })

    # 3) Pair central single-tick compressions. 15c may require both sides of a handoff to move together.
    central_ticks = [m for m in legal_single_ticks if m[0] in CENTRAL_ARMS]
    for first, second in combinations(central_ticks, 2):
        add(mutate_pair(reference, (first, second)), {
            "kind": "paired-ticks", "mutations": [list(first), list(second)],
        })

    # 4) Convert rotate <-> pivot in place. The geometry changes, but this catches the late pivot trick
    # that previously unlocked A41 without assuming which handoff needs it.
    replacements = {
        "rotate_cw": "pivot_cw", "rotate_ccw": "pivot_ccw",
        "pivot_cw": "rotate_cw", "pivot_ccw": "rotate_ccw",
    }
    for part_index in CENTRAL_ARMS:
        program = reference["parts"][part_index].get("program") or []
        for instruction_index, item in enumerate(program):
            old = str(item.get("instruction") or "")
            if old in replacements:
                add(substitute(reference, part_index, instruction_index, replacements[old]), {
                    "kind": "rotate-pivot", "part": part_index,
                    "instruction": instruction_index, "from": old, "to": replacements[old],
                })

    # 5) Combine one legal timing pull with one rotate/pivot substitution on the same central arm.
    for part_index in CENTRAL_ARMS:
        program = reference["parts"][part_index].get("program") or []
        timing_indices = [i for p, i in central_ticks if p == part_index]
        action_indices = [i for i, item in enumerate(program) if str(item.get("instruction") or "") in replacements]
        for timing_index in timing_indices:
            for action_index in action_indices:
                candidate = shift_instruction(reference, part_index, timing_index)
                if candidate is None:
                    continue
                old = str(candidate["parts"][part_index]["program"][action_index].get("instruction") or "")
                if old not in replacements:
                    continue
                candidate["parts"][part_index]["program"][action_index]["instruction"] = replacements[old]
                add(candidate, {
                    "kind": "timing-plus-pivot", "part": part_index,
                    "timingInstruction": timing_index, "actionInstruction": action_index,
                    "from": old, "to": replacements[old],
                })

    manifest = []
    for serial, (candidate, meta) in enumerate(variants):
        name = f"variant-{serial:04d}.solution"
        (output / name).write_bytes(write_solution_bytes(candidate))
        manifest.append({"file": name, **meta})

    (output / "manifest.json").write_text(json.dumps({
        "referenceMetrics": reference.get("metrics"),
        "candidateCount": len(manifest),
        "variants": manifest,
    }, indent=2))
    print(f"generated {len(manifest)} structural variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
