from packages.opus_solver.outcome_learning import (
    aggregate_repair_outcomes,
    build_outcome_index,
    generation_outcome_records,
    merge_outcome_records,
)


def _puzzle():
    return {
        "name": "Learning pair",
        "production": False,
        "outputScale": 1,
        "availableParts": {"arms": ["arm1"], "glyphs": ["bonder", "calcification"]},
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


def _assembly():
    return {
        "convergence": {
            "targetRole": "bonding",
            "targetMechanismHash": "bond-hash",
            "inputs": [
                {"sourceRole": "feed", "sourceMechanismHash": "feed-a", "relations": ["bond-created"]},
                {"sourceRole": "conversion", "sourceMechanismHash": "calc-hash", "relations": ["bond-created"]},
            ],
        },
        "branches": [[], []],
        "tail": [
            {
                "sourceRole": "bonding",
                "sourceMechanismHash": "bond-hash",
                "targetRole": "output",
                "targetMechanismHash": "out-hash",
                "relation": "delivered",
            }
        ],
    }


def _generation(timing_complete=True):
    return {
        "plan": {"strategy": "bonded-pair-v1"},
        "candidates": [
            {
                "rank": 1,
                "assemblyScore": 0.9,
                "assembly": _assembly(),
                "layoutSummary": {
                    "exactStaticConflictCount": 0,
                    "approximateStaticConflictCount": 1,
                    "armWorkspaceOverlapCount": 2,
                },
                "engineValidation": {
                    "complete": False,
                    "failureMode": "no-product-delivered",
                    "totalDelivered": 0,
                    "totalDeficit": 6,
                    "completedCycles": 30,
                },
                "repairPolicy": {"order": ["timing", "geometry"], "preferred": "timing"},
                "repairSucceededWith": "timing" if timing_complete else None,
                "temporalSearch": {
                    "summary": {
                        "searchedVariantCount": 9,
                        "completeVariantCount": 1 if timing_complete else 0,
                        "hasCompleteSolution": timing_complete,
                    },
                    "variants": [
                        {
                            "variantIndex": 2,
                            "displacement": 1,
                            "solution": {"parts": ["large payload must not persist"]},
                            "validation": {
                                "complete": timing_complete,
                                "failureMode": None if timing_complete else "no-product-delivered",
                                "totalDelivered": 6 if timing_complete else 0,
                                "totalDeficit": 0 if timing_complete else 6,
                                "completedCycles": 50,
                            },
                        }
                    ],
                },
            }
        ],
    }


def test_generation_outcome_is_compact_and_stable():
    first = generation_outcome_records(_puzzle(), _generation())[0]
    second = generation_outcome_records(_puzzle(), _generation())[0]
    assert first["id"] == second["id"]
    assert first["solved"] is True
    assert first["bestProgressSource"] == "timing"
    assert "solution" not in first
    assert "solution" not in repr(first)


def test_repair_attempt_and_layout_signals_are_retained():
    record = generation_outcome_records(_puzzle(), _generation())[0]
    assert record["layoutSignals"]["approximateStaticConflictCount"] == 1
    assert record["attempts"] == [
        {
            "repair": "timing",
            "searchedVariantCount": 9,
            "completeVariantCount": 1,
            "succeeded": True,
        }
    ]


def test_merge_prefers_better_progress_for_same_stable_outcome():
    failed = generation_outcome_records(_puzzle(), _generation(timing_complete=False))[0]
    solved = generation_outcome_records(_puzzle(), _generation(timing_complete=True))[0]
    assert failed["id"] == solved["id"]
    merged = merge_outcome_records([failed], [solved])
    assert len(merged) == 1
    assert merged[0]["solved"] is True


def test_aggregate_builds_failure_route_prior():
    record = generation_outcome_records(_puzzle(), _generation())[0]
    aggregate = aggregate_repair_outcomes([record])
    prior = aggregate["priors"][0]
    assert prior["failureMode"] == "no-product-delivered"
    assert prior["firstRepair"] == "timing"
    assert prior["solveRate"] == 1.0
    assert prior["repairAttempts"] == {"timing": 1}
    assert prior["repairSuccesses"] == {"timing": 1}


def test_build_outcome_index_merges_existing_records():
    initial = build_outcome_index(_puzzle(), _generation(timing_complete=False))
    updated = build_outcome_index(_puzzle(), _generation(timing_complete=True), existing_index=initial)
    assert updated["summary"]["outcomeCount"] == 1
    assert updated["summary"]["solvedOutcomeCount"] == 1
    assert updated["outcomes"][0]["solved"] is True


def test_component_timing_oracle_outcomes_are_learned_compactly():
    generation = _generation(timing_complete=False)
    generation["candidates"][0]["componentTimingSearch"] = {
        "summary": {
            "searchedVariantCount": 12,
            "completeVariantCount": 0,
            "hasCompleteSolution": False,
            "oracleValidatedVariantCount": 12,
            "oracleCompleteVariantCount": 0,
            "oracleOutcomeCounts": {"collision": 7, "cycle-limit": 5},
        },
        "variants": [],
    }

    record = generation_outcome_records(_puzzle(), generation)[0]
    component_attempt = next(
        item for item in record["attempts"] if item["repair"] == "component-timing"
    )

    assert component_attempt["oracleValidatedVariantCount"] == 12
    assert component_attempt["oracleCompleteVariantCount"] == 0
    assert component_attempt["oracleOutcomeCounts"] == {
        "collision": 7,
        "cycle-limit": 5,
    }
