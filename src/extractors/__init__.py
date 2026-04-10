"""
Pluggable extractor drivers for multi-language AST indexing.

Each driver implements ExtractorBase and handles a set of file extensions.
Registry maps extension → driver class.

v1 languages: Python (ast), TypeScript/JavaScript (tree-sitter), Go (tree-sitter).
"""
from .base import ExtractorBase
from .python_extractor import PythonExtractor
from .typescript_extractor import TypeScriptExtractor
from .go_extractor import GoExtractor

# Extension → extractor instance (instantiated lazily on first use)
_registry: dict[str, ExtractorBase] = {}

_EXTENSION_MAP: dict[str, type] = {
    ".py":  PythonExtractor,
    ".ts":  TypeScriptExtractor,
    ".tsx": TypeScriptExtractor,
    ".js":  TypeScriptExtractor,
    ".jsx": TypeScriptExtractor,
    ".go":  GoExtractor,
}

SUPPORTED_EXTENSIONS = set(_EXTENSION_MAP.keys())


def get_extractor(ext: str) -> "ExtractorBase | None":
    """Return the extractor for a file extension, or None if unsupported."""
    cls = _EXTENSION_MAP.get(ext.lower())
    if cls is None:
        return None
    if ext not in _registry:
        _registry[ext] = cls()
    return _registry[ext]


def supported_extensions() -> list[str]:
    return list(_EXTENSION_MAP.keys())
