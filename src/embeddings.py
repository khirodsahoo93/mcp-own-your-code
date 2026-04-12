"""
Semantic embeddings for intent search.

Requires sentence-transformers and numpy (optional dependencies).
If unavailable, all functions degrade gracefully so the rest of the
server keeps working — semantic search just returns an empty result with
an informative message.

Default model: all-MiniLM-L6-v2 (fast, 22M params, 384-dim vectors).
Override with the OWN_YOUR_CODE_EMBED_MODEL env var.

Offline / air-gapped: if the model is already in the Hugging Face cache (or you pass
a local directory path as OWN_YOUR_CODE_EMBED_MODEL), set one of:
  HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1, or OWN_YOUR_CODE_EMBED_LOCAL_ONLY=1
so loads use local_files_only=True and do not contact the Hub.
"""
from __future__ import annotations

import os
import struct
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("OWN_YOUR_CODE_EMBED_MODEL", "all-MiniLM-L6-v2")

_model_cache: dict[str, object] = {}


def _deps_available() -> bool:
    """
    True if sentence-transformers and numpy appear installed, without importing them.

    Delegates to :func:`deps.check_optional_dependencies` so probe logic stays in one place.
    """
    from .deps import check_optional_dependencies

    return bool(check_optional_dependencies()["semantic"]["available"])


def embedding_stack_available() -> bool:
    """True if sentence-transformers and numpy are installed (semantic / hybrid search)."""
    return _deps_available()


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def local_files_only_from_env() -> bool:
    """
    True when embedding loads should not contact the Hugging Face Hub.

    Honors standard HF/transformers offline flags plus OWN_YOUR_CODE_EMBED_LOCAL_ONLY.
    Requires weights already cached locally or model_name pointing at a local path.
    """
    if _truthy_env("OWN_YOUR_CODE_EMBED_LOCAL_ONLY"):
        return True
    if _truthy_env("HF_HUB_OFFLINE"):
        return True
    if _truthy_env("TRANSFORMERS_OFFLINE"):
        return True
    return False


def get_model(model_name: str = DEFAULT_MODEL):
    """Load (and cache) a SentenceTransformer model. Returns None if deps missing."""
    if not _deps_available():
        return None
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model %s …", model_name)
        kwargs: dict = {}
        if local_files_only_from_env():
            logger.info("Embedding load: local_files_only=True (HF Hub offline mode)")
            lf = {"local_files_only": True}
            kwargs["model_kwargs"] = lf
            kwargs["tokenizer_kwargs"] = lf
        _model_cache[model_name] = SentenceTransformer(model_name, **kwargs)
    return _model_cache[model_name]


def _intent_text(row: dict) -> str:
    """Build canonical text for a single intent row."""
    parts = [row.get("user_request") or ""]
    if row.get("reasoning"):
        parts.append(row["reasoning"])
    if row.get("implementation_notes"):
        parts.append(row["implementation_notes"])
    return " ".join(p for p in parts if p).strip()


def encode(texts: list[str], model_name: str = DEFAULT_MODEL) -> "list[np.ndarray] | None":
    """Encode a list of strings into L2-normalised vectors. Returns None if deps missing."""
    model = get_model(model_name)
    if model is None:
        return None
    import numpy as np
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [vecs[i] for i in range(len(vecs))]


def vec_to_blob(vec: "np.ndarray") -> bytes:
    """Serialise a float32 numpy vector to raw bytes for SQLite BLOB storage."""
    import numpy as np
    arr = np.asarray(vec, dtype=np.float32)
    return struct.pack(f"{len(arr)}f", *arr)


def blob_to_vec(blob: bytes) -> "np.ndarray":
    """Deserialise bytes from SQLite BLOB back to a float32 numpy array."""
    import numpy as np
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)


def cosine_scores(query_vec: "np.ndarray", stored_vecs: "list[np.ndarray]") -> "np.ndarray":
    """Compute cosine similarity between query_vec and each stored vector (already L2-normalised)."""
    import numpy as np
    if not stored_vecs:
        return np.array([], dtype=np.float32)
    matrix = np.stack(stored_vecs, axis=0)  # (N, dim)
    q = np.asarray(query_vec, dtype=np.float32)
    # Both are L2-normalised so dot product == cosine similarity
    return matrix @ q


def embed_project(project_id: int, model_name: str = DEFAULT_MODEL) -> dict:
    """
    Compute and store embeddings for all intents in a project that don't yet
    have an embedding for the given model.

    Returns a summary dict: {embedded, skipped, model, available}.
    """
    from . import db

    if not _deps_available():
        return {"available": False, "embedded": 0, "skipped": 0, "model": model_name,
                "message": "sentence-transformers not installed. Run: pip install sentence-transformers numpy"}

    unembedded = db.get_unembedded_intents(project_id, model_name)
    if not unembedded:
        return {"available": True, "embedded": 0, "skipped": 0, "model": model_name,
                "message": "All intents already embedded."}

    texts = [_intent_text(r) for r in unembedded]
    vecs = encode(texts, model_name)
    if vecs is None:
        return {"available": False, "embedded": 0, "skipped": len(unembedded), "model": model_name}

    for row, vec in zip(unembedded, vecs):
        db.store_embedding(row["intent_id"], model_name, vec_to_blob(vec))

    return {"available": True, "embedded": len(unembedded), "skipped": 0, "model": model_name}


def semantic_search(project_id: int, query: str, limit: int = 20,
                    model_name: str = DEFAULT_MODEL) -> tuple[list[dict], bool]:
    """
    Search intents by semantic similarity.

    Returns (results, available) where available=False if deps are missing.
    Each result dict has: qualname, file, lineno, signature, user_request,
    reasoning, score.
    """
    from . import db

    if not _deps_available():
        return [], False

    stored = db.get_embeddings_for_project(project_id, model_name)
    if not stored:
        return [], True  # available but nothing embedded yet

    import numpy as np
    query_vecs = encode([query], model_name)
    if query_vecs is None:
        return [], False

    query_vec = query_vecs[0]
    stored_vecs = [blob_to_vec(r["vector"]) for r in stored]
    scores = cosine_scores(query_vec, stored_vecs)

    indexed = sorted(zip(scores, stored), key=lambda x: -x[0])[:limit]

    results = []
    for score, row in indexed:
        results.append({
            "qualname":        row["qualname"],
            "file":            row["file"],
            "lineno":          row["lineno"],
            "signature":       row["signature"],
            "user_request":    row["user_request"],
            "reasoning": row.get("reasoning"),
            "score":           float(score),
        })
    return results, True


def hybrid_search(project_id: int, query: str, limit: int = 20,
                  model_name: str = DEFAULT_MODEL,
                  semantic_weight: float = 0.5) -> tuple[list[dict], str]:
    """
    Merge keyword (LIKE) and semantic results with tunable weights.

    Returns (results, mode_used) where mode_used is 'hybrid', 'keyword', or 'semantic'.
    """
    from . import db

    keyword_rows = db.search_intents(project_id, query)
    sem_results, sem_available = semantic_search(project_id, query, limit=limit * 2, model_name=model_name)

    if not sem_available or not sem_results:
        # Fall back to keyword only
        return keyword_rows[:limit], "keyword"

    if not keyword_rows:
        return sem_results[:limit], "semantic"

    # Merge by qualname+file key
    kw_weight = 1.0 - semantic_weight
    scores: dict[str, float] = {}
    rows_by_key: dict[str, dict] = {}

    max_kw_rank = len(keyword_rows)
    for rank, r in enumerate(keyword_rows):
        key = f"{r['file']}::{r['qualname']}"
        # Rank-based keyword score: best rank = 1.0
        kw_score = (max_kw_rank - rank) / max_kw_rank
        scores[key] = scores.get(key, 0.0) + kw_weight * kw_score
        rows_by_key[key] = r

    for r in sem_results:
        key = f"{r['file']}::{r['qualname']}"
        scores[key] = scores.get(key, 0.0) + semantic_weight * r["score"]
        if key not in rows_by_key:
            rows_by_key[key] = r

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:limit]
    results = []
    for key, score in ranked:
        row = dict(rows_by_key[key])
        row["score"] = round(score, 4)
        results.append(row)

    return results, "hybrid"
