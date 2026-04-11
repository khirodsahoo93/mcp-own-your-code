"""Tests for optional dependency probing."""
from src import deps


def test_check_optional_dependencies_shape():
    d = deps.check_optional_dependencies()
    assert set(d.keys()) == {"semantic", "multilang", "full", "dev"}
    for key in ("semantic", "multilang", "dev"):
        assert "available" in d[key]
        assert "modules" in d[key]
        assert "pip_install" in d[key]
        assert isinstance(d[key]["available"], bool)
        assert isinstance(d[key]["modules"], dict)
    assert "available" in d["full"]
    assert "pip_install" in d["full"]
    assert "modules" not in d["full"]
    assert d["full"]["available"] == (d["semantic"]["available"] and d["multilang"]["available"])


def test_semantic_false_if_sentence_transformers_missing(monkeypatch):
    import importlib.util

    real = importlib.util.find_spec

    def fake(name):
        if name == "sentence_transformers":
            return None
        return real(name)

    monkeypatch.setattr(importlib.util, "find_spec", fake)
    d = deps.check_optional_dependencies()
    assert d["semantic"]["available"] is False
    assert d["semantic"]["modules"]["sentence_transformers"] is False
