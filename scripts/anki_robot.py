#!/usr/bin/env python3
"""Thin command-line entry point for the Acervo Anki robot."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPOSITORY_ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from vocabgen.anki_sync.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
