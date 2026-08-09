from packages.opus_solver import mechanism_compatibility, puzzle_similarity, rank_mechanisms


def _features(*, product_element="salt", reagent_element="salt", glyphs=None, production=False):
    glyphs = glyphs or ["equilibrium", "bonder"]
    return {
        "production": production,
        "outputScale": 1,
        "availableArms": ["arm1", "arm2", "arm3", "arm6", "piston"],
        "availableGlyphs": glyphs,
        "reagents": {
            "count": 1,
            "atomCounts": [1],
            "bondCounts": [0],
            "elements": {reagent_element: 1},
            "bonds": {},
            "moleculeSignatures": [f"reagent-{reagent_element}"],
        },
        "products": {
            "count": 1,
            "atomCounts": [1],
            "bondCounts": [0],
            "elements": {product_element: 1},
            "bonds": {},
            "moleculeSignatures": [f"product-{product_element}"],
        },
    }


def test_puzzle_similarity_prefers_matching_chemistry():
    target = _features(product_element="gold", reagent_element="lead")
    close = _features(product_element="gold", reagent_element="lead")
    far = _features(product_element="water", reagent_element="air")

    assert puzzle_similarity(target, close)["score"] > puzzle_similarity(target, far)["score"]
    assert puzzle_similarity(target, close)["score"] == 1.0


def test_mechanism_compatibility_rejects_missing_known_glyph():
    target = _features(glyphs=["equilibrium", "bonder"])
    mechanism = {"partTypes": ["arm1", "bonder", "purification"]}

    result = mechanism_compatibility(target, mechanism)

    assert result["compatible"] is False
    assert result["missingParts"] == ["purification"]


def test_pipe_requires_production_mode():
    mechanism = {"partTypes": ["arm1", "pipe"]}

    assert mechanism_compatibility(_features(production=False), mechanism)["compatible"] is False
    assert mechanism_compatibility(_features(production=True), mechanism)["compatible"] is True


def test_rank_mechanisms_joins_feature_index_and_filters_incompatible():
    target = _features(product_element="gold", reagent_element="lead")
    feature_index = {
        "puzzles": [
            {
                "sourceFile": "chapter/P001.puzzle",
                "name": "Close puzzle",
                "fingerprint": "fp-close",
                "features": _features(product_element="gold", reagent_element="lead"),
            },
            {
                "sourceFile": "chapter/P002.puzzle",
                "name": "Far puzzle",
                "fingerprint": "fp-far",
                "features": _features(product_element="water", reagent_element="air"),
            },
        ]
    }
    solver_index = {
        "puzzles": [
            {
                "puzzleKey": "P001",
                "mechanisms": [
                    {"canonicalMechanismHash": "good", "partTypes": ["arm1", "bonder"]},
                    {"canonicalMechanismHash": "blocked", "partTypes": ["arm1", "purification"]},
                ],
            },
            {
                "puzzleKey": "P002",
                "mechanisms": [
                    {"canonicalMechanismHash": "far", "partTypes": ["arm1", "bonder"]},
                ],
            },
        ]
    }

    ranked = rank_mechanisms(target, feature_index, solver_index, limit=10)

    assert [item["mechanism"]["canonicalMechanismHash"] for item in ranked] == ["good", "far"]
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_mechanisms_can_surface_incompatible_candidates_for_diagnostics():
    target = _features(glyphs=["equilibrium", "bonder"])
    feature_index = {
        "puzzles": [{
            "sourceFile": "P001.puzzle",
            "name": "Puzzle",
            "fingerprint": "fp",
            "features": target,
        }]
    }
    solver_index = {
        "puzzles": [{
            "puzzleKey": "P001",
            "mechanisms": [{"canonicalMechanismHash": "blocked", "partTypes": ["purification"]}],
        }]
    }

    ranked = rank_mechanisms(target, feature_index, solver_index, include_incompatible=True)

    assert len(ranked) == 1
    assert ranked[0]["compatibility"]["compatible"] is False
