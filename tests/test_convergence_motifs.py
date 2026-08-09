from packages.opus_analysis.convergence import canonical_convergence_key, extract_convergence_motifs


def _node(anchor, role, mechanism):
    return {"anchorPartId": anchor, "role": role, "canonicalMechanismHash": mechanism}


def _edge(source, target, source_role, target_role, source_hash, target_hash, relation):
    return {
        "sourceAnchorPartId": source,
        "targetAnchorPartId": target,
        "sourceRole": source_role,
        "targetRole": target_role,
        "sourceMechanismHash": source_hash,
        "targetMechanismHash": target_hash,
        "relation": relation,
        "observationCount": 1,
        "firstCycle": 3,
        "lastCycle": 3,
    }


def test_two_concrete_predecessors_form_convergence_even_with_same_mechanism():
    graph = {
        "nodes": [
            _node("feed-a", "feed", "feed-h"),
            _node("feed-b", "feed", "feed-h"),
            _node("bond", "bonding", "bond-h"),
            _node("out", "output", "out-h"),
        ],
        "edges": [
            _edge("feed-a", "bond", "feed", "bonding", "feed-h", "bond-h", "bond-created"),
            _edge("feed-b", "bond", "feed", "bonding", "feed-h", "bond-h", "bond-created"),
            _edge("bond", "out", "bonding", "output", "bond-h", "out-h", "delivered"),
        ],
    }
    motifs = extract_convergence_motifs(graph)
    assert len(motifs) == 1
    assert motifs[0]["inputCount"] == 2
    assert len(motifs[0]["inputs"]) == 2
    key = canonical_convergence_key(motifs[0])
    assert len(key[0]) == 2


def test_single_predecessor_is_not_a_convergence():
    graph = {
        "nodes": [_node("feed", "feed", "f"), _node("bond", "bonding", "b")],
        "edges": [_edge("feed", "bond", "feed", "bonding", "f", "b", "bond-created")],
    }
    assert extract_convergence_motifs(graph) == []
