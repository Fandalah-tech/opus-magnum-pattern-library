from packages.opus_solver.fragment_planner import analyze_two_fragment_assembly


def _triangle(atom_element: str) -> dict:
    return {
        "atoms": [
            {"id": "a0", "element": atom_element, "position": [0, 0]},
            {"id": "a1", "element": atom_element, "position": [1, 0]},
            {"id": "a2", "element": atom_element, "position": [0, 1]},
        ],
        "bonds": [
            {"type": "normal", "from": [0, 0], "to": [1, 0]},
            {"type": "normal", "from": [0, 0], "to": [0, 1]},
            {"type": "normal", "from": [1, 0], "to": [0, 1]},
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
            "glyphs": ["bonder", "calcification"],
        },
        "reagents": [reagent0, reagent1],
        "products": [{
            "id": "product-0",
            "atoms": [
                {"id": "s0", "element": "salt", "position": [0, 0]},
                {"id": "s1", "element": "salt", "position": [1, 0]},
                {"id": "s2", "element": "salt", "position": [0, 1]},
                {"id": "w0", "element": "water", "position": [2, 0]},
                {"id": "w1", "element": "water", "position": [3, 0]},
                {"id": "w2", "element": "water", "position": [2, 1]},
            ],
            "bonds": [
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [0, 0], "to": [0, 1]},
                {"type": "normal", "from": [1, 0], "to": [0, 1]},
                {"type": "normal", "from": [2, 0], "to": [3, 0]},
                {"type": "normal", "from": [2, 0], "to": [2, 1]},
                {"type": "normal", "from": [3, 0], "to": [2, 1]},
                {"type": "normal", "from": [1, 0], "to": [2, 0]},
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
    assert len(plan.cross_bonds) == 1
    assert plan.required_glyphs == ("bonder", "glyph-calcification")


def test_aqueous_family_proves_input_bound_n_equals_six() -> None:
    plan = analyze_two_fragment_assembly(_aqueous_dagger_family_puzzle())

    assert plan.input_pulls_per_product == (1, 1)
    assert plan.input_bound_n(target_products=6) == 6


def test_aqueous_family_classical_bound_is_fifteen_when_l_is_two() -> None:
    plan = analyze_two_fragment_assembly(_aqueous_dagger_family_puzzle())

    assert plan.classical_cycle_bound(latency=2, target_products=6) == 15
