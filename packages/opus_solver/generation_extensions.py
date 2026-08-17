from __future__ import annotations

"""Compatibility bridge that routes composed generation through extended planning.

The mature generation pipeline still imports the original planner module
internally.  Keep that pipeline unchanged while newer chemistry recognizers are
stabilized: importing this module replaces only the planner callable used at
entry, then re-exports the existing generator.  All downstream assembly,
layout, scheduling and validation code remains untouched.
"""

from . import generation as _generation
from .manufacturing_extensions import build_manufacturing_plan

_generation.build_manufacturing_plan = build_manufacturing_plan

generate_composed_candidates = _generation.generate_composed_candidates

__all__ = ["generate_composed_candidates"]
