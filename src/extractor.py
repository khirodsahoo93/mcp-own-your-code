"""
AST extractor: walks a project and extracts every function
with full metadata. Used by annotate_existing and project scanning.

Supports Python (ast module), TypeScript/JavaScript, and Go via pluggable
drivers in src/extractors/. The legacy scan_project() function is kept for
backwards compatibility and still returns Python-only results. Use
scan_project_multi() for multi-language support.
"""
import ast
import textwrap
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
             "dist", "build", ".mypy_cache", "migrations", ".next", "target",
             ".tox", "coverage", "__snapshots__"}
SKIP_DUNDERS = {"__str__", "__repr__", "__eq__", "__hash__", "__lt__",
                "__le__", "__gt__", "__ge__", "__contains__", "__len__",
                "__iter__", "__next__", "__enter__", "__exit__",
                "__getitem__", "__setitem__", "__delitem__"}


def scan_project(root: str) -> tuple[list[dict], list[str]]:
    """Scan for Python files only (legacy, kept for backwards compatibility)."""
    root_path = Path(root).resolve()
    functions, errors = [], []

    for path in sorted(root_path.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(root_path))
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            fns = extract_functions(source, rel)
            functions.extend(fns)
        except SyntaxError as e:
            errors.append(f"{rel}: SyntaxError line {e.lineno}: {e.msg}")
        except Exception as e:
            errors.append(f"{rel}: {e}")

    return functions, errors


def scan_project_multi(
    root: str,
    include_globs: list[str] | None = None,
    ignore_dirs: list[str] | None = None,
    languages: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Scan a project for all supported languages using pluggable extractors.

    Args:
        root:          Absolute path to the project root.
        include_globs: List of glob patterns relative to root (e.g. ["src/**/*.ts"]).
                       If None, scans all files with supported extensions.
        ignore_dirs:   Additional directory names to skip (merged with SKIP_DIRS).
        languages:     Restrict to these language identifiers (e.g. ["python", "typescript"]).

    Returns:
        (functions, errors) — functions include a 'language' field.
    """
    from .extractors import get_extractor, SUPPORTED_EXTENSIONS

    root_path = Path(root).resolve()
    skip = SKIP_DIRS | set(ignore_dirs or [])
    functions: list[dict] = []
    errors: list[str] = []

    if include_globs:
        candidates = []
        for pattern in include_globs:
            candidates.extend(root_path.glob(pattern))
        candidates = sorted(set(candidates))
    else:
        candidates = []
        for ext in SUPPORTED_EXTENSIONS:
            candidates.extend(root_path.rglob(f"*{ext}"))
        candidates = sorted(set(candidates))

    for path in candidates:
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        ext = path.suffix.lower()
        extractor = get_extractor(ext)
        if extractor is None:
            continue
        if languages and extractor.language not in languages:
            continue
        fns, errs = extractor.scan_file(str(path), str(root_path))
        functions.extend(fns)
        errors.extend(errs)

    return functions, errors


def extract_functions(source: str, filepath: str) -> list[dict]:
    tree = ast.parse(source)
    lines = source.splitlines()
    results = []

    class_ranges: dict[str, tuple[int,int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_ranges[node.name] = (node.lineno, node.end_lineno)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in SKIP_DUNDERS:
            continue

        class_name = None
        for cname, (cs, ce) in class_ranges.items():
            if cs <= node.lineno <= ce:
                class_name = cname
                break

        qualname = f"{class_name}.{node.name}" if class_name else node.name
        func_lines = lines[node.lineno - 1: node.end_lineno]
        source_snippet = textwrap.dedent("\n".join(func_lines))
        docstring = ast.get_docstring(node)
        sig = _build_sig(node)
        calls = _extract_calls(node)

        results.append({
            "file": filepath,
            "name": node.name,
            "qualname": qualname,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "signature": sig,
            "docstring": docstring,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "is_method": class_name is not None,
            "class_name": class_name,
            "source": source_snippet,
            "calls": calls,
        })

    return results


def _build_sig(node) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = node.args
    parts = []
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        part = arg.arg
        if arg.annotation:
            part += f": {ast.unparse(arg.annotation)}"
        di = i - defaults_offset
        if di >= 0:
            part += f" = {ast.unparse(args.defaults[di])}"
        parts.append(part)
    if args.vararg: parts.append(f"*{args.vararg.arg}")
    if args.kwarg:  parts.append(f"**{args.kwarg.arg}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({', '.join(parts)}){ret}"


def _extract_calls(node) -> list[str]:
    calls = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.add(child.func.attr)
    return sorted(calls)


def get_git_hash(path: str) -> str | None:
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=path, capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None
