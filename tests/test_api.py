"""
API integration tests.

All tests use an isolated SQLite DB via the OWN_YOUR_CODE_DB env var and
monkeypatching src.db.DB_PATH so no real data is touched.
"""
import os
import textwrap
import time
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every test at a fresh temporary SQLite file."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("OWN_YOUR_CODE_DB", str(db_file))
    import src.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    monkeypatch.setattr(db_mod, "_db_initialized", False)
    db_mod.init_db()
    yield


@pytest.fixture()
def client():
    # Re-import app after env is patched so API_KEY is fresh
    import importlib
    import api.main as api_mod
    importlib.reload(api_mod)
    return TestClient(api_mod.app)


@pytest.fixture()
def registered(client, tmp_path):
    """Register a small project and return (client, project_path)."""
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "utils.py").write_text(textwrap.dedent("""\
        def add(a, b):
            return a + b

        def subtract(a, b):
            return a - b
    """))
    r = client.post("/register", json={"path": str(proj)})
    assert r.status_code == 200
    return client, str(proj)


# ── basic ──────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_serves_ui_when_own_your_code_ui_dist_set(tmp_path, monkeypatch, isolated_db):
    """PyPI installs have no ui/dist next to api; env override must still serve the SPA."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!DOCTYPE html><html><body>ledger-ui-test</body></html>"
    )
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("// ok")
    monkeypatch.setenv("OWN_YOUR_CODE_UI_DIST", str(dist))

    import importlib

    import api.main as api_mod

    importlib.reload(api_mod)
    tc = TestClient(api_mod.app)
    assert tc.get("/health").status_code == 200
    r = tc.get("/")
    assert r.status_code == 200
    assert b"ledger-ui-test" in r.content
    r_asset = tc.get("/assets/app.js")
    assert r_asset.status_code == 200


def test_projects_list_empty(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert r.json()["projects"] == []


def test_embed_preflight_not_registered(client):
    r = client.get(
        "/embed/preflight",
        params={"project_path": "/nonexistent/project/path"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["project_registered"] is False
    assert body["can_start"] is False
    assert body["pending_count"] == 0


def test_embed_preflight_registered_no_intents(client, tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "a.py").write_text("def f(): pass\n")
    assert client.post("/register", json={"path": str(proj)}).status_code == 200
    r = client.get("/embed/preflight", params={"project_path": str(proj)})
    assert r.status_code == 200
    body = r.json()
    assert body["project_registered"] is True
    assert body["pending_count"] == 0
    assert body["can_start"] is False


# ── register ──────────────────────────────────────────────────────────────

def test_register_indexes_functions(client, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "app.py").write_text("def hello(): pass\ndef world(): pass\n")
    r = client.post("/register", json={"path": str(proj)})
    assert r.status_code == 200
    body = r.json()
    assert body["functions"] >= 2
    assert body["by_language"]["python"] >= 2


def test_register_nonexistent_path(client):
    r = client.post("/register", json={"path": "/nonexistent/path/xyz"})
    assert r.status_code == 400


def test_register_idempotent(client, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "app.py").write_text("def hello(): pass\n")
    client.post("/register", json={"path": str(proj)})
    r2 = client.post("/register", json={"path": str(proj)})
    assert r2.status_code == 200
    assert r2.json()["new"] == 0  # nothing new second time


# ── map ────────────────────────────────────────────────────────────────────

def test_map_returns_by_file(registered):
    client, proj_path = registered
    r = client.get(f"/map?project_path={proj_path}")
    assert r.status_code == 200
    body = r.json()
    assert "by_file" in body
    assert any("utils.py" in f for f in body["by_file"])


def test_map_file_filter(registered):
    client, proj_path = registered
    r = client.get(f"/map?project_path={proj_path}&file=utils.py")
    assert r.status_code == 200
    body = r.json()
    assert list(body["by_file"].keys()) == ["utils.py"]


def test_map_file_filter_not_found(registered):
    client, proj_path = registered
    r = client.get(f"/map?project_path={proj_path}&file=nope.py")
    assert r.status_code == 404


def test_map_unregistered_project(client):
    r = client.get("/map?project_path=/does/not/exist")
    assert r.status_code == 404


# ── function ───────────────────────────────────────────────────────────────

def test_function_found(registered):
    client, proj_path = registered
    r = client.get(f"/function?project_path={proj_path}&function_name=add")
    assert r.status_code == 200
    assert r.json()["qualname"] == "add"


def test_function_not_found(registered):
    client, proj_path = registered
    r = client.get(f"/function?project_path={proj_path}&function_name=nonexistent")
    assert r.status_code == 404


# ── search ─────────────────────────────────────────────────────────────────

def test_search_keyword_no_intents(registered):
    client, proj_path = registered
    r = client.post("/search", json={"project_path": proj_path, "query": "add"})
    assert r.status_code == 200
    # no intents recorded yet — results may be empty but endpoint works
    assert "results" in r.json()


def test_search_keyword_finds_result(registered):
    client, proj_path = registered
    import src.db as db_mod
    proj = db_mod.get_project(proj_path)
    fn = db_mod.get_function(proj["id"], "add")
    db_mod.record_intent(fn["id"], {"user_request": "add two numbers together"})
    r = client.post("/search", json={"project_path": proj_path, "query": "add two"})
    assert r.status_code == 200
    assert len(r.json()["results"]) >= 1


def test_search_unregistered_project(client):
    r = client.post("/search", json={"project_path": "/nope", "query": "add"})
    assert r.status_code == 404


# ── embed ──────────────────────────────────────────────────────────────────

def test_embed_returns_202_and_job_id(registered):
    client, proj_path = registered
    r = client.post(f"/embed?project_path={proj_path}")
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["status"] == "running"


def test_embed_status_endpoint(registered):
    client, proj_path = registered
    r = client.post(f"/embed?project_path={proj_path}")
    job_id = r.json()["job_id"]
    # Poll until done (background tasks run in TestClient's thread)
    for _ in range(20):
        s = client.get(f"/embed/{job_id}")
        assert s.status_code == 200
        if s.json()["status"] != "running":
            break
        time.sleep(0.1)
    # status should be done or error (error = sentence-transformers not installed, which is fine)
    assert s.json()["status"] in ("done", "error")


def test_embed_status_unknown_job(client):
    r = client.get("/embed/doesnotexist")
    assert r.status_code == 404


def test_embed_unregistered_project(client):
    r = client.post("/embed?project_path=/nope")
    assert r.status_code == 404


def test_evolution_timeline_newest_first(client, registered, monkeypatch):
    """GET /evolution returns cross-function changes ordered by changed_at DESC."""
    client, path = registered
    from src import db

    proj = db.get_project(path)
    fns = db.get_all_functions(proj["id"])
    assert len(fns) >= 2
    f_a, f_b = fns[0], fns[1]

    seq = iter(
        [
            "2020-01-01T10:00:00",
            "2025-06-01T12:00:00",
            "2022-03-15T08:30:00",
        ]
    )
    monkeypatch.setattr(db, "now", lambda: next(seq))

    db.record_evolution(f_a["id"], {"change_summary": "oldest"})
    db.record_evolution(f_b["id"], {"change_summary": "newest"})
    db.record_evolution(f_a["id"], {"change_summary": "middle"})

    r = client.get(f"/evolution?project_path={quote(path)}")
    assert r.status_code == 200
    summaries = [e["change_summary"] for e in r.json()["entries"]]
    assert summaries == ["newest", "middle", "oldest"]


# ── auth ───────────────────────────────────────────────────────────────────

def test_auth_disabled_by_default(client):
    """No API key set — all requests pass without a header."""
    r = client.get("/health")
    assert r.status_code == 200


def test_auth_rejects_missing_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OWN_YOUR_CODE_API_KEY", "secret123")
    import importlib, api.main as api_mod
    importlib.reload(api_mod)
    c = TestClient(api_mod.app)
    r = c.get("/projects")
    assert r.status_code == 401


def test_auth_accepts_correct_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OWN_YOUR_CODE_API_KEY", "secret123")
    import importlib, api.main as api_mod
    importlib.reload(api_mod)
    c = TestClient(api_mod.app)
    r = c.get("/health", headers={"X-Api-Key": "secret123"})
    assert r.status_code == 200


def test_auth_rejects_wrong_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OWN_YOUR_CODE_API_KEY", "secret123")
    import importlib, api.main as api_mod
    importlib.reload(api_mod)
    c = TestClient(api_mod.app)
    r = c.get("/projects", headers={"X-Api-Key": "wrongkey"})
    assert r.status_code == 401


def test_server_info_public_when_auth_required(monkeypatch, tmp_path):
    """UI can read /server-info without a key even when API routes are protected."""
    monkeypatch.setenv("OWN_YOUR_CODE_API_KEY", "secret123")
    import importlib, api.main as api_mod
    importlib.reload(api_mod)
    c = TestClient(api_mod.app)
    r = c.get("/server-info")
    assert r.status_code == 200
    body = r.json()
    assert body["api_auth_required"] is True
    assert "semantic_stack_installed" in body


def test_server_info_when_auth_disabled(client):
    r = client.get("/server-info")
    assert r.status_code == 200
    assert r.json()["api_auth_required"] is False
