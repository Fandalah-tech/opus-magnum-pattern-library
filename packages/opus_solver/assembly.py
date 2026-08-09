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


def _relations_for_candidate(branches: list[list[dict[str, Any]]], convergence_relation: str, tail: list[dict[str, Any]]) -> Counter[str]:
    relations: Counter[str] = Counter()
    for branch in branches:
        for edge in branch:
            relation = str(edge.get("relation") or "")
            if relation:
                relations[relation] += 1
    if convergence_relation:
        relations[convergence_relation] += 1
    for edge in tail:
        relation = str(edge.get("relation") or "")
        if relation:
            relations[relation] += 1
    return relations


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
    required = required_flow_relations(plan)
    transitions = list(flow_index.get("transitions", []))
    candidates: list[dict[str, Any]] = []

    for motif in flow_index.get("convergenceMotifs", []):
        inputs = list(motif.get("inputs", []))
        if len(inputs) < source_count:
            continue
        target = _key(motif.get("targetRole"), motif.get("targetMechanismHash"))
        if not target[0] or not target[1]:
            continue

        branch_options = []
        valid = True
        for input_item in inputs[:source_count]:
            input_key = _key(input_item.get("sourceRole"), input_item.get("sourceMechanismHash"))
            options = _paths_to_target(transitions, input_key, max_depth=max_branch_depth)
            if not options:
                valid = False
                break
            options.sort(key=lambda path: (-sum(_edge_confidence(edge) for edge in path), len(path)))
            branch_options.append(options[0])
        if not valid:
            continue

        tails = _paths_from_source(transitions, target, max_depth=max_tail_depth)
        if not tails:
            continue
        tails.sort(key=lambda path: (-sum(_edge_confidence(edge) for edge in path), len(path)))
        tail = tails[0]

        motif_relations = sorted({relation for item in inputs for relation in item.get("relations", []) if relation})
        convergence_relation = motif_relations[0] if len(motif_relations) == 1 else ""
        observed = _relations_for_candidate(branch_options, convergence_relation, tail)
        missing = Counter({key: count - observed.get(key, 0) for key, count in required.items() if observed.get(key, 0) < count})
        if missing:
            continue

        edge_scores = [_edge_confidence(edge) for branch in branch_options for edge in branch]
        edge_scores.extend(_edge_confidence(edge) for edge in tail)
        motif_score = 1.0 - math.exp(-max(0, int(motif.get("observationCount") or 0)) / 2.0)
        empirical = (sum(edge_scores) + motif_score) / (len(edge_scores) + 1) if edge_scores else motif_score
        coverage = 1.0
        score = 0.65 * coverage + 0.25 * empirical + 0.10 * motif_score

        candidates.append({
            "score": round(score, 6),
            "functionalCoverageScore": 1.0,
            "assemblyComplete": True,
            "sourceCount": source_count,
            "convergence": motif,
            "branches": branch_options,
            "tail": tail,
            "observedRelations": dict(sorted(observed.items())),
            "requiredRelations": dict(sorted(required.items())),
            "empiricalScore": round(empirical, 6),
            "convergenceConfidence": round(motif_score, 6),
        })

    candidates.sort(key=lambda item: (-float(item["score"]), -float(item["convergenceConfidence"])))
    return candidates[:max(0, int(limit))]
