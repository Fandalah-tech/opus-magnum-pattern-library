from __future__ import annotations

from collections import Counter
from typing import Any

from .fragments import extract_solution_fragments
from .replay_glyphs import build_replay_trace
from .timeline import build_program_timeline


def trace_fragment_evidence(puzzle: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    """Annotate structural fragments with replay-observed evidence when available."""

    fragments = extract_solution_fragments(solution)
    timeline = build_program_timeline(solution)
    trace = build_replay_trace(puzzle, solution, timeline)

    arm_events: Counter[str] = Counter()
    grab_events: Counter[str] = Counter()
    drop_events: Counter[str] = Counter()
    consumer_events: Counter[str] = Counter()
    source_molecules: Counter[str] = Counter()
    glyph_events: Counter[str] = Counter()

    seen_source_molecules: set[str] = set()
    for frame in trace.get("frames", []):
        for molecule in frame.get("molecules", []):
            molecule_id = str(molecule.get("id") or "")
            source_part = str(molecule.get("sourcePartId") or "")
            if molecule_id and source_part and molecule_id not in seen_source_molecules:
                source_molecules[source_part] += 1
                seen_source_molecules.add(molecule_id)

        for event in frame.get("events", []):
            kind = str(event.get("kind") or "")
            part_id = str(event.get("partId") or "")
            if kind == "arm-instruction" and part_id:
                arm_events[part_id] += 1
                instruction = str(event.get("instruction") or "")
                if instruction == "grab":
                    grab_events[part_id] += 1
                elif instruction == "drop":
                    drop_events[part_id] += 1
            elif kind in {"product-delivered", "molecule-consumed"}:
                consumer = str(event.get("consumerPartId") or "")
                if consumer:
                    consumer_events[consumer] += 1
            elif kind == "glyph-effect":
                glyph_part = str(event.get("glyphPartId") or "")
                if glyph_part:
                    glyph_events[glyph_part] += 1

    annotated = []
    for fragment in fragments:
        anchor_id = str(fragment.get("anchorPartId") or "")
        member_ids = {str(value) for value in fragment.get("memberPartIds", [])}
        role = str(fragment.get("role") or "")

        observed_arm_instructions = sum(arm_events[part_id] for part_id in member_ids)
        observed_grabs = sum(grab_events[part_id] for part_id in member_ids)
        observed_drops = sum(drop_events[part_id] for part_id in member_ids)
        observed_source_molecules = source_molecules[anchor_id] if role == "feed" else 0
        observed_consumptions = consumer_events[anchor_id] if role in {"output", "disposal"} else 0
        observed_glyph_effects = glyph_events[anchor_id]

        if role == "feed":
            evidence_level = "dynamic-confirmed" if observed_source_molecules else "structural-only"
        elif role in {"output", "disposal"}:
            evidence_level = "dynamic-confirmed" if observed_consumptions else "structural-only"
        elif observed_glyph_effects:
            evidence_level = "dynamic-confirmed"
        elif observed_grabs or observed_drops:
            evidence_level = "dynamic-arm-observed"
        else:
            evidence_level = "structural-only"

        annotated_fragment = dict(fragment)
        annotated_fragment["evidence"] = {
            "level": evidence_level,
            "armInstructionCount": observed_arm_instructions,
            "grabCount": observed_grabs,
            "dropCount": observed_drops,
            "sourceMoleculeCount": observed_source_molecules,
            "consumerEventCount": observed_consumptions,
            "glyphEffectCount": observed_glyph_effects,
            "glyphSimulationAvailable": bool(trace.get("capabilities", {}).get("glyphSimulation")),
            "simulatedGlyphs": list(trace.get("capabilities", {}).get("simulatedGlyphs", [])),
        }
        annotated.append(annotated_fragment)

    return annotated
