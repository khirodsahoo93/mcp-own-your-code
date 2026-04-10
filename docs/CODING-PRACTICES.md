# Coding practices (Own Your Code)

Conventions for anyone changing this repository. End users should read [USER-GUIDE.md](USER-GUIDE.md) instead.

## Environment

- **Python:** 3.11+ (see `requires-python` in `pyproject.toml`). CI exercises 3.11, 3.12, and 3.13.
- **Install for development:**

  ```bash
  pip install -e ".[dev,full]"
  ```

  Use a virtual environment; do not commit `.venv` or local `owns.db` unless the project explicitly tracks fixtures.

## Before you push

```bash
pytest
ruff check src/ api/ tests/
```

Fix new lint issues in touched files. Prefer fixing warnings you introduce rather than widening ignore rules.

## Code changes

- **Scope:** Keep diffs focused on the task. Avoid drive-by refactors, unrelated formatting sweeps, or churn in files you do not need to touch.
- **Consistency:** Match naming, imports, error handling, and docstring depth of the surrounding module. Prefer extending existing helpers over parallel implementations.
- **Types:** Use type hints where they clarify public APIs and non-obvious data shapes; do not annotate every trivial local for its own sake.
- **Comments:** Explain *why* when the code cannot, not what the next line obviously does. Preserve existing comments unless they are wrong.
- **Errors:** Surface actionable messages (what failed, what the user can do). When embedding user or DB-derived text in HTML or logs, escape or structure it safely (see `html.escape` patterns in the CLI visualize path).

## Tests

- Add or update tests for behavior you change. Prefer tests that pin outcomes users care about, not implementation details.
- When tests need isolation from a developer’s real database, use environment variables such as `OWN_YOUR_CODE_DB` and a temporary path, consistent with existing `tests/` patterns.
- Run the full suite locally before opening a PR; flaky or skipped tests should be called out in the PR description.

## MCP tools and HTTP API

- **Contract:** Tool names, parameter shapes, and semantics are part of the product. Breaking changes require a deliberate version story and documentation updates.
- **Documentation:** If you add or change tools, update user-facing docs where appropriate ([README.md](../README.md), [USER-GUIDE.md](USER-GUIDE.md)) and [AGENTS.md](../AGENTS.md) so MCP clients know when and how to call them.
- **Parity:** Keep server behavior, FastAPI routes, and tests aligned so CLI, UI, and MCP stay consistent.

## SQLite and schema

- Schema evolution uses `PRAGMA user_version` and migration helpers in code. New migrations must be safe on existing databases (additive where possible, with clear upgrade paths).
- Do not assume the DB file lives in a single fixed path in tests; honor `OWN_YOUR_CODE_DB` and project registration flows.

## Security and privacy

- Do not commit API keys, tokens, or production database copies.
- Treat path and intent text as untrusted when rendering HTML or assembling shell-adjacent messages; escape and quote carefully.

## UI and npm wrapper

- The React UI under `ui/` has its own `npm` scripts; after meaningful UI changes, run `npm run build` and fix TypeScript or lint errors.
- The `npm/own-your-code-mcp` package is a thin installer shim; keep it aligned with PyPI versioning when you cut releases.

## Releases (maintainers)

- Bump `version` in `pyproject.toml` and `npm/own-your-code-mcp/package.json` together when publishing; follow the tagging flow in [README.md](../README.md#publishing-maintainers).
