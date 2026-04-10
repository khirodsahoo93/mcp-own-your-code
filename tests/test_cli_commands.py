"""CLI subcommands: status, update, visualize (isolated DB)."""
import importlib
import textwrap
from pathlib import Path

import pytest

from src.cli import main


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_test.db"
    monkeypatch.setenv("OWN_YOUR_CODE_DB", str(db_file))
    import src.db as db_mod

    importlib.reload(db_mod)
    db_mod.init_db()
    yield db_file
    importlib.reload(db_mod)


def test_status_empty_project_list(isolated_db, capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Database:" in out
    assert "No projects registered" in out


def test_update_defaults_to_cwd(isolated_db, tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def from_cwd(): pass\n")
    monkeypatch.chdir(proj)
    assert main(["update"]) == 0
    root = proj.resolve()
    assert main(["status", "--project-path", str(root)]) == 0


def test_update_then_status_and_visualize(isolated_db, tmp_path, capsys):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text(textwrap.dedent("""\
        def foo():
            return 1
    """))

    assert main(["update", str(proj)]) == 0
    assert main(["status", "--project-path", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "coverage:" in out

    html_out = tmp_path / "out.html"
    assert main(["visualize", "--project-path", str(proj), "--out", str(html_out)]) == 0
    text = html_out.read_text(encoding="utf-8")
    assert "Own Your Code" in text
    assert "foo" in text
    assert "a.py" in text


def test_status_visualize_infer_project_from_cwd(isolated_db, tmp_path, capsys, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def bar(): pass\n")
    assert main(["update", str(proj)]) == 0

    monkeypatch.chdir(proj)
    assert main(["status"]) == 0
    assert "coverage:" in capsys.readouterr().out

    html_out = tmp_path / "from_cwd.html"
    assert main(["visualize", "--out", str(html_out)]) == 0
    assert "bar" in html_out.read_text(encoding="utf-8")


def test_visualize_without_project_path_errors_outside_repo(isolated_db, tmp_path, capsys):
    assert main(["visualize", "--out", str(tmp_path / "x.html")]) != 0
    err = capsys.readouterr().err
    assert "No registered project" in err or "current directory" in err
