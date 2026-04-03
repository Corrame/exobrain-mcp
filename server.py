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
1. When the user says a fact, thought, preference, or something potentially useful to remember: Use `record_thought_or_fact(raw_thought_string, AI_summary)`.
   Always pass the EXACT user quote to `raw_thought_string`.
   
2. When the user asks you to remind them of something, or explicitly assigns a task to do: Use `add_actionable_task(task_name, raw_user_quote, due_date, priority, effort_estimate, parent_task_id)`.
   Always pass the EXACT user quote. Keep `task_name` short. Use `parent_task_id` if the task is a sub-step of a larger project.
   
3. When the user completes a task or cancels it: Use `update_task_status(task_id, new_status, reason)`. Valid statuses: 'active', 'completed', 'discarded'.

4. When you need to attach unstructured metadata or tags to a task (e.g., location, item type, URL): Use `add_task_metadata(task_id, tags_json_string)`.
   
5. When the user asks "Did I mention X?", "What was my plan for Y?": Use `recall_past_mentions_of(concept_or_keyword)`.
   
6. When the user asks "What should I do now?", "I'm bored": Use `suggest_next_actions(available_time_minutes)`.

7. MANDATORY PROTOCOL: When the user greets you or a new conversation starts, YOU MUST FIRST calling `check_active_emotions()`.
   This pulls the top 3 high-arousal memories floating in the user's subconscious. If there are heavy unresolved emotions, gently and naturally ask about them. Do not act like a robot running a script.
""",
)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Semantic Tools — Write (捕获与表达)
# ---------------------------------------------------------------------------


@mcp.tool()
async def record_thought_or_fact(
    raw_thought_string: str, ai_summary: Optional[str] = None
) -> str:
    """Record a raw thought, fact, or preference from the user into the Immutable Truth Layer.

    Use this when the user mentions:
    - A fact about themselves ("I don't like cilantro")
    - A random thought ("I might want to visit Japan next year")
    - General information you should remember for the future.

    Args:
        raw_thought_string: The EXACT, verbatim quote from the user. Do not edit it.
        ai_summary: Optional. Your short summary or interpretation of the quote.
    """
    domain, valence, arousal = None, 0.5, 0.3
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            client = anthropic.AsyncAnthropic(api_key=api_key)
            emotion_data = await emotion_engine.analyze_emotion_api(
                client=client, 
                model="claude-haiku-4-5-20251001", 
                content=raw_thought_string
            )
            domain = ",".join(emotion_data.get("domain", []))
            valence = emotion_data.get("valence", 0.5)
            arousal = emotion_data.get("arousal", 0.3)
        except Exception:
            pass

    result = db.record_thought_or_fact(
        raw_thought_string, 
        ai_summary, 
        domain=domain, 
        valence=valence, 
        arousal=arousal
    )
    return _json(result)


@mcp.tool()
def add_actionable_task(
    task_name: str,
    raw_user_quote: str,
    due_date: Optional[str] = None,
    priority: str = "normal",
    effort_estimate: Optional[str] = None,
    parent_task_id: Optional[int] = None,
) -> str:
    """Create a new actionable task in the Structural View.

    Use this when the user needs to get something done (e.g., "Remind me to buy milk", "I need to file taxes by March").

    Args:
        task_name: Short, scan-friendly name for the task (e.g., "Buy milk").
        raw_user_quote: The EXACT, verbatim quote from the user that triggered this task.
        due_date: Optional. ISO format date if there is a real deadline.
        priority: Optional. Priority of the task: 'low', 'normal', 'high', 'critical'. Defaults to 'normal'.
        effort_estimate: Optional. Estimated effort: 'quick', 'small', 'medium', 'large'.
        parent_task_id: Optional. The ID of the parent task, if this is a subtask of a project.
    """
    result = db.add_actionable_task(
        task_name, raw_user_quote, due_date, priority, effort_estimate, parent_task_id
    )
    return _json(result)


@mcp.tool()
def update_task_status(
    task_id: int, new_status: str, reason_for_change: Optional[str] = None
) -> str:
    """Update the status of an existing task.

    Use this when the user says they finished something or changed their mind about a task.

    Args:
        task_id: The ID of the task.
        new_status: Must be one of: 'active', 'completed', 'discarded'.
        reason_for_change: Optional brief explanation of why the status changed.
    """
    result = db.update_task_status(task_id, new_status, reason_for_change)
    return _json(result)


@mcp.tool()
def add_task_metadata(task_id: int, tags_json_string: str) -> str:
    """Add or update dynamic metadata tags for a specific task.

    Use this to attach unstructured data like location, context, links, or specific attributes.
    This acts as an escape hatch for fields that don't exist in the formal schema.

    Args:
        task_id: The ID of the task.
        tags_json_string: A JSON string representing a dictionary of key-value pairs to add or update (e.g., '{"location": "supermarket", "category": "shopping"}').
    """
    try:
        tags = json.loads(tags_json_string)
        if not isinstance(tags, dict):
            return _json(
                {
                    "error": "tags_json_string must represent a valid JSON object (dictionary)."
                }
            )
    except json.JSONDecodeError:
        return _json({"error": "Failed to parse tags_json_string. Must be valid JSON."})

    result = db.add_task_metadata(task_id, tags)
    return _json(result)


# ---------------------------------------------------------------------------
# Semantic Tools — Read (动态检索)
# ---------------------------------------------------------------------------


@mcp.tool()
def recall_past_mentions_of(concept_or_keyword: str) -> str:
    """Search the exobrain for past mentions of a keyword or concept.

    Use this when the user refers to past conversations, or asks if they mentioned something before.

    Args:
        concept_or_keyword: The word or short phrase to search for.
    """
    result = db.recall_past_mentions_of(concept_or_keyword)
    return _json(result)


@mcp.tool()
def suggest_next_actions(available_time_minutes: Optional[int] = None) -> str:
    """Get a list of suggested tasks for the user to work on.

    Use this when the user asks "What should I do now?" or has free time.

    Args:
        available_time_minutes: Optional. How many minutes of free time the user has right now.
    """
    result = db.suggest_next_actions(available_time_minutes)
    return _json({"suggestions": result})

@mcp.tool()
def check_active_emotions() -> str:
    """Check the user's subconscious to see what high-arousal memories are heavily weighting on their mind today.
    
    You MUST call this when the user first says hello or starts a new session.
    Use the result to empathetically guide the conversation if there are unresolved tensions or extreme joys.
    """
    result = db.check_active_emotions()
    return _json({"active_subtext": result})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    threading.Thread(target=db.load_models, daemon=True).start()
    mcp.run()
