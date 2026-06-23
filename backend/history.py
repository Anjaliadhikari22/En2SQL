"""
Query history persistence.

Stores and retrieves past NL-to-SQL conversions in a local JSON file.
Each entry includes prompt, SQL, explanation, expected output, and timestamp.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from config import Config


def _ensure_history_file() -> None:
    """Create the history file and parent directory if they do not exist."""
    history_path = Config.HISTORY_FILE
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    if not os.path.exists(history_path):
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)


def _load_history() -> list[dict[str, Any]]:
    """Load all history entries from disk."""
    _ensure_history_file()
    with open(Config.HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_history(entries: list[dict[str, Any]]) -> None:
    """Persist the full history list to disk."""
    _ensure_history_file()
    with open(Config.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, default=str)


def add_entry(
    user_prompt: str,
    generated_sql: str,
    database_type: str,
    query_type: str = "SELECT",
    explanation: str = "",
    expected_output: str = "",
    affected_tables: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Append a new query record to history.

    Returns the newly created entry including id and timestamp.
    """
    entry: dict[str, Any] = {
        "id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_prompt": user_prompt,
        "generated_sql": generated_sql,
        "database_type": database_type,
        "query_type": query_type,
        "explanation": explanation,
        "expected_output": expected_output,
        "affected_tables": affected_tables or [],
        "metadata": metadata or {},
    }

    history = _load_history()
    history.insert(0, entry)
    _save_history(history)
    return entry


def get_history(limit: int = 100) -> list[dict[str, Any]]:
    """
    Return history entries formatted for GET /api/history.

    Each entry contains: user_prompt, generated_sql, explanation,
    expected_output, database_type, timestamp, and query_type.
    """
    history = _load_history()
    result = []
    for entry in history[:limit]:
        result.append({
            "id": entry.get("id"),
            "timestamp": entry.get("timestamp"),
            "user_prompt": entry.get("user_prompt") or entry.get("natural_language", ""),
            "generated_sql": entry.get("generated_sql") or entry.get("sql", ""),
            "database_type": entry.get("database_type") or entry.get("db_type", ""),
            "query_type": entry.get("query_type", "SELECT"),
            "explanation": entry.get("explanation", ""),
            "expected_output": entry.get("expected_output", ""),
            "affected_tables": entry.get("affected_tables", []),
        })
    return result


def get_entry_by_id(entry_id: str) -> Optional[dict[str, Any]]:
    """Look up a single history entry by UUID."""
    for entry in _load_history():
        if entry.get("id") == entry_id:
            return entry
    return None


def clear_history() -> None:
    """Remove all history entries."""
    _save_history([])
