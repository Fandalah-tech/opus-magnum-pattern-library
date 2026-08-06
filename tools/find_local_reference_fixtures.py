from pathlib import Path

roots = [Path.cwd(), Path.cwd().parent, Path.home()]
seen = set()
for root in roots:
    if not root.exists() or root in seen:
        continue
    seen.add(root)
    print(f"ROOT {root}")
    try:
        for path in root.rglob("P007.puzzle"):
            print(path)
    except (PermissionError, OSError) as exc:
        print(f"SKIP {root}: {exc}")
