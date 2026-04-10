"""
FastAPI backend for the Own Your Code UI.

Local: ``uvicorn api.main:app --reload --port 8002``

Production: set ``PORT`` (e.g. Render/Fly). Optional ``OWN_YOUR_CODE_DB`` for SQLite path.

Auth:
  Set ``OWN_YOUR_CODE_API_KEY`` to require ``X-Api-Key: <key>`` on every request.
  Leave unset to run without auth (local / trusted-network only).

CORS:
  Set ``OWN_YOUR_CODE_CORS_ORIGINS`` to a comma-separated list of allowed origins
  (e.g. ``https://myapp.example.com,https://admin.example.com``).
  Defaults to ``*`` (open) when unset.
"""
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import db
from src import embeddings as emb
from src.extractor import scan_project_multi

# ── config from environment ────────────────────────────────────────────────

_API_KEY = os.environ.get("OWN_YOUR_CODE_API_KEY", "").strip()
_CORS_RAW = os.environ.get("OWN_YOUR_CODE_CORS_ORIGINS", "*")
_CORS_ORIGINS = [o.strip() for o in _CORS_RAW.split(",") if o.strip()]

# ── auth ───────────────────────────────────────────────────────────────────

def _auth(x_api_key: Optional[str] = Header(None, alias="X-Api-Key")):
    """Require X-Api-Key header when OWN_YOUR_CODE_API_KEY is set."""
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(401, "Invalid or missing API key. Set X-Api-Key header.")

# ── app ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Own Your Code",
    description="Living intent map — why your code exists, captured as you build (any MCP-capable agent).",
    dependencies=[Depends(_auth)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── background embed job tracking ─────────────────────────────────────────

_embed_jobs: dict[str, dict] = {}  # job_id -> {status, ...}


@app.get("/health")
def health():
    return {"status": "ok", "service": "own-your-code"}


class RegisterReq(BaseModel):
    path: str
    name: str = ""
    languages: list[str] = []
    include_globs: list[str] = []
    ignore_dirs: list[str] = []

class SearchReq(BaseModel):
    project_path: str
    query: str
    mode: str = "keyword"          # keyword | semantic | hybrid
    limit: int = 20
    semantic_weight: float = 0.5


@app.get("/projects")
def list_projects():
    return {"projects": db.list_projects()}


@app.post("/register")
def register(req: RegisterReq):
    if not Path(req.path).exists():
        raise HTTPException(400, f"Path not found: {req.path}")
    pid = db.upsert_project(req.path, req.name or None)
    functions, errors = scan_project_multi(
        req.path,
        include_globs=req.include_globs or None,
        ignore_dirs=req.ignore_dirs or None,
        languages=req.languages or None,
    )
    new = 0
    lang_counts: dict[str, int] = {}
    for fn in functions:
        _, is_new = db.upsert_function(pid, fn)
        if is_new:
            new += 1
        lang = fn.get("language", "python")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    return {"project_id": pid, "path": req.path, "functions": len(functions),
            "new": new, "by_language": lang_counts, "errors": errors}


@app.get("/map")
def codebase_map(project_path: str, file: Optional[str] = None):
    proj = db.get_project(project_path)
    if not proj: raise HTTPException(404, "Project not registered")
    cmap = db.get_codebase_map(proj["id"])
    if file:
        if file not in cmap["by_file"]:
            raise HTTPException(404, f"File '{file}' not in project map")
        cmap["by_file"] = {file: cmap["by_file"][file]}
    return cmap


@app.get("/features")
def features(project_path: str):
    proj = db.get_project(project_path)
    if not proj: raise HTTPException(404, "Not registered")
    return {"features": db.get_features(proj["id"])}


@app.get("/function")
def explain(project_path: str, function_name: str, file: str = ""):
    proj = db.get_project(project_path)
    if not proj: raise HTTPException(404, "Not registered")
    fn = db.get_function(proj["id"], function_name, file or None)
    if not fn: raise HTTPException(404, f"Function '{function_name}' not found")
    intents   = db.get_intents(fn["id"])
    decisions = db.get_decisions(fn["id"])
    evolution = db.get_evolution(fn["id"])
    for row in intents:
        if row.get("claude_reasoning") is not None:
            row["agent_reasoning"] = row["claude_reasoning"]
    return {**dict(fn), "intents": intents, "decisions": decisions, "evolution": evolution}


@app.post("/search")
def search(req: SearchReq):
    proj = db.get_project(req.project_path)
    if not proj:
        raise HTTPException(404, "Not registered")

    mode = req.mode
    if mode == "semantic":
        results, available = emb.semantic_search(proj["id"], req.query, limit=req.limit)
        if not available:
            raise HTTPException(422, "sentence-transformers not installed. Run: pip install sentence-transformers numpy")
        mode_used = "semantic"
    elif mode == "hybrid":
        results, mode_used = emb.hybrid_search(
            proj["id"], req.query, limit=req.limit, semantic_weight=req.semantic_weight
        )
    else:
        results = db.search_intents(proj["id"], req.query)[: req.limit]
        mode_used = "keyword"

    return {"query": req.query, "mode": mode_used, "results": results}


@app.post("/embed", status_code=202)
def embed_intents(project_path: str, background_tasks: BackgroundTasks, model: str = emb.DEFAULT_MODEL):
    """Start embedding in the background. Returns a job_id to poll with GET /embed/{job_id}."""
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Not registered")
    job_id = uuid.uuid4().hex[:10]
    _embed_jobs[job_id] = {"status": "running", "project_path": project_path, "model": model}

    def _run():
        try:
            result = emb.embed_project(proj["id"], model_name=model)
            _embed_jobs[job_id] = {"status": "done", **result}
        except Exception as e:
            _embed_jobs[job_id] = {"status": "error", "error": str(e)}

    background_tasks.add_task(_run)
    return {"job_id": job_id, "status": "running"}


@app.get("/embed/{job_id}")
def embed_status(job_id: str):
    """Poll the status of a background embed job."""
    job = _embed_jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


@app.get("/stats")
def stats(project_path: str):
    proj = db.get_project(project_path)
    if not proj: raise HTTPException(404, "Not registered")
    cmap = db.get_codebase_map(proj["id"])
    total = cmap["total_functions"]
    annotated = cmap["annotated"]
    backlog = cmap.get("hook_backlog") or []
    return {
        "total": total,
        "annotated": annotated,
        "coverage": round(annotated / total * 100, 1) if total else 0,
        "features": len(cmap["features"]),
        "unannotated_files": cmap["unannotated_files"],
        "hook_backlog": backlog,
        "pending_hook_files": len(backlog),
    }


@app.get("/graph")
def intent_graph(project_path: str):
    """ReactFlow nodes + edges coloured by annotation status and feature."""
    proj = db.get_project(project_path)
    if not proj: raise HTTPException(404, "Not registered")

    cmap = db.get_codebase_map(proj["id"])
    features = {f["title"]: i for i, f in enumerate(cmap["features"])}

    FEATURE_PALETTE = [
        "#388bfd","#3fb950","#d29922","#bc8cff","#39d353",
        "#f0883e","#58a6ff","#f85149","#79c0ff","#56d364",
    ]

    nodes, edges = [], []
    fn_index: dict[str, int] = {}
    i = 0

    for file, fns in cmap["by_file"].items():
        for fn in fns:
            node_id = fn["qualname"]
            fn_index[fn["qualname"]] = i

            # figure out feature colour
            intent = fn.get("intent")
            color = "#484f58"  # unannotated
            if intent:
                color = "#3fb950"  # annotated but no feature

            nodes.append({
                "id": node_id,
                "type": "intentNode",
                "data": {
                    "label":        fn["name"],
                    "qualname":     fn["qualname"],
                    "file":         fn["file"],
                    "has_intent":   fn["has_intent"],
                    "exists_because": intent["user_request"] if intent else None,
                    "confidence":   intent["confidence"] if intent else None,
                    "color":        color,
                },
                "position": {"x": (i % 6) * 280, "y": (i // 6) * 130},
            })
            i += 1

    seen_edges = set()
    for file, fns in cmap["by_file"].items():
        pass  # call graph edges would come from extractor — omitted to keep response lean

    return {"nodes": nodes, "edges": edges}


# serve built UI
UI_DIST = Path(__file__).parent.parent / "ui" / "dist"
if UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")
    @app.get("/{full_path:path}")
    def serve_ui(full_path: str):
        return FileResponse(UI_DIST / "index.html")
