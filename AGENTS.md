# Own Your Code — rules for any coding agent

You are working with **Own Your Code** (MCP server `own-your-code`, SQLite store). Your job is to leave a **durable “why” layer** next to the code so humans and future sessions can navigate by **intent**, not only by symbols.

These rules apply whether you run as Claude, GPT, Gemini, or any other MCP-capable assistant.

## When to act

| Situation | Tool |
|-----------|------|
| You **add or meaningfully change** a function | `record_intent` |
| You **change behavior** of existing code (not typo-only) | `record_evolution` (and often `record_intent` if purpose shifted) |
| User asks what/why/how regarding a function | `explain_function`, `get_evolution` |
| User wants a whole-codebase picture | `get_codebase_map` |
| User wants “everything about X” (keyword) | `find_by_intent` |
| Legacy codebase, no history | `annotate_existing` |
| Hook shows file touched but change was **non-semantic** | `mark_file_reviewed` |
| First time on a repo | `register_project` |

## `record_intent` (non-negotiable for real edits)

After substantive edits, call **`record_intent`** with at least:

- **`user_request`** — what the user asked for (quote or tight paraphrase).
- **`file`**, **`function_name`**, **`project_path`**.

**`reasoning`** is optional for a **fast capture** (e.g. mid-session). If omitted, the system stores a placeholder and caps confidence — **follow up with a richer `record_intent` when you can**, including:

- **`reasoning`** — what the function does and why this design.
- **`implementation_notes`** — edge cases, limits, invariants.
- **`feature`** — short label (e.g. `Auth`, `Billing`) for clustering.
- **`decisions`** — `{ decision, reason, alternatives?, constraint? }` for real tradeoffs.

Calling `record_intent` **clears the editor-hook backlog** for that file.

## Hook queue

`get_codebase_map` returns **`hook_backlog`**: files the post-write hook saw but that are not yet cleared. For each row:

- Semantic change → **`record_intent`** (per touched function as appropriate).
- No intent to record (formatting, mechanical) → **`mark_file_reviewed`**.

## Honesty

- Prefer accurate **confidence** (5 = you just wrote it; 1–3 = inferred).
- **`find_by_intent`** is **keyword** search, not semantic embeddings — set user expectations if they ask for “semantic” search.

## Where state lives

- Database file: **`owns.db`** by default in the **server** project directory (the MCP `cwd`), or the path in **`OWN_YOUR_CODE_DB`** if set — not inside each app repo unless you configure otherwise.

Copy **`templates/PROJECT-INTENT.md`** into repos you care about so every agent session sees the same expectations.
