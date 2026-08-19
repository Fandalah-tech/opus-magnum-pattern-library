import json
from pathlib import Path
from unittest.mock import patch

from packages.opus_solver.manufacturing import ManufacturingPlan
from packages.opus_solver.objective_portfolio import OBJECTIVES, generate_objective_candidates
from packages.opus_solver.portfolio_learning import (
    bounded_worker_count,
    learn_objective_blueprint_portfolio,
)


def _puzzle() -> dict:
    return {
        "source": {"name": "learned-example (1).puzzle"},
        "name": "LEARNED EXAMPLE",
        "production": False,
        "outputScale": 1,
        "availableParts": {
            "arms": ["arm1", "piston"],
            "glyphs": ["equilibrium", "bonder", "unbonder", "duplication"],
        },
        "reagents": [{
            "atoms": [{"element": "fire", "position": [0, 0]}],
            "bonds": [],
        }],
        "products": [{
            "atoms": [{"element": "fire", "position": [0, 0]}],
            "bonds": [],
        }],
    }


def _solution(index: int, *, long_program: bool = False) -> dict:
    count = 30 if long_program else index + 2
    return {
        "format": {"kind": "solution", "version": 7},
        "puzzleFile": "learned-example",
        "name": f"candidate-{index}",
        "metrics": {},
        "unknownMetrics": [],
        "parts": [{
            "id": f"arm-{index}",
            "type": "arm1",
            "enabled": True,
            "position": [index * 3, -index],
            "length": 1,
            "rotation": index % 6,
            "which": 0,
            "armNumber": index + 1,
            "program": [
                {"cycle": cycle, "instruction": "grab" if cycle % 2 == 0 else "drop"}
                for cycle in range(count)
            ],
        }],
    }


def _records() -> list[dict]:
    metrics = [
        {"cost": 50, "cycles": 1000, "area": 300, "instructions": 300, "rate": None},
        {"cost": 90, "cycles": 600, "area": 20, "instructions": 300, "rate": 100},
        {"cost": 500, "cycles": 20, "area": 100, "instructions": 200, "rate": 3},
        {"cost": 5000, "cycles": 60, "area": 1000, "instructions": 400, "rate": 1},
        {"cost": 500, "cycles": 300, "area": 200, "instructions": 2, "rate": 100},
        {"cost": 90, "cycles": 90, "area": 80, "instructions": 50, "rate": 8},
    ]
    return [
        {
            "valid": True,
            "solution": _solution(index, long_program=index == 0),
            "metrics": values,
            "sourceName": f"candidate-{index}.solution",
            "sourcePath": f"author-{index}/candidate.solution",
        }
        for index, values in enumerate(metrics)
    ]


def test_learner_selects_and_deduplicates_all_objective_winners() -> None:
    portfolio = learn_objective_blueprint_portfolio(
        _puzzle(),
        _records(),
        puzzle_strategy="learned-example-v1",
        source={"kind": "external-reference-only"},
    )

    focused = {
        objective
        for blueprint in portfolio["blueprints"]
        for objective in blueprint["objectives"]
    }
    assert focused == set(OBJECTIVES)
    assert len(portfolio["blueprints"]) == 6
    assert portfolio["baselineArchitectureId"] in {
        blueprint["id"] for blueprint in portfolio["blueprints"]
    }
    cost = next(
        blueprint for blueprint in portfolio["blueprints"] if "cost" in blueprint["objectives"]
    )
    assert "programTape" in cost["parts"][0]
    assert "program" not in cost["parts"][0]


def test_external_registry_materializes_for_matching_puzzle(tmp_path: Path) -> None:
    puzzle = _puzzle()
    portfolio = learn_objective_blueprint_portfolio(
        puzzle,
        _records(),
        puzzle_strategy="learned-example-v1",
        source={"kind": "external-reference-only"},
    )
    registry = tmp_path / "learned.json"
    registry.write_text(json.dumps(portfolio), encoding="utf-8")
    plan = ManufacturingPlan(
        strategy="learned-example-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=(),
        required_glyphs=(),
    )

    with patch(
        "packages.opus_solver.objective_portfolio.validate_generated_solution",
        return_value={"complete": True, "failureMode": None},
    ):
        candidates = generate_objective_candidates(
            puzzle,
            plan,
            blueprint_paths=(registry,),
        )

    assert len(candidates) == 6
    assert len({candidate.fingerprint for candidate in candidates}) == 6
    assert all(
        candidate.solution["puzzleFile"] == "learned-example"
        for candidate in candidates
    )


def test_worker_count_never_exceeds_user_cpu_limit() -> None:
    assert bounded_worker_count(None, cpu_count=20) == 10
    assert bounded_worker_count(50, cpu_count=20) == 10
    assert bounded_worker_count(4, cpu_count=20) == 4
    assert bounded_worker_count(10, cpu_count=6) == 6
