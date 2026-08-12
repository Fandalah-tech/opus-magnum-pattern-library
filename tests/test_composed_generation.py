from packages.opus_solver.generation import (
    _global_component_timing_portfolio,
    generate_composed_candidates,
)


def test_unsupported_puzzle_returns_clean_generation_report():
    puzzle = {"name": "Unsupported", "products": [], "reagents": [], "availableParts": {"glyphs": []}}
    result = generate_composed_candidates(puzzle, {"transitions": [], "convergenceMotifs": []}, {"fragments": []}, validate_engine=False)
    assert result["summary"]["supported"] is False
    assert result["summary"]["assemblyCandidateCount"] == 0
    assert result["candidates"] == []


def test_supported_plan_with_no_historical_assembly_returns_empty_candidates():
    puzzle = {
        "name": "Pair",
        "source": {"name": "P.puzzle"},
        "availableParts": {"glyphs": ["bonder", "calcification"]},
        "reagents": [
            {"atoms": [{"id": "a0", "element": "air", "position": [0, 0]}], "bonds": []},
            {"atoms": [{"id": "a0", "element": "fire", "position": [0, 0]}], "bonds": []},
        ],
        "products": [
            {
                "atoms": [
                    {"id": "p0", "element": "air", "position": [0, 0]},
                    {"id": "p1", "element": "salt", "position": [1, 0]},
                ],
                "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
            }
        ],
    }
    result = generate_composed_candidates(puzzle, {"transitions": [], "convergenceMotifs": []}, {"fragments": []}, validate_engine=False)
    assert result["summary"]["supported"] is True
    assert result["summary"]["assemblyCandidateCount"] == 0
    assert result["summary"]["serializableCount"] == 0


def test_global_oracle_portfolio_reallocates_capacity_between_assemblies():
    def variant(index, outcome, chemistry):
        return {
            "variantIndex": index,
            "oracleOutcome": outcome,
            "oracleValidation": {
                "valid": outcome == "complete",
                "issues": [],
            },
            "validation": {
                "complete": False,
                "totalDeficit": 6,
                "terminatedWithError": outcome != "cycle-limit",
                "completedCycles": 100,
                "distinctRequiredChemistryEventCount": chemistry,
                "requiredChemistryEventCount": chemistry,
            },
        }

    result = _global_component_timing_portfolio(
        [
            {
                "rank": 1,
                "componentTimingSearch": {
                    "variants": [variant(1, "collision", 3)],
                },
            },
            {
                "rank": 2,
                "componentTimingSearch": {
                    "variants": [
                        variant(2, "cycle-limit", 0),
                        variant(3, "cycle-limit", 0),
                    ],
                },
            },
        ],
        limit=2,
    )

    assert result["summary"]["returnedVariantCount"] == 2
    assert result["summary"]["returnedOracleOutcomeCounts"] == {"cycle-limit": 2}
    assert {item["candidateRank"] for item in result["variants"]} == {2}
