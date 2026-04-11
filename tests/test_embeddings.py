"""Tests for the embedding pipeline and semantic search."""
import os
import struct
import pytest

# conftest.py sets OWN_YOUR_CODE_DB before imports
from src import db
from src import embeddings as emb


@pytest.fixture()
def project(tmp_path):
    """Create a registered project with a few intents."""
    pid = db.upsert_project(str(tmp_path), "embed-test")
    fid1, _ = db.upsert_function(pid, {
        "file": "auth.py", "name": "login", "qualname": "login",
        "lineno": 1, "language": "python",
    })
    fid2, _ = db.upsert_function(pid, {
        "file": "payment.py", "name": "charge", "qualname": "charge",
        "lineno": 1, "language": "python",
    })
    iid1 = db.record_intent(fid1, {
        "user_request": "Allow users to log in with email and password",
        "claude_reasoning": "Validates credentials against the database",
    })
    iid2 = db.record_intent(fid2, {
        "user_request": "Charge a credit card for the order total",
        "claude_reasoning": "Calls Stripe API to process payment",
    })
    return {"project_id": pid, "path": str(tmp_path), "intent_ids": [iid1, iid2]}


# ── HF Hub offline env ────────────────────────────────────────────────────────

def test_local_files_only_from_env_default(monkeypatch):
    monkeypatch.delenv("OWN_YOUR_CODE_EMBED_LOCAL_ONLY", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    assert emb.local_files_only_from_env() is False


def test_local_files_only_from_env_flags(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.setenv("OWN_YOUR_CODE_EMBED_LOCAL_ONLY", "1")
    assert emb.local_files_only_from_env() is True


def test_local_files_only_hf_hub_offline(monkeypatch):
    monkeypatch.delenv("OWN_YOUR_CODE_EMBED_LOCAL_ONLY", raising=False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "true")
    assert emb.local_files_only_from_env() is True


def test_local_files_only_transformers_offline(monkeypatch):
    monkeypatch.delenv("OWN_YOUR_CODE_EMBED_LOCAL_ONLY", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    assert emb.local_files_only_from_env() is True


# ── vec serialisation ─────────────────────────────────────────────────────────

def test_vec_roundtrip():
    import numpy as np
    vec = np.array([0.1, 0.2, 0.3, -0.5], dtype=np.float32)
    blob = emb.vec_to_blob(vec)
    back = emb.blob_to_vec(blob)
    np.testing.assert_allclose(vec, back, atol=1e-6)


def test_cosine_scores_normalised():
    import numpy as np
    q = np.array([1.0, 0.0], dtype=np.float32)
    vecs = [
        np.array([1.0, 0.0], dtype=np.float32),  # identical
        np.array([0.0, 1.0], dtype=np.float32),  # orthogonal
    ]
    scores = emb.cosine_scores(q, vecs)
    assert abs(scores[0] - 1.0) < 1e-5
    assert abs(scores[1]) < 1e-5


# ── encode ───────────────────────────────────────────────────────────────────

def test_encode_returns_vectors():
    vecs = emb.encode(["hello world", "payments processing"])
    assert vecs is not None
    assert len(vecs) == 2
    import numpy as np
    for v in vecs:
        # Should be L2 normalised (length ≈ 1)
        assert abs(np.linalg.norm(v) - 1.0) < 1e-4


# ── embed_project ─────────────────────────────────────────────────────────────

def test_embed_project(project):
    result = emb.embed_project(project["project_id"])
    assert result["available"] is True
    assert result["embedded"] == 2

    # Idempotent — re-running embeds 0 new
    result2 = emb.embed_project(project["project_id"])
    assert result2["embedded"] == 0


# ── semantic_search ───────────────────────────────────────────────────────────

def test_semantic_search_returns_relevant_result(project):
    emb.embed_project(project["project_id"])
    results, available = emb.semantic_search(project["project_id"], "user login authentication")
    assert available is True
    assert len(results) > 0
    top = results[0]
    assert top["qualname"] == "login"
    assert "score" in top
    assert 0.0 <= top["score"] <= 1.0


def test_semantic_search_payment_query(project):
    emb.embed_project(project["project_id"])
    results, available = emb.semantic_search(project["project_id"], "credit card billing stripe")
    assert available is True
    assert results[0]["qualname"] == "charge"


def test_semantic_search_no_embeddings(tmp_path):
    pid = db.upsert_project(str(tmp_path / "empty"), "no-embeds")
    results, available = emb.semantic_search(pid, "anything")
    assert available is True
    assert results == []


# ── hybrid_search ─────────────────────────────────────────────────────────────

def test_hybrid_search(project):
    emb.embed_project(project["project_id"])
    results, mode_used = emb.hybrid_search(project["project_id"], "login auth")
    assert mode_used in ("hybrid", "keyword", "semantic")
    assert len(results) > 0


def test_hybrid_falls_back_to_keyword_without_embeddings(tmp_path):
    pid = db.upsert_project(str(tmp_path / "kw-only"), "kw")
    fid, _ = db.upsert_function(pid, {
        "file": "a.py", "name": "authenticate", "qualname": "authenticate",
        "lineno": 1, "language": "python",
    })
    db.record_intent(fid, {"user_request": "authenticate the user"})
    results, mode_used = emb.hybrid_search(pid, "authenticate")
    assert mode_used == "keyword"
    assert any(r.get("qualname") == "authenticate" for r in results)


# ── db helpers ────────────────────────────────────────────────────────────────

def test_store_and_retrieve_embedding(project):
    import numpy as np
    vec = np.array([0.5, -0.5, 0.1], dtype=np.float32)
    blob = emb.vec_to_blob(vec)
    intent_id = project["intent_ids"][0]
    db.store_embedding(intent_id, "test-model", blob)

    rows = db.get_embeddings_for_project(project["project_id"], "test-model")
    assert len(rows) == 1
    back = emb.blob_to_vec(rows[0]["vector"])
    np.testing.assert_allclose(vec, back, atol=1e-6)


def test_get_unembedded_intents(project):
    unembedded = db.get_unembedded_intents(project["project_id"], "all-MiniLM-L6-v2")
    assert len(unembedded) == 2

    # After embedding one, only one remains
    emb.embed_project(project["project_id"])
    unembedded2 = db.get_unembedded_intents(project["project_id"], "all-MiniLM-L6-v2")
    assert len(unembedded2) == 0
