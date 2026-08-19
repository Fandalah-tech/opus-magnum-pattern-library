from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .chemistry_composition import manufacturing_requirements, required_flow_relations
from .manufacturing import ManufacturingPlan

FragmentKey = tuple[str, str]


def _key(role: Any, mechanism: Any) -> FragmentKey:
    return str(role or ""), str(mechanism or "")


def _edge_confidence(edge: dict[str, Any]) -> float:
    observations = max(0, int(edge.get("observationCount") or 0))
    puzzles = max(0, int(edge.get("sourcePuzzleCount") or 0))
    solutions = max(0, int(edge.get("sourceSolutionCount") or 0))
    return 0.60 * (1.0 - math.exp(-observations / 3.0)) + 0.25 * (1.0 - math.exp(-puzzles / 2.0)) + 0.15 * (1.0 - math.exp(-solutions / 3.0))


def _edge_from_variants(
    edge: dict[str, Any],
    solution_path: str,
    variants: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not variants:
        return None
    selected = max(variants, key=lambda item: int(item.get("observationCount") or 0))
    result = dict(edge)
    result["sourceAnchorPartId"] = selected.get("sourceAnchorPartId")
    result["targetAnchorPartId"] = selected.get("targetAnchorPartId")
    result["repairRelativeTransforms"] = edge.get("relativeTransforms")
    result["repairRelativeTimings"] = edge.get("relativeTimings")
    result["relativeTransform"] = selected.get("relativeTransform")
    result["relativeTiming"] = selected.get("relativeTiming")
    result["relativeTransforms"] = {
        "preferred": selected.get("relativeTransform"),
        "variantCount": len(variants),
        "variants": [
            {
                "relativeTransform": item.get("relativeTransform"),
                "observationCount": int(item.get("observationCount") or 0),
            }
            for item in variants
            if item.get("relativeTransform")
        ],
    }
    result["relativeTimings"] = {
        "preferred": selected.get("relativeTiming"),
        "variantCount": len(variants),
        "variants": [
            {
                "relativeTiming": item.get("relativeTiming"),
                "observationCount": int(item.get("observationCount") or 0),
            }
            for item in variants
            if item.get("relativeTiming")
        ],
    }
    result["coherentSourceSolution"] = solution_path
    result["coherentObservationCount"] = max(1, int(selected.get("observationCount") or 0))
    return result


def _edge_for_solution(edge: dict[str, Any], solution_path: str) -> dict[str, Any] | None:
    variants = [
        item
        for item in edge.get("solutionVariants", [])
        if str(item.get("solutionPath") or "") == solution_path
    ]
    return _edge_from_variants(edge, solution_path, variants)


def _coherent_transition_index(
    transitions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Materialize each donor-specific transition once per ranking pass.

    The earlier implementation rescanned every transition for every convergence
    sample.  Large learned corpora contain thousands of transitions and motifs,
    turning a five-target benchmark into millions of repeated variant scans.
    This index walks the transition variants once and preserves exactly the same
    strongest-per-edge donor semantics used by `_edge_for_solution`.
    """
    by_solution: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in transitions:
        grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for variant in edge.get("solutionVariants", []) or []:
            path = str(variant.get("solutionPath") or "")
            if path:
                grouped[path].append(variant)
        for path, variants in grouped.items():
            selected = _edge_from_variants(edge, path, variants)
            if selected is not None:
                by_solution[path].append(selected)
    return dict(by_solution)


def _paths_to_target(transitions: list[dict[str, Any]], target: FragmentKey, *, max_depth: int) -> list[list[dict[str, Any]]]:
    if target[0] == "feed":
        return [[]]
    incoming: defaultdict[FragmentKey, list[dict[str, Any]]] = defaultdict(list)
    for edge in transitions:
        incoming[_key(edge.get("targetRole"), edge.get("targetMechanismHash"))].append(edge)
    paths: list[list[dict[str, Any]]] = []

    def walk(node: FragmentKey, reversed_steps: list[dict[str, Any]], visited: set[FragmentKey]) -> None:
        if len(reversed_steps) >= max_depth:
            return
        for edge in incoming.get(node, []):
            source = _key(edge.get("sourceRole"), edge.get("sourceMechanismHash"))
            if source in visited:
                continue
            steps = reversed_steps + [edge]
            if source[0] == "feed":
                paths.append(list(reversed(steps)))
            else:
                walk(source, steps, visited | {source})

    walk(target, [], {target})
    return paths


def _paths_from_source(transitions: list[dict[str, Any]], source: FragmentKey, *, max_depth: int) -> list[list[dict[str, Any]]]:
    outgoing: defaultdict[FragmentKey, list[dict[str, Any]]] = defaultdict(list)
    for edge in transitions:
        outgoing[_key(edge.get("sourceRole"), edge.get("sourceMechanismHash"))].append(edge)
    paths: list[list[dict[str, Any]]] = []

    def walk(node: FragmentKey, steps: list[dict[str, Any]], visited: set[FragmentKey]) -> None:
        if steps and node[0] == "output":
            paths.append(steps)
            return
        if len(steps) >= max_depth:
            return
        for edge in outgoing.get(node, []):
            target = _key(edge.get("targetRole"), edge.get("targetMechanismHash"))
            if target in visited:
                continue
            walk(target, steps + [edge], visited | {target})

    walk(source, [], {source})
    return paths


def _edge_relation_capacity(edge: dict[str, Any]) -> int:
    """Capacity proved by one coherent replay, otherwise one structural edge."""
    if edge.get("coherentSourceSolution"):
        return max(1, int(edge.get("coherentObservationCount") or 1))
    return 1


def _relations_for_candidate(
    branches: list[list[dict[str, Any]]],
    convergence_relations: list[str],
    tail: list[dict[str, Any]],
) -> Counter[str]:
    relations: Counter[str] = Counter()
    for branch in branches:
        for edge in branch:
            relation = str(edge.get("relation") or "")
            if relation:
                relations[relation] += _edge_relation_capacity(edge)
    for relation in convergence_relations:
        relations[relation] += 1
    for edge in tail:
        relation = str(edge.get("relation") or "")
        if relation:
            relations[relation] += _edge_relation_capacity(edge)
    return relations


def _infer_prismatic_relations(
    required: Counter[str],
    observed: Counter[str],
    motif: dict[str, Any],
) -> Counter[str]:
    inputs = list(motif.get("inputs", []))
    if str(motif.get("targetRole") or "") != "bonding" or len(inputs) < 3:
        return Counter()
    observed_triplex = {
        relation
        for relation, count in observed.items()
        if count > 0 and relation.startswith("triplex-bond-created:")
    }
    if not observed_triplex:
        return Counter()
    inferable = {
        "triplex-bond-created:red",
        "triplex-bond-created:black",
        "triplex-bond-created:yellow",
    }
    return Counter({
        relation: count - observed.get(relation, 0)
        for relation, count in required.items()
        if relation in inferable and count > observed.get(relation, 0)
    })


def rank_fragment_assemblies(
    plan: ManufacturingPlan,
    flow_index: dict[str, Any],
    *,
    max_branch_depth: int = 4,
    max_tail_depth: int = 4,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Rank replay-backed DAG assembly candidates with observed convergence."""
    if not plan.supported:
        return []
    requirements = manufacturing_requirements(plan)
    source_count = int(requirements["sourceCount"])
    convergence_input_count = int(requirements.get("convergenceInputCount") or source_count)
    required = required_flow_relations(plan)
    transitions = list(flow_index.get("transitions", []))
    coherent_transitions = _coherent_transition_index(transitions)
    candidates: list[dict[str, Any]] = []

    for motif in flow_index.get("convergenceMotifs", []):
        inputs = list(motif.get("inputs", []))
        if len(inputs) < convergence_input_count:
            continue
        coherent_samples = list(motif.get("solutionSamples", []))
        sample_options = coherent_samples or [None]
        for selected_sample in sample_options:
            solution_path = str((selected_sample or {}).get("solutionPath") or "")
            if solution_path:
                selected_transitions = coherent_transitions.get(solution_path, [])
                selected_motif = dict(motif)
                selected_motif["samples"] = [selected_sample]
                selected_motif["repairSamples"] = list(motif.get("solutionSamples", []))
                selected_motif["coherentSourceSolution"] = solution_path
            else:
                selected_transitions = transitions
                selected_motif = motif

            target = _key(motif.get("targetRole"), motif.get("targetMechanismHash"))
            if not target[0] or not target[1]:
                continue

            branch_options = []
            valid = True
            for input_item in inputs[:convergence_input_count]:
                input_key = _key(input_item.get("sourceRole"), input_item.get("sourceMechanismHash"))
                options = _paths_to_target(selected_transitions, input_key, max_depth=max_branch_depth)
                if not options:
                    valid = False
                    break
                options.sort(key=lambda path: (-sum(_edge_confidence(edge) for edge in path), len(path)))
                branch_options.append(options[0])
            if not valid:
                continue

            tails = _paths_from_source(selected_transitions, target, max_depth=max_tail_depth)
            if not tails:
                continue
            tails.sort(key=lambda path: (-sum(_edge_confidence(edge) for edge in path), len(path)))
            tail = tails[0]

            motif_relations = sorted({relation for item in inputs for relation in item.get("relations", []) if relation})
            observed = _relations_for_candidate(branch_options, motif_relations, tail)
            inferred = _infer_prismatic_relations(required, observed, selected_motif)
            covered = observed + inferred
            missing = Counter({key: count - covered.get(key, 0) for key, count in required.items() if covered.get(key, 0) < count})
            if missing:
                continue

            edge_scores = [_edge_confidence(edge) for branch in branch_options for edge in branch]
            edge_scores.extend(_edge_confidence(edge) for edge in tail)
            motif_score = 1.0 - math.exp(-max(0, int(motif.get("observationCount") or 0)) / 2.0)
            empirical = (sum(edge_scores) + motif_score) / (len(edge_scores) + 1) if edge_scores else motif_score
            coherence_bonus = 0.03 if solution_path else 0.0
            inference_penalty = min(0.12, 0.04 * sum(inferred.values()))
            score = min(1.0, 0.65 + 0.25 * empirical + 0.10 * motif_score + coherence_bonus) - inference_penalty

            capacities = [
                {
                    "relation": str(edge.get("relation") or ""),
                    "capacity": _edge_relation_capacity(edge),
                    "solutionPath": edge.get("coherentSourceSolution"),
                }
                for edge in [*(edge for branch in branch_options for edge in branch), *tail]
                if edge.get("relation")
            ]
            if inferred:
                relation_evidence = (
                    "engine-coherent-replay-capacity-plus-prism-physics"
                    if solution_path
                    else "engine-observed-plus-prism-physics"
                )
            elif solution_path:
                relation_evidence = "engine-coherent-replay-capacity"
            else:
                relation_evidence = "engine-observed"

            candidates.append({
                "score": round(score, 6),
                "functionalCoverageScore": 1.0,
                "assemblyComplete": True,
                "sourceCount": source_count,
                "convergenceInputCount": convergence_input_count,
                "convergenceRelations": motif_relations,
                "convergence": selected_motif,
                "branches": branch_options,
                "tail": tail,
                "observedRelations": dict(sorted(observed.items())),
                "relationCapacities": capacities,
                "inferredRelations": dict(sorted(inferred.items())),
                "relationCoverageEvidence": relation_evidence,
                "requiredRelations": dict(sorted(required.items())),
                "empiricalScore": round(empirical, 6),
                "convergenceConfidence": round(motif_score, 6),
                "coherentSourceSolution": solution_path or None,
            })

    candidates.sort(key=lambda item: (-float(item["score"]), -float(item["convergenceConfidence"])))
    return candidates[:max(0, int(limit))]
