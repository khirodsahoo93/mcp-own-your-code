"""
Go extractor using tree-sitter-go.

Falls back to a regex pass if tree-sitter-go is not installed.
"""
from __future__ import annotations

import re
import textwrap
from .base import ExtractorBase

_GO_PARSER = None
_GO_AVAILABLE = None


def _get_parser():
    global _GO_PARSER, _GO_AVAILABLE
    if _GO_AVAILABLE is not None:
        return _GO_PARSER
    try:
        import tree_sitter_go as tsgo
        from tree_sitter import Language, Parser
        lang = Language(tsgo.language())
        p = Parser(lang)
        _GO_PARSER = p
        _GO_AVAILABLE = True
    except Exception:
        _GO_AVAILABLE = False
    return _GO_PARSER


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
        if node.type != "function_declaration" and node.type != "method_declaration":
            continue

        name = None
        receiver_type = None

        if node.type == "method_declaration":
            # First child of method_declaration is the receiver parameter_list
            # Structure: (parameter_list (parameter_declaration name: (identifier) type: (pointer_type (type_identifier))))
            for child in node.children:
                if child.type == "parameter_list" and receiver_type is None:
                    for param in child.children:
                        if param.type == "parameter_declaration":
                            for pchild in param.children:
                                if pchild.type == "type_identifier":
                                    receiver_type = source_bytes[pchild.start_byte:pchild.end_byte].decode("utf-8", errors="replace")
                                    break
                                elif pchild.type == "pointer_type":
                                    for pp in pchild.children:
                                        if pp.type == "type_identifier":
                                            receiver_type = source_bytes[pp.start_byte:pp.end_byte].decode("utf-8", errors="replace")
                                            break
                                if receiver_type:
                                    break
                        if receiver_type:
                            break
                    break

        for child in node.children:
            if child.type == "identifier" and name is None:
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            elif child.type == "field_identifier" and name is None:
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

        if not name:
            continue

        qualname = f"{receiver_type}.{name}" if receiver_type else name
        lineno = node.start_point[0] + 1
        end_lineno = node.end_point[0] + 1
        func_lines = lines[node.start_point[0]: node.end_point[0] + 1]
        source_snippet = textwrap.dedent("\n".join(func_lines))

        # Build signature from first line
        sig_line = lines[node.start_point[0]] if lines else ""
        sig = sig_line.strip()

        results.append({
            "file":      filepath,
            "name":      name,
            "qualname":  qualname,
            "lineno":    lineno,
            "end_lineno": end_lineno,
            "signature": sig,
            "docstring": None,
            "is_async":  False,
            "is_method": node.type == "method_declaration",
            "class_name": receiver_type,
            "source":    source_snippet,
            "calls":     [],
            "language":  "go",
        })

    return results


# ── regex fallback ──────────────────────────────────────────────────────────

_FUNC_RE = re.compile(
    r"^func\s+(?:\(\w+\s+\*?(\w+)\)\s+)?(\w+)\s*\(",
    re.MULTILINE,
)


def _extract_regex_fallback(source: str, filepath: str) -> list[dict]:
    lines = source.splitlines()
    results = []
    for m in _FUNC_RE.finditer(source):
        receiver = m.group(1)
        name = m.group(2)
        lineno = source[: m.start()].count("\n") + 1
        qualname = f"{receiver}.{name}" if receiver else name
        results.append({
            "file":      filepath,
            "name":      name,
            "qualname":  qualname,
            "lineno":    lineno,
            "end_lineno": lineno,
            "signature": m.group(0).strip(),
            "docstring": None,
            "is_async":  False,
            "is_method": receiver is not None,
            "class_name": receiver,
            "source":    "\n".join(lines[lineno - 1: lineno + 10]),
            "calls":     [],
            "language":  "go",
        })
    return results


class GoExtractor(ExtractorBase):
    @property
    def language(self) -> str:
        return "go"

    def extract(self, source: str, filepath: str) -> list[dict]:
        results = _extract_with_treesitter(source, filepath)
        if not results:
            results = _extract_regex_fallback(source, filepath)
        return results
