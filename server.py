import json
from mcp.server.fastmcp import FastMCP
import db
from typing import Optional

# ---------------------------------------------------------------------------
# Server Configuration (Personal AI Cognitive Exobrain)
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "exobrain-memory-server",
    instructions="""You are connected to the user's Personal AI Cognitive Exobrain.
This is a dual-track system:
Track 1: The Immutable Truth (Everything the user says is recorded here unedited).
Track 2: The Structural View (Tasks and actions derived from Track 1).

You MUST use the provided semantic tools to interact with this exobrain. Do NOT ask the user for permission, just use the tools.

POLICY:
1. When the user says a fact, thought, preference, or something potentially useful to remember: Use `record_thought_or_fact(raw_thought_string, AI_summary)`.
   Always pass the EXACT user quote to `raw_thought_string`.
   
2. When the user asks you to remind them of something, or explicitly assigns a task to do: Use `add_actionable_task(task_name, raw_user_quote, due_date, urgency)`.
   Always pass the EXACT user quote. Keep `task_name` short.
   
3. When the user completes a task or cancels it: Use `update_task_status(task_id, new_status, reason)`. Valid statuses: 'active', 'completed', 'discarded'.
   
4. When the user asks "Did I mention X?", "What was my plan for Y?": Use `recall_past_mentions_of(concept_or_keyword)`.
   
5. When the user asks "What should I do now?", "I'm bored": Use `suggest_next_actions(available_time_minutes)`.
""",
)

def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)

# ---------------------------------------------------------------------------
# Semantic Tools — Write (捕获与表达)
# ---------------------------------------------------------------------------

@mcp.tool()
def record_thought_or_fact(raw_thought_string: str, ai_summary: Optional[str] = None) -> str:
    """Record a raw thought, fact, or preference from the user into the Immutable Truth Layer.
    
    Use this when the user mentions:
    - A fact about themselves ("I don't like cilantro")
    - A random thought ("I might want to visit Japan next year")
    - General information you should remember for the future.

    Args:
        raw_thought_string: The EXACT, verbatim quote from the user. Do not edit it.
        ai_summary: Optional. Your short summary or interpretation of the quote.
    """
    result = db.record_thought_or_fact(raw_thought_string, ai_summary)
    return _json(result)

@mcp.tool()
def add_actionable_task(
    task_name: str, 
    raw_user_quote: str, 
    due_date: Optional[str] = None, 
    urgency_level: Optional[str] = None
) -> str:
    """Create a new actionable task in the Structural View.
    
    Use this when the user needs to get something done (e.g., "Remind me to buy milk", "I need to file taxes by March").

    Args:
        task_name: Short, scan-friendly name for the task (e.g., "Buy milk").
        raw_user_quote: The EXACT, verbatim quote from the user that triggered this task.
        due_date: Optional. ISO format date if there is a real deadline.
        urgency_level: Optional. Must be one of: 'quick', 'small', 'medium', 'large'.
    """
    result = db.add_actionable_task(task_name, raw_user_quote, due_date, urgency_level)
    return _json(result)

@mcp.tool()
def update_task_status(task_id: int, new_status: str, reason_for_change: Optional[str] = None) -> str:
    """Update the status of an existing task.
    
    Use this when the user says they finished something or changed their mind about a task.

    Args:
        task_id: The ID of the task.
        new_status: Must be one of: 'active', 'completed', 'discarded'.
        reason_for_change: Optional brief explanation of why the status changed.
    """
    result = db.update_task_status(task_id, new_status, reason_for_change)
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

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    mcp.run()
