from __future__ import annotations

from pathlib import Path

PATH = Path("packages/opus_engine/simulator.py")
OLD = "next_length = min(3, arm.length + 1) if instruction in EXTEND else max(arm.base_length or 1, arm.length - 1)"
NEW = "next_length = min(3, arm.length + 1) if instruction in EXTEND else max(1, arm.length - 1)"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if OLD not in text:
        if NEW in text:
            print("piston retract floor already corrected")
            return
        raise RuntimeError("expected piston length expression not found")
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("corrected piston retract floor from base length to 1")


if __name__ == "__main__":
    main()
