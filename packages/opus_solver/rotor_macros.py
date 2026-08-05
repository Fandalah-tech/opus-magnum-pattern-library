from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .rotor_trace import RotorTrace, TraceMilestone, trace_solution_milestones


@dataclass(frozen=True, slots=True)
class MacroEvent:
    relative_cycle: int
    kind: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProductMacro:
    product_index: int
    start_cycle: int
    delivery_cycle: int
    duration: int
    events: tuple[MacroEvent, ...]
    event_counts: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RotorMacroProgram:
    startup: tuple[TraceMilestone, ...]
    products: tuple[ProductMacro, ...]
    steady_state_period: int | None
    stable_from_product: int | None
    event_signature: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _signature(events: Iterable[MacroEvent]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(event.kind for event in events).items()))


def _delivery_milestones(trace: RotorTrace) -> list[TraceMilestone]:
    return [milestone for milestone in trace.milestones if milestone.kind == "product-delivered"]


def extract_product_macros(trace: RotorTrace) -> RotorMacroProgram:
    """Segment a validated replay into startup and one macro per delivery.

    The segmentation deliberately uses only observable engine milestones.  It
    does not assume a specific arm layout or copy instruction ranges.  This
    makes the result suitable as a high-level target for a later mechanical
    compiler.
    """
    deliveries = _delivery_milestones(trace)
    if not deliveries:
        return RotorMacroProgram(tuple(trace.milestones), (), None, None, ())

    first_delivery_cycle = deliveries[0].cycle
    startup = tuple(
        milestone for milestone in trace.milestones
        if milestone.cycle < first_delivery_cycle
    )

    products: list[ProductMacro] = []
    previous_delivery = 0
    for index, delivery in enumerate(deliveries):
        start = previous_delivery + 1 if index else 0
        relevant = [
            milestone for milestone in trace.milestones
            if start <= milestone.cycle <= delivery.cycle
        ]
        events = tuple(
            MacroEvent(
                relative_cycle=milestone.cycle - start,
                kind=milestone.kind,
                data=milestone.data,
            )
            for milestone in relevant
        )
        products.append(ProductMacro(
            product_index=index,
            start_cycle=start,
            delivery_cycle=delivery.cycle,
            duration=delivery.cycle - start + 1,
            events=events,
            event_counts=_signature(events),
        ))
        previous_delivery = delivery.cycle

    periods = [
        products[index].delivery_cycle - products[index - 1].delivery_cycle
        for index in range(1, len(products))
    ]
    steady_state_period: int | None = None
    stable_from: int | None = None
    if periods:
        for offset in range(len(periods)):
            suffix = periods[offset:]
            if suffix and len(set(suffix)) == 1:
                steady_state_period = suffix[0]
                stable_from = offset + 1
                break

    signatures = [product.event_counts for product in products]
    common_signature: tuple[tuple[str, int], ...] = ()
    if signatures:
        common = Counter(dict(signatures[0]))
        for signature in signatures[1:]:
            current = Counter(dict(signature))
            common &= current
        common_signature = tuple(sorted(common.items()))

    return RotorMacroProgram(
        startup=startup,
        products=tuple(products),
        steady_state_period=steady_state_period,
        stable_from_product=stable_from,
        event_signature=common_signature,
    )


def learn_rotor_macros(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
) -> RotorMacroProgram:
    return extract_product_macros(trace_solution_milestones(puzzle, solution))
