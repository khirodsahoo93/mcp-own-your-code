# own-your-code-mcp (npm shim)

Node users can run:

```bash
npx own-your-code-mcp install
```

This installs the **[own-your-code](https://pypi.org/project/own-your-code/)** Python package (PyPI) if needed, then runs `own-your-code install` to merge MCP config for Cursor, Claude Desktop, and Windsurf.

**Requirements:** Python **3.11+** on your PATH (`python3` / `python`).

**Recommended (no Node):**

```bash
pipx install own-your-code
own-your-code install
```

The MCP server itself is Python (`own-your-code-mcp`); this npm package is only a convenience wrapper.
