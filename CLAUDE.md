# Claude Code / Cursor

Use **`AGENTS.md`** in this repo for full Own Your Code rules (any MCP-capable agent).

Summary: after real code changes, call **`record_intent`** (minimum: `user_request`; add `reasoning` + `decisions` when you can). Drain **`hook_backlog`** from **`get_codebase_map`** via `record_intent` or **`mark_file_reviewed`**.
