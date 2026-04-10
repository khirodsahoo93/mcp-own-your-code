from src import db


def test_upsert_and_get_project(tmp_path):
    root = str(tmp_path.resolve())
    pid = db.upsert_project(root, "demo")
    assert isinstance(pid, int) and pid >= 1
    row = db.get_project(root)
    assert row is not None
    assert row["path"] == root
    assert row["name"] == "demo"
