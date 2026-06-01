#!/usr/bin/env python3
"""Compatibility wrapper for scripts.geo.test_guangzhou_boundary_stress."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.geo.test_guangzhou_boundary_stress import main


if __name__ == "__main__":
    raise SystemExit(main())
