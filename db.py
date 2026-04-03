import sqlite3
import os
import json
from contextlib import contextmanager
from typing import Optional
from emotion_engine import EmotionEngine

emotion_engine = EmotionEngine()

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
    import logging

    logger = logging.getLogger("exobrain")

    try:
        from sentence_transformers import SentenceTransformer
        import torch

        logger.info("Loading embedding model: BAAI/bge-m3")
        logger.info(f"CUDA available: {torch.cuda.is_available()}")

        # BGE-M3: Multi-Lingual, Multi-Functionality, Multi-Granularity
        # ~500MB, supports 100+ languages including Chinese technical terms
        # 1024-dim dense embeddings via sentence-transformers
        _embedding_model = SentenceTransformer("BAAI/bge-m3")

        dim = _embedding_model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded successfully. Dimension: {dim}")
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        _embedding_model = None  # Graceful degradation: fall back to LIKE search only


# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get(
    "MEMORY_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "exobrain.db"),
)

SCHEMA_V1 = """
-- Track 1: The Immutable Truth Layer (Append Only, never modify)
CREATE TABLE raw_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text      TEXT NOT NULL,
    ai_summary    TEXT,
    domain        TEXT,
    valence       REAL DEFAULT 0.5,
    arousal       REAL DEFAULT 0.3,
    activation_count INTEGER DEFAULT 1,
    last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
        conn.execute(
            "ALTER TABLE actionable_tasks RENAME COLUMN urgency TO effort_estimate"
        )
        conn.execute(
            "ALTER TABLE actionable_tasks ADD COLUMN priority TEXT DEFAULT 'normal'"
        )
    if "parent_task_id" not in columns:
        conn.execute(
            "ALTER TABLE actionable_tasks ADD COLUMN "
            "parent_task_id INTEGER REFERENCES actionable_tasks(id) ON DELETE CASCADE"
        )

    # Inject Emotion Engine columns to raw_logs
    cursor_logs = conn.execute("PRAGMA table_info(raw_logs)")
    log_columns = [row["name"] for row in cursor_logs.fetchall()]
    if "valence" not in log_columns:
        conn.execute("ALTER TABLE raw_logs ADD COLUMN domain TEXT")
        conn.execute("ALTER TABLE raw_logs ADD COLUMN valence REAL DEFAULT 0.5")
        conn.execute("ALTER TABLE raw_logs ADD COLUMN arousal REAL DEFAULT 0.3")
        conn.execute(
            "ALTER TABLE raw_logs ADD COLUMN activation_count INTEGER DEFAULT 1"
        )
        conn.execute("ALTER TABLE raw_logs ADD COLUMN last_active_at DATETIME")
        conn.execute("UPDATE raw_logs SET last_active_at = created_at")

    # Inject embedding columns for pre-computed vectors
    if "embedding" not in log_columns:
        # BLOB to store float32 array (1024 dims * 4 bytes = 4096 bytes for BGE-M3)
        conn.execute("ALTER TABLE raw_logs ADD COLUMN embedding BLOB")
        conn.execute("ALTER TABLE raw_logs ADD COLUMN embedding_model TEXT")
        conn.execute("ALTER TABLE raw_logs ADD COLUMN embedding_dim INTEGER")


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
    import logging

    logger = logging.getLogger("exobrain")
    logger.info("load_models() started")
    _load_embedding_model()
    model = _get_embedding_model()
    if model is not None:
        logger.info("load_models() completed successfully")
    else:
        logger.error("load_models() failed - model is None")


def _get_current_model_info() -> tuple[str, int]:
    """Get the current embedding model name and dimension.
    Returns: (model_name, embedding_dim)
    """
    model = _get_embedding_model()
    if model is None:
        return ("none", 0)
    # For sentence-transformers, extract model name from model object
    model_name = getattr(model, "model_name", None)
    if model_name is None:
        # Try to get from the underlying transformer model
        try:
            model_name = model[0].auto_model.config._name_or_path
        except:
            model_name = "unknown"
    dim = model.get_sentence_embedding_dimension()
    return (model_name, dim)


# ---------------------------------------------------------------------------
# Write Tools
# ---------------------------------------------------------------------------


def record_thought_or_fact(
    raw_thought_string: str,
    ai_summary: Optional[str] = None,
    domain: Optional[str] = None,
    valence: float = 0.5,
    arousal: float = 0.3,
) -> dict:
    import logging

    logger = logging.getLogger("exobrain")

    model = _get_embedding_model()
    model_name, embedding_dim = _get_current_model_info()
    logger.info(
        f"record_thought_or_fact: model={model_name}, dim={embedding_dim}, model_obj={model is not None}"
    )

    # Pre-compute embedding if model is available
    embedding_blob = None
    if model is not None:
        try:
            import numpy as np

            vec = model.encode([raw_thought_string], normalize_embeddings=True)[0]
            embedding_blob = vec.astype(np.float32).tobytes()
            logger.info(
                f"Embedding computed: shape={vec.shape}, bytes={len(embedding_blob)}"
            )
        except Exception as e:
            logger.error(f"Failed to compute embedding: {e}")
            embedding_blob = None
    else:
        logger.warning("Model not available, skipping embedding computation")

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO raw_logs (raw_text, ai_summary, domain, valence, arousal, embedding, embedding_model, embedding_dim) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                raw_thought_string,
                ai_summary,
                domain,
                valence,
                arousal,
                embedding_blob,
                model_name,
                embedding_dim,
            ),
        )
        log_id = cursor.lastrowid
        conn.commit()
    return {
        "log_id": log_id,
        "status": "recorded",
        "emotion": {"valence": valence, "arousal": arousal},
    }


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
            "INSERT INTO raw_logs (raw_text, ai_summary, domain) VALUES (?, ?, ?)",
            (
                raw_user_quote,
                f"Task extraction source for: {task_name}",
                "待办事务/计划",
            ),
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
        row = conn.execute(
            "SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return dict(row)


def update_task(
    task_id: int,
    status: Optional[str] = None,
    metadata: Optional[dict] = None,
    reason: Optional[str] = None,
) -> dict:
    """Update task status, metadata, or both.

    Args:
        task_id: The ID of the task to update
        status: Optional. New status ('active', 'completed', 'discarded')
        metadata: Optional. Dict of metadata to merge into existing metadata
        reason: Optional. Reason for the update (stored in task_updates log)
    """
    with get_connection() as conn:
        task = conn.execute(
            "SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not task:
            return {"error": f"Task ID {task_id} not found."}

        updates = []
        params = []

        # Update status if provided
        if status is not None:
            updates.append("status = ?")
            params.append(status)
            # Log status change
            conn.execute(
                "INSERT INTO task_updates (task_id, new_status, reason) VALUES (?, ?, ?)",
                (task_id, status, reason),
            )

        # Update metadata if provided
        if metadata is not None:
            try:
                current_metadata = json.loads(task["metadata_json"] or "{}")
            except json.JSONDecodeError:
                current_metadata = {}
            current_metadata.update(metadata)
            updates.append("metadata_json = ?")
            params.append(json.dumps(current_metadata, ensure_ascii=False))

        # Execute update if there are changes
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(task_id)
            conn.execute(
                f"UPDATE actionable_tasks SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# LLM Re-ranking (Pass 3 — intent-level relevance filter)
# ---------------------------------------------------------------------------


def _rerank_with_llm(query: str, candidates: list[dict], top_n: int = 5) -> list[dict]:
    """Use Claude Haiku to filter candidates by query intent, not just keyword presence.

    Solves the case where a keyword appears in an unrelated document (e.g., 'milk'
    used as an example in a design doc). Returns only candidates where the content
    is actually about what the user is asking.
    """
    if not candidates:
        return []
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return candidates[:top_n]

    try:
        import re
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        items_text = "\n".join(
            f"[{i}] {c['raw_text'][:400]}" for i, c in enumerate(candidates)
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'Query: "{query}"\n\n'
                        f"Rate each item's relevance to the query intent. "
                        f"1.0 = directly about what the user is asking. "
                        f"0.0 = keyword appears but the text is not actually about this topic.\n"
                        f"Return ONLY a JSON array of floats, one per item, no explanation.\n\n"
                        f"{items_text}"
                    ),
                }
            ],
        )
        text = response.content[0].text.strip()
        match = re.search(r"\[[\d\s.,]+\]", text)
        if not match:
            return candidates[:top_n]

        scores = json.loads(match.group())
        for i, c in enumerate(candidates):
            c["rerank_score"] = float(scores[i]) if i < len(scores) else 0.0

        relevant = [c for c in candidates if c.get("rerank_score", 0) >= 0.4]
        return sorted(relevant, key=lambda x: x["rerank_score"], reverse=True)[:top_n]

    except Exception:
        return candidates[:top_n]  # Graceful degradation


# ---------------------------------------------------------------------------
# Read Tools
# ---------------------------------------------------------------------------


def recall_past_mentions_of(
    keyword: str,
    limit: int = 15,
    semantic: bool = True,
    time_days: Optional[int] = None,
    min_arousal: Optional[float] = None,
    min_valence: Optional[float] = None,
    semantic_threshold: float = 0.50,
    use_decay: bool = True,
) -> dict:
    """
    Recall past mentions with flexible filtering.

    Args:
        keyword: Search keyword or phrase
        limit: Maximum results to return
        semantic: Whether to include semantic (vector) search results
        time_days: If set, only search records from last N days
        min_arousal: If set (0.0-1.0), filter records with arousal >= threshold
        min_valence: If set (0.0-1.0), filter records with valence >= threshold
        semantic_threshold: Minimum semantic similarity score (0.0-1.0, default 0.50)
        use_decay: Whether to apply Ebbinghaus decay weighting to final scores
    """
    like_pattern = f"%{keyword}%"

    # Build WHERE clause for time filtering
    where_conditions = []
    params = []

    if time_days is not None:
        where_conditions.append(f"created_at >= datetime('now', '-{time_days} days')")

    if min_arousal is not None:
        where_conditions.append(f"arousal >= {min_arousal}")

    if min_valence is not None:
        where_conditions.append(f"valence >= {min_valence}")

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    with get_connection() as conn:
        # Pass 1: Fast exact LIKE search
        like_sql = f"""
            SELECT id, raw_text, created_at, domain, valence, arousal, activation_count, last_active_at 
            FROM raw_logs 
            {where_clause}
            {"AND" if where_conditions else "WHERE"} (raw_text LIKE ? OR ai_summary LIKE ?)
            ORDER BY created_at DESC LIMIT ?
        """.strip()

        raw_results = conn.execute(
            like_sql, (like_pattern, like_pattern, limit)
        ).fetchall()

        task_results = conn.execute(
            "SELECT id, task_name, status, due_date FROM actionable_tasks "
            "WHERE task_name LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like_pattern, limit),
        ).fetchall()

        raw_found = {r["id"]: dict(r) for r in raw_results}
        task_found = [dict(r) for r in task_results]

        # Pass 2: Semantic vector search (optional)
        if semantic:
            model = _get_embedding_model()
            current_model_name, current_dim = _get_current_model_info()
            if model is not None:
                try:
                    import numpy as np

                    # Build SQL with same filters for semantic search
                    semantic_where = where_clause

                    all_rows = conn.execute(
                        f"""
                        SELECT id, raw_text, embedding, embedding_model, embedding_dim, 
                               created_at, domain, valence, arousal, activation_count, last_active_at 
                        FROM raw_logs 
                        {semantic_where}
                        ORDER BY created_at DESC
                        """
                    ).fetchall()

                    if all_rows:
                        # Encode query once
                        query_vec = model.encode([keyword], normalize_embeddings=True)[
                            0
                        ]

                        # Build document vectors
                        doc_vecs = []
                        valid_rows = []

                        for row in all_rows:
                            row_dict = dict(row)
                            embedding_blob = row_dict.get("embedding")
                            stored_model = row_dict.get("embedding_model")
                            stored_dim = row_dict.get("embedding_dim")

                            vec = None
                            if (
                                embedding_blob is not None
                                and stored_model == current_model_name
                                and stored_dim == current_dim
                            ):
                                vec = np.frombuffer(embedding_blob, dtype=np.float32)
                            else:
                                # Re-encode and update
                                try:
                                    vec = model.encode(
                                        [row_dict["raw_text"]],
                                        normalize_embeddings=True,
                                    )[0]
                                    conn.execute(
                                        "UPDATE raw_logs SET embedding = ?, embedding_model = ?, embedding_dim = ? WHERE id = ?",
                                        (
                                            vec.astype(np.float32).tobytes(),
                                            current_model_name,
                                            current_dim,
                                            row_dict["id"],
                                        ),
                                    )
                                except Exception:
                                    continue

                            if vec is not None:
                                doc_vecs.append(vec)
                                valid_rows.append(row_dict)

                        conn.commit()

                        if doc_vecs:
                            doc_vecs = np.array(doc_vecs)
                            scores = np.dot(doc_vecs, query_vec)
                            for idx in np.argsort(scores)[::-1][: limit * 2]:
                                score = float(scores[idx])
                                # Use configurable threshold
                                if score > semantic_threshold:
                                    row = valid_rows[idx]
                                    raw_found[row["id"]] = {
                                        **raw_found.get(row["id"], row),
                                        "semantic_score": score,
                                    }
                except Exception:
                    pass  # Graceful degradation: return LIKE results only

        # Pass 2.5: Apply Ebbinghaus decay and Emotion weighting (optional)
        for log_id, row in list(raw_found.items()):
            if use_decay:
                decay_score = emotion_engine.calculate_decay_score(row)
                row["decay_score"] = decay_score
                # Final raw score = semantic score * decay score multiplier
                base_score = row.get(
                    "semantic_score", 0.5
                )  # Give LIKE-only hits a base 0.5
                row["final_hybrid_score"] = base_score * decay_score
            else:
                # Skip decay, use semantic score directly (or 0.5 for LIKE-only)
                row["decay_score"] = 1.0
                row["final_hybrid_score"] = row.get("semantic_score", 0.5)

        merged = sorted(
            raw_found.values(),
            key=lambda r: r.get("final_hybrid_score", 0),
            reverse=True,
        )[:limit]

        # Bump activation count for the ultimately surfaced logs
        if merged:
            surfaced_ids = [str(r["id"]) for r in merged]
            conn.execute(
                f"UPDATE raw_logs SET activation_count = activation_count + 1, last_active_at = CURRENT_TIMESTAMP WHERE id IN ({','.join(surfaced_ids)})"
            )
            conn.commit()

    reranked = _rerank_with_llm(keyword, merged)
    return {
        "raw_logs_found": reranked,
        "structured_tasks_found": task_found,
    }


def check_active_emotions() -> list[dict]:
    """Pull the top unresolved/heavy emotional logs based purely on decay score."""
    with get_connection() as conn:
        all_rows = conn.execute(
            "SELECT id, raw_text, created_at, domain, valence, arousal, activation_count, last_active_at FROM raw_logs ORDER BY created_at DESC"
        ).fetchall()

    scored_logs = []
    for r in all_rows:
        row = dict(r)
        decay_score = emotion_engine.calculate_decay_score(row)
        # We only care about high-arousal thoughts floating to the top
        if row.get("arousal", 0.5) >= 0.5:
            row["emotion_weight_score"] = decay_score
            scored_logs.append(row)

    scored_logs.sort(key=lambda x: x["emotion_weight_score"], reverse=True)
    return scored_logs[:3]  # Only return the top 3 heaviest active subtexts


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

        task["suggestion_score"] = PRIORITY_SCORES.get(priority, 0) + EFFORT_BONUS.get(
            effort, 0
        )
        results.append(task)

    results.sort(key=lambda x: x["suggestion_score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Schema Introspection (for Agentic use)
# ---------------------------------------------------------------------------


def get_schema_info() -> dict:
    """Expose database schema for agents who want to write custom SQL."""
    with get_connection() as conn:
        # Get all tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()

        schema = {}
        for table in tables:
            table_name = table[0]
            # Get columns for each table
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = [
                {
                    "name": row[1],
                    "type": row[2],
                    "nullable": not row[3],
                    "default": row[4],
                }
                for row in cursor.fetchall()
            ]

            # Get row count
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]

            schema[table_name] = {"columns": columns, "row_count": count}

    return {
        "database_path": DB_PATH,
        "tables": schema,
        "note": "This database is yours. You can read/write directly via SQLite if needed. For deletions, write your own SQL.",
    }
