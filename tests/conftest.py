"""Isolate SQLite for tests (must run before importing api.main or heavy db use)."""
from __future__ import annotations

import os
import tempfile

_fd, _TEST_DB = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["OWN_YOUR_CODE_DB"] = _TEST_DB


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_TEST_DB)
    except OSError:
        pass
