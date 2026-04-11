# Rollback record — 2026-04-11

This file inventories work that was **reverted** from `main` in a single revert commit, per maintainer request (“rollback new changes and record everything”).

## Reverted commit range

`fed1aad..HEAD` immediately before the revert (four commits), restoring the tree to the same state as **`fed1aad`** (`test(api): cover OWN_YOUR_CODE_UI_DIST SPA serving`).

| Commit | Summary |
|------------|---------|
| `3fefc61` | **embed_preflight** — `GET /embed/preflight`, MCP `embed_preflight`, `db.count_unembedded_intents`, UI preflight + confirm before `POST /embed`, tests. **embeddings:** `local_files_only_from_env`, HF offline env support. |
| `df624cf` | **v0.1.9** — version bump (`pyproject.toml`, `npm/.../package.json`), README (long-running tools, offline HF, evolution without Git, TOC), AGENTS.md, USER-GUIDE §9.2. |
| `c8e7548` | **Lightweight preflight** — `_deps_available()` via `importlib.util.find_spec` instead of importing `sentence_transformers`. |
| `f11553c` | **check_dependencies** — `src/deps.py`, `check_optional_dependencies()`, MCP `check_dependencies`, CLI `own-your-code deps`, `/server-info` `optional_dependencies`, `embedding_stack_available()` delegating to deps. |

## Tags / releases

- **`v0.1.9`** may still exist on the remote; it pointed at artifacts that included the above. After rollback, `main` no longer matches that tag’s code. **PyPI/npm** may already have published 0.1.9 — this rollback does not unpublish packages. Follow up manually if you need tag deletion or a corrective release.

## How to restore the reverted work

Cherry-pick the four commits in order (oldest first):

```bash
git cherry-pick 3fefc61 c8e7548 df624cf f11553c
```

Or recover from reflog before the revert commit.

## Post-revert version on `main`

Package version returns to **0.1.8** (as in `fed1aad`’s parent release commit `4338f15` / files at `fed1aad`).
