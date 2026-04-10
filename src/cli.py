"""
User-facing CLI: MCP installer (similar UX to code-review-graph).

  own-your-code install [--platform cursor|claude-desktop|windsurf|all] [--dry-run]
  own-your-code print-config   # print JSON block to paste manually
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SERVER_KEY = "own-your-code"


def _cursor_config_paths() -> list[Path]:
    return [Path.home() / ".cursor" / "mcp.json"]


def _claude_desktop_paths() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library/Application Support/Claude/claude_desktop_config.json"]
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return []
        return [Path(appdata) / "Claude" / "claude_desktop_config.json"]
    return [home / ".config" / "Claude" / "claude_desktop_config.json"]


def _windsurf_paths() -> list[Path]:
    return [Path.home() / ".codeium" / "windsurf" / "mcp_config.json"]


PLATFORM_PATHS: dict[str, list[Path]] = {
    "cursor": _cursor_config_paths,
    "claude-desktop": _claude_desktop_paths,
    "windsurf": _windsurf_paths,
}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="own-your-code",
        description="Own Your Code — installer and helpers for MCP hosts.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="Merge MCP server config for Cursor / Claude Desktop / Windsurf")
    p_install.add_argument(
        "--platform",
        action="append",
        dest="platforms",
        metavar="NAME",
        help="cursor | claude-desktop | windsurf (repeatable). Default: all for this OS.",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files",
    )

    sub.add_parser("print-config", help="Print mcpServers JSON fragment to stdout")

    args = parser.parse_args(argv)

    if args.cmd == "print-config":
        return cmd_print_config()

    if args.cmd == "install":
        platforms = args.platforms
        if not platforms:
            platforms = ["all"]
        return cmd_install(platforms, args.dry_run)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
