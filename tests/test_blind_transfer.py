import pytest

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from packages.opus_solver.blind_transfer import (
    BlindTransferContractError,
    generate_blind_transfer_candidates,
    validate_blind_transfer_contract,
)


def _molecule():
    return {
        "atoms": [{"id": "a0", "element": "salt", "position": [0, 0]}],
        "bonds": [],
    }


def _puzzle(name, *, products=1, arms=("arm1", "piston")):
    return {
        "source": {"name": f"{name}.puzzle"},
        "name": name.upper(),
        "availableParts": {"arms": list(arms), "glyphs": []},
        "reagents": [_molecule()],
        "products": [_molecule() for _ in range(products)],
    }


def _donor_solution(puzzle_file="donor"):
    def part(part_id, part_type, position, *, which=0, program=()):
        return {
            "id": part_id,
            "type": part_type,
            "enabled": True,
            "position": list(position),
            "length": 1,
            "rotation": 0,
            "which": which,
            "armNumber": 7,
            "program": list(program),
        }

    return {
        "source": {"sha256": "donor-sha"},
        "format": {"kind": "solution", "version": 7},
        "puzzleFile": puzzle_file,
        "name": "donor solution",
        "metrics": {},
        "unknownMetrics": [],
        "parts": [
            part("input", "input", (0, 0)),
            part("output", "out-std", (-1, 1), which=1),
            part("piston", "piston", (1, -1), program=(
                {"cycle": 2, "instruction": "grab"},
                {"cycle": 3, "instruction": "extend"},
                {"cycle": 4, "instruction": "reset"},
            )),
            part("arm", "arm1", (5, 5), program=(
                {"cycle": 0, "instruction": "grab"},
                {"cycle": 1, "instruction": "rotate_cw"},
                {"cycle": 2, "instruction": "reset"},
            )),
            part("unavailable", "arm6", (9, 9), program=(
                {"cycle": 0, "instruction": "grab"},
            )),
        ],
    }


def test_generates_minimal_donor_only_candidates_and_remaps_indices():
    target = _puzzle("target")
    donor = _puzzle("donor", products=2)
    candidates = generate_blind_transfer_candidates(target, donor, _donor_solution())

    assert len(candidates) == 2
    assert {candidate.source_part_ids[-1] for candidate in candidates} == {"piston", "arm"}
    assert all(candidate.donor_mapping == {"reagentIndex": 0, "productIndex": 1} for candidate in candidates)
    assert all(candidate.target_mapping == {"reagentIndex": 0, "productIndex": 0} for candidate in candidates)
    assert all(candidate.solution["puzzleFile"] == "target" for candidate in candidates)
    assert all(len(candidate.solution["parts"]) == 3 for candidate in candidates)
    assert all(candidate.solution["parts"][1]["which"] == 0 for candidate in candidates)
    assert all(candidate.solution["parts"][2]["armNumber"] == 0 for candidate in candidates)
    assert len({candidate.fingerprint for candidate in candidates}) == 2

    reparsed = parse_solution_bytes(write_solution_bytes(candidates[0].solution))
    assert reparsed["puzzleFile"] == "target"
    assert len(reparsed["parts"]) == 3


def test_contract_rejects_same_puzzle_family_even_with_copy_suffix():
    target = _puzzle("same (2)")
    donor = _puzzle("same")
    with pytest.raises(BlindTransferContractError, match="must differ"):
        validate_blind_transfer_contract(target, donor, _donor_solution("same"))


def test_contract_rejects_solution_that_does_not_belong_to_donor():
    with pytest.raises(BlindTransferContractError, match="expected 'donor'"):
        validate_blind_transfer_contract(
            _puzzle("target"),
            _puzzle("donor"),
            _donor_solution("third-puzzle"),
        )
