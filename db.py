import sqlite3
import os
import json
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Optional semantic search (lazy-loaded on first use)
# ---------------------------------------------------------------------------
_embedding_model = None

def _get_embedding_model():
    """Return the cached embedding model (loaded at startup via init_db)."""
    return _embedding_model

def _load_embedding_model():
    """Eagerly load the multilingual sentence embedding model."""
    global _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        # paraphrase-multilingual-MiniLM-L12-v2: 100MB, CPU-friendly, strong Chinese support
        _embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except Exception:
        _embedding_model = None  # Graceful degradation: fall back to LIKE search only

DB_PATH = os.environ.get(
    "MEMORY_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "exobrain.db")
)

SCHEMA_V1 = """
-- 轨一：绝对真实的原始记录层 (The Immutable Truth Layer)
-- 这一层只允许追加（Append Only），不可篡改
CREATE TABLE raw_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text      TEXT NOT NULL,
    ai_summary    TEXT,
    source_module TEXT DEFAULT 'mcp_agent',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 轨二：结构化投影层 (Projected Structural View)
-- 这一层是给当前的 AI 用的业务视图，随时可以删除并重构。
CREATE TABLE actionable_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id        INTEGER REFERENCES raw_logs(id) ON DELETE SET NULL,
    task_name     TEXT NOT NULL,
    status        TEXT DEFAULT 'active', -- active, completed, discarded
    due_date      TEXT,
    priority      TEXT DEFAULT 'normal', -- low, normal, high, critical
    effort_estimate TEXT,                -- quick, small, medium, large
    parent_task_id  INTEGER REFERENCES actionable_tasks(id) ON DELETE CASCADE,
    metadata_json TEXT DEFAULT '{}',     -- 其他所有长尾扩展数据以 JSON 存入
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_updates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       INTEGER NOT NULL REFERENCES actionable_tasks(id) ON DELETE CASCADE,
    new_status    TEXT NOT NULL,
    reason        TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_connection()
    # If the user is running the newly rewritten app, we create a new schema.
    # To not clash with the old old memory.db, we use exobrain.db (defined in DB_PATH)
    cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='raw_logs'")
    if cursor.fetchone()[0] == 0:
        conn.executescript(SCHEMA_V1)
    else:
        # Migration for adding priority and renaming urgency to effort_estimate
        cursor = conn.execute("PRAGMA table_info(actionable_tasks)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'urgency' in columns:
            conn.execute("ALTER TABLE actionable_tasks RENAME COLUMN urgency TO effort_estimate")
            conn.execute("ALTER TABLE actionable_tasks ADD COLUMN priority TEXT DEFAULT 'normal'")
        if 'parent_task_id' not in columns:
            conn.execute("ALTER TABLE actionable_tasks ADD COLUMN parent_task_id INTEGER REFERENCES actionable_tasks(id) ON DELETE CASCADE")
    conn.commit()
    conn.close()
    # Eagerly pre-load the embedding model so the first search has no cold-start delay
    _load_embedding_model()

# ---------------------------------------------------------------------------
# Core Operations for MCP Tools
# ---------------------------------------------------------------------------

def record_thought_or_fact(raw_thought_string: str, ai_summary: Optional[str] = None) -> dict:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO raw_logs (raw_text, ai_summary) VALUES (?, ?)",
        (raw_thought_string, ai_summary)
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"log_id": log_id, "status": "recorded"}

def add_actionable_task(task_name: str, raw_user_quote: str, due_date: Optional[str] = None, priority: str = 'normal', effort_estimate: Optional[str] = None, parent_task_id: Optional[int] = None) -> dict:
    conn = get_connection()
    
    # 无论如何，用户的原话先必须且强制地进入“轨一”
    cursor = conn.execute(
        "INSERT INTO raw_logs (raw_text, ai_summary) VALUES (?, ?)",
        (raw_user_quote, f"Task extraction source for: {task_name}")
    )
    log_id = cursor.lastrowid
    
    # 创建给 AI 当下消费用的业务数据
    cursor = conn.execute(
        """INSERT INTO actionable_tasks 
        (log_id, task_name, due_date, priority, effort_estimate, parent_task_id) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (log_id, task_name, due_date, priority, effort_estimate, parent_task_id)
    )
    task_id = cursor.lastrowid
    conn.commit()
    
    row = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)

def update_task_status(task_id: int, new_status: str, reason_for_change: Optional[str] = None) -> dict:
    conn = get_connection()
    
    old_task = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    if not old_task:
        conn.close()
        return {"error": f"Task ID {task_id} not found."}
        
    conn.execute(
        "UPDATE actionable_tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_status, task_id)
    )
    
    # 记录状态变更的原因，方便找回上下文
    conn.execute(
        "INSERT INTO task_updates (task_id, new_status, reason) VALUES (?, ?, ?)",
        (task_id, new_status, reason_for_change)
    )
    conn.commit()
    
    row = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)

def add_task_metadata(task_id: int, new_metadata: dict) -> dict:
    conn = get_connection()
    task = conn.execute("SELECT metadata_json FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    
    if not task:
        conn.close()
        return {"error": f"Task ID {task_id} not found."}
        
    current_metadata_str = task["metadata_json"] or "{}"
    try:
        current_metadata = json.loads(current_metadata_str)
    except json.JSONDecodeError:
        current_metadata = {}
        
    current_metadata.update(new_metadata)
    updated_metadata_str = json.dumps(current_metadata, ensure_ascii=False)
    
    conn.execute(
        "UPDATE actionable_tasks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (updated_metadata_str, task_id)
    )
    conn.commit()
    
    row = conn.execute("SELECT * FROM actionable_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)

def recall_past_mentions_of(keyword: str, limit: int = 15) -> dict:
    conn = get_connection()
    like_pattern = f"%{keyword}%"
    
    # --- Pass 1: Exact LIKE search ---
    raw_results = conn.execute(
        "SELECT id, raw_text, created_at FROM raw_logs WHERE raw_text LIKE ? OR ai_summary LIKE ? ORDER BY created_at DESC LIMIT ?",
        (like_pattern, like_pattern, limit)
    ).fetchall()
    task_results = conn.execute(
        "SELECT id, task_name, status, due_date FROM actionable_tasks WHERE task_name LIKE ? ORDER BY created_at DESC LIMIT ?",
        (like_pattern, limit)
    ).fetchall()

    raw_found = {r["id"]: dict(r) for r in raw_results}  # id -> record dict
    task_found = [dict(r) for r in task_results]

    # --- Pass 2: Semantic vector search (always runs, adds to results) ---
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
                top_indices = np.argsort(scores)[::-1][:limit]
                
                for idx in top_indices:
                    if scores[idx] > 0.35:
                        row = dict(all_rows[idx])
                        row["semantic_score"] = float(scores[idx])
                        # Merge into raw_found (LIKE results get overwritten with score enrichment)
                        raw_found[row["id"]] = {**raw_found.get(row["id"], row), "semantic_score": float(scores[idx])}
        except Exception:
            pass  # Graceful degradation on any failure

    conn.close()
    # Sort final merged results by semantic score (desc), fallback to recency
    merged = sorted(raw_found.values(), key=lambda r: r.get("semantic_score", 0), reverse=True)
    return {
        "raw_logs_found": merged[:limit],
        "structured_tasks_found": task_found
    }

def suggest_next_actions(available_time_minutes: Optional[int] = None) -> list[dict]:
    # 把复杂的过滤逻辑写在代码里，避免 AI 苦逼地写 SQL 或者判断
    conn = get_connection()
    
    # 获取所有的未完成活动
    sql = "SELECT id, task_name, due_date, priority, effort_estimate, parent_task_id FROM actionable_tasks WHERE status = 'active'"
    tasks = conn.execute(sql).fetchall()
    conn.close()
    
    results = []
    for t in tasks:
        task = dict(t)
        priority = (task.get("priority") or "normal").lower()
        effort = (task.get("effort_estimate") or "").lower()
        score = 0
        
        if priority == "critical": score += 20
        elif priority == "high": score += 10
        elif priority == "low": score -= 5
        
        if effort == "quick": score += 5
        elif effort == "small": score += 2
            
        # 如果用户说了当前只有 10 分钟闲时间，那么过滤掉 large 的任务
        if isinstance(available_time_minutes, int):
            if available_time_minutes <= 15 and effort in ["medium", "large"]:
                continue
            if available_time_minutes <= 30 and effort == "large":
                continue
                
        task['suggestion_score'] = score
        results.append(task)
        
    results.sort(key=lambda x: x['suggestion_score'], reverse=True)
    return results
