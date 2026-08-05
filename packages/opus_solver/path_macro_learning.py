from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .mechanical_macros import MechanicalMacro

Action = Mapping[str, str]


def learn_action_windows(
    actions: Sequence[Action],
    *,
    lengths: Iterable[int] = (2, 3, 4, 6, 8),
    tag: str = "path-learned",
) -> tuple[MechanicalMacro, ...]:
    """Compile reusable macros from a mechanically valid search trajectory.

    The trajectory has already been validated cycle by cycle by OMSIM.  Mining
    contiguous windows turns newly discovered motions into reusable search
    operators, including motions that temporarily reduce the structural score.
    Empty action frames are retained because they can trigger glyph processing.
    """
    frames = tuple(dict(action) for action in actions)
    if not frames:
        return ()

    macros: list[MechanicalMacro] = []
    seen: set[tuple[tuple[tuple[str, str], ...], ...]] = set()
    valid_lengths = sorted({int(length) for length in lengths if int(length) > 0})
    for length in valid_lengths:
        if length > len(frames):
            continue
        for start in range(len(frames) - length + 1):
            window = frames[start:start + length]
            signature = tuple(tuple(sorted(frame.items())) for frame in window)
            if not any(signature) or signature in seen:
                continue
            seen.add(signature)
            macros.append(MechanicalMacro.from_actions(
                f"{tag}-{start:03d}-{start + length - 1:03d}",
                window,
                tags={tag, "mechanical", "trajectory", f"length-{length}"},
            ))
    return tuple(macros)
