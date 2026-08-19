import json
from pathlib import Path
from unittest.mock import patch

from packages.opus_solver.manufacturing import ManufacturingPlan
from packages.opus_solver.objective_portfolio import (
    OBJECTIVES,
    generate_objective_candidates,
    objective_key,
    select_objective_winners,
)


def _plan() -> ManufacturingPlan:
    return ManufacturingPlan(
        strategy="corpus-derived-fragment-extraction-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=(),
        required_glyphs=(),
    )


def _base_solution() -> dict:
    return {
        "format": {"kind": "solution", "version": 7},
        "puzzleFile": "SOS_Salt_of_Saturn_by_Vinegar",
        "name": "base",
        "metrics": {},
        "unknownMetrics": [],
        "parts": [{
            "id": "base-part",
            "type": "arm1",
            "enabled": True,
            "position": [0, 0],
            "length": 1,
            "rotation": 0,
            "which": 0,
            "armNumber": 0,
            "program": [],
        }],
    }


def test_generator_materializes_independent_metric_architectures():
    puzzle = {"source": {"name": "SOS_Salt_of_Saturn_by_Vinegar (1).puzzle"}}
    complete = {"complete": True, "failureMode": None}
    portfolio = json.loads(
        Path("packages/opus_solver/data/sos_objective_blueprints.json").read_text(
            encoding="utf-8"
        )
    )
    with patch(
        "packages.opus_solver.objective_portfolio._generate_parallel_fragment_extraction_solution",
        return_value=_base_solution(),
    ), patch(
        "packages.opus_solver.objective_portfolio.validate_generated_solution",
        return_value=complete,
    ), patch(
        "packages.opus_solver.objective_portfolio.objective_portfolio_metadata",
        return_value=portfolio,
    ):
        candidates = generate_objective_candidates(puzzle, _plan())

    assert len(candidates) == 7
    assert len({candidate.fingerprint for candidate in candidates}) == 7
    assert {candidate.archetype for candidate in candidates} == {
        "single-arm-sequential",
        "periodic-pipeline",
        "balanced-cell",
        "parallel-throughput",
    }
    assert all(
        candidate.solution["puzzleFile"] == "SOS_Salt_of_Saturn_by_Vinegar"
        for candidate in candidates
    )


def test_objective_selection_scores_each_metric_independently():
    metrics = {
        "balanced-sum4-v1": dict(cost=145, cycles=95, area=84, instructions=19, rate=8),
        "single-arm-sequential-piston-v1": dict(cost=90, cycles=992, area=63, instructions=170, rate=170),
        "periodic-pipeline-v1": dict(cost=310, cycles=53, area=145, instructions=100, rate=9),
        "balanced-instructions-v1": dict(cost=165, cycles=83, area=109, instructions=15, rate=6),
        "parallel-throughput-v1": dict(cost=1970, cycles=239, area=859, instructions=115, rate=1),
        "single-arm-cost-minimum-v1": dict(cost=50, cycles=1722, area=3701, instructions=1722, rate=None),
        "single-piston-area-minimum-v1": dict(cost=90, cycles=2073, area=25, instructions=2094, rate=None),
    }
    records = [
        {
            "architectureId": architecture_id,
            "metrics": values,
            "oracleValidation": {"valid": True},
        }
        for architecture_id, values in metrics.items()
    ]
    winners = select_objective_winners(records)

    assert set(winners) == set(OBJECTIVES)
    assert winners["cost"]["architectureId"] == "single-arm-cost-minimum-v1"
    assert winners["area"]["architectureId"] == "single-piston-area-minimum-v1"
    assert winners["cycles"]["architectureId"] == "periodic-pipeline-v1"
    assert winners["rate"]["architectureId"] == "parallel-throughput-v1"
    assert winners["instructions"]["architectureId"] == "balanced-instructions-v1"
    assert winners["costarea"]["architectureId"] == "single-piston-area-minimum-v1"
    assert winners["costcycles"]["architectureId"] == "balanced-sum4-v1"
    assert winners["sum4"]["architectureId"] == "balanced-sum4-v1"
    assert objective_key("costarea", metrics["single-piston-area-minimum-v1"])[0] == 2250
    assert objective_key("costcycles", metrics["balanced-sum4-v1"])[0] == 240
    assert objective_key("sum4", metrics["balanced-sum4-v1"])[0] == 343
