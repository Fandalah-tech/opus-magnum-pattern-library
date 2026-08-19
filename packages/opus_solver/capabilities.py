from __future__ import annotations

from typing import Any


ARM_CAPABILITIES = {
    "arm1": "arm1",
    "arm2": "arm2",
    "arm3": "arm3",
    "arm6": "arm6",
    "piston": "piston",
    "baron": "van-berlo",
}
GLYPH_CAPABILITIES = {
    "bonder": "bonder",
    "unbonder": "unbonder",
    "multibonder": "multibonder",
    "bonder-speed": "multibonder",
    "bonder-prisma": "triplex-bonder",
    "triplex-bonder": "triplex-bonder",
    "glyph-calcification": "calcification",
    "glyph-duplication": "duplication",
    "glyph-projection": "projection",
    "glyph-purification": "purification",
    "glyph-animismus": "animismus",
    "glyph-disposal": "disposal",
    "glyph-unification": "unification",
    "glyph-dispersion": "dispersion",
}


def part_capability_requirement(puzzle: dict[str, Any], part_type: str) -> tuple[str, str] | None:
    if part_type in ARM_CAPABILITIES:
        return "arm", ARM_CAPABILITIES[part_type]
    if part_type in GLYPH_CAPABILITIES:
        return "glyph", GLYPH_CAPABILITIES[part_type]
    if part_type == "pipe" and not bool(puzzle.get("production")):
        return "production", "production-conduit"
    return None


def part_is_available(puzzle: dict[str, Any], part_type: str) -> bool:
    if not puzzle.get("availableParts"):
        return True
    requirement = part_capability_requirement(puzzle, part_type)
    if requirement is None:
        return True
    category, capability = requirement
    available = puzzle.get("availableParts") or {}
    if category == "arm":
        return capability in {str(value) for value in available.get("arms") or ()}
    if category == "glyph":
        return capability in {str(value) for value in available.get("glyphs") or ()}
    return bool(puzzle.get("production"))


def unavailable_solution_parts(puzzle: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, str]]:
    issues = []
    for part in solution.get("parts", []):
        part_type = str(part.get("type") or "")
        requirement = part_capability_requirement(puzzle, part_type)
        if requirement is None or part_is_available(puzzle, part_type):
            continue
        category, capability = requirement
        issues.append({
            "partId": str(part.get("id") or ""),
            "partType": part_type,
            "requiredCapability": capability,
            "category": category,
        })
    return issues
