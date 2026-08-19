from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS

from .candidate_solution import serialize_candidate_roundtrip
from .chemistry_transplant import mechanical_fingerprint, prism_poses_for_pair
from .component_timing import oracle_outcome
from .product_completion import reorder_instantaneous_bonders


OracleValidator = Callable[[dict[str, Any]], dict[str, Any]]
Hex = tuple[int, int]
TRIPLEX_CHANNELS = frozenset({"black", "red", "yellow"})
ORACLE_STABLE_OUTCOMES = {"complete", "cycle-limit"}


def _events(replay: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [
        event
        for frame in replay.get("frames", [])
        for event in frame.get("events", [])
        if str(event.get("kind") or "") == kind
    ]


def _frame_atoms(frame: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(atom.get("id") or ""): atom
        for atom in (frame.get("world") or {}).get("atoms", [])
    }


def _pair_channels(frame: dict[str, Any], pair: tuple[str, str]) -> set[str]:
    channels: set[str] = set()
    for bond in (frame.get("world") or {}).get("bonds", []):
        kind = str(bond.get("type") or "")
        if not kind.startswith("triplex-"):
            continue
        bond_pair = tuple(sorted((
            str(bond.get("fromAtomId") or ""),
            str(bond.get("toAtomId") or ""),
        )))
        if bond_pair == pair:
            channels.add(kind.removeprefix("triplex-"))
    return channels


def _has_normal_bond(frame: dict[str, Any], pair: tuple[str, str]) -> bool:
    return any(
        str(bond.get("type") or "") == "normal"
        and tuple(sorted((
            str(bond.get("fromAtomId") or ""),
            str(bond.get("toAtomId") or ""),
        ))) == pair
        for bond in (frame.get("world") or {}).get("bonds", [])
    )


def _first_streak_cycle(
    frames: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    *,
    minimum: int,
) -> int | None:
    streak = 0
    first_cycle: int | None = None
    for frame in frames:
        if predicate(frame):
            if streak == 0:
                first_cycle = int(frame.get("cycle") or 0)
            streak += 1
            if streak >= minimum:
                return first_cycle
        else:
            streak = 0
            first_cycle = None
    return None


def _best_duplication_progress(
    replay: dict[str, Any],
    *,
    persistence_frames: int,
) -> dict[str, Any] | None:
    frames = list(replay.get("frames", []))
    candidates = []
    for event in _events(replay, "atom-duplicated"):
        source_id = str(event.get("sourceAtomId") or "")
        transformed_id = str(event.get("transformedAtomId") or "")
        if not source_id or not transformed_id:
            continue
        pair = tuple(sorted((source_id, transformed_id)))
        event_cycle = int(event.get("cycle") or 0)
        eligible = [
            frame
            for frame in frames
            if int(frame.get("cycle") or 0) >= event_cycle + 1
        ]
        duplicated_cycle = _first_streak_cycle(
            eligible,
            lambda frame: (
                transformed_id in _frame_atoms(frame)
                and str(_frame_atoms(frame)[transformed_id].get("element") or "")
                == str(event.get("toElement") or "")
            ),
            minimum=persistence_frames,
        )
        removed_events = [
            item
            for item in _events(replay, "bond-removed")
            if tuple(sorted((
                str(item.get("fromAtomId") or ""),
                str(item.get("toAtomId") or ""),
            ))) == pair
        ]
        unbond_cycle = None
        if removed_events:
            unbond_cycle = _first_streak_cycle(
                eligible,
                lambda frame: (
                    source_id in _frame_atoms(frame)
                    and transformed_id in _frame_atoms(frame)
                    and not _has_normal_bond(frame, pair)
                ),
                minimum=persistence_frames,
            )

        persistent_channel_count = 0
        first_triplex_cycle = None
        for count in range(1, 4):
            cycle = _first_streak_cycle(
                eligible,
                lambda frame, required=count: len(_pair_channels(frame, pair)) >= required,
                minimum=persistence_frames,
            )
            if cycle is not None:
                persistent_channel_count = count
                if count == 3:
                    first_triplex_cycle = cycle

        calcified_triplex_cycle = _first_streak_cycle(
            eligible,
            lambda frame: (
                transformed_id in _frame_atoms(frame)
                and str(_frame_atoms(frame)[transformed_id].get("element") or "") == "salt"
                and _pair_channels(frame, pair) == TRIPLEX_CHANNELS
            ),
            minimum=persistence_frames,
        )
        ordered_stage_count = int(unbond_cycle is not None) + int(duplicated_cycle is not None)
        if unbond_cycle is not None and duplicated_cycle is not None:
            ordered_stage_count += persistent_channel_count
            if persistent_channel_count == 3:
                ordered_stage_count += int(calcified_triplex_cycle is not None)
        candidates.append({
            "sourceAtomId": source_id,
            "transformedAtomId": transformed_id,
            "pair": list(pair),
            "eventCycle": event_cycle,
            "persistentUnbondCycle": unbond_cycle,
            "persistentDuplicationCycle": duplicated_cycle,
            "persistentTriplexChannelCount": persistent_channel_count,
            "persistentCompleteTriplexCycle": first_triplex_cycle,
            "persistentCalcifiedCompleteTriplexCycle": calcified_triplex_cycle,
            "orderedStageCount": ordered_stage_count,
        })
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            int(item["persistentCalcifiedCompleteTriplexCycle"] is not None),
            int(item["persistentCompleteTriplexCycle"] is not None),
            int(item["persistentTriplexChannelCount"]),
            int(item["orderedStageCount"]),
            -int(item["eventCycle"]),
        ),
    )


def analyze_persistent_chemistry(
    replay: dict[str, Any],
    *,
    persistence_frames: int = 2,
) -> dict[str, Any]:
    """Measure durable molecular states instead of reversible event volume."""
    persistence_frames = max(1, int(persistence_frames))
    frames = list(replay.get("frames", []))
    best = _best_duplication_progress(
        replay,
        persistence_frames=persistence_frames,
    )
    event_counts = Counter(
        str(event.get("kind") or "unknown")
        for frame in frames
        for event in frame.get("events", [])
    )
    max_molecule_atoms = max(
        (
            len(molecule.get("atomIds", []))
            for frame in frames
            for molecule in (frame.get("world") or {}).get("molecules", [])
        ),
        default=0,
    )
    return {
        "persistenceFrames": persistence_frames,
        "terminatedWithError": any(str(frame.get("phase") or "") == "error" for frame in frames),
        "completedCycles": max((int(frame.get("cycle") or 0) for frame in frames), default=0),
        "eventCounts": dict(sorted(event_counts.items())),
        "maxMoleculeAtomCount": max_molecule_atoms,
        "bestDuplicatedPair": best,
        "orderedStageCount": int((best or {}).get("orderedStageCount") or 0),
        "maxPersistentTriplexChannelCount": int(
            (best or {}).get("persistentTriplexChannelCount") or 0
        ),
        "hasPersistentCompleteTriplex": bool(
            (best or {}).get("persistentCompleteTriplexCycle") is not None
        ),
        "hasPersistentCalcifiedCompleteTriplex": bool(
            (best or {}).get("persistentCalcifiedCompleteTriplexCycle") is not None
        ),
        "deliveredProductCount": int(event_counts.get("product-delivered") or 0),
    }


def _run_replay(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int,
) -> dict[str, Any]:
    timeline = build_program_timeline(solution, max_cycles=max(1, int(max_cycles)))
    return Simulator.from_models(puzzle, solution).run_timeline(timeline)


def _unique_part_id(solution: dict[str, Any], prefix: str) -> str:
    existing = {str(part.get("id") or "") for part in solution.get("parts", [])}
    if prefix not in existing:
        return prefix
    suffix = 2
    while f"{prefix}-{suffix}" in existing:
        suffix += 1
    return f"{prefix}-{suffix}"


def _adjacent(first: Hex, second: Hex) -> bool:
    return (second[0] - first[0], second[1] - first[1]) in DIRECTIONS


def _missing_prism_placements(
    replay: dict[str, Any],
    pair: tuple[str, str],
) -> list[dict[str, Any]]:
    placements: dict[tuple[Hex, int], dict[str, Any]] = {}
    for frame in replay.get("frames", []):
        atoms = _frame_atoms(frame)
        if pair[0] not in atoms or pair[1] not in atoms:
            continue
        first = tuple(atoms[pair[0]].get("position") or (0, 0))
        second = tuple(atoms[pair[1]].get("position") or (0, 0))
        if not _adjacent(first, second):
            continue
        for pose in prism_poses_for_pair(first, second):
            key = (tuple(pose["position"]), int(pose["rotation"]))
            placements.setdefault(key, {
                **pose,
                "observedCycle": int(frame.get("cycle") or 0),
                "observedPairPositions": [list(first), list(second)],
            })
    return list(placements.values())


def _calcification_positions(
    replay: dict[str, Any],
    progress: dict[str, Any],
) -> list[dict[str, Any]]:
    best = progress.get("bestDuplicatedPair") or {}
    transformed_id = str(best.get("transformedAtomId") or "")
    first_triplex = best.get("persistentCompleteTriplexCycle")
    if not transformed_id or first_triplex is None:
        return []
    positions: dict[Hex, dict[str, Any]] = {}
    for frame in replay.get("frames", []):
        cycle = int(frame.get("cycle") or 0)
        if cycle < int(first_triplex):
            continue
        atom = _frame_atoms(frame).get(transformed_id)
        if atom is None:
            continue
        position = tuple(atom.get("position") or (0, 0))
        positions.setdefault(position, {
            "position": list(position),
            "observedCycle": cycle,
            "transformedAtomId": transformed_id,
        })
    return list(positions.values())


def _evaluate(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    local_cycles: int,
    persistence_frames: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    roundtrip = serialize_candidate_roundtrip(solution)
    replay = _run_replay(
        puzzle,
        roundtrip["parsed"],
        max_cycles=local_cycles,
    )
    progress = analyze_persistent_chemistry(
        replay,
        persistence_frames=persistence_frames,
    )
    return roundtrip, replay, progress


def _validate_with_oracle(
    records: list[dict[str, Any]],
    *,
    oracle_validator: OracleValidator | None,
    workers: int,
) -> Counter[str]:
    outcomes: Counter[str] = Counter()
    if oracle_validator is None or not records:
        return outcomes

    def validate(record: dict[str, Any]) -> dict[str, Any]:
        try:
            return oracle_validator(record["solution"])
        except Exception as exc:
            return {
                "valid": False,
                "rawOutput": f"oracle validation error: {type(exc).__name__}: {exc}",
                "issues": [{"cycle": None, "message": str(exc)}],
            }

    with ThreadPoolExecutor(max_workers=max(1, min(10, int(workers)))) as executor:
        validations = list(executor.map(validate, records))
    for record, validation in zip(records, validations):
        record["oracleValidation"] = validation
        record["oracleOutcome"] = oracle_outcome(validation)
        outcomes[record["oracleOutcome"]] += 1
    return outcomes


def _progress_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    progress = record.get("persistentChemistry") or {}
    best = progress.get("bestDuplicatedPair") or {}
    completion_cycle = best.get("persistentCalcifiedCompleteTriplexCycle")
    if completion_cycle is None:
        completion_cycle = best.get("persistentCompleteTriplexCycle")
    return (
        int(str(record.get("oracleOutcome") or "") in ORACLE_STABLE_OUTCOMES),
        int(progress.get("hasPersistentCalcifiedCompleteTriplex")),
        int(progress.get("hasPersistentCompleteTriplex")),
        int(progress.get("maxPersistentTriplexChannelCount") or 0),
        int(progress.get("orderedStageCount") or 0),
        int(not progress.get("terminatedWithError")),
        -int(completion_cycle if completion_cycle is not None else 1_000_000),
    )


def search_ordered_chemistry_candidates(
    puzzle: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_limit: int = 8,
    prism_variant_limit: int = 256,
    calcification_variant_limit: int = 256,
    result_limit: int = 20,
    local_cycles: int = 160,
    persistence_frames: int = 2,
    prism_oracle_promotion_limit: int = 32,
    calcification_oracle_promotion_limit: int = 40,
    oracle_validator: OracleValidator | None = None,
    oracle_workers: int = 1,
) -> dict[str, Any]:
    """Grow stable transplants through persistent triplex and calcification stages."""
    stable_sources = [
        source
        for source in sources
        if source.get("solution")
        and (
            oracle_validator is None
            or str(source.get("oracleOutcome") or "") in ORACLE_STABLE_OUTCOMES
        )
    ][:max(0, int(source_limit))]

    prism_records: list[dict[str, Any]] = []
    prism_attempt_count = 0
    for source in stable_sources:
        if prism_attempt_count >= max(0, int(prism_variant_limit)):
            break
        ordered_source_solution = reorder_instantaneous_bonders(source["solution"])
        source_replay = _run_replay(
            puzzle,
            ordered_source_solution,
            max_cycles=local_cycles,
        )
        source_progress = analyze_persistent_chemistry(
            source_replay,
            persistence_frames=persistence_frames,
        )
        best = source_progress.get("bestDuplicatedPair") or {}
        pair = tuple(best.get("pair") or ())
        if len(pair) != 2:
            continue
        for placement in _missing_prism_placements(source_replay, pair):
            if prism_attempt_count >= max(0, int(prism_variant_limit)):
                break
            prism_attempt_count += 1
            solution = deepcopy(ordered_source_solution)
            solution.setdefault("parts", []).append({
                "id": _unique_part_id(solution, "ordered-prism"),
                "type": "bonder-prisma",
                "position": list(placement["position"]),
                "rotation": int(placement["rotation"]) % 6,
                "length": 1,
                "which": 0,
                "program": [],
            })
            solution = reorder_instantaneous_bonders(solution)
            if mechanical_fingerprint(solution) != mechanical_fingerprint(source["solution"]):
                raise AssertionError("Ordered prism stage changed the frozen mechanism")
            try:
                roundtrip, _, progress = _evaluate(
                    puzzle,
                    solution,
                    local_cycles=local_cycles,
                    persistence_frames=persistence_frames,
                )
            except Exception as exc:
                prism_records.append({
                    "stage": "complete-triplex",
                    "sourceVariantIndex": source.get("variantIndex"),
                    "sourceCandidateRank": source.get("sourceCandidateRank"),
                    "placement": placement,
                    "solution": solution,
                    "generationError": {
                        "errorType": type(exc).__name__,
                        "message": str(exc),
                    },
                    "persistentChemistry": {"terminatedWithError": True},
                })
                continue
            prism_records.append({
                "stage": "complete-triplex",
                "sourceVariantIndex": source.get("variantIndex"),
                "sourceCandidateRank": source.get("sourceCandidateRank"),
                "sourceOracleOutcome": source.get("oracleOutcome"),
                "placement": placement,
                "mechanicalFingerprint": mechanical_fingerprint(solution),
                "mechanicsPreserved": True,
                "serialization": roundtrip["diagnostics"],
                "persistentChemistry": progress,
                "solution": solution,
            })

    prism_local_stable = sorted(
        (
            record
            for record in prism_records
            if (record.get("persistentChemistry") or {}).get("hasPersistentCompleteTriplex")
            and not (record.get("persistentChemistry") or {}).get("terminatedWithError")
        ),
        key=_progress_rank,
        reverse=True,
    )
    prism_promoted = prism_local_stable[:max(0, int(prism_oracle_promotion_limit))]
    prism_outcomes = _validate_with_oracle(
        prism_promoted,
        oracle_validator=oracle_validator,
        workers=oracle_workers,
    )
    prism_stable = [
        record
        for record in prism_promoted
        if oracle_validator is None
        or str(record.get("oracleOutcome") or "") in ORACLE_STABLE_OUTCOMES
    ]

    calcification_records: list[dict[str, Any]] = []
    calcification_attempt_count = 0
    for source in prism_stable:
        if calcification_attempt_count >= max(0, int(calcification_variant_limit)):
            break
        replay = _run_replay(
            puzzle,
            source["solution"],
            max_cycles=local_cycles,
        )
        progress = analyze_persistent_chemistry(
            replay,
            persistence_frames=persistence_frames,
        )
        for placement in _calcification_positions(replay, progress):
            if calcification_attempt_count >= max(0, int(calcification_variant_limit)):
                break
            calcification_attempt_count += 1
            solution = deepcopy(source["solution"])
            part = next(
                (
                    item
                    for item in solution.get("parts", [])
                    if str(item.get("type") or "") == "glyph-calcification"
                ),
                None,
            )
            if part is None:
                part = {
                    "id": _unique_part_id(solution, "ordered-calcification"),
                    "type": "glyph-calcification",
                    "rotation": 0,
                    "length": 1,
                    "which": 0,
                    "program": [],
                }
                solution.setdefault("parts", []).append(part)
            part["position"] = list(placement["position"])
            if mechanical_fingerprint(solution) != mechanical_fingerprint(source["solution"]):
                raise AssertionError("Ordered calcification stage changed the frozen mechanism")
            try:
                roundtrip, _, child_progress = _evaluate(
                    puzzle,
                    solution,
                    local_cycles=local_cycles,
                    persistence_frames=persistence_frames,
                )
            except Exception as exc:
                calcification_records.append({
                    "stage": "calcified-complete-triplex",
                    "sourceVariantIndex": source.get("sourceVariantIndex"),
                    "sourceCandidateRank": source.get("sourceCandidateRank"),
                    "secondPrismPlacement": source.get("placement"),
                    "placement": placement,
                    "solution": solution,
                    "generationError": {
                        "errorType": type(exc).__name__,
                        "message": str(exc),
                    },
                    "persistentChemistry": {"terminatedWithError": True},
                })
                continue
            calcification_records.append({
                "stage": "calcified-complete-triplex",
                "sourceVariantIndex": source.get("sourceVariantIndex"),
                "sourceCandidateRank": source.get("sourceCandidateRank"),
                "sourceOracleOutcome": source.get("oracleOutcome"),
                "secondPrismPlacement": source.get("placement"),
                "placement": placement,
                "mechanicalFingerprint": mechanical_fingerprint(solution),
                "mechanicsPreserved": True,
                "serialization": roundtrip["diagnostics"],
                "persistentChemistry": child_progress,
                "solution": solution,
            })

    calcification_local_stable = sorted(
        (
            record
            for record in calcification_records
            if (record.get("persistentChemistry") or {}).get(
                "hasPersistentCalcifiedCompleteTriplex"
            )
            and not (record.get("persistentChemistry") or {}).get("terminatedWithError")
        ),
        key=_progress_rank,
        reverse=True,
    )
    calcification_promoted = calcification_local_stable[
        :max(0, int(calcification_oracle_promotion_limit))
    ]
    calcification_outcomes = _validate_with_oracle(
        calcification_promoted,
        oracle_validator=oracle_validator,
        workers=oracle_workers,
    )
    calcification_stable = [
        record
        for record in calcification_promoted
        if oracle_validator is None
        or str(record.get("oracleOutcome") or "") in ORACLE_STABLE_OUTCOMES
    ]
    selected = sorted(
        calcification_stable or prism_stable,
        key=_progress_rank,
        reverse=True,
    )[:max(0, int(result_limit))]

    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "selectedStableSourceCount": len(stable_sources),
            "searchedPrismVariantCount": prism_attempt_count,
            "localPersistentCompleteTriplexCount": len(prism_local_stable),
            "oraclePromotedPrismVariantCount": len(prism_promoted) if oracle_validator else 0,
            "oraclePrismOutcomeCounts": dict(sorted(prism_outcomes.items())),
            "oracleStableCompleteTriplexCount": len(prism_stable),
            "searchedCalcificationVariantCount": calcification_attempt_count,
            "localPersistentCalcifiedCompleteTriplexCount": len(calcification_local_stable),
            "oraclePromotedCalcificationVariantCount": (
                len(calcification_promoted) if oracle_validator else 0
            ),
            "oracleCalcificationOutcomeCounts": dict(sorted(calcification_outcomes.items())),
            "oracleStableCalcifiedCompleteTriplexCount": len(calcification_stable),
            "returnedVariantCount": len(selected),
            "hasPersistentCompleteTriplex": bool(prism_stable),
            "hasPersistentCalcifiedCompleteTriplex": bool(calcification_stable),
            "oracleCompleteVariantCount": sum(
                str(record.get("oracleOutcome") or "") == "complete"
                for record in [*prism_promoted, *calcification_promoted]
            ),
            "sourceLimit": max(0, int(source_limit)),
            "prismVariantLimit": max(0, int(prism_variant_limit)),
            "calcificationVariantLimit": max(0, int(calcification_variant_limit)),
            "localCycles": max(1, int(local_cycles)),
            "persistenceFrames": max(1, int(persistence_frames)),
            "oracleEnabled": oracle_validator is not None,
            "oracleWorkers": max(1, min(10, int(oracle_workers))),
            "selectionPolicy": "persistent-state-then-authoritative-survival",
        },
        "prismVariants": sorted(prism_promoted, key=_progress_rank, reverse=True)[
            :max(0, int(result_limit))
        ],
        "variants": selected,
    }
