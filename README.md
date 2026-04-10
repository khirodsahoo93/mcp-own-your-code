# Own Your Code

**A living intent ledger for your codebase.**

Own Your Code captures the *why* behind every function — user requests, tradeoffs, decisions, and evolution — recorded automatically by your coding agent as it builds. Search by keyword or semantic similarity. Browse in a React UI or query via MCP from any agent.

---

## The problem

Code is easy to read. It's impossible to understand.

You can read `hybrid_search()` in 5 minutes and know what it does. You can't know:
- Why cosine similarity instead of BM25?
- Was keyword-only search tried and rejected?
- What user request triggered this function?
- How did it behave before the last refactor?

That context lives in someone's head, a Slack thread, or nowhere.

**Own Your Code captures it at the moment it's created — by the agent that wrote the code.**

---

## Features

- **Intent recording** — `record_intent` captures user request, agent reasoning, implementation notes, and confidence. Called automatically by your coding agent.
- **Decision log** — tradeoffs, alternatives considered, constraints that forced a choice.
- **Evolution timeline** — every behavioral change with the reason and triggering request.
- **Multi-language AST indexing** — Python, TypeScript, JavaScript, Go. Pluggable extractor architecture.
- **Semantic search** — vector embeddings via `sentence-transformers`. Find `charge_card` by searching "what handles payments?".
- **Hybrid search** — merges keyword rank + semantic cosine score with tunable weight.
- **React UI** — Intent Map, Feature clusters, Search tab (keyword/semantic/hybrid), coverage bar, function detail panel.
- **MCP server** — works with Claude Code, Cursor, Claude Desktop, Copilot, or any MCP-capable agent.
- **FastAPI REST backend** — full API, suitable for team deployment.
- **Production-ready** — API key auth, SQLite WAL mode, configurable CORS, background embed jobs, 47 tests.

---

## Quick start

### 1. Install (pick one)

**PyPI (after you publish, or use TestPyPI):**

```bash
pipx install own-your-code # recommended — puts own-your-code-mcp on PATH
own-your-code install               # merges MCP config for Cursor, Claude Desktop, Windsurf
```

```bash
python3 -m pip install own-your-code
own-your-code install --platform cursor
own-your-code install --platform claude-desktop
```

**npm (wrapper — still requires Python 3.11+ on PATH):**

```bash
npx own-your-code-mcp install
```

This runs `pip install -U own-your-code` if needed, then the same `own-your-code install` as above. Publish the shim from `npm/own-your-code-mcp/` to the npm registry when you are ready.

Use **`own-your-code-mcp` on PATH** (pipx/pip) for the actual MCP stdio server. The npm package is mainly so people who live in Node can run **`npx … install`** without memorizing pip; running MCP through `npx` is possible (`bin/mcp-shim.cjs`) but adds latency — prefer the Python binary when you can.

**From source:**

```bash
git clone https://github.com/khirodsahoo93/mcp-own-your-code
cd mcp-own-your-code
python -m venv .venv && source .venv/bin/activate
pip install -e .

# With semantic search support
pip install -e ".[semantic]"

# With multi-language AST support (TypeScript, Go)
pip install -e ".[full]"
```

Manual JSON fragment (if you skip `install`):

```bash
own-your-code print-config
```

**uv users:** if `own-your-code-mcp` is not on PATH but `uvx` is, `own-your-code install` writes a block that runs `uvx --from own-your-code own-your-code-mcp` (once the package is on PyPI).

### 2. Add to your MCP host

After `own-your-code install`, restart the editor. To configure by hand from a git checkout:

```json
{
  "mcpServers": {
    "own-your-code": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/mcp-own-your-code"
    }
  }
}
```

Or if installed as a package:

```json
{
  "mcpServers": {
    "own-your-code": {
      "command": "own-your-code-mcp"
    }
  }
}
```

### 3. Register your project

In your agent (Claude, Cursor, etc.):

```
register_project path="/path/to/your/project"
```

This scans all Python, TypeScript, JavaScript, and Go files and indexes every function.

### 4. Start building

As you write code, your agent calls `record_intent` automatically:

```
record_intent
  project_path="/path/to/your/project"
  file="src/auth.py"
  function_name="verify_token"
  user_request="Add JWT verification so the API rejects unsigned requests"
  reasoning="Using PyJWT with RS256. Chose asymmetric keys so the public key can be distributed to services without exposing the signing key."
  decisions=[{"decision": "RS256 over HS256", "reason": "Asymmetric — services can verify without the secret", "alternatives": ["HS256"]}]
```

### 5. Open the UI

```bash
uvicorn api.main:app --reload --port 8002
```

Open [http://localhost:8002](http://localhost:8002).

---

## MCP tools

| Tool | Description |
|------|-------------|
| `register_project` | Scan and index a codebase (Python, TypeScript, JavaScript, Go) |
| `record_intent` | Record why a function exists — user request, reasoning, decisions |
| `record_evolution` | Log a behavioral change with the reason it happened |
| `explain_function` | Get the full story: intent, decisions, evolution timeline |
| `find_by_intent` | Search by keyword, semantic similarity, or hybrid |
| `embed_intents` | Backfill vector embeddings for semantic search |
| `get_codebase_map` | Full structured map: coverage, hook backlog, functions by file |
| `get_evolution` | Timeline of changes for a specific function |
| `annotate_existing` | Retroactively infer intents on a legacy codebase |
| `mark_file_reviewed` | Clear hook backlog for a file without adding intent |

---

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/projects` | List registered projects |
| `POST` | `/register` | Register and index a project |
| `GET` | `/map` | Full codebase map (supports `?file=` filter) |
| `GET` | `/function` | Intent, decisions, evolution for one function |
| `POST` | `/search` | Search intents (keyword / semantic / hybrid) |
| `POST` | `/embed` | Start background embedding job (returns `job_id`) |
| `GET` | `/embed/{job_id}` | Poll embedding job status |
| `GET` | `/stats` | Coverage and hook backlog summary |
| `GET` | `/features` | Feature clusters |
| `GET` | `/graph` | ReactFlow-compatible node graph |

---

## Search modes

```bash
# Keyword — fast LIKE search over intent text
find_by_intent project_path="..." query="authentication" mode="keyword"

# Semantic — vector cosine similarity (run embed_intents first)
find_by_intent project_path="..." query="what handles retries?" mode="semantic"

# Hybrid — merges keyword rank + semantic score
find_by_intent project_path="..." query="payment processing" mode="hybrid" semantic_weight=0.6
```

Via REST:

```bash
curl -X POST http://localhost:8002/search \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/my/project", "query": "what handles payments?", "mode": "hybrid"}'
```

---

## Multi-language support

| Language | Parser | Fallback |
|----------|--------|---------|
| Python | `ast` (stdlib) | — |
| TypeScript / JavaScript | `tree-sitter-javascript` | regex |
| Go | `tree-sitter-go` | regex |

Configure indexing:

```json
{
  "path": "/my/project",
  "languages": ["python", "typescript"],
  "include_globs": ["src/**/*.ts", "src/**/*.py"],
  "ignore_dirs": ["vendor", "generated"]
}
```

---

## Production deployment

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OWN_YOUR_CODE_DB` | `owns.db` | Path to SQLite file |
| `OWN_YOUR_CODE_API_KEY` | *(unset)* | Require `X-Api-Key` header. Leave unset for local use. |
| `OWN_YOUR_CODE_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `OWN_YOUR_CODE_EMBED_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |

### Docker

```bash
docker compose up
```

Or standalone:

```bash
docker build -t own-your-code .
docker run -p 8002:8002 \
  -e OWN_YOUR_CODE_API_KEY=your-secret \
  -e OWN_YOUR_CODE_CORS_ORIGINS=https://yourapp.com \
  -v $(pwd)/data:/data \
  -e OWN_YOUR_CODE_DB=/data/owns.db \
  own-your-code
```

### Render / Fly.io

A `render.yaml` is included. Set `OWN_YOUR_CODE_API_KEY` and `OWN_YOUR_CODE_DB` as environment variables in your deployment dashboard.

---

## Post-write hook

The post-write hook fires when your editor saves a file and records it in the backlog. Any file written without a subsequent `record_intent` appears in `get_codebase_map` as pending.

```bash
# Install the hook script for non-pip use
cp hooks/post_write.py .git/hooks/post-write && chmod +x .git/hooks/post-write

# Or use the installed entry point
own-your-code-hook
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,full]"

# Run tests
pytest

# Lint
ruff check src/ api/ tests/

# Build UI
cd ui && npm install && npm run build
```

CI runs on Python 3.11, 3.12, and 3.13.

---

## Schema

SQLite. Tables:

| Table | Purpose |
|-------|---------|
| `projects` | Registered codebase roots |
| `functions` | Every known function (AST-extracted) |
| `intents` | Why a function exists — user request, reasoning, confidence |
| `intent_embeddings` | Vector blobs for semantic search (schema v2) |
| `decisions` | Tradeoffs and alternatives considered |
| `evolution` | Timeline of behavioral changes |
| `features` | High-level feature labels |
| `feature_links` | Many-to-many: functions ↔ features |
| `hook_events` | Files written by editor but not yet annotated |

Schema version tracked via `PRAGMA user_version`. Migrations are safe to run on existing databases.

---

## Publishing (maintainers)

### One-time setup

1. **PyPI** — Create the project `own-your-code` on [pypi.org](https://pypi.org). Under **Manage → Publishing**, add a **trusted publisher** for this GitHub repo and workflow **`.github/workflows/release.yml`** (see [PyPI docs](https://docs.pypi.org/trusted-publishers/)).
2. **npm** — Log in locally (`npm login`) once, or create a granular **Automation** token and add it as the GitHub secret **`NPM_TOKEN`** for this repository.

### Automated (recommended)

Push a **semver tag** after bumping `version` in `pyproject.toml` and `npm/own-your-code-mcp/package.json`:

```bash
# bump versions first, commit, then:
git tag v0.1.0
git push origin main && git push origin v0.1.0
```

GitHub Actions **Release** workflow uploads the wheel + sdist to **PyPI** and publishes **`own-your-code-mcp`** to npm.

### Manual

```bash
python3 -m pip install build twine
python3 -m build
TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-YOUR_PYPI_API_TOKEN python3 -m twine upload dist/*
```

```bash
cd npm/own-your-code-mcp
npm publish --access public
```

## License

MIT
