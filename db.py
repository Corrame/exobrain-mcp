import sqlite3
import os
import json
from contextlib import contextmanager
from typing import Optional

# ---------------------------------------------------------------------------
# Semantic Search (Eagerly loaded at startup)
# ---------------------------------------------------------------------------
_embedding_model = None

def _get_embedding_model():
    """Return the cached embedding model (pre-loaded at startup)."""
    return _embedding_model

def _load_embedding_model() -> None:
    """Load the multilingual sentence embedding model into memory.
    Called once at startup. Fails silently: falls back to LIKE-only search.
    """
    global _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        # paraphrase-multilingual-MiniLM-L12-v2: ~100MB, CPU-friendly, strong Chinese/multilingual support
        _embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except Exception:
        _embedding_model = None  # Graceful degradation: fall back to LIKE search only

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get(
    "MEMORY_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "exobrain.db")
)

SCHEMA_V1 = """
-- Track 1: The Immutable Truth Layer (Append Only, never modify)
CREATE TABLE raw_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text      TEXT NOT NULL,
    ai_summary    TEXT,
    source_module TEXT DEFAULT 'mcp_agent',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Track 2: The Projected Structural View (Reconstructible cache for current AI)
CREATE TABLE actionable_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id          INTEGER REFERENCES raw_logs(id) ON DELETE SET NULL,
    task_name       TEXT NOT NULL,
    status          TEXT DEFAULT 'active',     -- active, completed, discarded
    due_date        TEXT,
    priority        TEXT DEFAULT 'normal',     -- low, normal, high, critical
    effort_estimate TEXT,                      -- quick, small, medium, large
    parent_task_id  INTEGER REFERENCES actionable_tasks(id) ON DELETE CASCADE,
    metadata_json   TEXT DEFAULT '{}',         -- Escape hatch for arbitrary key-value tags
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_updates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES actionable_tasks(id) ON DELETE CASCADE,
    new_status TEXT NOT NULL,
    reason     TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

@contextmanager
def get_connection():
    """Context manager for SQLite connections.
    Guarantees the connection is always closed, even if an exception occurs.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Initialization & Migrations
# ---------------------------------------------------------------------------

def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply incremental schema migrations on existing databases."""
    cursor = conn.execute("PRAGMA table_info(actionable_tasks)")
    columns = [row["name"] for row in cursor.fetchall()]
    if "urgency" in columns:
        conn.execute("ALTER TABLE actionable_tasks RENAME COLUMN urgency TO effort_estimate")
        conn.execute("ALTER TABLE actionable_tasks ADD COLUMN priority TEXT DEFAULT 'normal'")
    if "parent_task_id" not in columns:
        conn.execute(
            "ALTER TABLE actionable_tasks ADD COLUMN "
            "parent_task_id INTEGER REFERENCES actionable_tasks(id) ON DELETE CASCADE"
        )

def init_db() -> None:
    """Initialize the database schema and run any pending migrations."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='raw_logs'"
        )
        if cursor.fetchone()[0] == 0:
            conn.executescript(SCHEMA_V1)
        else:
            _migrate_schema(conn)
        conn.commit()

def load_models() -> None:
    """Pre-load ML models into memory. Call once at server startup."""
    _load_embedding_model()

# ---------------------------------------------------------------------------
# Write Tools
# ---------------------------------------------------------------------------

def record_thought_or_fact(raw_thought_string: str, ai_summary: Optional[str] = None) -> dict:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO raw_logs (raw_text, ai_summary) VALUES (?, ?)",
            (raw_thought_string, ai_summary),
        )
        log_id = cursor.lastrowid
        conn.commit()
    return {"log_id": log_id, "status": "recorded"}

def add_actionable_task(
    task_name: str,
    raw_user_quote: str,
    due_date: Optional[str] = None,
    priority: str = "normal",
    effort_estimate: Optional[str] = None,
    parent_task_id: Optional[int] = None,
) -> dict:
    with get_connection() as conn:
        # Always write the original quote to Track 1 first
        cursor = conn.execute(
            "INSERT INTO raw_logs (raw_text, ai_summary) VALUES (?, ?)",
            (raw_user_quote, f"Task extraction source for: {task_name}"),
        )
        log_id = cursor.lastrowid

        cursor = conn.execute(
            """INSERT INTO actionable_tasks
            (log_id, task_name, due_date, priority, effort_estimate, parent_task_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (log_id, task_name, due_date, priority, effort_estimate, parent_task_id),
        )
        task_id = cursor.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)

def update_task_status(task_id: int, new_status: str, reason_for_change: Optional[str] = None) -> dict:
    with get_connection() as conn:
        if not conn.execute(
            "SELECT id FROM actionable_tasks WHERE id = ?", (task_id,)
        ).fetchone():
            return {"error": f"Task ID {task_id} not found."}

        conn.execute(
            "UPDATE actionable_tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, task_id),
        )
        conn.execute(
            "INSERT INTO task_updates (task_id, new_status, reason) VALUES (?, ?, ?)",
            (task_id, new_status, reason_for_change),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)

def add_task_metadata(task_id: int, new_metadata: dict) -> dict:
    with get_connection() as conn:
        task = conn.execute(
            "SELECT metadata_json FROM actionable_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not task:
            return {"error": f"Task ID {task_id} not found."}

        try:
            current_metadata = json.loads(task["metadata_json"] or "{}")
        except json.JSONDecodeError:
            current_metadata = {}

        current_metadata.update(new_metadata)
        conn.execute(
            "UPDATE actionable_tasks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(current_metadata, ensure_ascii=False), task_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)

# ---------------------------------------------------------------------------
# Read Tools
# ---------------------------------------------------------------------------

def recall_past_mentions_of(keyword: str, limit: int = 15) -> dict:
    like_pattern = f"%{keyword}%"

    with get_connection() as conn:
        # Pass 1: Fast exact LIKE search
        raw_results = conn.execute(
            "SELECT id, raw_text, created_at FROM raw_logs "
            "WHERE raw_text LIKE ? OR ai_summary LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (like_pattern, like_pattern, limit),
        ).fetchall()
        task_results = conn.execute(
            "SELECT id, task_name, status, due_date FROM actionable_tasks "
            "WHERE task_name LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like_pattern, limit),
        ).fetchall()

        raw_found = {r["id"]: dict(r) for r in raw_results}
        task_found = [dict(r) for r in task_results]

        # Pass 2: Semantic vector search (always runs alongside LIKE)
        model = _get_embedding_model()
        if model is not None:
            try:
                import numpy as np
                all_rows = conn.execute(
                    "SELECT id, raw_text, created_at FROM raw_logs ORDER BY created_at DESC"
                ).fetchall()
                if all_rows:
                    texts = [r["raw_text"] for r in all_rows]
                    query_vec = model.encode([keyword], normalize_embeddings=True)[0]
                    doc_vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                    scores = np.dot(doc_vecs, query_vec)
                    for idx in np.argsort(scores)[::-1][:limit]:
                        if scores[idx] > 0.35:
                            row = dict(all_rows[idx])
                            # Enrich existing LIKE results or add new semantic-only hits
                            raw_found[row["id"]] = {
                                **raw_found.get(row["id"], row),
                                "semantic_score": float(scores[idx]),
                            }
            except Exception:
                pass  # Graceful degradation: return LIKE results only

    merged = sorted(raw_found.values(), key=lambda r: r.get("semantic_score", 0), reverse=True)
    return {
        "raw_logs_found": merged[:limit],
        "structured_tasks_found": task_found,
    }

def suggest_next_actions(available_time_minutes: Optional[int] = None) -> list[dict]:
    """Score and rank active tasks. All filtering/sorting is done here, not by the AI."""
    # Priority scores: how urgent is this task?
    PRIORITY_SCORES = {"critical": 20, "high": 10, "normal": 0, "low": -5}
    # Effort bonus: prefer quick wins when scoring is equal
    EFFORT_BONUS = {"quick": 5, "small": 2}

    with get_connection() as conn:
        tasks = conn.execute(
            "SELECT id, task_name, due_date, priority, effort_estimate, parent_task_id "
            "FROM actionable_tasks WHERE status = 'active'"
        ).fetchall()

    results = []
    for t in tasks:
        task = dict(t)
        priority = (task.get("priority") or "normal").lower()
        effort = (task.get("effort_estimate") or "").lower()

        # Filter by available time before scoring to avoid wasting cycles
        if isinstance(available_time_minutes, int):
            if available_time_minutes <= 15 and effort in ("medium", "large"):
                continue
            if available_time_minutes <= 30 and effort == "large":
                continue

        task["suggestion_score"] = PRIORITY_SCORES.get(priority, 0) + EFFORT_BONUS.get(effort, 0)
        results.append(task)

    results.sort(key=lambda x: x["suggestion_score"], reverse=True)
    return results
