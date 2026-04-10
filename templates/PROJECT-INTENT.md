# Own Your Code — expectations for this repository

This project uses **Own Your Code** (your team’s MCP install): a small server that stores **why** functions exist, **what was decided**, and **how code evolved**.

## For any coding agent (Claude, GPT, Cursor, Copilot, …)

1. **`register_project`** once with the absolute path to this repo root (if not already registered).
2. After you **write or materially change** a function, call **`record_intent`** with `user_request` at minimum; add `reasoning`, `feature`, and `decisions` when possible.
3. If **`get_codebase_map`** shows **`hook_backlog`** entries for files you touched, clear them with **`record_intent`** or **`mark_file_reviewed`** (non-semantic edits only).
4. For behavioral changes to existing functions, use **`record_evolution`** and update intent if the “why” changed.

Intent data lives in the server’s SQLite store (`owns.db` by default, or **`OWN_YOUR_CODE_DB`**), not necessarily in this repo.

---

*Copy this file into your application repo as `INTENT.md` or `AGENTS.md` and adjust the intro link to your team’s docs.*
