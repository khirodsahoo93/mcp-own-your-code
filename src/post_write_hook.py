"""
Post-write hook for editors that support post-save / post-edit commands.
Fires after Write / Edit / NotebookEdit on supported source files.

Also available as the ``own-your-code-hook`` console script (on PATH after pip/pipx install).

Example hook config (shape depends on your editor; use ``own-your-code-hook`` on PATH):

{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          { "type": "command", "command": "own-your-code-hook" }
        ]
      }
    ]
  }
}

Git checkout without install: ``python3 path/to/hooks/post_write.py`` (wrapper sets PYTHONPATH).

The hook reads a JSON payload on stdin with tool_name and tool_input.

Behaviour per function after each file write:
  - Changed function WITH existing intent  → auto-record evolution (no backlog entry needed)
  - Changed/new function WITHOUT intent    → add file to backlog (needs record_intent later)
  - Unchanged functions                    → skip
  - Project root not found (no .git etc.) → fall back to file's parent dir so files are
                                             still tracked even without a local project setup
"""
import json
import sys
from pathlib import Path

from src import db
from src.extractor import get_git_hash, scan_single_file

WATCHED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go"}

_PROJECT_MARKERS = [
    ".git", "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "go.mod", "Cargo.toml",
]


def _find_project_root(file_path: Path) -> str:
    """
    Walk up from the file looking for a project marker.
    Falls back to the file's immediate parent so that files outside any
    recognised project structure are still tracked.
    """
    for parent in [file_path.parent, *file_path.parents]:
        if any((parent / m).exists() for m in _PROJECT_MARKERS):
            return str(parent)
    return str(file_path.parent)


def _process_file(project_id: int, project_root: str, fp: Path, rel: str, tool_name: str) -> None:
    """
    Scan the written file, diff each function against the DB, then:
      - auto-record evolution for changed functions that already have intent
      - add file to backlog for any new or intent-less changed functions
    """
    functions = scan_single_file(str(fp), project_root)

    if not functions:
        # No extractable functions (e.g. config file, empty module) — log and move on
        db.record_hook_event(project_id, rel, tool_name)
        return

    git_hash = get_git_hash(project_root)
    needs_backlog = False

    for fn in functions:
        existing = db.get_function(project_id, fn["qualname"], fn["file"])
        fn_id, is_changed = db.upsert_function(project_id, fn)

        if not is_changed:
            continue  # source identical — nothing to do

        if existing is not None:
            # Function already known — check whether it's been annotated
            latest_intent = db.get_latest_intent(fn_id)
            if latest_intent:
                # Annotated: auto-record that it changed (we don't know WHY yet)
                db.record_evolution(fn_id, {
                    "change_summary": f"Modified via {tool_name}",
                    "reason": None,
                    "triggered_by": None,
                    "git_hash": git_hash,
                })
            else:
                # Changed but never annotated — flag for record_intent
                needs_backlog = True
        else:
            # Brand-new function — needs intent annotation
            needs_backlog = True

    if needs_backlog:
        db.record_hook_event(project_id, rel, tool_name)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    file_path = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("notebook_path")
        or ""
    )

    if not file_path or not any(file_path.endswith(ext) for ext in WATCHED_EXTENSIONS):
        sys.exit(0)

    fp = Path(file_path).resolve()
    if not fp.exists():
        sys.exit(0)

    project_root = _find_project_root(fp)

    try:
        project_id = db.upsert_project(project_root)
        rel = str(fp.relative_to(project_root))
        _process_file(project_id, project_root, fp, rel, tool_name)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
