"""
MCP server: Own Your Code

Any MCP client can call these tools while code changes — capturing WHY
each function exists, what tradeoffs were made, and how things evolve.

Core tools:
  record_intent, explain_function, get_codebase_map, find_by_intent,
  get_evolution, annotate_existing, mark_file_reviewed

Also:
  register_project — index a codebase (AST scan of .py files)
  record_evolution — log a change to an existing function
"""

_INTENT_REASONING_FALLBACK = (
    "Quick capture: only the user request was recorded. "
    "Follow up with a fuller `record_intent` (reasoning + decisions) when possible."
)
import json
import asyncio
from pathlib import Path

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from . import db
from . import embeddings as emb
from .extractor import scan_project, scan_project_multi, extract_functions, get_git_hash

server = Server("own-your-code")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="register_project",
            description=(
                "Register a codebase with Own Your Code. Scans Python, TypeScript, JavaScript, and Go files, "
                "extracts every function, and sets up the project in the database. "
                "Run once when you start working on a project, or re-run to pick up new files. "
                "Use include_globs to restrict to specific paths; languages to restrict to specific languages."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":          {"type": "string", "description": "Absolute path to the project root"},
                    "name":          {"type": "string", "description": "Human-readable project name (optional)"},
                    "languages":     {"type": "array", "items": {"type": "string"},
                                     "description": "Restrict indexing to these languages (python, typescript, go). Default: all."},
                    "include_globs": {"type": "array", "items": {"type": "string"},
                                     "description": "Glob patterns relative to root (e.g. ['src/**/*.ts']). Default: all supported extensions."},
                    "ignore_dirs":   {"type": "array", "items": {"type": "string"},
                                     "description": "Additional directory names to skip (merged with defaults)."},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="record_intent",
            description=(
                "CALL THIS EVERY TIME you write or significantly modify a function. "
                "Records WHY the function exists, the user request that caused it, "
                "and (when provided) implementation reasoning and tradeoffs. "
                "Minimum viable: user_request only — omit reasoning for a fast capture, then enrich later. "
                "Clears the post-write hook backlog for this file when recorded."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path":    {"type": "string"},
                    "file":            {"type": "string", "description": "Relative path to the file (e.g. src/auth.py)"},
                    "function_name":   {"type": "string", "description": "Function or qualified name (e.g. AuthService.validate)"},
                    "user_request":    {"type": "string", "description": "The user's request that caused this function to be written. Quote or paraphrase their words."},
                    "reasoning":       {"type": "string", "description": "What this function does and why you implemented it this way (optional for quick capture)"},
                    "implementation_notes": {"type": "string", "description": "Anything non-obvious: edge cases handled, known limitations, why a specific algorithm"},
                    "feature":         {"type": "string", "description": "High-level feature this belongs to (e.g. 'User Authentication', 'Payment Processing')"},
                    "decisions": {
                        "type": "array",
                        "description": "Tradeoffs made. Each item: {decision, alternatives, reason, constraint}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "decision":     {"type": "string"},
                                "alternatives": {"type": "array", "items": {"type": "string"}},
                                "reason":       {"type": "string"},
                                "constraint":   {"type": "string"},
                            },
                            "required": ["decision", "reason"],
                        },
                    },
                    "confidence": {
                        "type": "integer",
                        "description": "1-5: how confident you are in this annotation (5=you just wrote it, 1=inferred from existing code)",
                        "default": 5,
                    },
                },
                "required": ["project_path", "file", "function_name", "user_request"],
            },
        ),
        types.Tool(
            name="mark_file_reviewed",
            description=(
                "Clear the post-write hook backlog for a file without adding intent — use when you "
                "reviewed edits and no new annotation is needed (e.g. typo-only or mechanical change), "
                "or you will annotate later. Prefer record_intent when behavior or purpose changed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "file":         {"type": "string", "description": "Relative path within the project"},
                    "note":         {"type": "string", "description": "Optional note for humans (not stored in DB v1)"},
                },
                "required": ["project_path", "file"],
            },
        ),
        types.Tool(
            name="record_evolution",
            description=(
                "Call this when you MODIFY an existing function (not create it). "
                "Records what changed, why, and what user request triggered the change. "
                "Clears the post-write hook backlog for this file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path":   {"type": "string"},
                    "file":           {"type": "string"},
                    "function_name":  {"type": "string"},
                    "change_summary": {"type": "string", "description": "What changed in this function"},
                    "reason":         {"type": "string", "description": "Why it changed"},
                    "triggered_by":   {"type": "string", "description": "User request that triggered this change"},
                },
                "required": ["project_path", "file", "function_name", "change_summary", "reason"],
            },
        ),
        types.Tool(
            name="explain_function",
            description=(
                "Get the full story of a function: why it exists, what the user asked for, "
                "decisions made, and how it evolved. Use when the user asks 'what does X do' "
                "or 'why does this exist' or 'how did this change'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path":  {"type": "string"},
                    "function_name": {"type": "string"},
                    "file":          {"type": "string", "description": "Optional: narrow to a specific file"},
                },
                "required": ["project_path", "function_name"],
            },
        ),
        types.Tool(
            name="get_codebase_map",
            description=(
                "Get the full living map of a codebase: every function grouped by file and feature, "
                "with intents, coverage (what % has been annotated), and hook_backlog "
                "(files touched by the editor hook still awaiting record_intent or mark_file_reviewed). "
                "Use when the user wants to understand the codebase as a whole."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                },
                "required": ["project_path"],
            },
        ),
        types.Tool(
            name="find_by_intent",
            description=(
                "Search functions by intent. Supports three modes: "
                "'keyword' (default, fast LIKE-based), 'semantic' (vector similarity, requires embed_intents first), "
                "or 'hybrid' (merges both). Use natural-language phrases. Examples: payments, auth, retry."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "query":        {"type": "string", "description": "Words or phrase to match against names and intent fields"},
                    "mode":         {"type": "string", "enum": ["keyword", "semantic", "hybrid"],
                                     "description": "Search mode. Default: keyword. Use semantic/hybrid after embed_intents.", "default": "keyword"},
                    "limit":        {"type": "integer", "description": "Max results. Default: 20.", "default": 20},
                    "semantic_weight": {"type": "number", "description": "0-1, weight for semantic score in hybrid mode. Default: 0.5.", "default": 0.5},
                },
                "required": ["project_path", "query"],
            },
        ),
        types.Tool(
            name="embed_preflight",
            description=(
                "Check whether sentence-transformers is available and how many intents still need embeddings — "
                "fast, no model load. Call before embed_intents to confirm dependencies and backlog size."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "model":        {"type": "string", "description": "Embedding model name. Default: all-MiniLM-L6-v2.", "default": "all-MiniLM-L6-v2"},
                },
                "required": ["project_path"],
            },
        ),
        types.Tool(
            name="embed_intents",
            description=(
                "Compute and store vector embeddings for all intents in a project (backfill). "
                "Required before using semantic or hybrid search modes in find_by_intent. "
                "Uses sentence-transformers (all-MiniLM-L6-v2 by default). "
                "Safe to re-run; only processes intents that haven't been embedded yet. "
                "Prefer calling embed_preflight first to verify deps and pending count."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "model":        {"type": "string", "description": "Embedding model name. Default: all-MiniLM-L6-v2.", "default": "all-MiniLM-L6-v2"},
                },
                "required": ["project_path"],
            },
        ),
        types.Tool(
            name="get_evolution",
            description=(
                "Get the full timeline of how a function changed over time and why. "
                "Shows every modification with the reason and user request that triggered it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path":  {"type": "string"},
                    "function_name": {"type": "string"},
                    "file":          {"type": "string", "description": "Optional: narrow to a specific file (relative path) when multiple functions share the same name."},
                },
                "required": ["project_path", "function_name"],
            },
        ),
        types.Tool(
            name="annotate_existing",
            description=(
                "Retroactively annotate an existing codebase that predates Own Your Code. "
                "Scans every function, reads its source, and YOU infer its intent from the code. "
                "Call this when first setting up on an existing project. "
                "Pass your inferences as the annotations array."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "file": {
                        "type": "string",
                        "description": "Optional: annotate only this file (relative path). Omit to get list of files needing annotation.",
                    },
                    "annotations": {
                        "type": "array",
                        "description": "Your inferred intents for each function in the file",
                        "items": {
                            "type": "object",
                            "properties": {
                                "function_name": {"type": "string"},
                                "user_request":  {"type": "string", "description": "Your best inference of what the user asked for"},
                                "reasoning":     {"type": "string"},
                                "implementation_notes": {"type": "string"},
                                "feature":       {"type": "string"},
                            },
                            "required": ["function_name", "user_request", "reasoning"],
                        },
                    },
                },
                "required": ["project_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _dispatch, name, arguments)
        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        import traceback
        return [types.TextContent(type="text", text=f"Error in '{name}': {e}\n{traceback.format_exc()}")]


def _dispatch(name: str, args: dict) -> str:
    match name:
        case "register_project":   return _register_project(args)
        case "record_intent":      return _record_intent(args)
        case "mark_file_reviewed": return _mark_file_reviewed(args)
        case "record_evolution":   return _record_evolution(args)
        case "explain_function":   return _explain_function(args)
        case "get_codebase_map":   return _get_codebase_map(args)
        case "find_by_intent":     return _find_by_intent(args)
        case "get_evolution":      return _get_evolution(args)
        case "annotate_existing":  return _annotate_existing(args)
        case "embed_preflight":    return _embed_preflight(args)
        case "embed_intents":      return _embed_intents(args)
        case _: raise ValueError(f"Unknown tool: {name}")


# ── implementations ────────────────────────────────────────────────────────

def _register_project(args: dict) -> str:
    path = args["path"]
    if not Path(path).exists():
        return json.dumps({"error": f"Path not found: {path}"})

    project_id = db.upsert_project(path, args.get("name"))
    functions, errors = scan_project_multi(
        path,
        include_globs=args.get("include_globs"),
        ignore_dirs=args.get("ignore_dirs"),
        languages=args.get("languages"),
    )
    new_count = 0
    lang_counts: dict[str, int] = {}
    for fn in functions:
        fid, is_new = db.upsert_function(project_id, fn)
        if is_new:
            new_count += 1
        lang = fn.get("language", "python")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    return json.dumps({
        "status": "registered",
        "project_id": project_id,
        "path": path,
        "functions_found": len(functions),
        "new_or_changed": new_count,
        "by_language": lang_counts,
        "parse_errors": errors,
        "next_step": (
            "Use annotate_existing to infer intent for existing functions, or start writing new code "
            "and call record_intent after each function. Any MCP client can use these tools."
        ),
    }, indent=2)


def _mark_file_reviewed(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered. Call register_project first."})
    file = args["file"]
    db.mark_annotated(proj["id"], file)
    return json.dumps(
        {
            "status": "cleared",
            "file": file,
            "note": args.get("note"),
        },
        indent=2,
    )


def _record_intent(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        db.upsert_project(path)
        proj = db.get_project(path)

    # upsert the function (in case file was written before register_project)
    file = args["file"]
    fname = args["function_name"]

    # try to find existing function record
    fn = db.get_function(proj["id"], fname, file)
    if not fn:
        # create a minimal record
        fid, _ = db.upsert_function(proj["id"], {
            "file": file, "name": fname.split(".")[-1],
            "qualname": fname, "lineno": 0,
        })
    else:
        fid = fn["id"]

    reasoning = (args.get("reasoning") or "").strip() or _INTENT_REASONING_FALLBACK
    conf = args.get("confidence", 5)
    if not (args.get("reasoning") or "").strip() and conf >= 4:
        conf = min(conf, 4)

    # record intent
    intent_id = db.record_intent(fid, {
        "user_request":          args["user_request"],
        "claude_reasoning":      reasoning,
        "implementation_notes":  args.get("implementation_notes"),
        "confidence":            conf,
    })

    # record decisions
    for dec in args.get("decisions", []):
        db.record_decision(fid, dec)

    # link to feature
    if feature_title := args.get("feature"):
        feat_id = db.upsert_feature(proj["id"], feature_title)
        db.link_feature(feat_id, fid)

    db.mark_annotated(proj["id"], file)

    return json.dumps({
        "status": "recorded",
        "function": fname,
        "intent_id": intent_id,
        "decisions_recorded": len(args.get("decisions", [])),
        "feature": args.get("feature"),
        "hook_backlog_cleared_for_file": file,
    }, indent=2)


def _record_evolution(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered. Call register_project first."})

    fn = db.get_function(proj["id"], args["function_name"], args.get("file"))
    if not fn:
        return json.dumps({"error": f"Function '{args['function_name']}' not found. Call record_intent first."})

    git_hash = get_git_hash(path)
    ev_id = db.record_evolution(fn["id"], {
        "change_summary": args["change_summary"],
        "reason":         args.get("reason"),
        "triggered_by":   args.get("triggered_by"),
        "git_hash":       git_hash,
    })

    db.mark_annotated(proj["id"], args["file"])

    return json.dumps({
        "status": "recorded",
        "function": args["function_name"],
        "evolution_id": ev_id,
        "git_hash": git_hash,
        "hook_backlog_cleared_for_file": args["file"],
    }, indent=2)


def _explain_function(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered."})

    fn = db.get_function(proj["id"], args["function_name"], args.get("file"))
    if not fn:
        return json.dumps({"error": f"Function '{args['function_name']}' not found. Has it been indexed?"})

    intents   = db.get_intents(fn["id"])
    decisions = db.get_decisions(fn["id"])
    evolution = db.get_evolution(fn["id"])

    if not intents:
        return json.dumps({
            "function": fn["qualname"],
            "file": fn["file"],
            "signature": fn["signature"],
            "status": "no_intent_recorded",
            "message": (
                "This function has not been annotated yet. Use annotate_existing to infer intent from source, "
                "or record_intent after the next change."
            ),
        }, indent=2)

    latest = intents[0]
    return json.dumps({
        "function": fn["qualname"],
        "file": fn["file"],
        "lineno": fn["lineno"],
        "signature": fn["signature"],
        "exists_because": latest["user_request"],
        "how_it_works": latest["claude_reasoning"],
        "implementation_notes": latest["implementation_notes"],
        "confidence": latest["confidence"],
        "decisions": decisions,
        "evolution": [
            {
                "when": e["changed_at"],
                "what": e["change_summary"],
                "why": e["reason"],
                "triggered_by": e["triggered_by"],
                "git": e["git_hash"],
            } for e in evolution
        ],
        "full_intent_history": [
            {"when": i["recorded_at"], "request": i["user_request"]}
            for i in intents[1:]
        ],
    }, indent=2)


def _get_codebase_map(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered."})

    cmap = db.get_codebase_map(proj["id"])
    total = cmap["total_functions"]
    annotated = cmap["annotated"]
    coverage = round((annotated / total * 100) if total > 0 else 0, 1)

    return json.dumps({
        "project": path,
        "coverage": f"{coverage}% annotated ({annotated}/{total} functions)",
        "unannotated_files": cmap["unannotated_files"],
        "hook_backlog": cmap.get("hook_backlog") or [],
        "hook_backlog_instruction": (
            "Each entry is a file the editor hook saw written but not yet cleared. "
            "For real changes: call record_intent (reasoning optional). "
            "For no semantic change: mark_file_reviewed."
        ),
        "features": [
            {
                "title": f["title"],
                "description": f["description"],
                "functions": f["functions"],
            } for f in cmap["features"]
        ],
        "by_file": {
            file: [
                {
                    "qualname": fn["qualname"],
                    "signature": fn["signature"],
                    "has_intent": fn["has_intent"],
                    "exists_because": fn["intent"]["user_request"] if fn["intent"] else None,
                    "feature_titles": fn.get("feature_titles") or [],
                    "feature": (fn.get("feature_titles") or [None])[0],
                }
                for fn in fns
            ]
            for file, fns in cmap["by_file"].items()
        },
    }, indent=2)


def _find_by_intent(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered."})

    query = args["query"]
    mode = args.get("mode", "keyword")
    limit = int(args.get("limit", 20))
    sem_weight = float(args.get("semantic_weight", 0.5))
    model_name = emb.DEFAULT_MODEL

    if mode == "semantic":
        results, available = emb.semantic_search(proj["id"], query, limit=limit, model_name=model_name)
        if not available:
            return json.dumps({"error": "sentence-transformers not installed. Run: pip install sentence-transformers numpy"})
        if not results:
            return json.dumps({"query": query, "mode": "semantic", "count": 0, "results": [],
                               "hint": "No embeddings found. Call embed_intents first."})
        mode_used = "semantic"
    elif mode == "hybrid":
        results, mode_used = emb.hybrid_search(proj["id"], query, limit=limit, model_name=model_name,
                                               semantic_weight=sem_weight)
    else:
        results = db.search_intents(proj["id"], query)[:limit]
        mode_used = "keyword"

    return json.dumps({
        "query": query,
        "mode": mode_used,
        "count": len(results),
        "results": [
            {
                "function":      r.get("qualname", r.get("function", "")),
                "file":          r["file"],
                "lineno":        r.get("lineno"),
                "signature":     r.get("signature"),
                "exists_because": r.get("user_request"),
                "how_it_works":  r.get("claude_reasoning"),
                **({"score": r["score"]} if "score" in r else {}),
            }
            for r in results
        ],
    }, indent=2)


def _embed_preflight(args: dict) -> str:
    path = args["project_path"]
    model_name = args.get("model", emb.DEFAULT_MODEL)
    deps_ok = emb.embedding_stack_available()
    proj = db.get_project(path)
    if not proj:
        return json.dumps(
            {
                "semantic_stack_installed": deps_ok,
                "project_registered": False,
                "pending_count": 0,
                "model": model_name,
                "can_start": False,
                "message": "Project not registered.",
                "warnings": [],
            },
            indent=2,
        )
    pending = db.count_unembedded_intents(proj["id"], model_name) if deps_ok else 0
    warnings: list[str] = []
    if deps_ok and pending > 500:
        warnings.append(
            f"Very large backlog ({pending} intents): expect long runtime and high RAM on CPU-only machines."
        )
    elif deps_ok and pending > 200:
        warnings.append(
            f"Large backlog ({pending} intents): embedding may take several minutes and use significant RAM."
        )
    elif deps_ok and pending > 50:
        warnings.append(
            f"{pending} intents to embed — may take a few minutes on a laptop CPU."
        )
    if not deps_ok:
        msg = (
            "Semantic stack not installed. Run: pip install sentence-transformers numpy "
            "(or pip install 'own-your-code[semantic]')."
        )
        can_start = False
    elif pending == 0:
        msg = f"All intents already embedded for model {model_name}."
        can_start = False
    else:
        msg = f"Ready to index {pending} intent(s) with {model_name}."
        can_start = True
    return json.dumps(
        {
            "semantic_stack_installed": deps_ok,
            "project_registered": True,
            "pending_count": pending,
            "model": model_name,
            "can_start": can_start,
            "message": msg,
            "warnings": warnings,
        },
        indent=2,
    )


def _embed_intents(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered."})

    model_name = args.get("model", emb.DEFAULT_MODEL)
    result = emb.embed_project(proj["id"], model_name=model_name)
    return json.dumps(result, indent=2)


def _get_evolution(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        return json.dumps({"error": "Project not registered."})

    fn = db.get_function(proj["id"], args["function_name"], args.get("file"))
    if not fn:
        return json.dumps({"error": f"Function '{args['function_name']}' not found. Use the 'file' parameter to disambiguate if multiple functions share this name."})

    evolution = db.get_evolution(fn["id"])
    intents   = db.get_intents(fn["id"])

    return json.dumps({
        "function": fn["qualname"],
        "file": fn["file"],
        "first_seen": fn["first_seen"],
        "last_seen": fn["last_seen"],
        "original_intent": intents[-1]["user_request"] if intents else None,
        "evolution": [
            {
                "when": e["changed_at"],
                "what_changed": e["change_summary"],
                "why": e["reason"],
                "triggered_by": e["triggered_by"],
                "git": e["git_hash"],
            } for e in evolution
        ],
        "intent_history": [
            {"when": i["recorded_at"], "request": i["user_request"], "confidence": i["confidence"]}
            for i in intents
        ],
    }, indent=2)


def _annotate_existing(args: dict) -> str:
    path = args["project_path"]
    proj = db.get_project(path)
    if not proj:
        # auto-register
        db.upsert_project(path)
        proj = db.get_project(path)
        scan_project(path)  # index functions

    file = args.get("file")
    annotations = args.get("annotations", [])

    # No file + no annotations = return what needs doing
    if not file and not annotations:
        cmap = db.get_codebase_map(proj["id"])
        unannotated = []
        for f, fns in cmap["by_file"].items():
            fns_without = [fn for fn in fns if not fn["has_intent"]]
            if fns_without:
                unannotated.append({
                    "file": f,
                    "functions": [fn["qualname"] for fn in fns_without],
                    "count": len(fns_without),
                })

        return json.dumps({
            "status": "needs_annotation",
            "total_unannotated": sum(f["count"] for f in unannotated),
            "files": unannotated,
            "instruction": (
                "For each file, call annotate_existing with the file path and your inferred annotations. "
                "Read the source of each function and infer: what user request likely caused this? "
                "Set confidence=1-3 since you are inferring, not recalling. "
                "Works with any MCP-enabled client."
            ),
        }, indent=2)

    # Has annotations — record them
    recorded = 0
    errors = []
    for ann in annotations:
        fname = ann["function_name"]
        fn = db.get_function(proj["id"], fname, file)
        if not fn:
            errors.append(f"Function '{fname}' not found in {file}")
            continue

        db.record_intent(fn["id"], {
            "user_request":          ann["user_request"],
            "claude_reasoning":      ann.get("reasoning"),
            "implementation_notes":  ann.get("implementation_notes"),
            "confidence":            ann.get("confidence", 2),
        })

        if feature := ann.get("feature"):
            fid = db.upsert_feature(proj["id"], feature)
            db.link_feature(fid, fn["id"])

        recorded += 1

    if file:
        db.mark_annotated(proj["id"], file)

    return json.dumps({
        "status": "annotated",
        "file": file,
        "recorded": recorded,
        "errors": errors,
    }, indent=2)


# ── entry ──────────────────────────────────────────────────────────────────

def main():
    asyncio.run(_run())


async def _run():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    main()
