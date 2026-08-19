from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Callable

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS, rotate_hex

from .candidate_solution import serialize_candidate_roundtrip


Hex = tuple[int, int]
ProductOracleValidator = Callable[[dict[str, Any]], dict[str, Any]]
TRIPLEX_CHANNELS = frozenset({"black", "red", "yellow"})
_BONDER_ORDER = {
    "unbonder": 0,
    "bonder": 1,
    "bonder-prisma": 2,
    "bonder-speed": 3,
}


@dataclass(frozen=True, slots=True)
class ProductCore:
    """Persistent three-atom prefix of the four-atom held-out product."""

    cycle: int
    endpoint: Hex
    neighbor: Hex
    atom_ids: tuple[str, ...]


def reorder_instantaneous_bonders(solution: dict[str, Any]) -> dict[str, Any]:
    """Return a copy whose bonder family has an explicit chemistry order.

    OMSim applies instantaneous glyphs in solution-file order.  Stable sorting
    unbonders ahead of prisms lets a normal bond be removed before a prism adds
    triplex channels to the same pair.
    """
    result = deepcopy(solution)
    indexed_parts = list(enumerate(result.get("parts", [])))
    indexed_parts.sort(key=lambda item: (
        _BONDER_ORDER.get(str(item[1].get("type") or ""), len(_BONDER_ORDER)),
        item[0],
    ))
    result["parts"] = [part for _, part in indexed_parts]
    return result


def _frame_core_states(frame: dict[str, Any]) -> list[ProductCore]:
    world = frame.get("world") or {}
    atoms = {
        str(atom.get("id") or ""): atom
        for atom in world.get("atoms", [])
    }
    triplex: dict[tuple[str, str], set[str]] = {}
    for bond in world.get("bonds", []):
        kind = str(bond.get("type") or "")
        if not kind.startswith("triplex-"):
            continue
        pair = tuple(sorted((
            str(bond.get("fromAtomId") or ""),
            str(bond.get("toAtomId") or ""),
        )))
        triplex.setdefault(pair, set()).add(kind.removeprefix("triplex-"))

    states: list[ProductCore] = []
    for molecule in world.get("molecules", []):
        atom_ids = tuple(sorted(str(value) for value in molecule.get("atomIds", [])))
        if len(atom_ids) != 3 or any(atom_id not in atoms for atom_id in atom_ids):
            continue
        if sorted(str(atoms[atom_id].get("element") or "") for atom_id in atom_ids) != [
            "fire",
            "fire",
            "salt",
        ]:
            continue

        full_pairs = {
            pair
            for pair, channels in triplex.items()
            if set(pair).issubset(atom_ids) and channels == TRIPLEX_CHANNELS
        }
        if len(full_pairs) != 2:
            continue
        degree = Counter(atom_id for pair in full_pairs for atom_id in pair)
        if sorted(degree.values()) != [1, 1, 2]:
            continue

        for endpoint_id in atom_ids:
            if (
                str(atoms[endpoint_id].get("element") or "") != "fire"
                or degree[endpoint_id] != 1
            ):
                continue
            neighbor_id = next(
                other
                for pair in full_pairs
                if endpoint_id in pair
                for other in pair
                if other != endpoint_id
            )
            if str(atoms[neighbor_id].get("element") or "") != "fire":
                continue
            endpoint = tuple(int(value) for value in atoms[endpoint_id].get("position", (0, 0)))
            neighbor = tuple(int(value) for value in atoms[neighbor_id].get("position", (0, 0)))
            if (
                neighbor[0] - endpoint[0],
                neighbor[1] - endpoint[1],
            ) not in DIRECTIONS:
                continue
            states.append(ProductCore(
                cycle=int(frame.get("cycle") or 0),
                endpoint=endpoint,
                neighbor=neighbor,
                atom_ids=atom_ids,
            ))
    return states


def find_persistent_product_core(
    replay: dict[str, Any],
    *,
    persistence_frames: int = 2,
) -> ProductCore | None:
    """Find the first stationary, fully triplex-bonded fire-fire-salt core."""
    required = max(1, int(persistence_frames))
    streaks: dict[tuple[Any, ...], tuple[int, ProductCore]] = {}
    for frame in replay.get("frames", []):
        current: dict[tuple[Any, ...], ProductCore] = {}
        for state in _frame_core_states(frame):
            signature = (state.endpoint, state.neighbor, state.atom_ids)
            current[signature] = state
        next_streaks: dict[tuple[Any, ...], tuple[int, ProductCore]] = {}
        for signature, state in current.items():
            count, first = streaks.get(signature, (0, state))
            count += 1
            next_streaks[signature] = (count, first)
            if count >= required:
                return first
        streaks = next_streaks
    return None


def _rotation_for_core(core: ProductCore) -> int:
    delta = (
        core.neighbor[0] - core.endpoint[0],
        core.neighbor[1] - core.endpoint[1],
    )
    canonical_delta = (1, -1)
    for rotation in range(6):
        if rotate_hex(canonical_delta, rotation) == delta:
            return rotation
    raise ValueError("product core endpoint and neighbor must be adjacent")


def _unique_part_id(solution: dict[str, Any], prefix: str) -> str:
    existing = {str(part.get("id") or "") for part in solution.get("parts", [])}
    if prefix not in existing:
        return prefix
    suffix = 2
    while f"{prefix}-{suffix}" in existing:
        suffix += 1
    return f"{prefix}-{suffix}"


def _transform_relative(relative: Hex, core: ProductCore, rotation: int) -> list[int]:
    offset = rotate_hex(relative, rotation)
    return [core.endpoint[0] + offset[0], core.endpoint[1] + offset[1]]


def materialize_single_product_completion(
    source_solution: dict[str, Any],
    core: ProductCore,
    *,
    fire_reagent_index: int = 0,
) -> dict[str, Any]:
    """Attach the bounded two-arm/two-prism finisher around a detected core."""
    solution = deepcopy(source_solution)
    rotation = _rotation_for_core(core)
    ready = int(core.cycle)

    def part(
        prefix: str,
        part_type: str,
        relative: Hex,
        part_rotation: int,
        *,
        which: int = 0,
        program: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": _unique_part_id(solution, prefix),
            "type": part_type,
            "position": _transform_relative(relative, core, rotation),
            "rotation": (part_rotation + rotation) % 6,
            "length": 1,
            "which": which,
            "program": list(program or []),
        }

    additions = [
        part("fire-supply-unbonder", "unbonder", (-2, 2), 0),
        part("fire-supply-prism", "bonder-prisma", (-1, 1), 5),
        part("final-yellow-prism", "bonder-prisma", (0, 0), 0),
        part(
            "fire-supply-input",
            "input",
            (-1, 2),
            0,
            which=int(fire_reagent_index),
        ),
        part(
            "fire-supply-arm",
            "arm1",
            (-2, 1),
            1,
            program=[
                {"cycle": ready + 2, "instruction": "grab"},
                {"cycle": ready + 3, "instruction": "rotate_cw"},
                {"cycle": ready + 4, "instruction": "drop"},
            ],
        ),
        part(
            "final-red-arm",
            "arm1",
            (-1, 0),
            0,
            program=[
                {"cycle": ready + 5, "instruction": "grab"},
                {"cycle": ready + 6, "instruction": "pivot_cw"},
                {"cycle": ready + 7, "instruction": "drop"},
            ],
        ),
    ]
    solution.setdefault("parts", []).extend(additions)

    output = next(
        (
            item
            for item in solution["parts"]
            if str(item.get("type") or "") == "out-std"
            and int(item.get("which") or 0) == 0
        ),
        None,
    )
    if output is None:
        output = part("single-product-output", "out-std", (0, -1), 4)
        solution["parts"].append(output)
    else:
        output["position"] = _transform_relative((0, -1), core, rotation)
        output["rotation"] = (4 + rotation) % 6

    return reorder_instantaneous_bonders(solution)


def _part_with_id(
    solution: dict[str, Any],
    part_id: str,
    *,
    part_type: str | None = None,
    position: Hex | None = None,
) -> dict[str, Any]:
    part = next(
        (item for item in solution.get("parts", []) if str(item.get("id") or "") == part_id),
        None,
    )
    if part is None and part_type is not None and position is not None:
        part = next(
            (
                item
                for item in solution.get("parts", [])
                if str(item.get("type") or "") == part_type
                and tuple(int(value) for value in item.get("position", (0, 0))) == position
            ),
            None,
        )
    if part is None:
        raise ValueError(f"missing product-completion part {part_id}")
    return part


def _producer_arm(
    solution: dict[str, Any],
    *,
    producer_arm_id: str | None,
) -> dict[str, Any]:
    excluded = {"fire-supply-arm", "final-red-arm"}
    candidates = [
        part
        for part in solution.get("parts", [])
        if (
            str(part.get("type") or "").startswith("arm")
            or str(part.get("type") or "") in {"piston", "baron"}
        )
        and part.get("program")
        and str(part.get("id") or "") not in excluded
    ]
    if producer_arm_id is not None:
        candidates = [
            part
            for part in candidates
            if str(part.get("id") or "") == producer_arm_id
        ]
    if not candidates:
        raise ValueError("could not identify the product-core producer arm")
    return max(candidates, key=lambda part: len(part.get("program", [])))


def materialize_repeating_product_completion(
    single_product_solution: dict[str, Any],
    core: ProductCore,
    *,
    producer_arm_id: str | None = None,
) -> dict[str, Any]:
    """Convert the one-shot finisher into a six-output periodic machine.

    The auxiliary reagent already contains two fire atoms and one salt.  A
    second unbonder and duplication glyph turn it into three isolated fires.
    One tracked feeder consumes those fires over three core-production blocks;
    the cleared auxiliary input then respawns for the next three products.
    """
    solution = deepcopy(single_product_solution)
    rotation = _rotation_for_core(core)
    feeder = _part_with_id(
        solution,
        "fire-supply-arm",
        part_type="arm1",
        position=tuple(_transform_relative((-2, 1), core, rotation)),
    )
    red_arm = _part_with_id(
        solution,
        "final-red-arm",
        part_type="arm1",
        position=tuple(_transform_relative((-1, 0), core, rotation)),
    )
    supply_input = _part_with_id(
        solution,
        "fire-supply-input",
        part_type="input",
        position=tuple(_transform_relative((-1, 2), core, rotation)),
    )
    producer = _producer_arm(solution, producer_arm_id=producer_arm_id)
    ready = int(core.cycle)

    producer_prefix = [
        deepcopy(item)
        for item in producer.get("program", [])
        if int(item.get("cycle") or 0) <= ready
    ]
    if not producer_prefix:
        raise ValueError("producer arm has no instructions before the core-ready cycle")
    producer_block = [
        *producer_prefix,
        {"cycle": ready + 1, "instruction": "reset"},
    ]

    # Isolate the producer while measuring the physical reset expansion.  This
    # avoids allowing the delayed finisher programs to define the chemistry
    # block period.
    producer_probe = {
        "parts": [
            deepcopy(producer),
            *[
                deepcopy(part)
                for part in solution.get("parts", [])
                if str(part.get("type") or "") == "track"
            ],
        ],
    }
    producer_probe["parts"][0]["program"] = deepcopy(producer_block)
    block_period = int(
        build_program_timeline(producer_probe).get("summary", {}).get("globalPeriod")
        or 0
    )
    if block_period < ready + 1:
        raise ValueError("producer reset did not create a complete physical period")

    producer["program"] = [
        {**deepcopy(item), "cycle": int(item.get("cycle") or 0) + offset}
        for offset in (0, block_period, 2 * block_period)
        for item in producer_block
    ]

    core_cycles = [ready + index * block_period for index in range(3)]
    first, second, third = core_cycles
    feeder["program"] = [
        {"cycle": first + 2, "instruction": "grab"},
        {"cycle": first + 3, "instruction": "rotate_cw"},
        {"cycle": first + 4, "instruction": "drop"},
        {"cycle": first + 5, "instruction": "rotate_ccw"},
        {"cycle": first + 7, "instruction": "track_plus"},
        {"cycle": second + 2, "instruction": "grab"},
        {"cycle": second + 3, "instruction": "track_minus"},
        {"cycle": second + 4, "instruction": "rotate_cw"},
        {"cycle": second + 5, "instruction": "drop"},
        {"cycle": second + 6, "instruction": "rotate_ccw"},
        {"cycle": second + 7, "instruction": "track_plus"},
        {"cycle": second + 8, "instruction": "track_plus"},
        {"cycle": third + 2, "instruction": "grab"},
        {"cycle": third + 3, "instruction": "track_minus"},
        {"cycle": third + 4, "instruction": "track_minus"},
        {"cycle": third + 5, "instruction": "rotate_cw"},
        {"cycle": third + 6, "instruction": "drop"},
        {"cycle": third + 8, "instruction": "rotate_ccw"},
    ]
    red_arm["program"] = [
        {"cycle": core_cycle + offset, "instruction": instruction}
        for core_cycle in core_cycles
        for offset, instruction in (
            (5, "grab"),
            (6, "pivot_cw"),
            (7, "drop"),
        )
    ]

    track_step = rotate_hex((1, 0), rotation)
    solution.setdefault("parts", []).extend([
        {
            "id": _unique_part_id(solution, "fire-supply-second-unbonder"),
            "type": "unbonder",
            "position": list(supply_input.get("position") or (0, 0)),
            "rotation": int(supply_input.get("rotation") or 0) % 6,
            "length": 1,
            "which": 0,
            "program": [],
        },
        {
            "id": _unique_part_id(solution, "fire-supply-duplication"),
            "type": "glyph-duplication",
            "position": list(supply_input.get("position") or (0, 0)),
            "rotation": int(supply_input.get("rotation") or 0) % 6,
            "length": 1,
            "which": 0,
            "program": [],
        },
        {
            "id": _unique_part_id(solution, "fire-supply-track"),
            "type": "track",
            "position": list(feeder.get("position") or (0, 0)),
            "rotation": rotation,
            "length": 1,
            "which": 0,
            "program": [],
            "trackHexes": [
                [0, 0],
                [track_step[0], track_step[1]],
                [2 * track_step[0], 2 * track_step[1]],
            ],
        },
    ])
    return reorder_instantaneous_bonders(solution)


def analyze_product_delivery(replay: dict[str, Any]) -> dict[str, Any]:
    events = [
        event
        for frame in replay.get("frames", [])
        for event in frame.get("events", [])
        if str(event.get("kind") or "") == "product-delivered"
    ]
    cycles = [int(event.get("cycle") or 0) for event in events]
    return {
        "deliveredProductCount": len(events),
        "firstDeliveryCycle": min(cycles) if cycles else None,
    }


def _run_replay(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int,
) -> dict[str, Any]:
    timeline = build_program_timeline(solution, max_cycles=max(1, int(max_cycles)))
    return Simulator.from_models(puzzle, solution).run_timeline(timeline)


def search_single_product_completions(
    puzzle: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_limit: int = 20,
    local_cycles: int = 100,
    persistence_frames: int = 2,
    fire_reagent_index: int = 0,
    result_limit: int = 20,
    oracle_promotion_limit: int = 20,
    product_oracle_validator: ProductOracleValidator | None = None,
    oracle_workers: int = 1,
) -> dict[str, Any]:
    """Promote persistent three-atom cores to explicit one-product proofs."""
    records: list[dict[str, Any]] = []
    searched = list(sources)[:max(0, int(source_limit))]
    core_count = 0
    for source_index, source in enumerate(searched):
        source_solution = source.get("solution") if "solution" in source else source
        if not isinstance(source_solution, dict):
            continue
        ordered = reorder_instantaneous_bonders(source_solution)
        try:
            source_replay = _run_replay(puzzle, ordered, max_cycles=local_cycles)
            core = find_persistent_product_core(
                source_replay,
                persistence_frames=persistence_frames,
            )
            if core is None:
                continue
            core_count += 1
            completed = materialize_single_product_completion(
                ordered,
                core,
                fire_reagent_index=fire_reagent_index,
            )
            roundtrip = serialize_candidate_roundtrip(completed)
            replay = _run_replay(
                puzzle,
                roundtrip["parsed"],
                max_cycles=max(local_cycles, core.cycle + 12),
            )
            delivery = analyze_product_delivery(replay)
            records.append({
                "stage": "single-product-completion",
                "sourceIndex": source_index,
                "sourceCandidateRank": source.get("sourceCandidateRank"),
                "sourceVariantIndex": source.get("sourceVariantIndex"),
                "core": asdict(core),
                "serialization": roundtrip["diagnostics"],
                "localProductDelivery": delivery,
                "solution": completed,
            })
        except Exception as exc:
            records.append({
                "stage": "single-product-completion",
                "sourceIndex": source_index,
                "generationError": {
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                },
            })

    local_complete = [
        record
        for record in records
        if int((record.get("localProductDelivery") or {}).get("deliveredProductCount") or 0) > 0
    ]
    promoted = local_complete[:max(0, int(oracle_promotion_limit))]
    outcomes: Counter[str] = Counter()

    def validate(record: dict[str, Any]) -> dict[str, Any]:
        try:
            assert product_oracle_validator is not None
            return product_oracle_validator(record["solution"])
        except Exception as exc:
            return {
                "status": "validator-error",
                "valid": None,
                "value": None,
                "issues": [{"message": f"{type(exc).__name__}: {exc}"}],
            }

    if product_oracle_validator is not None and promoted:
        with ThreadPoolExecutor(max_workers=max(1, min(10, int(oracle_workers)))) as executor:
            validations = list(executor.map(validate, promoted))
        for record, validation in zip(promoted, validations):
            record["productOracleValidation"] = validation
            outcome = str(validation.get("status") or "unknown")
            record["productOracleOutcome"] = outcome
            outcomes[outcome] += 1

    oracle_complete = [
        record
        for record in promoted
        if str(record.get("productOracleOutcome") or "") == "product-complete"
    ]
    oracle_cycles = [
        int((record.get("productOracleValidation") or {}).get("value"))
        for record in oracle_complete
        if (record.get("productOracleValidation") or {}).get("value") is not None
    ]
    ranked = sorted(
        records,
        key=lambda record: (
            int(str(record.get("productOracleOutcome") or "") == "product-complete"),
            int((record.get("localProductDelivery") or {}).get("deliveredProductCount") or 0),
            -int((record.get("localProductDelivery") or {}).get("firstDeliveryCycle") or 1_000_000),
        ),
        reverse=True,
    )
    return {
        "summary": {
            "searchedSourceCount": len(searched),
            "persistentProductCoreCount": core_count,
            "generatedCompletionCount": len(records),
            "localSingleProductCompleteCount": len(local_complete),
            "oraclePromotedCount": len(promoted) if product_oracle_validator is not None else 0,
            "oracleSingleProductCompleteCount": len(oracle_complete),
            "hasOracleSingleProduct": bool(oracle_complete),
            "bestSingleProductCycle": min(oracle_cycles) if oracle_cycles else None,
            "oracleOutcomeCounts": dict(sorted(outcomes.items())),
        },
        "variants": ranked[:max(0, int(result_limit))],
    }


def search_repeating_product_completions(
    puzzle: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_limit: int = 20,
    local_cycles: int = 400,
    result_limit: int = 20,
    oracle_promotion_limit: int = 20,
    full_product_oracle_validator: ProductOracleValidator | None = None,
    oracle_workers: int = 1,
) -> dict[str, Any]:
    """Turn accepted one-product candidates into six-product periodic machines."""
    searched = list(sources)[:max(0, int(source_limit))]
    records: list[dict[str, Any]] = []
    for source_index, source in enumerate(searched):
        solution = source.get("solution") if "solution" in source else source
        core_payload = source.get("core") if isinstance(source, dict) else None
        if not isinstance(solution, dict) or not isinstance(core_payload, dict):
            continue
        try:
            core = ProductCore(
                cycle=int(core_payload.get("cycle") or 0),
                endpoint=tuple(int(value) for value in core_payload.get("endpoint", (0, 0))),
                neighbor=tuple(int(value) for value in core_payload.get("neighbor", (0, 0))),
                atom_ids=tuple(str(value) for value in core_payload.get("atom_ids", ())),
            )
            completed = materialize_repeating_product_completion(solution, core)
            roundtrip = serialize_candidate_roundtrip(completed)
            replay = _run_replay(
                puzzle,
                roundtrip["parsed"],
                max_cycles=max(1, int(local_cycles)),
            )
            delivery = analyze_product_delivery(replay)
            period = int(
                build_program_timeline(roundtrip["parsed"]).get("summary", {}).get(
                    "globalPeriod"
                ) or 0
            )
            records.append({
                "stage": "repeating-product-completion",
                "sourceIndex": source_index,
                "sourceCandidateRank": source.get("sourceCandidateRank"),
                "sourceVariantIndex": source.get("sourceVariantIndex"),
                "core": asdict(core),
                "globalPeriod": period,
                "serialization": roundtrip["diagnostics"],
                "localProductDelivery": delivery,
                "solution": completed,
            })
        except Exception as exc:
            records.append({
                "stage": "repeating-product-completion",
                "sourceIndex": source_index,
                "generationError": {
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                },
            })

    local_complete = [
        record
        for record in records
        if int((record.get("localProductDelivery") or {}).get("deliveredProductCount") or 0)
        >= 6
    ]
    promoted = local_complete[:max(0, int(oracle_promotion_limit))]
    outcomes: Counter[str] = Counter()

    def validate(record: dict[str, Any]) -> dict[str, Any]:
        try:
            assert full_product_oracle_validator is not None
            return full_product_oracle_validator(record["solution"])
        except Exception as exc:
            return {
                "status": "validator-error",
                "valid": None,
                "value": None,
                "issues": [{"message": f"{type(exc).__name__}: {exc}"}],
            }

    if full_product_oracle_validator is not None and promoted:
        with ThreadPoolExecutor(max_workers=max(1, min(10, int(oracle_workers)))) as executor:
            validations = list(executor.map(validate, promoted))
        for record, validation in zip(promoted, validations):
            record["fullProductOracleValidation"] = validation
            outcome = str(validation.get("status") or "unknown")
            record["fullProductOracleOutcome"] = outcome
            outcomes[outcome] += 1

    oracle_complete = [
        record
        for record in promoted
        if str(record.get("fullProductOracleOutcome") or "") == "product-complete"
        and int((record.get("fullProductOracleValidation") or {}).get("productCount") or 0)
        >= 6
    ]
    oracle_cycles = [
        int((record.get("fullProductOracleValidation") or {}).get("value"))
        for record in oracle_complete
        if (record.get("fullProductOracleValidation") or {}).get("value") is not None
    ]
    ranked = sorted(
        records,
        key=lambda record: (
            int(record in oracle_complete),
            int((record.get("localProductDelivery") or {}).get("deliveredProductCount") or 0),
            -int((record.get("fullProductOracleValidation") or {}).get("value") or 1_000_000),
        ),
        reverse=True,
    )
    return {
        "summary": {
            "searchedSourceCount": len(searched),
            "generatedRepeatingCompletionCount": len(records),
            "localFullProductCompleteCount": len(local_complete),
            "oraclePromotedCount": len(promoted) if full_product_oracle_validator else 0,
            "oracleFullProductCompleteCount": len(oracle_complete),
            "hasOracleFullPuzzle": bool(oracle_complete),
            "bestFullProductCycle": min(oracle_cycles) if oracle_cycles else None,
            "oracleOutcomeCounts": dict(sorted(outcomes.items())),
        },
        "variants": ranked[:max(0, int(result_limit))],
    }
