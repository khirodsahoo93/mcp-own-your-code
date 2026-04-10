# own-your-code-mcp (npm shim)

**Own Your Code** — an **[MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server** for **Cursor**, **Claude Desktop**, **Windsurf**, and other hosts. It records *why* each function exists (intent ledger, SQLite). The real implementation is the Python package **[own-your-code](https://pypi.org/project/own-your-code/)** on PyPI; this npm package is a small installer/MCP launcher.

## Install (Node users)

```bash
npx own-your-code-mcp install
```

This ensures the **PyPI** package is available, then runs `own-your-code install` to merge MCP config (paths documented in the [main README](https://github.com/khirodsahoo93/mcp-own-your-code)).

## Install (recommended, no Node)

```bash
pipx install own-your-code
own-your-code install
```

## Links

| Resource | URL |
|----------|-----|
| **PyPI** (`pip install own-your-code`) | https://pypi.org/project/own-your-code/ |
| **GitHub** (source, UI, docs) | https://github.com/khirodsahoo93/mcp-own-your-code |
| **User guide** | https://github.com/khirodsahoo93/mcp-own-your-code/blob/main/docs/USER-GUIDE.md |

**Requirements:** Python **3.11+** on your PATH (`python3` / `python`).

The MCP server process is **`own-your-code-mcp`** (Python); this npm package only wraps it for Node-based workflows.
