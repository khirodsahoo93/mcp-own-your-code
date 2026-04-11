"""
Optional dependency probes for semantic search, multi-language indexing, and dev tools.

Uses importlib.util.find_spec only (no import of torch, sentence_transformers, etc.)
so checks stay fast for preflight, server-info, and MCP.
"""
from __future__ import annotations

import importlib.util
from typing import Any


def _has_dist(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_optional_dependencies() -> dict[str, Any]:
    """
    Return install status for each optional bundle defined in pyproject.toml extras.

    Keys:
        semantic — sentence-transformers + numpy (embeddings, semantic/hybrid search)
        multilang  — tree-sitter + language grammars (TS/JS/Go AST; Python always via ast)
        full       — both semantic and multilang
        dev        — pytest, httpx, ruff (contributors)
    """
    semantic_modules = {
        "sentence_transformers": _has_dist("sentence_transformers"),
        "numpy": _has_dist("numpy"),
    }
    semantic_ok = all(semantic_modules.values())

    multilang_modules = {
        "tree_sitter": _has_dist("tree_sitter"),
        "tree_sitter_javascript": _has_dist("tree_sitter_javascript"),
        "tree_sitter_go": _has_dist("tree_sitter_go"),
    }
    multilang_ok = all(multilang_modules.values())

    dev_modules = {
        "pytest": _has_dist("pytest"),
        "httpx": _has_dist("httpx"),
        "ruff": _has_dist("ruff"),
    }

    return {
        "semantic": {
            "available": semantic_ok,
            "modules": semantic_modules,
            "pip_install": 'pip install "own-your-code[semantic]"',
        },
        "multilang": {
            "available": multilang_ok,
            "modules": multilang_modules,
            "pip_install": 'pip install "own-your-code[multilang]"',
        },
        "full": {
            "available": semantic_ok and multilang_ok,
            "pip_install": 'pip install "own-your-code[full]"',
        },
        "dev": {
            "available": all(dev_modules.values()),
            "modules": dev_modules,
            "pip_install": 'pip install "own-your-code[dev]"',
        },
    }
