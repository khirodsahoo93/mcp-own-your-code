# Own Your Code — rules for MCP clients

**Who should read this:** Anyone who clones the repo and connects an **AI editor or MCP host** (Cursor, Claude Desktop, Windsurf, …) to the `own-your-code` server. It is **end-user documentation**: it tells the assistant when to call `record_intent`, `record_evolution`, and related tools—not internal maintainer notes.

You are working with **Own Your Code** (MCP server `own-your-code`, SQLite store). Your job is to leave a **durable “why” layer** next to the code so humans and future sessions can navigate by **intent**, not only by symbols.

These rules apply to any tool that speaks MCP to this server.

## When to act

| Situation | Tool |
|-----------|------|
| You **add or meaningfully change** a function | `record_intent` |
| You **change behavior** of existing code (not typo-only) | `record_evolution` (and often `record_intent` if purpose shifted) |
| User asks what/why/how regarding a function | `explain_function`, `get_evolution` |
| User wants a whole-codebase picture | `get_codebase_map` |
| User wants “everything about X” (keyword) | `find_by_intent` |
| Before **`embed_intents`** (large repo, confirm deps/backlog) | `embed_preflight` |
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

## Long-running tools (timeouts)

MCP hosts may kill slow tool calls. Prefer **`keyword`** for **`find_by_intent`** unless semantic quality matters. Call **`embed_preflight`** before **`embed_intents`** on large projects. **`get_codebase_map`** can be slow on huge codebases (many functions). The web UI runs **`POST /embed`** in the background; the **`embed_intents`** MCP tool blocks until embedding finishes.

## Honesty

- Prefer accurate **confidence** (5 = you just wrote it; 1–3 = inferred).
- **`find_by_intent`** keyword / hybrid modes are documented in the README — set user expectations for search quality.

## Where state lives

- Database file: **`owns.db`** by default in the **server** project directory (the MCP `cwd`), or the path in **`OWN_YOUR_CODE_DB`** if set — not inside each app repo unless you configure otherwise.

Copy **`templates/PROJECT-INTENT.md`** into repos you care about so every session sees the same expectations.
