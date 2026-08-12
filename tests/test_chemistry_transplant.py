from copy import deepcopy

import packages.opus_solver.chemistry_transplant as transplant_module
from packages.opus_solver.chemistry_transplant import (
    arm_grab_sites,
    enumerate_chemistry_transplants,
    mechanical_fingerprint,
    search_chemistry_transplant_candidates,
    transplant_operation_coverage,
)


def _puzzle():
    return {
        "reagents": [
            {
                "atoms": [
                    {"element": "fire", "position": [0, 0]},
                    {"element": "salt", "position": [1, 0]},
                ],
                "bonds": [
                    {"type": "normal", "from": [0, 0], "to": [1, 0]},
                ],
            },
        ],
    }


def _solution():
    return {
        "metrics": {},
        "parts": [
            {
                "id": "arm",
                "type": "arm1",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "program": [
                    {"cycle": 0, "instruction": "grab"},
                    {"cycle": 1, "instruction": "drop"},
                ],
            },
            {"id": "input", "type": "input", "position": [5, 5], "rotation": 0, "which": 0, "program": []},
            {"id": "unbond", "type": "unbonder", "position": [5, 5], "rotation": 0, "program": []},
            {"id": "duplicate", "type": "glyph-duplication", "position": [5, 5], "rotation": 0, "program": []},
            {"id": "prism", "type": "bonder-prisma", "position": [5, 5], "rotation": 0, "program": []},
        ],
    }


def test_grab_sites_are_replayed_from_the_frozen_mechanism():
    assert arm_grab_sites(_solution(), max_cycles=2) == [
        {
            "cycle": 0,
            "partId": "arm",
            "branchIndex": 0,
            "position": [1, 0],
        },
    ]


def test_transplant_enumeration_is_deterministic_and_preserves_mechanics():
    source = _solution()
    before = mechanical_fingerprint(source)
    first = enumerate_chemistry_transplants(_puzzle(), source, max_grab_cycles=2, limit=6)
    second = enumerate_chemistry_transplants(_puzzle(), source, max_grab_cycles=2, limit=6)

    assert len(first) == 6
    assert [item["placement"] for item in first] == [item["placement"] for item in second]
    assert all(item["mechanicsPreserved"] for item in first)
    assert all(mechanical_fingerprint(item["solution"]) == before for item in first)
    assert mechanical_fingerprint(source) == before
    assert source["parts"][1]["position"] == [5, 5]


def test_operation_coverage_collapses_bond_event_variants():
    validation = {
        "eventCounts": {
            "bond-removed": 2,
            "atom-duplicated": 1,
            "floating-bond-created": 4,
            "floating-bond-settled": 4,
        },
    }
    assert transplant_operation_coverage(validation) == ["unbond", "duplicate", "bond"]


def test_search_promotes_oracle_stable_active_transplant(monkeypatch):
    variants = []
    for index in range(3):
        solution = {"marker": index, "parts": deepcopy(_solution()["parts"])}
        variants.append({
            "solution": solution,
            "placement": {"prismChannel": ("black", "red", "yellow")[index]},
            "mechanicalFingerprint": "frozen",
            "mechanicsPreserved": True,
        })

    monkeypatch.setattr(
        transplant_module,
        "enumerate_chemistry_transplants",
        lambda *_args, **_kwargs: variants,
    )
    monkeypatch.setattr(
        transplant_module,
        "serialize_candidate_roundtrip",
        lambda solution: {"parsed": solution, "diagnostics": {"roundTripClean": True}},
    )

    def local_validation(_puzzle, solution, max_cycles=None):
        marker = solution["marker"]
        return {
            "terminatedWithError": marker == 2,
            "completedCycles": max_cycles,
            "distinctRequiredChemistryEventCount": 3,
            "manipulationEventCount": 4,
            "eventCounts": {
                "atom-grabbed": 1,
                "input-spawned": 1,
                "bond-removed": 1,
                "atom-duplicated": 1,
                "bond-created": 1,
            },
        }

    monkeypatch.setattr(transplant_module, "validate_generated_solution", local_validation)

    def oracle(solution):
        if solution["marker"] == 0:
            return {
                "valid": False,
                "rawOutput": "solution did not complete within cycle limit",
                "issues": [],
            }
        return {
            "valid": False,
            "rawOutput": "collision during motion phase on cycle 3",
            "issues": [{"cycle": 3}],
        }

    source = {
        "solution": _solution(),
        "candidateRank": 1,
        "sourceVariantIndex": 0,
        "oracleOutcome": "cycle-limit",
    }
    result = search_chemistry_transplant_candidates(
        _puzzle(),
        [source],
        source_limit=1,
        variant_limit=3,
        result_limit=2,
        local_cycles=12,
        oracle_promotion_limit=3,
        oracle_validator=oracle,
        oracle_workers=10,
    )

    assert result["summary"]["searchedVariantCount"] == 3
    assert result["summary"]["oracleOutcomeCounts"] == {
        "collision": 2,
        "cycle-limit": 1,
    }
    assert result["summary"]["oracleStableActiveFullOperationVariantCount"] == 1
    assert result["summary"]["hasOracleStableActiveTransplant"] is True
    assert result["variants"][0]["oracleOutcome"] == "cycle-limit"
