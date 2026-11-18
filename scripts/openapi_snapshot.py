#!/usr/bin/env python3
"""Write the FastAPI OpenAPI contract to ``api/openapi.json``.

The snapshot lets reviewers diff API changes and gives the hand-written
TypeScript interfaces in ``web/src/api/types.ts`` a machine-readable reference.

Usage:
    python scripts/openapi_snapshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from fabpulse.main import app  # noqa: E402  (path setup must come first)


def main() -> int:
    """Write the OpenAPI document and print its path and endpoint count."""
    spec = app.openapi()
    out = ROOT / "api" / "openapi.json"
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = len(spec.get("paths", {}))
    print(f"wrote {out} ({paths} paths, {len(spec.get('components', {}).get('schemas', {}))} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
