#!/usr/bin/env python3
"""Thin wrapper so a git checkout can run the hook without installing the package."""
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.post_write_hook import main  # noqa: E402

if __name__ == "__main__":
    main()
