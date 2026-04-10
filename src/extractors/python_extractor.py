"""Python extractor — wraps the existing ast-based logic."""
from __future__ import annotations

from .base import ExtractorBase


class PythonExtractor(ExtractorBase):
    @property
    def language(self) -> str:
        return "python"

    def extract(self, source: str, filepath: str) -> list[dict]:
        from ..extractor import extract_functions
        try:
            fns = extract_functions(source, filepath)
            for fn in fns:
                fn["language"] = "python"
            return fns
        except Exception:
            return []
