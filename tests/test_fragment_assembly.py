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


def test_assembly_prefers_one_engine_coherent_source_solution():
    transform = {"frame": "source-anchor-local", "delta": [2, -1], "rotationDelta": 1}
    timing = {"frame": "source-fragment-program-start", "programStartDelta": 3}
    calc_edge = _edge("feed", "fa", "conversion", "calc", "calcify")
    calc_edge["solutionVariants"] = [{
        "solutionPath": "coherent.solution",
        "relativeTransform": transform,
        "relativeTiming": timing,
        "observationCount": 2,
    }]
    output_edge = _edge("bonding", "bond", "output", "out", "delivered")
    output_edge["solutionVariants"] = [{
        "solutionPath": "coherent.solution",
        "relativeTransform": transform,
        "relativeTiming": timing,
        "observationCount": 2,
    }]
    flow = {
        "transitions": [calc_edge, output_edge],
        "convergenceMotifs": [{
            "targetRole": "bonding",
            "targetMechanismHash": "bond",
            "inputCount": 2,
            "inputs": [
                {"sourceRole": "conversion", "sourceMechanismHash": "calc", "relations": ["bond-created"]},
                {"sourceRole": "feed", "sourceMechanismHash": "fb", "relations": ["bond-created"]},
            ],
            "observationCount": 1,
            "solutionSamples": [{
                "solutionPath": "coherent.solution",
                "inputs": [
                    {"sourceRole": "conversion", "sourceMechanismHash": "calc", "relativeTransforms": [transform], "relativeTimings": [timing]},
                    {"sourceRole": "feed", "sourceMechanismHash": "fb", "relativeTransforms": [transform], "relativeTimings": [timing]},
                ],
            }],
        }],
    }
    ranked = rank_fragment_assemblies(_plan(), flow)
    assert len(ranked) == 1
    assert ranked[0]["coherentSourceSolution"] == "coherent.solution"
    assert ranked[0]["branches"][0][0]["relativeTransform"] == transform
    assert ranked[0]["tail"][0]["relativeTiming"] == timing


def test_three_input_prism_generalizes_an_unobserved_channel():
    plan = ManufacturingPlan(
        strategy="triplex-test",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=(
            ManufacturingOperation(id="source", kind="source", inputs=(), outputs=("raw",)),
            ManufacturingOperation(id="split", kind="unbond", inputs=("raw",), outputs=("a", "b"), glyph="unbonder"),
            ManufacturingOperation(id="copy", kind="duplicate", inputs=("a",), outputs=("a", "c"), glyph="glyph-duplication"),
            ManufacturingOperation(
                id="prism",
                kind="bond",
                inputs=("a", "b", "c"),
                outputs=("product",),
                glyph="bonder-prisma",
                metadata={"triplexChannels": ["red", "black", "yellow"]},
            ),
            ManufacturingOperation(id="deliver", kind="deliver", inputs=("product",), outputs=("out",)),
        ),
        required_glyphs=("unbonder", "duplication", "triplex-bonder"),
    )
    flow = {
        "transitions": [
            _edge("feed", "feed", "process", "split", "bond-removed"),
            _edge("process", "split", "conversion", "copy", "duplicate"),
            _edge("bonding", "prism", "output", "out", "delivered"),
        ],
        "convergenceMotifs": [{
            "targetRole": "bonding",
            "targetMechanismHash": "prism",
            "inputCount": 3,
            "inputs": [
                {"sourceRole": "conversion", "sourceMechanismHash": "copy", "relations": ["triplex-bond-created:red"]},
                {"sourceRole": "process", "sourceMechanismHash": "split", "relations": ["triplex-bond-created:black"]},
                {"sourceRole": "feed", "sourceMechanismHash": "feed", "relations": ["triplex-bond-created:red"]},
            ],
            "observationCount": 2,
        }],
    }

    ranked = rank_fragment_assemblies(plan, flow)

    assert len(ranked) == 1
    assert ranked[0]["inferredRelations"] == {"triplex-bond-created:yellow": 1}
    assert ranked[0]["relationCoverageEvidence"] == "engine-observed-plus-prism-physics"
