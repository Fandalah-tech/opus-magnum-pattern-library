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
PROGRAM_ACTIONS = (
    "grab", "drop", "rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw",
    "track_plus", "track_minus", "extend", "retract",
)
MOTION_ACTIONS = {"rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw", "track_plus", "track_minus", "extend", "retract"}


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

    # B. Instruction semantic jumps.
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

    # C. Coupled arm + station relocation.
    for ai in arms:
        for si in stations:
            if ai == si:
                continue
            for da, ds in product(DIRECTIONS, repeat=2):
                candidate = clean(ref, "coupled arm station move")
                move(candidate, ai, da)
                move(candidate, si, ds)
                add(candidate, {"kind": "arm-station-coupled", "arm": ai, "station": si, "armDelta": list(da), "stationDelta": list(ds)})

    # D. Coupled arm/arm geometry.
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

    # E. Move a handoff module as a block.
    for ai in arms:
        for s1, s2 in combinations(stations, 2):
            for d in DIRECTIONS:
                candidate = clean(ref, "module block move")
                move(candidate, ai, d)
                move(candidate, s1, d)
                move(candidate, s2, d)
                add(candidate, {"kind": "module-translate", "arm": ai, "stations": [s1, s2], "delta": list(d)})

    # F. Station-pair independent relocation.
    for s1, s2 in combinations(stations, 2):
        for d1, d2 in product(DIRECTIONS, repeat=2):
            candidate = clean(ref, "two station coupled")
            move(candidate, s1, d1)
            move(candidate, s2, d2)
            add(candidate, {"kind": "two-station-coupled", "stations": [s1, s2], "deltas": [list(d1), list(d2)]})

    # G. Arm type/length jumps.
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

    # H. Extra helper arm.
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

    # I. Program insertion/deletion for helper-rich mechanisms.
    if len(arms) >= 4:
        for ai in arms:
            program = parts[ai].get("program") or []
            occupied = {int(x.get("cycle") or 0) for x in program}
            max_cycle = max(occupied, default=6) + 2
            for cycle in range(0, min(max_cycle, 10) + 1):
                if cycle in occupied:
                    continue
                for action in PROGRAM_ACTIONS:
                    if action in {"track_plus", "track_minus"} and not any(p.get("type") == "track" for p in parts):
                        continue
                    if action in {"extend", "retract"} and parts[ai].get("type") != "piston":
                        continue
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

    # K. Direct single-arm geometry. Earlier searches mostly reached these states
    # only through coupled mutations; emit them explicitly and combine base move,
    # rotation and length to cross invalid one-dimensional intermediates.
    for ai in arms:
        base_rot = int(parts[ai].get("rotation") or 0) % 6
        base_len = int(parts[ai].get("length") or 1)
        for d in DIRECTIONS:
            candidate = clean(ref, "single arm base move")
            move(candidate, ai, d)
            add(candidate, {"kind": "arm-base-move", "part": ai, "delta": list(d)})
            for drot in (-2, -1, 1, 2, 3):
                candidate = clean(ref, "arm move rotation coupled")
                move(candidate, ai, d)
                candidate["parts"][ai]["rotation"] = (base_rot + drot) % 6
                add(candidate, {"kind": "arm-move-rotate", "part": ai, "delta": list(d), "rotationDelta": drot})
        for drot in (-2, -1, 1, 2, 3):
            candidate = clean(ref, "single arm base rotate")
            candidate["parts"][ai]["rotation"] = (base_rot + drot) % 6
            add(candidate, {"kind": "arm-base-rotate", "part": ai, "rotationDelta": drot})
            for length in (1, 2, 3):
                if length == base_len:
                    continue
                candidate = clean(ref, "arm rotation length coupled")
                candidate["parts"][ai]["rotation"] = (base_rot + drot) % 6
                candidate["parts"][ai]["length"] = length
                add(candidate, {"kind": "arm-rotate-length", "part": ai, "rotationDelta": drot, "length": length})

    # L. Controlled later timing moves. These include larger jumps, whole-arm
    # phase shifts and suffix shifts; all preserve a legal one-action-per-cycle tape.
    for ai in arms:
        program = parts[ai].get("program") or []
        for ii, item in enumerate(program):
            for delta in (-4, -3, 3, 4):
                candidate = clean(ref, "direct later timing jump")
                candidate["parts"][ai]["program"][ii]["cycle"] = int(item.get("cycle") or 0) + delta
                if legal_program(candidate["parts"][ai].get("program") or []):
                    add(candidate, {"kind": "timing-direct-wide", "part": ai, "instruction": ii, "delta": delta})
        for phase in (-4, -3, -2, -1, 1, 2, 3, 4):
            candidate = clean(ref, "whole arm phase shift")
            for item in candidate["parts"][ai].get("program") or []:
                item["cycle"] = int(item.get("cycle") or 0) + phase
            if legal_program(candidate["parts"][ai].get("program") or []):
                add(candidate, {"kind": "arm-phase", "part": ai, "delta": phase})
        for start in range(1, len(program)):
            for delta in (-2, -1, 1, 2):
                candidate = clean(ref, "program suffix shift")
                for item in candidate["parts"][ai]["program"][start:]:
                    item["cycle"] = int(item.get("cycle") or 0) + delta
                if legal_program(candidate["parts"][ai].get("program") or []):
                    add(candidate, {"kind": "timing-suffix", "part": ai, "start": start, "delta": delta})

    # M. Pivot/rotation topology with timing compensation. A semantic action
    # change can require an adjacent schedule change to avoid a transient collision.
    for ai in arms:
        program = parts[ai].get("program") or []
        occupied = {int(x.get("cycle") or 0) for x in program}
        for ii, item in enumerate(program):
            old = str(item.get("instruction") or "")
            for new in replacement.get(old, ()):
                for delta in (-2, -1, 1, 2):
                    candidate = clean(ref, "action timing coupled")
                    candidate["parts"][ai]["program"][ii]["instruction"] = new
                    if ii + 1 < len(program):
                        candidate["parts"][ai]["program"][ii + 1]["cycle"] = int(program[ii + 1].get("cycle") or 0) + delta
                    else:
                        candidate["parts"][ai]["program"][ii]["cycle"] = int(item.get("cycle") or 0) + delta
                    if legal_program(candidate["parts"][ai].get("program") or []):
                        add(candidate, {"kind": "action-timing-coupled", "part": ai, "instruction": ii, "to": new, "delta": delta})
        # Insert a pivot in an unoccupied nearby slot on any arm, not only helper-rich states.
        max_cycle = min(max(occupied, default=6) + 2, 12)
        for cycle in range(0, max_cycle + 1):
            if cycle in occupied:
                continue
            for action in ("pivot_cw", "pivot_ccw"):
                candidate = clean(ref, "pivot insertion")
                candidate["parts"][ai].setdefault("program", []).append({"cycle": cycle, "instruction": action})
                candidate["parts"][ai]["program"] = sorted(candidate["parts"][ai]["program"], key=lambda x: int(x.get("cycle") or 0))
                add(candidate, {"kind": "pivot-insert", "part": ai, "cycle": cycle, "action": action})

    # N. Short track bridges. Add a two-cell track through an arm base and replace
    # one or two motion instructions with a track excursion. This creates a new
    # translational degree of freedom that cannot be reached by arm/station moves.
    if not any(p.get("type") == "track" for p in parts):
        for ai in arms:
            q, r = map(int, parts[ai].get("position") or (0, 0))
            program = parts[ai].get("program") or []
            motion_slots = [ii for ii, item in enumerate(program) if str(item.get("instruction") or "") in MOTION_ACTIONS]
            for d in DIRECTIONS:
                nq, nr = q + d[0], r + d[1]
                for direction_name, cells, outbound, inbound in (
                    ("plus", [[q, r], [nq, nr]], "track_plus", "track_minus"),
                    ("minus", [[nq, nr], [q, r]], "track_minus", "track_plus"),
                ):
                    track = {
                        "type": "track", "enabled": True, "position": [q, r], "length": 1,
                        "rotation": 0, "which": 0, "program": [], "trackHexes": cells, "armNumber": 0,
                    }
                    for ii in motion_slots:
                        candidate = clean(ref, "single track bridge")
                        candidate["parts"].append(copy.deepcopy(track))
                        candidate["parts"][ai]["program"][ii]["instruction"] = outbound
                        add(candidate, {"kind": "track-bridge", "part": ai, "instruction": ii, "delta": list(d), "direction": direction_name})
                    for ia, ib in combinations(motion_slots, 2):
                        candidate = clean(ref, "track round trip")
                        candidate["parts"].append(copy.deepcopy(track))
                        candidate["parts"][ai]["program"][ia]["instruction"] = outbound
                        candidate["parts"][ai]["program"][ib]["instruction"] = inbound
                        add(candidate, {"kind": "track-roundtrip", "part": ai, "instructions": [ia, ib], "delta": list(d), "direction": direction_name})

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
