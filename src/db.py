"""
SQLite schema for the intent store.

Override the database file with env ``OWN_YOUR_CODE_DB`` (absolute path). Useful for
Docker volumes and hosted deploys.

Default location:

- **Git checkout / editable install:** ``owns.db`` next to ``pyproject.toml``.
- **pip/pipx install:** user data directory (writable), e.g.
  ``~/Library/Application Support/OwnYourCode/owns.db`` on macOS.

Tables:
  projects          — registered codebases
  functions         — every known function (AST-extracted)
  intents           — WHY a function exists (captured via MCP / tooling)
  intent_embeddings — vector embeddings for semantic search (optional)
  decisions         — tradeoffs recorded (chosen vs alternatives, why)
  evolution         — timeline of changes to a function and the reason each time
  feature_links     — many:many between functions and the user feature that caused them
  features          — high-level features / user requests that triggered code
  hook_events       — raw post-write events (safety net when record_intent is skipped)

Schema versioning:
  PRAGMA user_version tracks migrations. Current version: 2.
  v1 → v2: added intent_embeddings table.
"""
import os
import sqlite3
import json
import sys
import threading
from collections import defaultdict
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime


def _user_data_dir() -> Path:
    home = Path.home()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "OwnYourCode"
        return home / "AppData" / "Local" / "OwnYourCode"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "OwnYourCode"
    xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
    return Path(xdg) / "own-your-code"


def _default_db_path() -> Path:
    """Repo / editable install uses project root; wheel install uses a user-writable path."""
    here = Path(__file__).resolve()
    candidate_root = here.parent.parent
    if (candidate_root / "pyproject.toml").is_file():
        return candidate_root / "owns.db"
    return _user_data_dir() / "owns.db"


_DEFAULT_DB = _default_db_path()
DB_PATH = Path(os.environ.get("OWN_YOUR_CODE_DB", str(_DEFAULT_DB))).expanduser().resolve()

_db_initialized = False
_db_init_lock = threading.Lock()

SCHEMA_VERSION = 3

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS functions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id),
    file        TEXT NOT NULL,
    name        TEXT NOT NULL,
    qualname    TEXT NOT NULL,
    signature   TEXT,
    lineno      INTEGER,
    end_lineno  INTEGER,
    is_async    INTEGER DEFAULT 0,
    is_method   INTEGER DEFAULT 0,
    class_name  TEXT,
    language    TEXT DEFAULT 'python',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    source_hash TEXT,
    UNIQUE(project_id, file, qualname)
);

CREATE TABLE IF NOT EXISTS intents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id     INTEGER REFERENCES functions(id),
    recorded_at     TEXT NOT NULL,
    user_request    TEXT NOT NULL,
    reasoning       TEXT,
    implementation_notes TEXT,
    confidence      INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id     INTEGER REFERENCES functions(id),
    recorded_at     TEXT NOT NULL,
    decision        TEXT NOT NULL,
    alternatives    TEXT,
    reason          TEXT NOT NULL,
    constraint_     TEXT
);

CREATE TABLE IF NOT EXISTS evolution (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id     INTEGER REFERENCES functions(id),
    changed_at      TEXT NOT NULL,
    change_summary  TEXT NOT NULL,
    reason          TEXT,
    triggered_by    TEXT,
    git_hash        TEXT
);

CREATE TABLE IF NOT EXISTS features (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id),
    title       TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_links (
    feature_id  INTEGER REFERENCES features(id),
    function_id INTEGER REFERENCES functions(id),
    PRIMARY KEY (feature_id, function_id)
);

CREATE TABLE IF NOT EXISTS hook_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id),
    file        TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    annotated   INTEGER DEFAULT 0
);
"""

_MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS intent_embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id   INTEGER NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    vector      BLOB NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_intent_model ON intent_embeddings(intent_id, model);
"""

_MIGRATION_V3 = """
ALTER TABLE intents RENAME COLUMN claude_reasoning TO reasoning;
"""


def init_db():
    """Create tables and run any pending migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(DB_PATH), isolation_level=None)
    raw.row_factory = sqlite3.Row
    try:
        # WAL mode: concurrent reads + single writer, no read/write contention
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, faster than FULL
        raw.execute("PRAGMA foreign_keys=ON")
        raw.executescript(_SCHEMA_V1)
        # Add language column to existing DBs that predate it
        try:
            raw.execute("ALTER TABLE functions ADD COLUMN language TEXT DEFAULT 'python'")
        except Exception:
            pass  # already exists
        version = raw.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:
            raw.executescript(_MIGRATION_V2)
        if version < 3:
            try:
                raw.executescript(_MIGRATION_V3)
            except Exception:
                pass  # column already renamed (new DB created with updated schema)
        if version < SCHEMA_VERSION:
            raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    finally:
        raw.close()


def _ensure_schema():
    global _db_initialized
    if not _db_initialized:
        with _db_init_lock:
            if not _db_initialized:
                init_db()
                _db_initialized = True


@contextmanager
def conn():
    _ensure_schema()
    db = sqlite3.connect(DB_PATH, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        db.close()


def now() -> str:
    return datetime.now().isoformat()


# ── projects ───────────────────────────────────────────────────────────────

def upsert_project(path: str, name: str | None = None) -> int:
    with conn() as c:
        c.execute("""
            INSERT INTO projects(path, name, created_at, last_seen)
            VALUES(?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET last_seen=excluded.last_seen, name=COALESCE(excluded.name, name)
        """, (path, name or Path(path).name, now(), now()))
        return c.execute("SELECT id FROM projects WHERE path=?", (path,)).fetchone()["id"]


def get_project(path: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM projects WHERE path=?", (path,)).fetchone()
        return dict(row) if row else None


def list_projects() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM projects ORDER BY last_seen DESC")]


# ── functions ──────────────────────────────────────────────────────────────

def upsert_function(project_id: int, fn: dict) -> int:
    import hashlib
    src_hash = hashlib.md5((fn.get("source") or "").encode()).hexdigest()
    language = fn.get("language", "python")
    with conn() as c:
        existing = c.execute(
            "SELECT id, source_hash FROM functions WHERE project_id=? AND file=? AND qualname=?",
            (project_id, fn["file"], fn["qualname"])
        ).fetchone()

        if existing:
            changed = existing["source_hash"] != src_hash
            c.execute("""
                UPDATE functions SET last_seen=?, lineno=?, end_lineno=?, signature=?,
                    source_hash=?, is_async=?, is_method=?, class_name=?, language=?
                WHERE id=?
            """, (now(), fn["lineno"], fn.get("end_lineno"), fn.get("signature"),
                  src_hash, int(fn.get("is_async", False)), int(fn.get("is_method", False)),
                  fn.get("class_name"), language, existing["id"]))
            return existing["id"], changed
        else:
            cur = c.execute("""
                INSERT INTO functions(project_id, file, name, qualname, signature,
                    lineno, end_lineno, is_async, is_method, class_name, language,
                    first_seen, last_seen, source_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (project_id, fn["file"], fn["name"], fn["qualname"], fn.get("signature"),
                  fn["lineno"], fn.get("end_lineno"),
                  int(fn.get("is_async", False)), int(fn.get("is_method", False)),
                  fn.get("class_name"), language, now(), now(), src_hash))
            return cur.lastrowid, True  # new = always "changed"


def get_function(project_id: int, qualname: str, file: str | None = None) -> dict | None:
    with conn() as c:
        q = "SELECT * FROM functions WHERE project_id=? AND (qualname=? OR name=?)"
        params = [project_id, qualname, qualname]
        if file:
            q += " AND file=?"
            params.append(file)
        q += " ORDER BY last_seen DESC LIMIT 1"
        row = c.execute(q, params).fetchone()
        return dict(row) if row else None


def get_all_functions(project_id: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM functions WHERE project_id=? ORDER BY file, lineno",
            (project_id,)
        )]


def _chunked_ids(ids: list[int], size: int = 400):
    """SQLite parameter limits — keep IN clauses small."""
    for i in range(0, len(ids), size):
        yield ids[i : i + size]


def prune_stale_functions(
    project_id: int,
    keep_keys: set[tuple[str, str]],
    *,
    dry_run: bool = False,
) -> dict:
    """
    Delete ``functions`` rows for *project_id* whose ``(file, qualname)`` is not in
    *keep_keys*, and delete dependent intents (plus intent_embeddings), decisions,
    evolution rows, and feature_links.

    *keep_keys* must match a fresh ``scan_project_multi`` result: ``(fn['file'], fn['qualname'])``.

    **Warning:** Functions only created via ``record_intent`` (never returned by a scan)
    disappear from *keep_keys* and will be pruned, deleting their ledger rows.

    Returns a dict with counts and ``dry_run`` bool.
    """
    _ensure_schema()
    with conn() as c:
        rows = c.execute(
            "SELECT id, file, qualname FROM functions WHERE project_id=?",
            (project_id,),
        ).fetchall()
    stale_ids = [r["id"] for r in rows if (r["file"], r["qualname"]) not in keep_keys]

    out: dict = {
        "removed_functions": len(stale_ids),
        "removed_intents": 0,
        "removed_decisions": 0,
        "removed_evolution": 0,
        "removed_feature_links": 0,
        "removed_intent_embeddings": 0,
        "dry_run": dry_run,
    }
    if not stale_ids:
        out["removed_functions"] = 0
        return out

    def _count_intent_embeddings_for_functions(c, batch: list[int]) -> int:
        q = ",".join("?" * len(batch))
        row = c.execute(
            f"""SELECT COUNT(*) FROM intent_embeddings
                WHERE intent_id IN (SELECT id FROM intents WHERE function_id IN ({q}))""",
            batch,
        ).fetchone()
        return int(row[0]) if row else 0

    if dry_run:
        with conn() as c:
            for batch in _chunked_ids(stale_ids):
                q = ",".join("?" * len(batch))
                out["removed_intents"] += int(
                    c.execute(
                        f"SELECT COUNT(*) FROM intents WHERE function_id IN ({q})",
                        batch,
                    ).fetchone()[0]
                )
                out["removed_decisions"] += int(
                    c.execute(
                        f"SELECT COUNT(*) FROM decisions WHERE function_id IN ({q})",
                        batch,
                    ).fetchone()[0]
                )
                out["removed_evolution"] += int(
                    c.execute(
                        f"SELECT COUNT(*) FROM evolution WHERE function_id IN ({q})",
                        batch,
                    ).fetchone()[0]
                )
                out["removed_feature_links"] += int(
                    c.execute(
                        f"SELECT COUNT(*) FROM feature_links WHERE function_id IN ({q})",
                        batch,
                    ).fetchone()[0]
                )
                out["removed_intent_embeddings"] += _count_intent_embeddings_for_functions(c, batch)
        return out

    with conn() as c:
        c.execute("BEGIN")
        try:
            for batch in _chunked_ids(stale_ids):
                q = ",".join("?" * len(batch))
                cur = c.execute(
                    f"""DELETE FROM intent_embeddings WHERE intent_id IN
                        (SELECT id FROM intents WHERE function_id IN ({q}))""",
                    batch,
                )
                out["removed_intent_embeddings"] += cur.rowcount
                cur = c.execute(f"DELETE FROM intents WHERE function_id IN ({q})", batch)
                out["removed_intents"] += cur.rowcount
                cur = c.execute(f"DELETE FROM decisions WHERE function_id IN ({q})", batch)
                out["removed_decisions"] += cur.rowcount
                cur = c.execute(f"DELETE FROM evolution WHERE function_id IN ({q})", batch)
                out["removed_evolution"] += cur.rowcount
                cur = c.execute(f"DELETE FROM feature_links WHERE function_id IN ({q})", batch)
                out["removed_feature_links"] += cur.rowcount
                c.execute(f"DELETE FROM functions WHERE id IN ({q})", batch)
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    out["removed_functions"] = len(stale_ids)
    return out


# ── intents ────────────────────────────────────────────────────────────────

def record_intent(function_id: int, data: dict) -> int:
    with conn() as c:
        cur = c.execute("""
            INSERT INTO intents(function_id, recorded_at, user_request,
                reasoning, implementation_notes, confidence)
            VALUES(?,?,?,?,?,?)
        """, (function_id, now(), data["user_request"], data.get("reasoning"),
              data.get("implementation_notes"), data.get("confidence", 3)))
        return cur.lastrowid


def get_intents(function_id: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM intents WHERE function_id=? ORDER BY recorded_at DESC",
            (function_id,)
        )]


def get_latest_intent(function_id: int) -> dict | None:
    with conn() as c:
        row = c.execute(
            "SELECT * FROM intents WHERE function_id=? ORDER BY recorded_at DESC LIMIT 1",
            (function_id,)
        ).fetchone()
        return dict(row) if row else None


def get_latest_intents_batch(function_ids: list[int]) -> dict[int, dict | None]:
    """Fetch the latest intent for each function in one pass (avoids N+1)."""
    if not function_ids:
        return {}
    result: dict[int, dict | None] = {fid: None for fid in function_ids}
    with conn() as c:
        for batch in _chunked_ids(function_ids):
            q = ",".join("?" * len(batch))
            rows = c.execute(
                f"""
                SELECT * FROM intents
                WHERE id IN (
                    SELECT MAX(id) FROM intents
                    WHERE function_id IN ({q})
                    GROUP BY function_id
                )
                """,
                batch,
            ).fetchall()
            for row in rows:
                result[row["function_id"]] = dict(row)
    return result


def get_decisions_batch(function_ids: list[int]) -> dict[int, list[dict]]:
    """Fetch decisions for all functions in one pass (avoids N+1)."""
    if not function_ids:
        return {}
    result: dict[int, list[dict]] = {fid: [] for fid in function_ids}
    with conn() as c:
        for batch in _chunked_ids(function_ids):
            q = ",".join("?" * len(batch))
            rows = c.execute(
                f"SELECT * FROM decisions WHERE function_id IN ({q}) ORDER BY recorded_at DESC",
                batch,
            ).fetchall()
            for row in rows:
                d = dict(row)
                try:
                    d["alternatives"] = json.loads(d["alternatives"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    d["alternatives"] = []
                result[d["function_id"]].append(d)
    return result


def get_evolution_batch(function_ids: list[int]) -> dict[int, list[dict]]:
    """Fetch evolution rows for all functions in one pass (avoids N+1)."""
    if not function_ids:
        return {}
    result: dict[int, list[dict]] = {fid: [] for fid in function_ids}
    with conn() as c:
        for batch in _chunked_ids(function_ids):
            q = ",".join("?" * len(batch))
            rows = c.execute(
                f"SELECT * FROM evolution WHERE function_id IN ({q}) ORDER BY changed_at ASC, id ASC",
                batch,
            ).fetchall()
            for row in rows:
                d = dict(row)
                result[d["function_id"]].append(d)
    return result


# ── decisions ──────────────────────────────────────────────────────────────

def record_decision(function_id: int, data: dict) -> int:
    with conn() as c:
        cur = c.execute("""
            INSERT INTO decisions(function_id, recorded_at, decision, alternatives, reason, constraint_)
            VALUES(?,?,?,?,?,?)
        """, (function_id, now(), data["decision"],
              json.dumps(data.get("alternatives", [])),
              data["reason"], data.get("constraint")))
        return cur.lastrowid


def get_decisions(function_id: int) -> list[dict]:
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM decisions WHERE function_id=? ORDER BY recorded_at DESC",
            (function_id,)
        )]
        for r in rows:
            try:
                r["alternatives"] = json.loads(r["alternatives"] or "[]")
            except (json.JSONDecodeError, TypeError):
                r["alternatives"] = []
        return rows


# ── evolution ──────────────────────────────────────────────────────────────

def record_evolution(function_id: int, data: dict) -> int:
    with conn() as c:
        cur = c.execute("""
            INSERT INTO evolution(function_id, changed_at, change_summary, reason, triggered_by, git_hash)
            VALUES(?,?,?,?,?,?)
        """, (function_id, now(), data["change_summary"], data.get("reason"),
              data.get("triggered_by"), data.get("git_hash")))
        return cur.lastrowid


def get_evolution(function_id: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM evolution WHERE function_id=? ORDER BY changed_at ASC, id ASC",
            (function_id,)
        )]


def get_evolution_timeline(project_id: int, limit: int = 200) -> list[dict]:
    """All evolution rows for a project, newest change first (by changed_at, then id)."""
    limit = max(1, min(int(limit), 500))
    with conn() as c:
        rows = c.execute(
            """
            SELECT e.id, e.changed_at, e.change_summary, e.reason, e.triggered_by, e.git_hash,
                   f.qualname, f.file, f.lineno
            FROM evolution e
            JOIN functions f ON f.id = e.function_id
            WHERE f.project_id = ?
            ORDER BY e.changed_at DESC, e.id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ── features ───────────────────────────────────────────────────────────────

def upsert_feature(project_id: int, title: str, description: str | None = None) -> int:
    with conn() as c:
        existing = c.execute(
            "SELECT id FROM features WHERE project_id=? AND title=?",
            (project_id, title)
        ).fetchone()
        if existing:
            return existing["id"]
        cur = c.execute(
            "INSERT INTO features(project_id, title, description, created_at) VALUES(?,?,?,?)",
            (project_id, title, description, now())
        )
        return cur.lastrowid


def link_feature(feature_id: int, function_id: int):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO feature_links(feature_id, function_id) VALUES(?,?)",
                  (feature_id, function_id))


def get_features(project_id: int) -> list[dict]:
    with conn() as c:
        features = [dict(r) for r in c.execute(
            "SELECT * FROM features WHERE project_id=? ORDER BY created_at DESC",
            (project_id,)
        )]
        for feat in features:
            links = c.execute("""
                SELECT f.qualname, f.file FROM feature_links fl
                JOIN functions f ON f.id = fl.function_id
                WHERE fl.feature_id=?
            """, (feat["id"],)).fetchall()
            feat["functions"] = [dict(l) for l in links]
        return features


# ── hook events ────────────────────────────────────────────────────────────

def record_hook_event(project_id: int, file: str, event_type: str):
    with conn() as c:
        c.execute(
            "INSERT INTO hook_events(project_id, file, event_type, occurred_at) VALUES(?,?,?,?)",
            (project_id, file, event_type, now())
        )


def get_unannotated_files(project_id: int) -> list[str]:
    with conn() as c:
        rows = c.execute("""
            SELECT DISTINCT file FROM hook_events
            WHERE project_id=? AND annotated=0
        """, (project_id,)).fetchall()
        return [r["file"] for r in rows]


def mark_annotated(project_id: int, file: str):
    with conn() as c:
        c.execute(
            "UPDATE hook_events SET annotated=1 WHERE project_id=? AND file=?",
            (project_id, file)
        )


# ── full codebase map ──────────────────────────────────────────────────────

def get_codebase_map(project_id: int) -> dict:
    """Full structured map: functions grouped by file, with intents + decisions."""
    funcs = get_all_functions(project_id)
    features = get_features(project_id)

    function_ids = [f["id"] for f in funcs]
    intents_by_fn   = get_latest_intents_batch(function_ids)
    decisions_by_fn = get_decisions_batch(function_ids)
    evolution_by_fn = get_evolution_batch(function_ids)

    fn_map = {}
    for f in funcs:
        intent = intents_by_fn.get(f["id"])
        fn_map[f["id"]] = {
            **dict(f),
            "intent": intent,
            "decisions": decisions_by_fn.get(f["id"], []),
            "evolution": evolution_by_fn.get(f["id"], []),
            "has_intent": intent is not None,
        }

    titles_by_fn: dict[int, list] = defaultdict(list)
    with conn() as c:
        link_rows = c.execute(
            """
            SELECT fl.function_id, fe.title FROM feature_links fl
            JOIN features fe ON fe.id = fl.feature_id
            JOIN functions fn ON fn.id = fl.function_id
            WHERE fn.project_id = ?
            """,
            (project_id,),
        ).fetchall()
    for r in link_rows:
        titles_by_fn[r["function_id"]].append(r["title"])
    for fid, meta in fn_map.items():
        meta["feature_titles"] = titles_by_fn.get(fid, [])

    by_file: dict[str, list] = {}
    for fn in fn_map.values():
        by_file.setdefault(fn["file"], []).append(fn)

    unannotated = get_unannotated_files(project_id)
    hook_backlog = _hook_backlog_entries(project_id, by_file)

    return {
        "by_file": by_file,
        "features": features,
        "total_functions": len(funcs),
        "annotated": sum(1 for f in fn_map.values() if f["has_intent"]),
        "unannotated_files": unannotated,
        "hook_backlog": hook_backlog,
    }


def _hook_backlog_entries(project_id: int, by_file: dict[str, list]) -> list[dict]:
    """Files with unresolved hook events + how many functions still lack intent."""
    with conn() as c:
        rows = c.execute(
            """
            SELECT file, COUNT(*) AS hook_count, MAX(occurred_at) AS last_touch
            FROM hook_events
            WHERE project_id=? AND annotated=0
            GROUP BY file
            ORDER BY last_touch DESC
            """,
            (project_id,),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        fns = by_file.get(r["file"], [])
        missing = sum(1 for fn in fns if not fn["has_intent"])
        out.append(
            {
                "file": r["file"],
                "hook_events": r["hook_count"],
                "last_touch": r["last_touch"],
                "functions_without_intent": missing,
                "functions_in_file": len(fns),
            }
        )
    return out


# ── embeddings ─────────────────────────────────────────────────────────────

def store_embedding(intent_id: int, model: str, vector: bytes):
    with conn() as c:
        c.execute("""
            INSERT INTO intent_embeddings(intent_id, model, vector, created_at)
            VALUES(?,?,?,?)
            ON CONFLICT(intent_id, model) DO UPDATE SET vector=excluded.vector, created_at=excluded.created_at
        """, (intent_id, model, vector, now()))


def get_embeddings_for_project(project_id: int, model: str) -> list[dict]:
    """Return list of {intent_id, function_id, qualname, file, vector, user_request} for semantic search."""
    with conn() as c:
        rows = c.execute("""
            SELECT ie.intent_id, ie.vector, i.user_request, i.reasoning,
                   i.implementation_notes, f.id AS function_id, f.qualname, f.file, f.lineno, f.signature
            FROM intent_embeddings ie
            JOIN intents i ON i.id = ie.intent_id
            JOIN functions f ON f.id = i.function_id
            WHERE f.project_id = ? AND ie.model = ?
        """, (project_id, model)).fetchall()
        return [dict(r) for r in rows]


def count_unembedded_intents(project_id: int, model: str) -> int:
    """Count intents with no embedding for the given model (cheap preflight for embed)."""
    with conn() as c:
        row = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM intents i
            JOIN functions f ON f.id = i.function_id
            WHERE f.project_id = ?
              AND i.id NOT IN (
                  SELECT intent_id FROM intent_embeddings WHERE model = ?
              )
            """,
            (project_id, model),
        ).fetchone()
        return int(row["n"]) if row else 0


def get_unembedded_intents(project_id: int, model: str) -> list[dict]:
    """Return intents that have no embedding for the given model."""
    with conn() as c:
        rows = c.execute("""
            SELECT i.id AS intent_id, i.user_request, i.reasoning, i.implementation_notes,
                   f.qualname, f.file
            FROM intents i
            JOIN functions f ON f.id = i.function_id
            WHERE f.project_id = ?
              AND i.id NOT IN (
                  SELECT intent_id FROM intent_embeddings WHERE model = ?
              )
        """, (project_id, model)).fetchall()
        return [dict(r) for r in rows]


# ── intent search ──────────────────────────────────────────────────────────

def search_intents(project_id: int, query: str) -> list[dict]:
    """Simple keyword search across intents, decisions, and function names."""
    q = f"%{query.lower()}%"
    with conn() as c:
        rows = c.execute("""
            SELECT DISTINCT f.id, f.qualname, f.file, f.lineno, f.signature,
                i.user_request, i.reasoning, i.implementation_notes
            FROM functions f
            LEFT JOIN intents i ON i.function_id = f.id
            WHERE f.project_id=?
              AND (
                LOWER(f.name) LIKE ? OR
                LOWER(f.qualname) LIKE ? OR
                LOWER(COALESCE(i.user_request,'')) LIKE ? OR
                LOWER(COALESCE(i.reasoning,'')) LIKE ? OR
                LOWER(COALESCE(i.implementation_notes,'')) LIKE ?
              )
            ORDER BY f.file, f.lineno
        """, (project_id, q, q, q, q, q)).fetchall()
        return [dict(r) for r in rows]
