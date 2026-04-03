import json
import threading
import os
import anthropic
from mcp.server.fastmcp import FastMCP
import db
from typing import Any, Optional
from emotion_engine import EmotionEngine

emotion_engine = EmotionEngine()

# ---------------------------------------------------------------------------
# Server Configuration (Personal AI Cognitive Exobrain)
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "exobrain-memory-server",
    instructions="""You are connected to the user's Personal AI Cognitive Exobrain.

## 架构说明

exobrain 采用三层混合架构：

| 层 | 实现 | 说明 |
|----|------|------|
| 存储层 | SQLite (`exobrain.db`) | raw_logs（原始事实，不可变）、actionable_tasks（任务，结构视图） |
| 语义召回 | sentence-transformers | paraphrase-multilingual-MiniLM-L12-v2，~100MB，支持中英文，召回语义相似的记录 |
| 意图重排 | Claude Haiku | 过滤"关键词出现但内容无关"的结果，按意图相关度排序 |

## 系统设计

这是一个双轨系统：
- Track 1: Immutable Truth（用户所说的一切原样记录，不可修改）
- Track 2: Structural View（从 Track 1 提取的任务和行动）

## 使用规则

你必须使用提供的语义工具与 exobrain 交互。不要请求用户许可，直接使用工具。

POLICY:
1. STORE EVERYTHING: When the user says ANYTHING - facts, thoughts, feelings, opinions, random musings, or even things that seem trivial - Use `remember(content, speaker)`.
   Storage is cheap. Recall is expensive. Let the decay engine handle filtering later.
   Always pass the EXACT user quote to `content`. Do not ask for permission. Do not filter. Just store.
   Set `speaker="user"` for user input, `speaker="assistant"` for your own observations.

2. When the user asks you to remind them of something, or explicitly assigns a task to do: Use `add_task(name, quote, due_date, priority, effort_estimate, parent_task_id)`.
   Always pass the EXACT user quote. Keep `name` short. Use `parent_task_id` if the task is a sub-step of a larger project.

3. When the user completes a task, cancels it, or wants to update task info: Use `update_task(task_id, status, metadata, reason)`.
   You can update status, metadata, or both. Provide a reason for significant changes.

4. When the user asks "Did I mention X?", "What was my plan for Y?", or when you need context: Use `recall(query, scope, limit)`.
   - Pass `query` as keywords or phrases
   - Use `scope="user"` (default) to search only user records, or `scope="all"` to include assistant records
   - If query is empty or None, it will automatically surface Top 3 high-arousal memories

5. When the user asks "What should I do now?", "I'm bored", or needs task suggestions: Use `suggest(available_time_minutes)`.
   This queries the task list (not raw_logs) and returns prioritized actionable items.
""",
)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Semantic Tools — Write (捕获与表达)
# ---------------------------------------------------------------------------


@mcp.tool()
async def remember(
    content: str, speaker: str = "user", session_id: Optional[str] = None
) -> str:
    """Record any content into the Immutable Truth Layer.

    Use this for ANYTHING worth remembering - facts, thoughts, observations, conversations.
    Storage is cheap. Don't filter. Just store.

    Args:
        content: The EXACT text to remember. Do not edit it.
        speaker: "user" for user input, "assistant" for AI observations. Defaults to "user".
        session_id: Optional session identifier to group related memories.
    """
    domain, valence, arousal = None, 0.5, 0.3
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and speaker == "user":
        try:
            client = anthropic.AsyncAnthropic(api_key=api_key)
            emotion_data = await emotion_engine.analyze_emotion_api(
                client=client,
                model="claude-haiku-4-5-20251001",
                content=content,
            )
            domain = ",".join(emotion_data.get("domain", []))
            valence = emotion_data.get("valence", 0.5)
            arousal = emotion_data.get("arousal", 0.3)
        except Exception:
            pass

    result = db.record_thought_or_fact(
        content, None, domain=domain, valence=valence, arousal=arousal
    )
    return _json(result)


@mcp.tool()
def add_task(
    name: str,
    quote: str,
    due_date: Optional[str] = None,
    priority: str = "normal",
    effort_estimate: Optional[str] = None,
    parent_task_id: Optional[int] = None,
) -> str:
    """Create a new actionable task in the Structural View.

    Use this when the user needs to get something done (e.g., "Remind me to buy milk", "I need to file taxes by March").

    Args:
        name: Short, scan-friendly name for the task (e.g., "Buy milk").
        quote: The EXACT, verbatim quote from the user that triggered this task.
        due_date: Optional. ISO format date if there is a real deadline.
        priority: Optional. Priority of the task: 'low', 'normal', 'high', 'critical'. Defaults to 'normal'.
        effort_estimate: Optional. Estimated effort: 'quick', 'small', 'medium', 'large'.
        parent_task_id: Optional. The ID of the parent task, if this is a subtask of a project.
    """
    result = db.add_actionable_task(
        name, quote, due_date, priority, effort_estimate, parent_task_id
    )
    return _json(result)


@mcp.tool()
def update_task(
    task_id: int,
    status: Optional[str] = None,
    metadata: Optional[str] = None,
    reason: Optional[str] = None,
) -> str:
    """Update a task's status, metadata, or both.

    Use this when the user completes a task, cancels it, or wants to add notes/tags.

    Args:
        task_id: The ID of the task to update.
        status: Optional. New status: 'active', 'completed', 'discarded'.
        metadata: Optional. JSON string of metadata to merge (e.g., '{"location": "supermarket"}').
        reason: Optional. Explanation for why the update was made.
    """
    metadata_dict = None
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
            if not isinstance(metadata_dict, dict):
                return _json(
                    {"error": "metadata must be a valid JSON object (dictionary)."}
                )
        except json.JSONDecodeError:
            return _json({"error": "Failed to parse metadata. Must be valid JSON."})

    result = db.update_task(task_id, status, metadata_dict, reason)
    return _json(result)


# ---------------------------------------------------------------------------
# Semantic Tools — Read (动态检索)
# ---------------------------------------------------------------------------


@mcp.tool()
def recall(query: Optional[str] = None, scope: str = "user", limit: int = 10) -> str:
    """Search the exobrain or surface high-priority memories.

    Use this when the user refers to past conversations, asks about previous mentions,
    or when you need context. If query is empty, automatically surfaces Top 3 high-arousal memories.

    Args:
        query: Keywords or phrases to search for. If None or empty, returns high-arousal memories.
        scope: "user" (default, search only user records) or "all" (include assistant records).
        limit: Maximum number of results to return. Defaults to 10.
    """
    if not query:
        # Surface high-arousal memories (Top 3)
        result = db.check_active_emotions()
        return _json({"active_memories": result, "mode": "emotion_surfacing"})
    else:
        # Regular search
        result = db.recall_past_mentions_of(query)
        # Filter by scope if needed
        if scope == "user" and "raw_logs_found" in result:
            result["raw_logs_found"] = [
                r
                for r in result["raw_logs_found"]
                if r.get("source_module", "mcp_agent") == "mcp_agent"
            ]
        return _json(result)


@mcp.tool()
def suggest(available_time_minutes: Optional[int] = None) -> str:
    """Get suggested tasks based on priority and available time.

    Use this when the user asks "What should I do now?" or needs task recommendations.
    This queries the actionable_tasks table (not raw_logs) and returns prioritized items.

    Args:
        available_time_minutes: Optional. How many minutes of free time the user has right now.
            Tasks requiring more time will be filtered out.
    """
    result = db.suggest_next_actions(available_time_minutes)
    return _json({"suggestions": result})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    threading.Thread(target=db.load_models, daemon=True).start()
    mcp.run()
