from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from packages.opus_analysis import canonical_molecule_hash
from packages.opus_parser.solution_writer import write_solution_bytes


ARM_PART_CAPABILITIES = {
    "arm1": "arm1",
    "arm2": "arm2",
    "arm3": "arm3",
    "arm6": "arm6",
    "piston": "piston",
    "baron": "van-berlo",
}


class BlindTransferContractError(ValueError):
    """Raised when a transfer would read from the target solution family."""


@dataclass(slots=True)
class BlindTransferCandidate:
    candidate_id: str
    molecule_hash: str
    donor_mapping: dict[str, int]
    target_mapping: dict[str, int]
    source_part_ids: tuple[str, ...]
    solution: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(write_solution_bytes(self.solution)).hexdigest()

    def to_dict(self, *, include_solution: bool = False) -> dict[str, Any]:
        result = {
            "candidateId": self.candidate_id,
            "fingerprint": self.fingerprint,
            "moleculeHash": self.molecule_hash,
            "donorMapping": deepcopy(self.donor_mapping),
            "targetMapping": deepcopy(self.target_mapping),
            "sourcePartIds": list(self.source_part_ids),
        }
        if include_solution:
            result["solution"] = deepcopy(self.solution)
        return result


def puzzle_file_id(puzzle: dict[str, Any]) -> str:
    source_name = str((puzzle.get("source") or {}).get("name") or "")
    if not source_name:
        raise BlindTransferContractError("Puzzle source.name is required by the blind-transfer contract")
    stem = Path(source_name).stem
    return re.sub(r" \(\d+\)$", "", stem)


def validate_blind_transfer_contract(
    target_puzzle: dict[str, Any],
    donor_puzzle: dict[str, Any],
    donor_solution: dict[str, Any],
) -> dict[str, Any]:
    """Prove that the only supplied solution belongs to a different puzzle.

    The API deliberately accepts one donor solution rather than a solution
    corpus or target-solution root.  A caller therefore cannot accidentally
    retrieve, rank, or inspect a solution associated with the target ID.
    """

    target_id = puzzle_file_id(target_puzzle)
    donor_id = puzzle_file_id(donor_puzzle)
    solution_id = str(donor_solution.get("puzzleFile") or "")
    if target_id == donor_id:
        raise BlindTransferContractError(
            f"Target and donor puzzle IDs must differ; both resolve to {target_id!r}"
        )
    if solution_id != donor_id:
        raise BlindTransferContractError(
            f"Donor solution belongs to {solution_id!r}, expected {donor_id!r}"
        )
    if solution_id == target_id:
        raise BlindTransferContractError(
            f"Donor solution belongs to forbidden target family {target_id!r}"
        )
    return {
        "targetPuzzleId": target_id,
        "donorPuzzleId": donor_id,
        "donorSolutionPuzzleId": solution_id,
        "targetSolutionsRead": 0,
        "targetSolutionAccess": "forbidden-by-input-contract",
    }


def _passthrough_pairs(puzzle: dict[str, Any]) -> list[tuple[int, int, str]]:
    reagent_hashes = [
        canonical_molecule_hash(molecule)
        for molecule in puzzle.get("reagents") or ()
    ]
    product_hashes = [
        canonical_molecule_hash(molecule)
        for molecule in puzzle.get("products") or ()
    ]
    return [
        (reagent_index, product_index, reagent_hash)
        for reagent_index, reagent_hash in enumerate(reagent_hashes)
        for product_index, product_hash in enumerate(product_hashes)
        if reagent_hash == product_hash
    ]


def _part_id(part: dict[str, Any], index: int) -> str:
    return str(part.get("id") or f"part-{index}")


def _materialize_candidate(
    target_id: str,
    donor_solution: dict[str, Any],
    *,
    candidate_index: int,
    molecule_hash: str,
    donor_reagent_index: int,
    donor_product_index: int,
    target_reagent_index: int,
    target_product_index: int,
    input_part: dict[str, Any],
    output_part: dict[str, Any],
    arm_part: dict[str, Any],
) -> BlindTransferCandidate:
    candidate_id = f"direct-transfer-{candidate_index:03d}"
    source_parts = (input_part, output_part, arm_part)
    source_part_ids = tuple(
        _part_id(part, index) for index, part in enumerate(source_parts)
    )
    parts = [deepcopy(part) for part in source_parts]
    for index, part in enumerate(parts):
        part["id"] = f"{candidate_id}-part-{index}"
        part["enabled"] = True
        if part.get("type") == "input":
            part["which"] = target_reagent_index
        elif part.get("type") == "out-std":
            part["which"] = target_product_index
        elif str(part.get("type") or "") in ARM_PART_CAPABILITIES:
            part["armNumber"] = 0

    solution = {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {
            "name": None,
            "generator": "opus_solver/blind-direct-transfer-v1",
            "donorSolutionSha256": (donor_solution.get("source") or {}).get("sha256"),
            "donorPartIds": list(source_part_ids),
        },
        "puzzleFile": target_id,
        "name": f"Opus Solver - blind transfer {candidate_index:03d}",
        "metrics": {},
        "unknownMetrics": [],
        "parts": parts,
        "trailingBytes": 0,
    }
    return BlindTransferCandidate(
        candidate_id=candidate_id,
        molecule_hash=molecule_hash,
        donor_mapping={
            "reagentIndex": donor_reagent_index,
            "productIndex": donor_product_index,
        },
        target_mapping={
            "reagentIndex": target_reagent_index,
            "productIndex": target_product_index,
        },
        source_part_ids=source_part_ids,
        solution=solution,
    )


def generate_blind_transfer_candidates(
    target_puzzle: dict[str, Any],
    donor_puzzle: dict[str, Any],
    donor_solution: dict[str, Any],
) -> tuple[BlindTransferCandidate, ...]:
    """Transplant minimal direct-transfer mechanisms from another puzzle.

    A candidate contains exactly one donor input, one donor standard output,
    and one donor arm.  Chemistry is matched by rotation/translation-invariant
    molecule hashes; input/output indices are remapped to the target.  No
    target solution is accepted by this API.
    """

    contract = validate_blind_transfer_contract(
        target_puzzle,
        donor_puzzle,
        donor_solution,
    )
    target_pairs = _passthrough_pairs(target_puzzle)
    donor_pairs = _passthrough_pairs(donor_puzzle)
    if not target_pairs:
        raise BlindTransferContractError(
            "Target has no reagent/product molecule pair that can pass through unchanged"
        )
    if not donor_pairs:
        raise BlindTransferContractError(
            "Donor has no reagent/product molecule pair that can pass through unchanged"
        )

    available_arms = set(
        str(value)
        for value in (target_puzzle.get("availableParts") or {}).get("arms") or ()
    )
    parts = list(donor_solution.get("parts") or ())
    inputs = [part for part in parts if part.get("type") == "input"]
    outputs = [part for part in parts if part.get("type") == "out-std"]
    arms = [
        part
        for part in parts
        if ARM_PART_CAPABILITIES.get(str(part.get("type") or "")) in available_arms
        and part.get("program")
    ]

    candidates: list[BlindTransferCandidate] = []
    for target_reagent, target_product, target_hash in target_pairs:
        for donor_reagent, donor_product, donor_hash in donor_pairs:
            if donor_hash != target_hash:
                continue
            matching_inputs = [
                part for part in inputs if int(part.get("which") or 0) == donor_reagent
            ]
            matching_outputs = [
                part for part in outputs if int(part.get("which") or 0) == donor_product
            ]
            for input_part in matching_inputs:
                for output_part in matching_outputs:
                    for arm_part in arms:
                        candidates.append(_materialize_candidate(
                            contract["targetPuzzleId"],
                            donor_solution,
                            candidate_index=len(candidates) + 1,
                            molecule_hash=target_hash,
                            donor_reagent_index=donor_reagent,
                            donor_product_index=donor_product,
                            target_reagent_index=target_reagent,
                            target_product_index=target_product,
                            input_part=input_part,
                            output_part=output_part,
                            arm_part=arm_part,
                        ))

    if not candidates:
        raise BlindTransferContractError(
            "No donor input/output/arm fragment is chemistry- and capability-compatible"
        )
    return tuple(candidates)
