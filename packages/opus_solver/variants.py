from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


def _timing_invariant(timing: dict[str, Any] | None) -> dict[str, Any] | None:
    if not timing or timing.get("programStartDelta") is None:
        return None
    return {
        "frame": "source-fragment-program-start",
        "programStartDelta": timing.get("programStartDelta"),
        "eventFirstFromSourceStart": timing.get("eventFirstFromSourceStart"),
        "eventFirstFromTargetStart": timing.get("eventFirstFromTargetStart"),
    }


def empirical_edge_options(edge: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    """Return correlated transform/timing observations for one canonical edge.

    Transition-level transform/timing aggregates are useful independently, but
    combining their preferred variants can synthesize a pair never observed in
    one historical solution. Samples preserve this correlation and are preferred
    here whenever both dimensions are present.
    """
    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, sample in enumerate(edge.get("samples", [])):
        transform = sample.get("relativeTransform")
        timing = _timing_invariant(sample.get("relativeTiming"))
        if not transform and not timing:
            continue
        payload = {"relativeTransform": transform, "relativeTiming": timing}
        key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        options.append({
            **payload,
            "source": "same-solution-sample",
            "sampleRank": rank,
            "weight": max(1, int(sample.get("observationCount") or 1)),
        })
        if len(options) >= max(1, int(limit)):
            break

    if not options:
        transform = (edge.get("relativeTransforms") or {}).get("preferred") or edge.get("relativeTransform")
        timing = (edge.get("relativeTimings") or {}).get("preferred") or _timing_invariant(edge.get("relativeTiming"))
        if transform or timing:
            options.append({
                "relativeTransform": transform,
                "relativeTiming": timing,
                "source": "aggregate-preferred",
                "sampleRank": None,
                "weight": max(1, int(edge.get("observationCount") or 1)),
            })
    return options


def _edge_locations(candidate: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    locations = []
    for branch_index, branch in enumerate(candidate.get("branches", [])):
        for edge_index, edge in enumerate(branch):
            locations.append((f"branch-{branch_index}", edge_index, edge))
    for edge_index, edge in enumerate(candidate.get("tail", [])):
        locations.append(("tail", edge_index, edge))
    return locations


def _replace_edge(candidate: dict[str, Any], location: str, index: int, option: dict[str, Any]) -> None:
    if location == "tail":
        edge = candidate["tail"][index]
    else:
        branch_index = int(location.split("-", 1)[1])
        edge = candidate["branches"][branch_index][index]
    if option.get("relativeTransform") is not None:
        edge["relativeTransforms"] = {"preferred": deepcopy(option["relativeTransform"]), "variantCount": 1, "variants": []}
        edge["relativeTransform"] = deepcopy(option["relativeTransform"])
    if option.get("relativeTiming") is not None:
        edge["relativeTimings"] = {"preferred": deepcopy(option["relativeTiming"]), "variantCount": 1, "variants": []}
        edge["relativeTiming"] = deepcopy(option["relativeTiming"])


def enumerate_empirical_assembly_variants(
    candidate: dict[str, Any],
    *,
    max_variants: int = 50,
    edge_option_limit: int = 4,
    convergence_sample_limit: int = 4,
) -> list[dict[str, Any]]:
    """Bounded beam expansion of same-solution geometry/timing evidence.

    The beam starts with convergence-sample alternatives, then expands each
    canonical transition using correlated sample options. Lower sample ranks are
    preferred, but multiple historically observed combinations survive.
    """
    max_variants = max(1, int(max_variants))
    convergence_samples = list((candidate.get("convergence") or {}).get("samples", []))
    seeds = []
    if convergence_samples:
        for sample_rank in range(min(len(convergence_samples), max(1, int(convergence_sample_limit)))):
            item = deepcopy(candidate)
            samples = list(item.get("convergence", {}).get("samples", []))
            selected = samples.pop(sample_rank)
            item["convergence"]["samples"] = [selected, *samples]
            seeds.append((float(sample_rank), item, [{"kind": "convergence-sample", "rank": sample_rank}]))
    else:
        seeds.append((0.0, deepcopy(candidate), []))

    beam = seeds[:max_variants]
    locations = _edge_locations(candidate)
    for location, edge_index, original_edge in locations:
        options = empirical_edge_options(original_edge, limit=edge_option_limit)
        if not options:
            continue
        expanded = []
        for base_penalty, base_candidate, provenance in beam:
            for option_rank, option in enumerate(options):
                variant = deepcopy(base_candidate)
                _replace_edge(variant, location, edge_index, option)
                penalty = base_penalty + float(option_rank)
                expanded.append((
                    penalty,
                    variant,
                    provenance + [{
                        "kind": "edge-sample",
                        "location": location,
                        "edgeIndex": edge_index,
                        "rank": option_rank,
                        "source": option.get("source"),
                    }],
                ))
        expanded.sort(key=lambda item: (item[0], json.dumps(item[2], sort_keys=True)))
        beam = expanded[:max_variants]

    results = []
    seen = set()
    for rank, (penalty, item, provenance) in enumerate(beam, start=1):
        signature = json.dumps({"branches": item.get("branches"), "tail": item.get("tail"), "convergence": item.get("convergence", {}).get("samples", [])[:1]}, sort_keys=True, separators=(",", ":"))
        if signature in seen:
            continue
        seen.add(signature)
        item["variant"] = {
            "rank": rank,
            "penalty": penalty,
            "evidenceSelections": provenance,
        }
        results.append(item)
        if len(results) >= max_variants:
            break
    return results
