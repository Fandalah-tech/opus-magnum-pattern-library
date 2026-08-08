from packages.opus_solver.cycle_bounds import overlap_cycle_bound
from packages.opus_solver.fragment_planner import analyze_two_fragment_assembly


def _triangle(atom_element: str) -> dict:
    # Up/down orientation is irrelevant to the planner because embeddings may
    # rotate, but this is the same three-hex triangle shape visible in the
    # Aqueous Dagger reagents.
    return {
        "atoms": [
            {"id": "a0", "element": atom_element, "position": [0, 0]},
            {"id": "a1", "element": atom_element, "position": [-1, 1]},
            {"id": "a2", "element": atom_element, "position": [0, 1]},
        ],
        "bonds": [
            {"type": "normal", "from": [0, 0], "to": [-1, 1]},
            {"type": "normal", "from": [0, 0], "to": [0, 1]},
            {"type": "normal", "from": [-1, 1], "to": [0, 1]},
        ],
    }


def _aqueous_dagger_family_puzzle() -> dict:
    reagent0 = _triangle("water")
    reagent0["id"] = "reagent-0"
    reagent1 = _triangle("water")
    reagent1["id"] = "reagent-1"

    return {
        "name": "AQUEOUS DAGGER FAMILY",
        "availableParts": {
            "arms": ["arm1", "arm2", "arm3", "arm6", "piston"],
            "glyphs": ["bonder", "unbonder", "multibonder", "calcification"],
        },
        "reagents": [reagent0, reagent1],
        "products": [{
            "id": "product-0",
            "atoms": [
                {"id": "s0", "element": "salt", "position": [0, 0]},
                {"id": "s1", "element": "salt", "position": [-1, 1]},
                {"id": "s2", "element": "salt", "position": [0, 1]},
                {"id": "w0", "element": "water", "position": [1, 0]},
                {"id": "w1", "element": "water", "position": [2, -1]},
                {"id": "w2", "element": "water", "position": [2, 0]},
            ],
            "bonds": [
                {"type": "normal", "from": [0, 0], "to": [-1, 1]},
                {"type": "normal", "from": [0, 0], "to": [0, 1]},
                {"type": "normal", "from": [-1, 1], "to": [0, 1]},
                {"type": "normal", "from": [1, 0], "to": [2, -1]},
                {"type": "normal", "from": [1, 0], "to": [2, 0]},
                {"type": "normal", "from": [2, -1], "to": [2, 0]},
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [0, 1], "to": [1, 0]},
            ],
        }],
        "outputScale": 1,
        "production": False,
    }


def test_two_fragment_planner_preserves_reagent_submolecules() -> None:
    plan = analyze_two_fragment_assembly(_aqueous_dagger_family_puzzle())

    assert plan.supported is True
    assert plan.strategy == "two-fragment-assembly-v1"
    assert len(plan.embeddings) == 2
    assert sorted(len(item.conversions) for item in plan.embeddings) == [0, 3]
    assert len(plan.cross_bonds) == 2
    assert plan.required_glyphs == ("bonder", "glyph-calcification")


def test_aqueous_family_proves_input_bound_n_equals_six() -> None:
    plan = analyze_two_fragment_assembly(_aqueous_dagger_family_puzzle())

    assert plan.input_pulls_per_product == (1, 1)
    assert plan.input_bound_n(target_products=6) == 6


def test_aqueous_family_classical_bound_is_fifteen_when_l_is_two() -> None:
    plan = analyze_two_fragment_assembly(_aqueous_dagger_family_puzzle())

    assert plan.classical_cycle_bound(latency=2, target_products=6) == 15


def test_aqueous_family_overlap_bound_is_eight_when_n_six_l_two_d_zero() -> None:
    plan = analyze_two_fragment_assembly(_aqueous_dagger_family_puzzle())
    bound = overlap_cycle_bound(plan, latency=2, double_consumptions=0, target_products=6)

    assert bound.n == 6
    assert bound.d == 0
    assert bound.latency == 2
    assert bound.cycles == 8
