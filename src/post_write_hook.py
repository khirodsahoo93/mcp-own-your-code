"""
Post-write hook for editors that support post-save / post-edit commands.
Fires after Write / Edit / NotebookEdit on Python files.

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
"""
import json
import sys
from pathlib import Path

from src import db


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

    WATCHED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go"}
    if not file_path or not any(file_path.endswith(ext) for ext in WATCHED_EXTENSIONS):
        sys.exit(0)

    fp = Path(file_path).resolve()
    project_root = None
    for parent in [fp.parent] + list(fp.parents):
        if any(
            (parent / marker).exists()
            for marker in [".git", "pyproject.toml", "setup.py", "setup.cfg"]
        ):
            project_root = str(parent)
            break

    if not project_root:
        sys.exit(0)

    try:
        project_id = db.upsert_project(project_root)
        rel = str(fp.relative_to(project_root))
        db.record_hook_event(project_id, rel, tool_name)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
