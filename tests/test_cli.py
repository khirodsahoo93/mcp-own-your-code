import json
from pathlib import Path

from src.cli import merge_mcp_file, SERVER_KEY


def test_merge_mcp_file_creates_and_merges(tmp_path: Path):
    cfg = tmp_path / "mcp.json"
    merge_mcp_file(cfg, SERVER_KEY, {"command": "own-your-code-mcp", "args": []})
    data = json.loads(cfg.read_text())
    assert "mcpServers" in data
    assert data["mcpServers"][SERVER_KEY]["command"] == "own-your-code-mcp"

    merge_mcp_file(cfg, SERVER_KEY, {"command": "/other", "args": ["-v"]})
    data = json.loads(cfg.read_text())
    assert data["mcpServers"][SERVER_KEY]["command"] == "/other"


def test_merge_preserves_other_servers(tmp_path: Path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"x": {"command": "true"}}}))
    merge_mcp_file(cfg, SERVER_KEY, {"command": "oyc", "args": []})
    data = json.loads(cfg.read_text())
    assert "x" in data["mcpServers"]
    assert SERVER_KEY in data["mcpServers"]
