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


def test_repair_choices_include_other_engine_complete_sources_after_coherent_preferred():
    candidate = _candidate()
    candidate["convergence"]["samples"] = [{
        "inputs": [{
            "sourceRole": "conversion",
            "sourceMechanismHash": "conversion-hash",
            "relativeTransforms": [T0],
        }],
    }]
    candidate["convergence"]["repairSamples"] = [{
        "inputs": [{
            "sourceRole": "conversion",
            "sourceMechanismHash": "conversion-hash",
            "relativeTransforms": [T1],
        }],
    }]
    edge = candidate["branches"][0][0]
    edge["relativeTransforms"] = {
        "preferred": E0,
        "variants": [{"relativeTransform": E0, "observationCount": 3}],
    }
    edge["repairRelativeTransforms"] = {
        "preferred": E1,
        "variants": [{"relativeTransform": E1, "observationCount": 5}],
    }

    slots = transform_slots(candidate)

    assert [choice["transform"] for choice in slots[0]["choices"]] == [T0, T1]
    assert [choice["transform"] for choice in slots[1]["choices"]] == [E0, E1]
    assert slots[1]["choices"][1]["repairEvidence"] == "other-engine-complete-source"


def test_synthetic_repair_adds_local_hex_translations_and_rotations():
    slots = transform_slots(
        _candidate(),
        synthetic_translation_radius=1,
        synthetic_rotation_radius=1,
    )

    first_choices = slots[0]["choices"]
    synthetic = [choice for choice in first_choices if choice.get("repairEvidence") == "local-geometric-perturbation"]
    assert synthetic
    assert any(choice["translationOffset"] != [0, 0] for choice in synthetic)
    assert any(choice["rotationOffset"] != 0 for choice in synthetic)
    assert first_choices[0]["transform"] == T0
