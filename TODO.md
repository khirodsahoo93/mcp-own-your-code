# Own Your Code — roadmap / todo

Actionable follow-ups for this project. Check items off as you ship.

## Semantic intent search

- [x] **Embedding model** — `all-MiniLM-L6-v2` via `sentence-transformers` (optional dep). Override with `OWN_YOUR_CODE_EMBED_MODEL` env var. Documented in `src/embeddings.py`.
- [x] **Schema** — `intent_embeddings(intent_id, model, vector BLOB, created_at)` table added via migration v2. `PRAGMA user_version` tracks schema version.
- [x] **Indexing** — `embed_project()` in `src/embeddings.py` computes and stores L2-normalised vectors from `user_request + claude_reasoning + implementation_notes`.
- [x] **Backfill job** — `embed_intents` MCP tool + `POST /embed` API endpoint. Idempotent; only processes un-embedded intents.
- [x] **`find_by_intent`** — New `mode` param: `keyword` (default) / `semantic` / `hybrid`. Semantic uses cosine similarity over stored vectors; hybrid merges keyword rank + semantic score with tunable `semantic_weight`.
- [x] **Hybrid search** — `emb.hybrid_search()` merges keyword LIKE ranks and semantic cosine scores.
- [x] **UI Search tab** — Mode toggle bar (Keyword / Semantic / Hybrid). Shows score % for semantic/hybrid results. Displays which mode was actually used (auto-routing hint).
- [x] **Tests** — `tests/test_embeddings.py`: vec roundtrip, cosine scores, encode, embed_project idempotency, semantic search relevance, hybrid fallback, db helpers.

## Multi-language AST indexing

- [x] **Scope** — v1: Python (ast), TypeScript/JavaScript (tree-sitter-javascript), Go (tree-sitter-go). Regex fallback when tree-sitter not installed.
- [x] **Extractor abstraction** — `src/extractors/` package: `ExtractorBase` ABC + `PythonExtractor`, `TypeScriptExtractor`, `GoExtractor` drivers. Registry maps extension → driver.
- [x] **`register_project` / scan** — `scan_project_multi()` in `extractor.py`. Accepts `include_globs`, `ignore_dirs`, `languages` config. `register_project` MCP tool + `/register` API both updated.
- [x] **Stable qualnames** — Python: `Class.method`. TypeScript: `ClassName.method` (via tree-sitter parent walk). Go: `ReceiverType.Method`.
- [x] **Hook** — `post_write_hook.py` now watches `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.go`.
- [x] **Docs** — See README (update if needed). Supported: Python, TypeScript, JavaScript, Go.

## Cross-cutting

- [x] **CI** — `.github/workflows/ci.yml`: lint (ruff), tests on Python 3.11/3.12/3.13, smoke test, UI build.
- [x] **Versioning** — `PRAGMA user_version` (current: 2). Migration v1→v2 adds `intent_embeddings` table. `ALTER TABLE` for `language` column backfills existing DBs.
