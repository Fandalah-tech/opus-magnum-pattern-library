from __future__ import annotations

from collections import Counter
from typing import Any

PERIOD_OVERRIDE = "period_override"
REPEAT = "repeat"
RESET = "reset"

ROTATE_CCW = "rotate_ccw"
ROTATE_CW = "rotate_cw"
EXTEND = "extend"
RETRACT = "retract"
TRACK_PLUS = "track_plus"
TRACK_MINUS = "track_minus"
GRAB = "grab"
DROP = "drop"

STANDARD_PRODUCT_TARGET = 6


def _absolute_tracks(solution: dict[str, Any]) -> list[tuple[tuple[int, int], ...]]:
    tracks: list[tuple[tuple[int, int], ...]] = []
    for part in solution.get("parts", []):
        if part.get("type") != "track" or not part.get("trackHexes"):
            continue
        origin = tuple(part.get("position") or (0, 0))
        tracks.append(tuple(
            (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
            for cell in part.get("trackHexes", [])
        ))
    return tracks


def _adjacent(first: tuple[int, int], second: tuple[int, int]) -> bool:
    delta = (second[0] - first[0], second[1] - first[1])
    return delta in {(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)}


def _owned_track(arm: dict[str, Any], tracks: list[tuple[tuple[int, int], ...]]) -> tuple[tuple[int, int], ...]:
    origin = tuple(arm.get("position") or (0, 0))
    return next((track for track in tracks if origin in track), tracks[0] if tracks else ())


def _set_tape(tape: list[dict[str, Any] | None], index: int, item: dict[str, Any]) -> None:
    while len(tape) <= index:
        tape.append(None)
    tape[index] = item


def _generated(source: dict[str, Any], instruction: str, generated_by: str) -> dict[str, Any]:
    return {
        "instruction": instruction,
        "rawCode": None,
        "generatedBy": generated_by,
        "sourceCycle": source.get("cycle"),
    }


def _track_next_index(
    track: tuple[tuple[int, int], ...],
    index: int,
    step: int,
    is_loop: bool,
) -> int:
    if not track:
        return index
    next_index = index + step
    if is_loop:
        return next_index % len(track)
    return max(0, min(len(track) - 1, next_index))


def _expand_arm_tape(
    arm: dict[str, Any],
    tracks: list[tuple[tuple[int, int], ...]],
) -> dict[str, Any]:
    """Decode one arm tape using the same reset rules as OMSim.

    A reset is not an instantaneous teleport. It expands into physical drop,
    piston, rotation and track instructions and can therefore lengthen the tape.
    """
    ordered = sorted(arm.get("program", []), key=lambda item: int(item.get("cycle", 0)))
    ordered = [item for item in ordered if item.get("instruction") != PERIOD_OVERRIDE]
    if not ordered:
        return {"start": 0, "tape": [], "sourceCount": 0}

    min_tape = int(ordered[0].get("cycle", 0))
    max_tape = int(ordered[-1].get("cycle", 0))
    tape: list[dict[str, Any] | None] = [None] * max(1, max_tape - min_tape + 1)
    last_end = 0
    last_repeat = 0
    reset_from = 0
    j = 0

    track = _owned_track(arm, tracks)
    base_position = tuple(arm.get("position") or (0, 0))
    base_track_index = track.index(base_position) if track and base_position in track else 0
    track_loop = len(track) >= 3 and _adjacent(track[-1], track[0])
    base_piston = max(1, int(arm.get("length") or 1))

    while j < len(ordered):
        item = ordered[j]
        instruction = str(item.get("instruction") or "")
        n = int(item.get("cycle", 0)) - min_tape

        if instruction == REPEAT:
            if last_repeat < -min_tape:
                last_repeat = -min_tape
            while j < len(ordered) and ordered[j].get("instruction") == REPEAT:
                repeat_n = int(ordered[j].get("cycle", 0)) - min_tape
                if last_end > last_repeat:
                    block = tape[last_repeat:last_end]
                    for offset, copied in enumerate(block):
                        if copied is not None:
                            clone = dict(copied)
                            clone["generatedBy"] = REPEAT
                            clone["sourceCycle"] = copied.get("sourceCycle", copied.get("cycle"))
                            _set_tape(tape, repeat_n + offset, clone)
                    last_end = max(last_end, repeat_n + len(block))
                j += 1
            if j < len(ordered):
                last_repeat = int(ordered[j].get("cycle", 0)) - min_tape
                reset_from = last_repeat
            continue

        if instruction == RESET:
            rotation = 0
            piston = base_piston
            grabbing = False
            track_index = base_track_index
            track_steps = 0
            track_looping_steps = 0

            for entry in tape[reset_from:n]:
                if entry is None:
                    continue
                action = entry.get("instruction")
                if action == ROTATE_CCW:
                    rotation += 1
                elif action == ROTATE_CW:
                    rotation -= 1
                elif action == EXTEND:
                    piston = min(3, piston + 1)
                elif action == RETRACT:
                    piston = max(1, piston - 1)
                elif action in {TRACK_PLUS, TRACK_MINUS} and track:
                    step = 1 if action == TRACK_PLUS else -1
                    next_index = _track_next_index(track, track_index, step, track_loop)
                    if next_index != track_index:
                        track_steps += step
                    track_index = next_index
                elif action == GRAB:
                    grabbing = True
                elif action == DROP:
                    grabbing = False

                if track and track_index == base_track_index:
                    track_looping_steps += track_steps
                    track_steps = 0

            cursor = n
            if grabbing:
                _set_tape(tape, cursor, _generated(item, DROP, RESET))
                cursor += 1
            while piston > base_piston:
                _set_tape(tape, cursor, _generated(item, RETRACT, RESET))
                piston -= 1
                cursor += 1

            while rotation > 3:
                rotation -= 6
            while rotation < -3:
                rotation += 6
            while rotation > 0:
                _set_tape(tape, cursor, _generated(item, ROTATE_CW, RESET))
                rotation -= 1
                cursor += 1
            while rotation < 0:
                _set_tape(tape, cursor, _generated(item, ROTATE_CCW, RESET))
                rotation += 1
                cursor += 1

            # OMSim preserves the signed path accumulated since reset_from and
            # only considers the opposite route around a loop within that search
            # depth. This also reproduces its tie-breaking behavior.
            if track and track_steps != 0:
                search_depth = abs(track_steps)
                direction = 1 if track_steps > 0 else -1
                if track_steps * (track_steps + track_looping_steps) < 0:
                    search_depth += 1
                probe_index = track_index
                for distance in range(search_depth):
                    if probe_index == base_track_index:
                        track_steps = -distance * direction
                        break
                    probe_index = _track_next_index(track, probe_index, direction, track_loop)

            while track_steps > 0:
                _set_tape(tape, cursor, _generated(item, TRACK_MINUS, RESET))
                track_steps -= 1
                cursor += 1
            while track_steps < 0:
                _set_tape(tape, cursor, _generated(item, TRACK_PLUS, RESET))
                track_steps += 1
                cursor += 1

            while piston < base_piston:
                _set_tape(tape, cursor, _generated(item, EXTEND, RESET))
                piston += 1
                cursor += 1

            # A no-op reset still occupies one tape cell.
            if cursor == n:
                cursor += 1
            reset_from = cursor
            last_end = max(last_end, cursor)
            j += 1
            continue

        copied = dict(item)
        copied["cycle"] = int(item.get("cycle", 0))
        _set_tape(tape, n, copied)
        last_end = max(last_end, n + 1)
        j += 1

    while tape and tape[-1] is None:
        tape.pop()
    return {"start": min_tape, "tape": tape, "sourceCount": len(ordered)}


def _validation_cycle_hint(solution: dict[str, Any], global_period: int) -> int | None:
    """Return an internal simulation horizon hint without changing file metrics.

    Generated candidates are deliberately serialized without guessed metrics.
    Some productive mechanisms nevertheless require several tape periods before
    six complete products emerge.  Their non-serialized generator provenance
    may therefore carry enough structural information to request a longer local
    replay while leaving the resulting `.solution` unscored.
    """
    source = solution.get("source") or {}
    explicit = source.get("validationCycleHint")
    if isinstance(explicit, int) and explicit > 0:
        return explicit

    rotary = source.get("rotarySingletonAccumulator")
    if isinstance(rotary, dict):
        atom_count = max(1, int(rotary.get("targetAtomCount") or 1))
        period = max(1, int(rotary.get("period") or global_period or 1))
        assembly_steps = max(1, atom_count - 1)
        # Six standard products, each requiring the complete target assembly,
        # plus one warm-up period.  This is intentionally a conservative local
        # validation horizon, not an asserted cycle score.
        return period * (STANDARD_PRODUCT_TARGET * assembly_steps + 1)
    return None


def build_program_timeline(solution: dict[str, Any], *, max_cycles: int | None = None) -> dict[str, Any]:
    """Build the physical, globally synchronized instruction timeline."""
    arms = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    tracks = _absolute_tracks(solution)
    decoded = [_expand_arm_tape(arm, tracks) for arm in arms]
    starts = [item["start"] for item in decoded if item["tape"]]
    global_start = min(starts, default=0)
    global_period = max((len(item["tape"]) for item in decoded), default=1)

    metric_declared_cycles = solution.get("metrics", {}).get("cycles")
    validation_cycle_hint = _validation_cycle_hint(solution, global_period)
    effective_declared_cycles = metric_declared_cycles or validation_cycle_hint
    default_horizon = max(int(effective_declared_cycles or 0), global_period, 1)
    horizon = max(1, int(max_cycles) if max_cycles is not None else default_horizon)

    cycles: list[dict[str, Any]] = []
    active_counts: Counter[int] = Counter()
    per_arm: list[dict[str, Any]] = []
    expanded_by_arm: dict[str, dict[int, list[dict[str, Any]]]] = {}

    for arm, decoded_arm in zip(arms, decoded):
        tape = decoded_arm["tape"]
        start = decoded_arm["start"] - global_start
        expanded: dict[int, list[dict[str, Any]]] = {}
        if tape:
            for cycle in range(horizon):
                relative = cycle - start
                if relative < 0:
                    continue
                index = relative % global_period
                if index >= len(tape):
                    continue
                item = tape[index]
                if item is None:
                    continue
                expanded[cycle] = [item]
        expanded_by_arm[str(arm["id"])] = expanded
        active = sorted(expanded)
        histogram = Counter(
            item["instruction"]
            for cycle in active
            for item in expanded[cycle]
        )
        per_arm.append({
            "partId": arm["id"],
            "type": arm["type"],
            "armNumber": arm.get("armNumber"),
            "period": global_period,
            "periodSource": "decoded_physical_tape",
            "instructionCount": decoded_arm["sourceCount"],
            "expandedInstructionCount": sum(1 for item in tape if item is not None),
            "actionCount": sum(len(expanded[cycle]) for cycle in active),
            "activeCycleCount": len(active),
            "idleCycles": horizon - len(active),
            "utilization": round(len(active) / horizon, 4),
            "firstActionCycle": min(active) if active else None,
            "lastActionCycle": max(active) if active else None,
            "histogram": dict(sorted(histogram.items())),
        })
        for cycle in active:
            active_counts[cycle] += 1

    for cycle in range(horizon):
        events: list[dict[str, Any]] = []
        for arm in arms:
            for item in expanded_by_arm.get(str(arm["id"]), {}).get(cycle, []):
                events.append({
                    "partId": arm["id"],
                    "type": arm["type"],
                    "armNumber": arm.get("armNumber"),
                    "instruction": item["instruction"],
                    "rawCode": item.get("rawCode"),
                    "tapeCycle": cycle % global_period,
                    "generatedBy": item.get("generatedBy"),
                    "sourceCycle": item.get("sourceCycle"),
                })
        cycles.append({"cycle": cycle, "activeArms": active_counts[cycle], "events": events})

    distribution = Counter(active_counts[cycle] for cycle in range(horizon))
    peak = max(active_counts.values(), default=0)
    active_cycle_count = sum(1 for cycle in range(horizon) if active_counts[cycle] > 0)

    return {
        "schemaVersion": "0.4.2",
        "analysisType": "physical-decoded-global-program-timeline",
        "limitations": [
            "Reset instructions are expanded into physical motions.",
            "An instruction is counted as scheduled even if physical execution later fails or is blocked.",
            "Internal validation-cycle hints extend diagnostic replay only; they are not authoritative cycle metrics.",
        ],
        "summary": {
            "horizon": horizon,
            "declaredCycles": effective_declared_cycles,
            "metricDeclaredCycles": metric_declared_cycles,
            "validationCycleHint": validation_cycle_hint,
            "globalPeriod": global_period,
            "periodSource": "decoded_physical_tape",
            "armCount": len(arms),
            "activeCycleCount": active_cycle_count,
            "globalIdleCycles": horizon - active_cycle_count,
            "peakParallelArms": peak,
            "averageParallelArms": round(sum(active_counts.values()) / horizon, 4),
            "parallelismDistribution": {str(key): value for key, value in sorted(distribution.items())},
        },
        "arms": per_arm,
        "cycles": cycles,
    }
