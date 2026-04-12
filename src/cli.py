"""
User-facing CLI: MCP installer + terminal helpers.

  own-your-code install [--platform editor-a|editor-b|editor-c|claude-code|all] [--dry-run]
  own-your-code print-config
  own-your-code status [--project-path PATH]
  own-your-code update [PATH] [--name NAME]   (PATH defaults to current directory)
  own-your-code prune [PATH] [--dry-run]      (remove DB rows not in current scan)
  own-your-code visualize [--project-path PATH] --out FILE.html
  own-your-code watch [--project-path PATH] [--interval SEC]
  own-your-code deps [--json]

MCP tools (record_intent, register_project, …) are for AI hosts over stdio.
These CLI commands are for you in a terminal — same SQLite DB, same project_path rules.

Why ``project_path`` exists: the MCP server often runs with cwd = this package’s install
directory, not your app repo, and one DB can hold many projects — so tools need an
explicit root. In a terminal, ``cd`` into your repo and run ``update`` with no path
(or ``update .``) to register the current directory.

Platform IDs map to common MCP config file locations on disk (see README).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
import time
from pathlib import Path

SERVER_KEY = "own-your-code"


def _paths_editor_a() -> list[Path]:
    """Host config: ~/.cursor/mcp.json"""
    return [Path.home() / ".cursor" / "mcp.json"]


def _paths_editor_b() -> list[Path]:
    """Host config: desktop MCP JSON (OS-specific path)."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library/Application Support/Claude/claude_desktop_config.json"]
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return []
        return [Path(appdata) / "Claude" / "claude_desktop_config.json"]
    return [home / ".config" / "Claude" / "claude_desktop_config.json"]


def _paths_editor_c() -> list[Path]:
    """Host config: Codeium / Windsurf MCP JSON."""
    return [Path.home() / ".codeium" / "windsurf" / "mcp_config.json"]


def _paths_claude_code() -> list[Path]:
    """Host config: Claude Code CLI and VSCode Claude extension (~/.claude.json)."""
    return [Path.home() / ".claude.json"]


PLATFORM_PATHS: dict[str, list[Path]] = {
    "editor-a": _paths_editor_a,
    "editor-b": _paths_editor_b,
    "editor-c": _paths_editor_c,
    "claude-code": _paths_claude_code,
}


def shlex_quote(s: str) -> str:
    if not s:
        return "''"
    if all(c.isalnum() or c in "/._-:" for c in s):
        return s
    return json.dumps(s)


def resolve_mcp_server_block() -> tuple[dict, str]:
    """
    Build the JSON object for mcpServers[SERVER_KEY].
    Returns (block, explanation).
    """
    mcp = shutil.which("own-your-code-mcp")
    if mcp:
        return {"command": mcp, "args": [], "env": {}}, "own-your-code-mcp on PATH (pipx/pip install)"

    uvx = shutil.which("uvx")
    if uvx:
        return {
            "command": uvx,
            "args": ["--from", "own-your-code", "own-your-code-mcp"],
            "env": {},
        }, "uvx --from own-your-code (requires PyPI package; https://pypi.org/project/own-your-code/)"

    return {}, (
        "Could not find own-your-code-mcp or uvx. Install first:\n"
        "  pipx install own-your-code\n"
        "  # or: python3 -m pip install own-your-code\n"
        "Then re-run: own-your-code install"
    )


def merge_mcp_file(path: Path, server_key: str, server_block: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}: invalid JSON — {e}") from e
    else:
        data = {}
    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}
    data["mcpServers"][server_key] = server_block
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def cmd_print_config() -> int:
    block, hint = resolve_mcp_server_block()
    if not block:
        print(hint, file=sys.stderr)
        return 1
    print(json.dumps({SERVER_KEY: block}, indent=2))
    print(f"# {hint}", file=sys.stderr)
    return 0


def cmd_install(platforms: list[str], dry_run: bool) -> int:
    block, hint = resolve_mcp_server_block()
    if not block:
        print(hint, file=sys.stderr)
        return 1

    want = set(platforms)
    if "all" in want:
        want = set(PLATFORM_PATHS.keys())

    paths: list[Path] = []
    for name in sorted(want):
        if name not in PLATFORM_PATHS:
            print(f"Unknown platform: {name}", file=sys.stderr)
            print(f"Choose from: {', '.join(sorted(PLATFORM_PATHS))}, all", file=sys.stderr)
            return 2
        paths.extend(PLATFORM_PATHS[name]())

    seen: set[Path] = set()
    unique = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)

    print(f"own-your-code install — {hint}\n")
    for p in unique:
        if dry_run:
            print(f"[dry-run] would merge into {p}:")
            print(json.dumps({SERVER_KEY: block}, indent=2))
            print()
        else:
            merge_mcp_file(p, SERVER_KEY, block)
            print(f"Updated {p}")

    if not dry_run:
        print("\nRestart your editor or MCP host so it reloads configuration.")
    return 0


def infer_registered_project_from_cwd() -> str | None:
    """
    If the current working directory is a registered project root, or lies inside one,
    return that project's stored path (the longest / most specific match). Otherwise None.
    """
    from src import db

    try:
        cwd = Path.cwd().resolve()
    except (OSError, RuntimeError):
        return None

    cwd_s = str(cwd)
    if db.get_project(cwd_s):
        return cwd_s

    candidates: list[str] = []
    for row in db.list_projects():
        reg = row["path"]
        try:
            base = Path(reg).resolve()
        except OSError:
            base = Path(reg)
        if cwd == base:
            candidates.append(reg)
            continue
        try:
            if cwd.is_relative_to(base):
                candidates.append(reg)
        except ValueError:
            pass

    if not candidates:
        return None
    return max(candidates, key=lambda s: len(Path(s).parts))


def resolve_cli_project_path(explicit: str | None) -> tuple[str | None, str | None]:
    """
    Resolve which registered project path to use for visualize/watch (and optional status).

    Returns (registered_path, err_msg). err_msg set when resolution fails.
    """
    from src import db

    if explicit:
        root = Path(explicit).expanduser().resolve()
        s = str(root)
        if db.get_project(s):
            return s, None
        return None, (
            f"Not registered: {s}\n"
            f"Run: own-your-code update {shlex_quote(s)}"
        )

    inferred = infer_registered_project_from_cwd()
    if inferred:
        return inferred, None

    try:
        cwd_s = str(Path.cwd().resolve())
    except (OSError, RuntimeError):
        cwd_s = "(could not resolve cwd)"
    return None, (
        f"No registered project contains the current directory {cwd_s}.\n"
        "From your repo root run: own-your-code update\n"
        "Or pass: --project-path /absolute/path/to/project"
    )


def cmd_status(project_path: str | None) -> int:
    """Print DB location and optional per-project coverage stats."""
    from src import db

    print(f"Database: {db.DB_PATH}")
    if not db.DB_PATH.exists():
        print("(file not created yet — run register/update or MCP register_project.)")
    if not project_path:
        inferred = infer_registered_project_from_cwd()
        if inferred:
            project_path = inferred
        else:
            projects = db.list_projects()
            if not projects:
                print("No projects registered yet.")
            else:
                print("Registered projects:")
                for p in projects:
                    print(f"  {p['path']}")
            return 0

    proj = db.get_project(project_path)
    if not proj:
        print(f"Not registered: {project_path}", file=sys.stderr)
        print("Run: own-your-code update " + json.dumps(project_path), file=sys.stderr)
        return 1
    cmap = db.get_codebase_map(proj["id"])
    total = cmap["total_functions"]
    ann = cmap["annotated"]
    pct = round(ann / total * 100, 1) if total else 0.0
    print(f"Project: {proj['path']}")
    print(f"Functions: {total}  annotated: {ann}  coverage: {pct}%")
    print(f"Features: {len(cmap['features'])}  hook backlog files: {len(cmap.get('hook_backlog') or [])}")
    return 0


def cmd_update(path: str, name: str | None) -> int:
    """Re-scan and upsert functions (same idea as MCP register_project)."""
    from src import db
    from src.extractor import scan_project_multi

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    project_id = db.upsert_project(str(root), name)
    functions, errors = scan_project_multi(str(root))
    new = 0
    for fn in functions:
        _, is_new = db.upsert_function(project_id, fn)
        if is_new:
            new += 1
    print(f"Registered {root} — {len(functions)} functions indexed, {new} new/changed rows.")
    for e in errors[:10]:
        print(f"  parse note: {e}", file=sys.stderr)
    if len(errors) > 10:
        print(f"  … and {len(errors) - 10} more parse notes", file=sys.stderr)
    return 0


def cmd_prune(path: str, dry_run: bool) -> int:
    """Remove functions (and intents, etc.) not present in a fresh scan."""
    from src import db
    from src.extractor import scan_project_multi

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    proj = db.get_project(str(root))
    if not proj:
        print(f"Not registered: {root}", file=sys.stderr)
        print(f"Run: own-your-code update {shlex_quote(str(root))}", file=sys.stderr)
        return 1

    functions, errors = scan_project_multi(str(root))
    keys = {(f["file"], f["qualname"]) for f in functions}
    stats = db.prune_stale_functions(proj["id"], keys, dry_run=dry_run)

    label = "Would remove" if dry_run else "Removed"
    print(
        f"{label} {stats['removed_functions']} stale function row(s); "
        f"intents {stats['removed_intents']}, decisions {stats['removed_decisions']}, "
        f"evolution {stats['removed_evolution']}, feature_links {stats['removed_feature_links']}, "
        f"intent_embeddings {stats['removed_intent_embeddings']}."
    )
    if dry_run:
        print("(dry-run — no changes written. Run without --dry-run to apply.)")
    for e in errors[:5]:
        print(f"  parse note: {e}", file=sys.stderr)
    if len(errors) > 5:
        print(f"  … and {len(errors) - 5} more parse notes", file=sys.stderr)
    return 0


def cmd_visualize(project_path: str | None, out: Path) -> int:
    """Write a standalone HTML report (open in a browser)."""
    from src import db

    resolved, err = resolve_cli_project_path(project_path)
    if err:
        print(err, file=sys.stderr)
        return 1
    project_path = resolved

    proj = db.get_project(project_path)
    if not proj:
        print(f"Not registered: {project_path}", file=sys.stderr)
        print("Run: own-your-code update " + shlex_quote(project_path), file=sys.stderr)
        return 1
    cmap = db.get_codebase_map(proj["id"])
    total = cmap["total_functions"]
    ann = cmap["annotated"]
    pct = round(ann / total * 100, 1) if total else 0.0

    rows_html = []
    for file, fns in sorted(cmap["by_file"].items()):
        n = len(fns)
        a = sum(1 for f in fns if f["has_intent"])
        fpct = round(a / n * 100, 1) if n else 0
        rows_html.append(
            f"<tr><td class='mono'>{html.escape(file)}</td>"
            f"<td>{a}/{n}</td><td>{fpct}%</td></tr>"
        )

    fn_rows = []
    for file, fns in sorted(cmap["by_file"].items()):
        for fn in sorted(fns, key=lambda x: (x.get("lineno") or 0, x["qualname"])):
            intent = fn.get("intent") or {}
            snippet = (intent.get("user_request") or "")[:120]
            fn_rows.append(
                "<tr>"
                f"<td class='mono'>{html.escape(fn['qualname'])}</td>"
                f"<td class='mono'>{html.escape(file)}</td>"
                f"<td>{html.escape(snippet)}{'…' if len((intent.get('user_request') or '')) > 120 else ''}</td>"
                f"<td>{'yes' if fn['has_intent'] else '—'}</td>"
                "</tr>"
            )

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Own Your Code — {html.escape(proj['path'])}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:24px;}}
h1{{font-size:1.25rem;}} .muted{{color:#8b949e;font-size:0.9rem;}}
table{{border-collapse:collapse;width:100%;margin-top:16px;font-size:0.85rem;}}
th,td{{border:1px solid #30363d;padding:8px;text-align:left;}}
th{{background:#161b22;color:#8b949e;}}
.mono{{font-family:ui-monospace,monospace;font-size:0.8rem;}}
.stats{{display:flex;gap:24px;margin-top:12px;flex-wrap:wrap;}}
.stat strong{{color:#3fb950;}}
</style></head><body>
<h1>Own Your Code — intent map</h1>
<p class="muted">Generated from the same SQLite ledger as MCP. Open this file in any browser.</p>
<p class="mono">{html.escape(proj['path'])}</p>
<div class="stats">
  <div class="stat"><strong>{total}</strong> functions</div>
  <div class="stat"><strong>{ann}</strong> annotated</div>
  <div class="stat"><strong>{pct}%</strong> coverage</div>
  <div class="stat"><strong>{len(cmap['features'])}</strong> features</div>
</div>
<h2>By file</h2>
<table><thead><tr><th>File</th><th>Annotated / total</th><th>%</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table>
<h2>Functions</h2>
<table><thead><tr><th>Function</th><th>File</th><th>Intent (preview)</th><th>OK</th></tr></thead>
<tbody>{''.join(fn_rows)}</tbody></table>
</body></html>"""
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


def cmd_deps(as_json: bool) -> int:
    """Print optional dependency status (semantic, multilang, dev)."""
    from src.deps import check_optional_dependencies

    data = check_optional_dependencies()
    if as_json:
        print(json.dumps(data, indent=2))
        return 0

    print("Optional dependencies (own-your-code)\n")
    for key in ("semantic", "multilang", "full", "dev"):
        block = data[key]
        if key == "full":
            ok = "yes" if block["available"] else "no"
            print(f"full (semantic + multilang): {ok}")
            print(f"  install: {block['pip_install']}\n")
            continue
        print(f"{key}:")
        for mod, present in block["modules"].items():
            print(f"  {mod}: {'yes' if present else 'no'}")
        overall = "ready" if block["available"] else "incomplete"
        print(f"  overall: {overall}")
        print(f"  install: {block['pip_install']}\n")
    return 0


def cmd_watch(project_path: str | None, interval: int) -> int:
    """Print coverage stats every INTERVAL seconds until Ctrl+C."""
    from src import db

    resolved, err = resolve_cli_project_path(project_path)
    if err:
        print(err, file=sys.stderr)
        return 1
    project_path = resolved

    proj = db.get_project(project_path)
    if not proj:
        print(f"Not registered: {project_path}", file=sys.stderr)
        return 1
    print(f"Watching {project_path} every {interval}s (Ctrl+C to stop)\n")
    try:
        while True:
            cmap = db.get_codebase_map(proj["id"])
            total = cmap["total_functions"]
            ann = cmap["annotated"]
            pct = round(ann / total * 100, 1) if total else 0.0
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            backlog = len(cmap.get("hook_backlog") or [])
            print(f"[{ts}] annotated {ann}/{total} ({pct}%) hook backlog files: {backlog}")
            time.sleep(max(1, interval))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="own-your-code",
        description="Own Your Code — installer and helpers for MCP hosts.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser(
        "install",
        help="Merge MCP server config into known host config files (see --platform).",
    )
    p_install.add_argument(
        "--platform",
        action="append",
        dest="platforms",
        metavar="NAME",
        help="editor-a (Cursor) | editor-b (Claude Desktop) | editor-c (Windsurf) | claude-code (Claude Code CLI + VSCode) (repeatable). Default: all.",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files",
    )

    sub.add_parser("print-config", help="Print mcpServers JSON fragment to stdout")

    p_deps = sub.add_parser(
        "deps",
        help="Show optional packages (semantic, multilang, dev) without importing torch.",
    )
    p_deps.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable output",
    )

    p_status = sub.add_parser(
        "status",
        help="Show SQLite DB path and registered projects, or stats for one project.",
    )
    p_status.add_argument(
        "--project-path",
        metavar="PATH",
        help="Registered project root (optional). If omitted: use cwd when it lies inside a registered project, else list all projects.",
    )

    p_up = sub.add_parser(
        "update",
        help="Scan and index a codebase (terminal equivalent of MCP register_project).",
    )
    p_up.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root (default: current working directory). Use . or an absolute path.",
    )
    p_up.add_argument("--name", default=None, help="Optional display name")

    p_prune = sub.add_parser(
        "prune",
        help="Delete function rows (and linked intents, etc.) not found in a fresh scan.",
    )
    p_prune.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root (default: current working directory). Must match a registered path.",
    )
    p_prune.add_argument(
        "--dry-run",
        action="store_true",
        help="Show counts only; do not delete.",
    )

    p_vis = sub.add_parser(
        "visualize",
        help="Write a standalone HTML intent report (open in a browser).",
    )
    p_vis.add_argument(
        "--project-path",
        default=None,
        metavar="PATH",
        help="Registered project root (default: infer from current directory).",
    )
    p_vis.add_argument("--out", required=True, type=Path, metavar="FILE.html", help="Output HTML path")

    p_watch = sub.add_parser(
        "watch",
        help="Print coverage stats every N seconds until Ctrl+C.",
    )
    p_watch.add_argument(
        "--project-path",
        default=None,
        metavar="PATH",
        help="Registered project root (default: infer from current directory).",
    )
    p_watch.add_argument("--interval", type=int, default=30, metavar="SEC", help="Seconds between lines (default: 30)")

    args = parser.parse_args(argv)

    if args.cmd == "print-config":
        return cmd_print_config()

    if args.cmd == "deps":
        return cmd_deps(args.json)

    if args.cmd == "install":
        platforms = args.platforms
        if not platforms:
            platforms = ["all"]
        return cmd_install(platforms, args.dry_run)

    if args.cmd == "status":
        return cmd_status(args.project_path)

    if args.cmd == "update":
        return cmd_update(args.path, args.name)

    if args.cmd == "prune":
        return cmd_prune(args.path, args.dry_run)

    if args.cmd == "visualize":
        return cmd_visualize(args.project_path, args.out)

    if args.cmd == "watch":
        return cmd_watch(args.project_path, args.interval)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
