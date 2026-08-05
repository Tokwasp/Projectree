#!/usr/bin/env python3
"""Deprecated CLI wrapper; use scripts/operations/backfill_node_embeddings.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.operations.backfill_node_embeddings import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
