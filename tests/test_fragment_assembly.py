from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.manufacturing import ManufacturingOperation, ManufacturingPlan


def _plan():
    return ManufacturingPlan(
        strategy="test",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=(
            ManufacturingOperation(id="s1", kind="source", inputs=(), outputs=("a",)),
            ManufacturingOperation(id="s2", kind="source", inputs=(), outputs=("b",)),
            ManufacturingOperation(id="c", kind="transform", inputs=("a",), outputs=("c",), glyph="glyph-calcification"),
            ManufacturingOperation(id="b", kind="bond", inputs=("c", "b"), outputs=("m",), glyph="bonder"),
            ManufacturingOperation(id="d", kind="deliver", inputs=("m",), outputs=("o",)),
        ),
        required_glyphs=("bonder", "glyph-calcification"),
    )


def _edge(sr, sh, tr, th, relation):
    return {
        "sourceRole": sr,
        "sourceMechanismHash": sh,
        "targetRole": tr,
        "targetMechanismHash": th,
        "relation": relation,
        "observationCount": 5,
        "sourcePuzzleCount": 3,
        "sourceSolutionCount": 4,
    }


def test_two_feed_convergence_can_be_marked_assembly_complete():
    flow = {
        "transitions": [
            _edge("feed", "fa", "conversion", "calc", "calcify"),
            _edge("bonding", "bond", "output", "out", "delivered"),
        ],
        "convergenceMotifs": [
            {
                "targetRole": "bonding",
                "targetMechanismHash": "bond",
                "inputCount": 2,
                "inputs": [
                    {"sourceRole": "conversion", "sourceMechanismHash": "calc", "relations": ["bond-created"]},
                    {"sourceRole": "feed", "sourceMechanismHash": "fb", "relations": ["bond-created"]},
                ],
                "observationCount": 3,
                "sourcePuzzleCount": 2,
                "sourceSolutionCount": 3,
            }
        ],
    }
    ranked = rank_fragment_assemblies(_plan(), flow)
    assert len(ranked) == 1
    assert ranked[0]["assemblyComplete"] is True
    assert ranked[0]["observedRelations"] == {"bond-created": 1, "calcify": 1, "delivered": 1}


def test_convergence_with_too_few_inputs_is_rejected():
    flow = {
        "transitions": [_edge("bonding", "bond", "output", "out", "delivered")],
        "convergenceMotifs": [
            {
                "targetRole": "bonding",
                "targetMechanismHash": "bond",
                "inputCount": 1,
                "inputs": [{"sourceRole": "feed", "sourceMechanismHash": "f", "relations": ["bond-created"]}],
                "observationCount": 10,
            }
        ],
    }
    assert rank_fragment_assemblies(_plan(), flow) == []
