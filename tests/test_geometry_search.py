from packages.opus_solver.geometry_search import enumerate_transform_variants, transform_slots
from packages.opus_solver.layout import materialize_assembly_layout


T0 = {"delta": [1, 0], "rotationDelta": 0}
T1 = {"delta": [2, 0], "rotationDelta": 0}
E0 = {"delta": [0, 1], "rotationDelta": 1}
E1 = {"delta": [0, 2], "rotationDelta": 1}


def _edge():
    return {
        "sourceRole": "feed",
        "sourceMechanismHash": "feed-hash",
        "targetRole": "conversion",
        "targetMechanismHash": "conversion-hash",
        "relation": "calcify",
        "relativeTransforms": {
            "preferred": E0,
            "variantCount": 2,
            "variants": [
                {"relativeTransform": E0, "observationCount": 8},
                {"relativeTransform": E1, "observationCount": 2},
            ],
        },
    }


def _candidate():
    return {
        "convergence": {
            "targetRole": "bonding",
            "targetMechanismHash": "bond-hash",
            "inputs": [
                {"sourceRole": "conversion", "sourceMechanismHash": "conversion-hash", "relations": ["bond-created"]},
            ],
            "samples": [
                {
                    "inputs": [
                        {
                            "sourceRole": "conversion",
                            "sourceMechanismHash": "conversion-hash",
                            "relativeTransforms": [T0, T1],
                        }
                    ]
                },
                {
                    "inputs": [
                        {
                            "sourceRole": "conversion",
                            "sourceMechanismHash": "conversion-hash",
                            "relativeTransforms": [T0],
                        }
                    ]
                },
            ],
        },
        "branches": [[_edge()]],
        "tail": [],
    }


def _fragment(role, mechanism, part_type):
    return {
        "role": role,
        "canonicalMechanismHash": mechanism,
        "representativeGeometry": {
            "anchorPartType": part_type,
            "parts": [
                {
                    "id": "original",
                    "type": part_type,
                    "enabled": True,
                    "position": [0, 0],
                    "rotation": 0,
                    "length": 1,
                    "which": 0,
                    "program": [],
                }
            ],
        },
    }


def test_transform_slots_expose_convergence_and_branch_edge_choices():
    slots = transform_slots(_candidate())
    assert [item["slot"] for item in slots] == [
        "branch-0:convergence-input",
        "branch-0:edge-0",
    ]
    assert len(slots[0]["choices"]) == 2
    assert len(slots[1]["choices"]) == 2


def test_transform_variants_keep_historical_combination_first():
    variants = enumerate_transform_variants(_candidate(), per_slot_limit=2, limit=10)
    assert variants
    assert variants[0]["overrides"] == {}
    assert variants[0]["displacement"] == 0
    assert any(item["displacement"] == 1 for item in variants[1:])


def test_transform_variant_enumeration_is_deterministic_and_deduplicated():
    first = enumerate_transform_variants(_candidate(), per_slot_limit=2, limit=10)
    second = enumerate_transform_variants(_candidate(), per_slot_limit=2, limit=10)
    assert first == second
    signatures = [repr(sorted(item["overrides"].items())) for item in first]
    assert len(signatures) == len(set(signatures))


def test_layout_override_moves_selected_convergence_input():
    candidate = {
        "convergence": {
            "targetRole": "bonding",
            "targetMechanismHash": "bond-hash",
            "inputs": [{"sourceRole": "conversion", "sourceMechanismHash": "conversion-hash"}],
            "samples": [{"inputs": [{"sourceRole": "conversion", "sourceMechanismHash": "conversion-hash", "relativeTransforms": [T0]}]}],
        },
        "branches": [[]],
        "tail": [],
    }
    fragment_index = {
        "fragments": [
            _fragment("bonding", "bond-hash", "bonder"),
            _fragment("conversion", "conversion-hash", "glyph-calcification"),
        ]
    }
    base = materialize_assembly_layout(candidate, fragment_index)
    moved = materialize_assembly_layout(
        candidate,
        fragment_index,
        transform_overrides={"branch-0:convergence-input": T1},
    )
    base_input = next(item for item in base["placements"] if item["instanceId"] == "branch-0:input")
    moved_input = next(item for item in moved["placements"] if item["instanceId"] == "branch-0:input")
    assert base_input["anchorPosition"] == [-1, 0]
    assert moved_input["anchorPosition"] == [-2, 0]
    assert moved["summary"]["transformOverrideCount"] == 1
