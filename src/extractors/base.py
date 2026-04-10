"""Abstract base class for language-specific extractors."""
from __future__ import annotations
from abc import ABC, abstractmethod


class ExtractorBase(ABC):
    """
    Extract function/method metadata from source files.

    Each returned dict must contain at minimum:
      file, name, qualname, lineno, language

    And optionally:
      end_lineno, signature, docstring, is_async, is_method,
      class_name, source, calls
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Language identifier stored in the DB (e.g. 'python', 'typescript', 'go')."""

    @abstractmethod
    def extract(self, source: str, filepath: str) -> list[dict]:
        """
        Parse *source* text (from *filepath*) and return a list of function dicts.

        Must not raise — return [] on unparseable input.
        """

    def scan_file(self, path_str: str, root_str: str) -> tuple[list[dict], list[str]]:
        """
        Read a file from disk and extract functions. Returns (functions, errors).
        Sets the 'file' key to a path relative to root_str.
        """
        from pathlib import Path
        path = Path(path_str)
        root = Path(root_str)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            rel = str(path.relative_to(root))
            fns = self.extract(source, rel)
            return fns, []
        except Exception as e:
            rel = str(path.relative_to(root)) if path.is_relative_to(root) else path_str
            return [], [f"{rel}: {e}"]
