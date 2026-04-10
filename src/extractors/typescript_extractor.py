"""
TypeScript / JavaScript extractor using tree-sitter.

Falls back to a lightweight regex pass if tree-sitter-javascript is not installed,
so the server keeps working even without the optional dependency.
"""
from __future__ import annotations

import re
import textwrap
from .base import ExtractorBase

_TS_PARSER = None
_TS_AVAILABLE = None


def _get_parser():
    global _TS_PARSER, _TS_AVAILABLE
    if _TS_AVAILABLE is not None:
        return _TS_PARSER
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
        lang = Language(tsjs.language())
        p = Parser(lang)
        _TS_PARSER = p
        _TS_AVAILABLE = True
    except Exception:
        _TS_AVAILABLE = False
    return _TS_PARSER


# tree-sitter node types that represent functions/methods
_FUNC_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function_declaration",
    "generator_function",
}


def _extract_ts_name(node, source_bytes: bytes) -> str | None:
    """Best-effort name extraction from a tree-sitter function node."""
    # function_declaration / generator_function_declaration → has a 'name' child
    for child in node.children:
        if child.type == "identifier":
            return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    # method_definition → first named child is the key
    if node.type == "method_definition":
        for child in node.children:
            if child.type in ("property_identifier", "identifier", "computed_property_name"):
                return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return None


def _find_class_name(node, source_bytes: bytes) -> str | None:
    """Walk up the tree to find an enclosing class name."""
    parent = node.parent
    while parent is not None:
        if parent.type in ("class_declaration", "class_expression"):
            for child in parent.children:
                if child.type == "identifier":
                    return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        parent = parent.parent
    return None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _extract_with_treesitter(source: str, filepath: str) -> list[dict]:
    parser = _get_parser()
    if parser is None:
        return []

    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    lines = source.splitlines()
    results = []

    for node in _walk(tree.root_node):
        if node.type not in _FUNC_TYPES:
            continue

        name = _extract_ts_name(node, source_bytes)
        if not name or name.startswith("_") and len(name) == 1:
            name = "<anonymous>"

        class_name = _find_class_name(node, source_bytes)
        qualname = f"{class_name}.{name}" if class_name else name

        lineno = node.start_point[0] + 1
        end_lineno = node.end_point[0] + 1

        func_lines = lines[node.start_point[0]: node.end_point[0] + 1]
        source_snippet = textwrap.dedent("\n".join(func_lines))

        is_async = False
        for child in node.children:
            if child.type == "async":
                is_async = True
                break

        # Build a rough signature from the parameter list
        sig = name
        for child in node.children:
            if child.type in ("formal_parameters", "parameters"):
                params = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                sig = f"function {name}{params}"
                break

        results.append({
            "file":      filepath,
            "name":      name,
            "qualname":  qualname,
            "lineno":    lineno,
            "end_lineno": end_lineno,
            "signature": sig,
            "docstring": None,
            "is_async":  is_async,
            "is_method": node.type == "method_definition",
            "class_name": class_name,
            "source":    source_snippet,
            "calls":     [],
            "language":  "typescript",
        })

    return results


# ── regex fallback ──────────────────────────────────────────────────────────

_FUNC_RE = re.compile(
    r"(?:(?:export\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\([^)]*\)"
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\s*\*?\s*\([^)]*\)|\([^)]*\)\s*=>)"
    r"|(\w+)\s*\([^)]*\)\s*\{)",
    re.MULTILINE,
)

_CLASS_RE = re.compile(r"class\s+(\w+)", re.MULTILINE)


def _extract_regex_fallback(source: str, filepath: str) -> list[dict]:
    lines = source.splitlines()
    results = []
    for m in _FUNC_RE.finditer(source):
        name = m.group(1) or m.group(2) or m.group(3)
        if not name:
            continue
        lineno = source[: m.start()].count("\n") + 1
        results.append({
            "file":      filepath,
            "name":      name,
            "qualname":  name,
            "lineno":    lineno,
            "end_lineno": lineno,
            "signature": m.group(0).strip()[:120],
            "docstring": None,
            "is_async":  "async" in m.group(0),
            "is_method": False,
            "class_name": None,
            "source":    "\n".join(lines[lineno - 1: lineno + 10]),
            "calls":     [],
            "language":  "typescript",
        })
    return results


class TypeScriptExtractor(ExtractorBase):
    @property
    def language(self) -> str:
        return "typescript"

    def extract(self, source: str, filepath: str) -> list[dict]:
        results = _extract_with_treesitter(source, filepath)
        if not results:
            results = _extract_regex_fallback(source, filepath)
        return results
