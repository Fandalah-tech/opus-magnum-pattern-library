from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .rotor_macros import ProductMacro, RotorMacroProgram


@dataclass(frozen=True, slots=True)
class TemplateEvent:
    relative_cycle: int
    kind: str
    occurrences_per_product: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RotorMacroTemplate:
    period: int
    source_product_indices: tuple[int, ...]
    events: tuple[TemplateEvent, ...]
    exact_timing_match: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _event_timing_signature(product: ProductMacro) -> tuple[tuple[int, str], ...]:
    return tuple(sorted((event.relative_cycle, event.kind) for event in product.events))


def build_steady_state_template(program: RotorMacroProgram) -> RotorMacroTemplate | None:
    """Build a reusable periodic chemistry target from stable product macros.

    Atom identifiers and other run-specific payload are intentionally removed.
    Repeated events at the same phase are retained through multiplicity counts.
    """
    if program.steady_state_period is None or program.stable_from_product is None:
        return None

    products = program.products[program.stable_from_product :]
    if not products:
        return None

    signatures = [_event_timing_signature(product) for product in products]
    exact = all(signature == signatures[0] for signature in signatures[1:])

    common = Counter(signatures[0])
    for signature in signatures[1:]:
        common &= Counter(signature)

    events = tuple(
        TemplateEvent(relative_cycle=cycle, kind=kind, occurrences_per_product=count)
        for (cycle, kind), count in sorted(common.items())
    )
    return RotorMacroTemplate(
        period=program.steady_state_period,
        source_product_indices=tuple(product.product_index for product in products),
        events=events,
        exact_timing_match=exact,
    )
