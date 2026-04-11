"""
FastAPI backend for the Own Your Code UI.

Local: ``uvicorn api.main:app --reload --port 8002``

Production: set ``PORT`` (e.g. Render/Fly). Optional ``OWN_YOUR_CODE_DB`` for SQLite path.

Auth:
  Set ``OWN_YOUR_CODE_API_KEY`` to require ``X-Api-Key: <key>`` on API routes.
  ``GET /health`` and ``GET /server-info`` stay public (health checks + UI bootstrap).
  The built SPA shell and ``/assets/*`` are also unauthenticated so browsers can load the UI;
  store a key in the UI footer to attach ``X-Api-Key`` to API calls when auth is enabled.

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

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException
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

# ── routers ────────────────────────────────────────────────────────────────

public = APIRouter(tags=["Meta"])
protected = APIRouter(dependencies=[Depends(_auth)])

app = FastAPI(
    title="Own Your Code",
    description="Living intent map — why your code exists, captured as you build via MCP.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── background embed job tracking ─────────────────────────────────────────

_embed_jobs: dict[str, dict] = {}  # job_id -> {status, ...}


@public.get("/health")
def health():
    return {"status": "ok", "service": "own-your-code"}


@public.get("/server-info")
def server_info():
    """Public deployment metadata for the UI and operators (no secrets)."""
    try:
        from importlib.metadata import version

        ver = version("own-your-code")
    except Exception:
        ver = None
    return {
        "service": "own-your-code",
        "version": ver,
        "api_auth_required": bool(_API_KEY),
        "cors_allow_all": _CORS_RAW.strip() == "*",
        "semantic_stack_installed": emb.embedding_stack_available(),
        "default_embed_model": emb.DEFAULT_MODEL,
        "database_env_set": bool(os.environ.get("OWN_YOUR_CODE_DB", "").strip()),
        "openapi_docs_path": "/docs",
    }


class RegisterReq(BaseModel):
    path: str
    name: str = ""
    languages: list[str] = []
    include_globs: list[str] = []
    ignore_dirs: list[str] = []


class SearchReq(BaseModel):
    project_path: str
    query: str
    mode: str = "keyword"  # keyword | semantic | hybrid
    limit: int = 20
    semantic_weight: float = 0.5


@protected.get("/projects", tags=["Projects"])
def list_projects():
    return {"projects": db.list_projects()}


@protected.post("/register", tags=["Projects"])
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
    return {
        "project_id": pid,
        "path": req.path,
        "functions": len(functions),
        "new": new,
        "by_language": lang_counts,
        "errors": errors,
    }


@protected.get("/map", tags=["Map"])
def codebase_map(project_path: str, file: Optional[str] = None):
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Project not registered")
    cmap = db.get_codebase_map(proj["id"])
    if file:
        if file not in cmap["by_file"]:
            raise HTTPException(404, f"File '{file}' not in project map")
        cmap["by_file"] = {file: cmap["by_file"][file]}
    return cmap


@protected.get("/features", tags=["Map"])
def features(project_path: str):
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Not registered")
    return {"features": db.get_features(proj["id"])}


@protected.get("/evolution", tags=["Intent"])
def evolution_timeline(project_path: str, limit: int = 200):
    """Recorded function changes across the project, newest first."""
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Not registered")
    entries = db.get_evolution_timeline(proj["id"], limit=limit)
    return {"entries": entries}


@protected.get("/function", tags=["Intent"])
def explain(project_path: str, function_name: str, file: str = ""):
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Not registered")
    fn = db.get_function(proj["id"], function_name, file or None)
    if not fn:
        raise HTTPException(404, f"Function '{function_name}' not found")
    intents = db.get_intents(fn["id"])
    decisions = db.get_decisions(fn["id"])
    evolution = db.get_evolution(fn["id"])
    for row in intents:
        if row.get("claude_reasoning") is not None:
            row["agent_reasoning"] = row["claude_reasoning"]
    return {**dict(fn), "intents": intents, "decisions": decisions, "evolution": evolution}


@protected.post("/search", tags=["Search"])
def search(req: SearchReq):
    proj = db.get_project(req.project_path)
    if not proj:
        raise HTTPException(404, "Not registered")

    mode = req.mode
    if mode == "semantic":
        results, available = emb.semantic_search(proj["id"], req.query, limit=req.limit)
        if not available:
            raise HTTPException(
                422,
                "sentence-transformers not installed. Run: pip install sentence-transformers numpy",
            )
        mode_used = "semantic"
    elif mode == "hybrid":
        results, mode_used = emb.hybrid_search(
            proj["id"], req.query, limit=req.limit, semantic_weight=req.semantic_weight
        )
    else:
        results = db.search_intents(proj["id"], req.query)[: req.limit]
        mode_used = "keyword"

    return {"query": req.query, "mode": mode_used, "results": results}


@protected.post("/embed", status_code=202, tags=["Search"])
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


@protected.get("/embed/{job_id}", tags=["Search"])
def embed_status(job_id: str):
    """Poll the status of a background embed job."""
    job = _embed_jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


@protected.get("/stats", tags=["Map"])
def stats(project_path: str):
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Not registered")
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


@protected.get("/graph", tags=["Map"])
def intent_graph(project_path: str):
    """ReactFlow nodes + edges coloured by annotation status and feature."""
    proj = db.get_project(project_path)
    if not proj:
        raise HTTPException(404, "Not registered")

    cmap = db.get_codebase_map(proj["id"])

    nodes, edges = [], []
    i = 0

    for file, fns in cmap["by_file"].items():
        for fn in fns:
            node_id = fn["qualname"]

            intent = fn.get("intent")
            color = "#484f58"  # unannotated
            if intent:
                color = "#3fb950"  # annotated but no feature

            nodes.append(
                {
                    "id": node_id,
                    "type": "intentNode",
                    "data": {
                        "label": fn["name"],
                        "qualname": fn["qualname"],
                        "file": fn["file"],
                        "has_intent": fn["has_intent"],
                        "exists_because": intent["user_request"] if intent else None,
                        "confidence": intent["confidence"] if intent else None,
                        "color": color,
                    },
                    "position": {"x": (i % 6) * 280, "y": (i // 6) * 130},
                }
            )
            i += 1

    return {"nodes": nodes, "edges": edges}


app.include_router(public)
app.include_router(protected)

# serve built UI (no API key — browser loads shell + assets without custom headers)
# PyPI wheels do not bundle ui/dist; set OWN_YOUR_CODE_UI_DIST to an absolute path to a
# built tree (the folder containing index.html and assets/), e.g. after `cd ui && npm run build`.
_ui_override = os.environ.get("OWN_YOUR_CODE_UI_DIST", "").strip()
if _ui_override:
    UI_DIST = Path(_ui_override).expanduser().resolve()
else:
    UI_DIST = (Path(__file__).parent.parent / "ui" / "dist").resolve()
if UI_DIST.is_dir() and (UI_DIST / "index.html").is_file():
    _assets = UI_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_ui(full_path: str):
        return FileResponse(UI_DIST / "index.html")
