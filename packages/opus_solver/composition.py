from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

FragmentKey = tuple[str, str]


def _fragment_key(role: str | None, mechanism_hash: str | None) -> FragmentKey:
    return (str(role or ""), str(mechanism_hash or ""))


def _edge_score(edge: dict[str, Any]) -> dict[str, float]:
    observations = max(0, int(edge.get("observationCount") or 0))
    puzzles = max(0, int(edge.get("sourcePuzzleCount") or 0))
    solutions = max(0, int(edge.get("sourceSolutionCount") or 0))

    observation_confidence = 1.0 - math.exp(-observations / 3.0)
    puzzle_breadth = 1.0 - math.exp(-puzzles / 2.0)
    solution_breadth = 1.0 - math.exp(-solutions / 3.0)
    score = 0.60 * observation_confidence + 0.25 * puzzle_breadth + 0.15 * solution_breadth
    return {
        "score": round(score, 6),
        "observationConfidence": round(observation_confidence, 6),
        "puzzleBreadth": round(puzzle_breadth, 6),
        "solutionBreadth": round(solution_breadth, 6),
    }


def _fragment_metadata(fragment_index: dict[str, Any] | None) -> dict[FragmentKey, dict[str, Any]]:
    if not fragment_index:
        return {}
    result: dict[FragmentKey, dict[str, Any]] = {}
    for item in fragment_index.get("fragments", []):
        key = _fragment_key(item.get("role"), item.get("canonicalMechanismHash"))
        result[key] = {
            "occurrenceCount": item.get("occurrenceCount"),
            "sourcePuzzleCount": item.get("sourcePuzzleCount"),
            "structuralVariantCount": item.get("structuralVariantCount"),
            "partTypes": list(item.get("partTypes", [])),
            "evidence": item.get("evidence", {}),
        }
    return result


def rank_fragment_chains(
    flow_index: dict[str, Any],
    *,
    fragment_index: dict[str, Any] | None = None,
    start_roles: Iterable[str] = ("feed",),
    target_roles: Iterable[str] = ("output",),
    max_depth: int = 6,
    limit: int = 25,
    min_observations: int = 1,
) -> list[dict[str, Any]]:
    """Rank observed canonical fragment chains from source roles to target roles.

    The planner is deliberately empirical: it only traverses transitions that
    were observed by replay. Repeated fragment nodes are forbidden within one
    path so accidental cycles do not dominate ranking.
    """
    start_role_set = {str(value) for value in start_roles}
    target_role_set = {str(value) for value in target_roles}
    max_depth = max(1, int(max_depth))
    limit = max(0, int(limit))
    min_observations = max(1, int(min_observations))
    metadata = _fragment_metadata(fragment_index)

    adjacency: defaultdict[FragmentKey, list[dict[str, Any]]] = defaultdict(list)
    start_nodes: set[FragmentKey] = set()
    for transition in flow_index.get("transitions", []):
        if int(transition.get("observationCount") or 0) < min_observations:
            continue
        source = _fragment_key(transition.get("sourceRole"), transition.get("sourceMechanismHash"))
        target = _fragment_key(transition.get("targetRole"), transition.get("targetMechanismHash"))
        if not source[0] or not source[1] or not target[0] or not target[1]:
            continue
        scored = dict(transition)
        scored["empirical"] = _edge_score(transition)
        adjacency[source].append(scored)
        if source[0] in start_role_set:
            start_nodes.add(source)

    for edges in adjacency.values():
        edges.sort(
            key=lambda edge: (
                -float(edge["empirical"]["score"]),
                str(edge.get("targetRole") or ""),
                str(edge.get("targetMechanismHash") or ""),
                str(edge.get("relation") or ""),
            )
        )

    candidates: list[dict[str, Any]] = []

    def walk(node: FragmentKey, nodes: list[FragmentKey], steps: list[dict[str, Any]], visited: set[FragmentKey]) -> None:
        if steps and node[0] in target_role_set:
            edge_scores = [float(step["empirical"]["score"]) for step in steps]
            average = sum(edge_scores) / len(edge_scores)
            bottleneck = min(edge_scores)
            length_penalty = 0.04 * max(0, len(steps) - 1)
            score = max(0.0, min(1.0, 0.75 * average + 0.25 * bottleneck - length_penalty))
            candidates.append({
                "score": round(score, 6),
                "edgeAverage": round(average, 6),
                "bottleneckScore": round(bottleneck, 6),
                "stepCount": len(steps),
                "nodes": [
                    {
                        "role": role,
                        "canonicalMechanismHash": mechanism_hash,
                        "metadata": metadata.get((role, mechanism_hash)),
                    }
                    for role, mechanism_hash in nodes
                ],
                "steps": steps,
            })
            return

        if len(steps) >= max_depth:
            return

        for edge in adjacency.get(node, []):
            target = _fragment_key(edge.get("targetRole"), edge.get("targetMechanismHash"))
            if target in visited:
                continue
            step = {
                "sourceRole": edge.get("sourceRole"),
                "sourceMechanismHash": edge.get("sourceMechanismHash"),
                "targetRole": edge.get("targetRole"),
                "targetMechanismHash": edge.get("targetMechanismHash"),
                "relation": edge.get("relation"),
                "observationCount": edge.get("observationCount"),
                "sourcePuzzleCount": edge.get("sourcePuzzleCount"),
                "sourceSolutionCount": edge.get("sourceSolutionCount"),
                "empirical": edge["empirical"],
            }
            walk(target, nodes + [target], steps + [step], visited | {target})

    for start in sorted(start_nodes):
        walk(start, [start], [], {start})

    deduped: dict[tuple[FragmentKey, ...], dict[str, Any]] = {}
    for candidate in candidates:
        key = tuple((str(node["role"]), str(node["canonicalMechanismHash"])) for node in candidate["nodes"])
        previous = deduped.get(key)
        if previous is None or candidate["score"] > previous["score"]:
            deduped[key] = candidate

    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            -float(item["score"]),
            int(item["stepCount"]),
            tuple((node["role"], node["canonicalMechanismHash"]) for node in item["nodes"]),
        ),
    )
    return ranked[:limit]


def build_composition_prior(
    flow_index: dict[str, Any],
    *,
    fragment_index: dict[str, Any] | None = None,
    max_depth: int = 6,
    limit: int = 100,
) -> dict[str, Any]:
    chains = rank_fragment_chains(
        flow_index,
        fragment_index=fragment_index,
        max_depth=max_depth,
        limit=limit,
    )
    return {
        "schemaVersion": "0.1.0",
        "sourceFlowSchemaVersion": flow_index.get("schemaVersion"),
        "summary": {
            "chainCount": len(chains),
            "maxDepth": max_depth,
            "bestScore": chains[0]["score"] if chains else None,
        },
        "chains": chains,
    }
