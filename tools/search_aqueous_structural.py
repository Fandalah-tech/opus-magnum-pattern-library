from __future__ import annotations

import argparse
import base64
import copy
import json
from itertools import combinations, product
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes

DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
STATION_TYPES = {"input", "out-std", "bonder", "bonder-speed", "glyph-calcification"}
ROTATABLE_TYPES = {"input", "out-std", "bonder", "bonder-speed"}
PROGRAM_ACTIONS = ("grab", "drop", "rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw")


def load_reference(path: Path) -> dict:
    return parse_solution_bytes(base64.b64decode(path.read_text().strip()), source_name="aqueous-coupled-parent.solution")


def clean(solution: dict, name: str) -> dict:
    candidate = copy.deepcopy(solution)
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    candidate["name"] = name
    return candidate


def legal_program(program: list[dict]) -> bool:
    cycles = [int(item.get("cycle", 0)) for item in program]
    return min(cycles, default=0) >= 0 and len(cycles) == len(set(cycles))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ref = load_reference(Path(args.fixture))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    parts = ref.get("parts") or []
    arms = [i for i, p in enumerate(parts) if p.get("type") in ARM_TYPES]
    stations = [i for i, p in enumerate(parts) if p.get("type") in STATION_TYPES]
    rot_stations = [i for i in stations if parts[i].get("type") in ROTATABLE_TYPES]

    variants: list[tuple[dict, dict]] = []
    seen: set[bytes] = set()

    def add(candidate: dict | None, meta: dict) -> None:
        if candidate is None:
            return
        payload = write_solution_bytes(candidate)
        if payload in seen:
            return
        seen.add(payload)
        variants.append((candidate, meta))

    def move(candidate: dict, index: int, direction: tuple[int, int]) -> None:
        q, r = candidate["parts"][index].get("position") or (0, 0)
        candidate["parts"][index]["position"] = [q + direction[0], r + direction[1]]

    # A. Second-order timing moves. A one-instruction intermediate can collide,
    # while two simultaneous changes can remain a valid full solution.
    timed: list[tuple[int, int]] = []
    for pi in arms:
        for ii, _ in enumerate(parts[pi].get("program") or []):
            timed.append((pi, ii))
    for (pa, ia), (pb, ib) in combinations(timed, 2):
        for da, db in product((-2, -1, 1, 2), repeat=2):
            candidate = clean(ref, "paired timing jump")
            candidate["parts"][pa]["program"][ia]["cycle"] += da
            candidate["parts"][pb]["program"][ib]["cycle"] += db
            if legal_program(candidate["parts"][pa].get("program") or []) and legal_program(candidate["parts"][pb].get("program") or []):
                add(candidate, {"kind": "paired-timing-jump", "a": [pa, ia, da], "b": [pb, ib, db]})

    # B. Instruction semantic jumps. Rotate/pivot was already searched heavily;
    # also permit direction reversals in one step, optionally compensated by a
    # base rotation of the same arm.
    replacement = {
        "rotate_cw": ("rotate_ccw", "pivot_cw", "pivot_ccw"),
        "rotate_ccw": ("rotate_cw", "pivot_cw", "pivot_ccw"),
        "pivot_cw": ("pivot_ccw", "rotate_cw", "rotate_ccw"),
        "pivot_ccw": ("pivot_cw", "rotate_cw", "rotate_ccw"),
    }
    for pi in arms:
        base_rot = int(parts[pi].get("rotation") or 0) % 6
        for ii, item in enumerate(parts[pi].get("program") or []):
            old = str(item.get("instruction") or "")
            for new in replacement.get(old, ()):
                candidate = clean(ref, "action semantic jump")
                candidate["parts"][pi]["program"][ii]["instruction"] = new
                add(candidate, {"kind": "action-jump", "part": pi, "instruction": ii, "from": old, "to": new})
                for drot in (-1, 1):
                    candidate = clean(ref, "action plus base rotation")
                    candidate["parts"][pi]["program"][ii]["instruction"] = new
                    candidate["parts"][pi]["rotation"] = (base_rot + drot) % 6
                    add(candidate, {"kind": "action-base-coupled", "part": pi, "instruction": ii, "to": new, "baseDelta": drot})

    # C. Coupled arm + station relocation. Directions are intentionally
    # independent: this crosses invalid single-move intermediates and changes
    # reach/handoff geometry in one validatable state.
    for ai in arms:
        for si in stations:
            if ai == si:
                continue
            for da, ds in product(DIRECTIONS, repeat=2):
                candidate = clean(ref, "coupled arm station move")
                move(candidate, ai, da)
                move(candidate, si, ds)
                add(candidate, {"kind": "arm-station-coupled", "arm": ai, "station": si, "armDelta": list(da), "stationDelta": list(ds)})

    # D. Coupled arm/arm geometry, including independent base moves and small
    # rotations. This directly changes handoff topology without requiring either
    # intermediate arm placement to solve the puzzle on its own.
    for a, b in combinations(arms, 2):
        for da, db in product(DIRECTIONS, repeat=2):
            candidate = clean(ref, "coupled two arm move")
            move(candidate, a, da)
            move(candidate, b, db)
            add(candidate, {"kind": "two-arm-coupled", "arms": [a, b], "deltas": [list(da), list(db)]})
        for ra, rb in product((-1, 1), repeat=2):
            candidate = clean(ref, "coupled two arm rotate")
            candidate["parts"][a]["rotation"] = (int(parts[a].get("rotation") or 0) + ra) % 6
            candidate["parts"][b]["rotation"] = (int(parts[b].get("rotation") or 0) + rb) % 6
            add(candidate, {"kind": "two-arm-rotate", "arms": [a, b], "deltas": [ra, rb]})

    # E. Move a handoff module as a block: one arm plus two stations. This is
    # particularly useful for the input/calcification/bonder and bonder/output
    # modules in the 27c architecture.
    for ai in arms:
        for s1, s2 in combinations(stations, 2):
            for d in DIRECTIONS:
                candidate = clean(ref, "module block move")
                move(candidate, ai, d)
                move(candidate, s1, d)
                move(candidate, s2, d)
                add(candidate, {"kind": "module-translate", "arm": ai, "stations": [s1, s2], "delta": list(d)})

    # F. Station-pair independent relocation. Calcification/bonders frequently
    # need to move together; searching them one at a time can make all bridge
    # states invalid.
    for s1, s2 in combinations(stations, 2):
        for d1, d2 in product(DIRECTIONS, repeat=2):
            candidate = clean(ref, "two station coupled")
            move(candidate, s1, d1)
            move(candidate, s2, d2)
            add(candidate, {"kind": "two-station-coupled", "stations": [s1, s2], "deltas": [list(d1), list(d2)]})

    # G. Arm type/length jumps. Cost is irrelevant for the cycle objective, so
    # allow a different grabber geometry even when it is more expensive.
    for ai in arms:
        p = parts[ai]
        current_type = str(p.get("type") or "arm1")
        current_length = int(p.get("length") or 1)
        for new_type in ("arm1", "arm2", "arm3", "arm6", "piston"):
            if new_type == current_type:
                continue
            candidate = clean(ref, "arm type jump")
            candidate["parts"][ai]["type"] = new_type
            add(candidate, {"kind": "arm-type", "part": ai, "from": current_type, "to": new_type})
        for length in (1, 2, 3):
            if length == current_length:
                continue
            candidate = clean(ref, "arm direct length jump")
            candidate["parts"][ai]["length"] = length
            add(candidate, {"kind": "arm-length-direct", "part": ai, "length": length})
            for d in DIRECTIONS:
                candidate = clean(ref, "arm length move coupled")
                candidate["parts"][ai]["length"] = length
                move(candidate, ai, d)
                add(candidate, {"kind": "arm-length-move", "part": ai, "length": length, "delta": list(d)})

    # H. Extra helper arm, seeded from an existing four-instruction arm. A 26c
    # solution may need a fourth handoff even though the 27c seed uses three.
    # Clone locally with phase offsets so useful helpers can appear in one step.
    if len(arms) < 5:
        for src_index in arms:
            source = parts[src_index]
            q, r = source.get("position") or (0, 0)
            for d in DIRECTIONS:
                for drot in (-1, 0, 1):
                    for phase in (-1, 0, 1):
                        clone = copy.deepcopy(source)
                        clone["position"] = [q + d[0], r + d[1]]
                        clone["rotation"] = (int(source.get("rotation") or 0) + drot) % 6
                        for item in clone.get("program") or []:
                            item["cycle"] = int(item.get("cycle") or 0) + phase
                        if not legal_program(clone.get("program") or []):
                            continue
                        candidate = clean(ref, "cloned helper arm")
                        candidate["parts"].append(clone)
                        add(candidate, {"kind": "clone-helper-arm", "source": src_index, "delta": list(d), "rotationDelta": drot, "phase": phase})

    # I. If a helper arm already exists, program insertion/deletion lets the
    # graph repurpose it rather than remaining locked to the cloned program.
    if len(arms) >= 4:
        for ai in arms:
            program = parts[ai].get("program") or []
            occupied = {int(x.get("cycle") or 0) for x in program}
            max_cycle = max(occupied, default=6) + 2
            for cycle in range(0, min(max_cycle, 10) + 1):
                if cycle in occupied:
                    continue
                for action in PROGRAM_ACTIONS:
                    candidate = clean(ref, "insert helper instruction")
                    candidate["parts"][ai].setdefault("program", []).append({"cycle": cycle, "instruction": action})
                    candidate["parts"][ai]["program"] = sorted(candidate["parts"][ai]["program"], key=lambda x: int(x.get("cycle") or 0))
                    add(candidate, {"kind": "instruction-insert", "part": ai, "cycle": cycle, "action": action})
            if len(program) > 1:
                for ii in range(len(program)):
                    candidate = clean(ref, "delete helper instruction")
                    del candidate["parts"][ai]["program"][ii]
                    add(candidate, {"kind": "instruction-delete", "part": ai, "instruction": ii})

    # J. Rotatable stations may need a coordinated orientation change.
    for s1, s2 in combinations(rot_stations, 2):
        for d1, d2 in product((-1, 1), repeat=2):
            candidate = clean(ref, "two station rotate")
            candidate["parts"][s1]["rotation"] = (int(parts[s1].get("rotation") or 0) + d1) % 6
            candidate["parts"][s2]["rotation"] = (int(parts[s2].get("rotation") or 0) + d2) % 6
            add(candidate, {"kind": "two-station-rotate", "stations": [s1, s2], "deltas": [d1, d2]})

    manifest = []
    for number, (candidate, meta) in enumerate(variants):
        filename = f"variant-{number:05d}.solution"
        (out / filename).write_bytes(write_solution_bytes(candidate))
        manifest.append({"file": filename, **meta})

    payload = {
        "candidateCount": len(manifest),
        "armIndices": arms,
        "stationIndices": stations,
        "variants": manifest,
    }
    (out / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"candidateCount": len(manifest), "armIndices": arms, "stationIndices": stations}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
