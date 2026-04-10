#!/usr/bin/env node
/**
 * Starts the stdio MCP server via the Python entry point (after pip install own-your-code).
 */
const { spawnSync } = require("child_process");

function findPython() {
  for (const cmd of ["python3", "python", "py"]) {
    const r = spawnSync(cmd, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"], {
      encoding: "utf8",
    });
    if (r.status === 0) {
      return cmd;
    }
  }
  return null;
}

const py = findPython();
if (!py) {
  console.error("own-your-code-mcp: need Python 3.11+ on PATH.");
  process.exit(1);
}

const shell = process.platform === "win32";
let r = spawnSync("own-your-code-mcp", { stdio: "inherit", shell });
if (r.status !== null && !r.error) {
  process.exit(r.status ?? 0);
}

r = spawnSync(py, ["-m", "pip", "install", "-U", "own-your-code"], { stdio: "inherit" });
if (r.status !== 0) {
  process.exit(r.status ?? 1);
}

r = spawnSync("own-your-code-mcp", { stdio: "inherit", shell });
if (r.error) {
  console.error("Run: pipx install own-your-code (then ensure pipx bin is on PATH)");
  process.exit(1);
}
process.exit(r.status ?? 0);
