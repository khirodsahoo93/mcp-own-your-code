import textwrap

from src import db
from src.extractor import scan_project_multi


def test_upsert_and_get_project(tmp_path):
    root = str(tmp_path.resolve())
    pid = db.upsert_project(root, "demo")
    assert isinstance(pid, int) and pid >= 1
    row = db.get_project(root)
    assert row is not None
    assert row["path"] == root
    assert row["name"] == "demo"


def test_prune_stale_functions_removes_orphan_rows(tmp_path, monkeypatch):
    db_file = tmp_path / "p.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    monkeypatch.setattr(db, "_db_initialized", False)
    db.init_db()

    proj_root = tmp_path / "app"
    proj_root.mkdir()
    (proj_root / "a.py").write_text("def a(): pass\n")
    (proj_root / "b.py").write_text("def b(): pass\n")

    pid = db.upsert_project(str(proj_root.resolve()))
    for fn in scan_project_multi(str(proj_root.resolve()))[0]:
        db.upsert_function(pid, fn)

    assert len(db.get_all_functions(pid)) == 2

    (proj_root / "b.py").unlink()
    keys = {(f["file"], f["qualname"]) for f in scan_project_multi(str(proj_root.resolve()))[0]}
    assert len(keys) == 1

    dry = db.prune_stale_functions(pid, keys, dry_run=True)
    assert dry["removed_functions"] == 1
    assert dry["removed_intents"] == 0
    assert len(db.get_all_functions(pid)) == 2

    stats = db.prune_stale_functions(pid, keys, dry_run=False)
    assert stats["removed_functions"] == 1
    assert len(db.get_all_functions(pid)) == 1
    remaining = db.get_all_functions(pid)[0]
    assert remaining["qualname"] == "a"


def test_prune_stale_functions_deletes_intents_for_removed_function(tmp_path, monkeypatch):
    db_file = tmp_path / "q.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    monkeypatch.setattr(db, "_db_initialized", False)
    db.init_db()

    proj_root = tmp_path / "app2"
    proj_root.mkdir()
    (proj_root / "x.py").write_text(textwrap.dedent("""\
        def keep(): pass
        def drop(): pass
    """))

    pid = db.upsert_project(str(proj_root.resolve()))
    fns = scan_project_multi(str(proj_root.resolve()))[0]
    for fn in fns:
        fid, _ = db.upsert_function(pid, fn)
        if fn["qualname"] == "drop":
            db.record_intent(
                fid,
                {"user_request": "test", "reasoning": "r", "confidence": 3},
            )

    (proj_root / "x.py").write_text("def keep(): pass\n")
    keys = {(f["file"], f["qualname"]) for f in scan_project_multi(str(proj_root.resolve()))[0]}
    assert len(keys) == 1

    stats = db.prune_stale_functions(pid, keys, dry_run=False)
    assert stats["removed_functions"] == 1
    assert stats["removed_intents"] == 1
    assert len(db.get_all_functions(pid)) == 1
