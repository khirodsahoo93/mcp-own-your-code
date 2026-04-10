#!/usr/bin/env node
/**
 * Delegates to the Python `own-your-code` CLI after ensuring the PyPI package is importable.
 * Usage: npx own-your-code-mcp install [--platform editor-a] [--dry-run]
 */
const { spawnSync } = require("child_process");

function findPython() {
  const candidates = ["python3", "python", "py"];
  for (const cmd of candidates) {
    const r = spawnSync(cmd, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"], {
      encoding: "utf8",
    });
    if (r.status === 0) {
      return cmd;
    }
  }
  return null;
}

function pyOk(py) {
  const r = spawnSync(
    py,
    ["-c", "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('src') and importlib.util.find_spec('src.cli') else 1)"],
    { encoding: "utf8" },
  );
  return r.status === 0;
}

function pipInstall(py) {
  return spawnSync(py, ["-m", "pip", "install", "-U", "own-your-code"], { stdio: "inherit" }).status === 0;
}

function runOwnYourCode(py, args) {
  const shell = process.platform === "win32";
  let r = spawnSync("own-your-code", args, { stdio: "inherit", shell });
  if (r.status !== null && !r.error) {
    return r.status;
  }
  r = spawnSync(py, ["-m", "pip", "show", "own-your-code"], { encoding: "utf8", shell });
  if (r.status !== 0) {
    console.error("Installing own-your-code from PyPI…");
    if (!pipInstall(py)) {
      console.error("pip install own-your-code failed. Install Python 3.11+ and try again.");
      return 1;
    }
  }
  r = spawnSync("own-your-code", args, { stdio: "inherit", shell });
  if (r.status !== null && !r.error) {
    return r.status;
  }
  console.error(
    "Could not run `own-your-code`. Add Python Scripts to PATH (Windows) or use: pipx install own-your-code",
  );
  return 1;
}

const py = findPython();
if (!py) {
  console.error("own-your-code-mcp: need Python 3.11+ (python3) on PATH.");
  process.exit(1);
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: npx own-your-code-mcp install [--platform editor-a] [--dry-run]\n       npx own-your-code-mcp print-config");
  process.exit(2);
}

if (!pyOk(py)) {
  console.error("Installing / upgrading own-your-code…");
  if (!pipInstall(py)) {
    process.exit(1);
  }
}

process.exit(runOwnYourCode(py, args));
