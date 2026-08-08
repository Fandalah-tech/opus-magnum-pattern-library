from __future__ import annotations

# Compatibility entry point retained because the hosted workflow invokes the v5
# filename.  The implementation lives in v6 so it can evolve without creating
# multiple push-triggered search runs while support files are prepared.
from tools.run_aqueous_evolution_v6 import main


if __name__ == "__main__":
    raise SystemExit(main())
