from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DEFAULT_WEIGHTS = {
    "productElements": 0.18,
    "reagentElements": 0.12,
    "productBonds": 0.04,
    "reagentBonds": 0.025,
    "productBondVariants": 0.04,
    "reagentBondVariants": 0.025,
    "productMolecules": 0.16,
    "reagentMolecules": 0.08,
    "productAtomCounts": 0.07,
    "reagentAtomCounts": 0.05,
    "productBondCounts": 0.04,
    "reagentBondCounts": 0.03,
    "availableGlyphs": 0.05,
    "availableArms": 0.03,
    "production": 0.03,
    "outputScale": 0.03,
}

_ALWAYS_AVAILABLE_PARTS = {
    "input",
    "output",
    "reagent",
    "product",
    "track",
    "equilibrium",
}


def _counter_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = Counter({str(key): int(value) for key, value in left.items() if isinstance(value, int) and value > 0})
    b = Counter({str(key): int(value) for key, value in right.items() if isinstance(value, int) and value > 0})
    keys = set(a) | set(b)
    if not keys:
        return 1.0
    intersection = sum(min(a[key], b[key]) for key in keys)
    union = sum(max(a[key], b[key]) for key in keys)
    return intersection / union if union else 1.0


def _multiset_similarity(left: Iterable[Any], right: Iterable[Any]) -> float:
    a = Counter(str(value) for value in left)
    b = Counter(str(value) for value in right)
    keys = set(a) | set(b)
    if not keys:
        return 1.0
    intersection = sum(min(a[key], b[key]) for key in keys)
    union = sum(max(a[key], b[key]) for key in keys)
    return intersection / union if union else 1.0


def _scalar_similarity(left: Any, right: Any) -> float:
    if left is None and right is None:
        return 1.0
    if left is None or right is None:
        return 0.0
    if isinstance(left, bool) or isinstance(right, bool):
        return 1.0 if bool(left) == bool(right) else 0.0
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        maximum = max(abs(float(left)), abs(float(right)), 1.0)
        return max(0.0, 1.0 - abs(float(left) - float(right)) / maximum)
    return 1.0 if left == right else 0.0


def puzzle_similarity(
    target: dict[str, Any],
    candidate: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return a 0..1 similarity score plus interpretable component scores."""

    configured = dict(DEFAULT_WEIGHTS)
    if weights:
        configured.update(weights)

    target_reagents = target.get("reagents", {})
    target_products = target.get("products", {})
    candidate_reagents = candidate.get("reagents", {})
    candidate_products = candidate.get("products", {})

    components = {
        "productElements": _counter_similarity(target_products.get("elements", {}), candidate_products.get("elements", {})),
        "reagentElements": _counter_similarity(target_reagents.get("elements", {}), candidate_reagents.get("elements", {})),
        "productBonds": _counter_similarity(target_products.get("bonds", {}), candidate_products.get("bonds", {})),
        "reagentBonds": _counter_similarity(target_reagents.get("bonds", {}), candidate_reagents.get("bonds", {})),
        "productBondVariants": _counter_similarity(target_products.get("bondVariants", {}), candidate_products.get("bondVariants", {})),
        "reagentBondVariants": _counter_similarity(target_reagents.get("bondVariants", {}), candidate_reagents.get("bondVariants", {})),
        "productMolecules": _multiset_similarity(target_products.get("moleculeSignatures", []), candidate_products.get("moleculeSignatures", [])),
        "reagentMolecules": _multiset_similarity(target_reagents.get("moleculeSignatures", []), candidate_reagents.get("moleculeSignatures", [])),
        "productAtomCounts": _multiset_similarity(target_products.get("atomCounts", []), candidate_products.get("atomCounts", [])),
        "reagentAtomCounts": _multiset_similarity(target_reagents.get("atomCounts", []), candidate_reagents.get("atomCounts", [])),
        "productBondCounts": _multiset_similarity(target_products.get("bondCounts", []), candidate_products.get("bondCounts", [])),
        "reagentBondCounts": _multiset_similarity(target_reagents.get("bondCounts", []), candidate_reagents.get("bondCounts", [])),
        "availableGlyphs": _multiset_similarity(target.get("availableGlyphs", []), candidate.get("availableGlyphs", [])),
        "availableArms": _multiset_similarity(target.get("availableArms", []), candidate.get("availableArms", [])),
        "production": _scalar_similarity(target.get("production"), candidate.get("production")),
        "outputScale": _scalar_similarity(target.get("outputScale"), candidate.get("outputScale")),
    }

    denominator = sum(max(0.0, configured.get(name, 0.0)) for name in components)
    score = (
        sum(components[name] * max(0.0, configured.get(name, 0.0)) for name in components) / denominator
        if denominator
        else 0.0
    )
    return {"score": round(score, 6), "components": {key: round(value, 6) for key, value in components.items()}}


def _normalize_part_type(value: str) -> str:
    name = value.strip().lower()
    for prefix in ("glyph-", "glyph_", "arm-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    aliases = {
        "baron": "van-berlo",
        "vanberlo": "van-berlo",
        "triplexbonder": "triplex-bonder",
        "multi-bonder": "multibonder",
    }
    return aliases.get(name, name)


def mechanism_compatibility(target_features: dict[str, Any], mechanism: dict[str, Any]) -> dict[str, Any]:
    available = {
        _normalize_part_type(str(value))
        for value in target_features.get("availableGlyphs", []) + target_features.get("availableArms", [])
    }
    production = bool(target_features.get("production"))
    required = sorted({_normalize_part_type(str(value)) for value in mechanism.get("partTypes", [])})

    missing = []
    recognized = []
    for part_type in required:
        if part_type in _ALWAYS_AVAILABLE_PARTS:
            continue
        if part_type == "pipe":
            recognized.append(part_type)
            if not production:
                missing.append(part_type)
            continue
        # Only assert incompatibility for parts that belong to the known puzzle
        # availability vocabulary. Unknown serialized part types remain neutral.
        known_vocabulary = available | {
            "bonder", "unbonder", "multibonder", "triplex-bonder", "calcification",
            "duplication", "projection", "purification", "animismus", "disposal",
            "unification", "dispersion", "arm1", "arm2", "arm3", "arm6", "piston",
            "van-berlo", "pipe",
        }
        if part_type in known_vocabulary:
            recognized.append(part_type)
            if part_type not in available:
                missing.append(part_type)

    ratio = 1.0 if not recognized else (len(recognized) - len(missing)) / len(recognized)
    return {
        "compatible": not missing,
        "score": round(max(0.0, ratio), 6),
        "requiredParts": required,
        "missingParts": missing,
    }


def _aliases(feature_record: dict[str, Any]) -> set[str]:
    aliases = set()
    source = str(feature_record.get("sourceFile") or "")
    name = str(feature_record.get("name") or "")
    if source:
        aliases.add(source.lower())
        aliases.add(Path(source).name.lower())
        aliases.add(Path(source).stem.lower())
    if name:
        aliases.add(name.lower())
    return aliases


def rank_mechanisms(
    target_features: dict[str, Any],
    puzzle_feature_index: dict[str, Any],
    solver_index: dict[str, Any],
    *,
    limit: int = 25,
    include_incompatible: bool = False,
) -> list[dict[str, Any]]:
    """Rank reusable mechanisms from similar puzzles for a target puzzle."""

    feature_records = list(puzzle_feature_index.get("puzzles", []))
    features_by_alias: dict[str, dict[str, Any]] = {}
    for record in feature_records:
        for alias in _aliases(record):
            features_by_alias.setdefault(alias, record)

    ranked = []
    for source_puzzle in solver_index.get("puzzles", []):
        puzzle_key = str(source_puzzle.get("puzzleKey") or "")
        normalized_keys = {
            puzzle_key.lower(),
            Path(puzzle_key).name.lower(),
            Path(puzzle_key).stem.lower(),
        }
        feature_record = next((features_by_alias[key] for key in normalized_keys if key in features_by_alias), None)
        if feature_record is None:
            continue

        similarity = puzzle_similarity(target_features, feature_record.get("features", {}))
        for mechanism in source_puzzle.get("mechanisms", []):
            compatibility = mechanism_compatibility(target_features, mechanism)
            if not compatibility["compatible"] and not include_incompatible:
                continue
            # Puzzle similarity is primary. Compatibility is intentionally a
            # smaller term because hard incompatibilities are filtered above.
            retrieval_score = similarity["score"] * 0.85 + compatibility["score"] * 0.15
            ranked.append({
                "score": round(retrieval_score, 6),
                "puzzleSimilarity": similarity,
                "compatibility": compatibility,
                "sourcePuzzle": {
                    "puzzleKey": puzzle_key,
                    "name": feature_record.get("name"),
                    "fingerprint": feature_record.get("fingerprint"),
                },
                "mechanism": mechanism,
            })

    ranked.sort(key=lambda item: (
        -float(item["score"]),
        -float(item["puzzleSimilarity"]["score"]),
        str(item["sourcePuzzle"]["puzzleKey"]),
        str(item["mechanism"].get("canonicalMechanismHash") or ""),
    ))
    return ranked[:max(0, int(limit))]
