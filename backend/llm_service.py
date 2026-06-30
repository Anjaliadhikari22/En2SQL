"""Optional local LLM service for En2SQL.

This module is intentionally standalone. It is not wired into /api/generate yet,
so the existing rule-based pipeline keeps its current runtime behavior.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    import requests
except Exception:  # pragma: no cover - dependency may be absent before install
    requests = None

from config import Config


def is_llm_enabled() -> bool:
    """Return True only when LLM_ENABLED is explicitly true."""
    configured = getattr(Config, "LLM_ENABLED", False)
    raw = os.getenv("LLM_ENABLED")
    if raw is not None:
        return raw.strip().lower() == "true"
    return bool(configured)


def build_llm_prompt(user_prompt: str, dialect: str, schema_summary: str, role: str) -> str:
    """Build a safe local-LLM prompt without secrets, rows, or execution data."""
    dialect_name = "PostgreSQL" if (dialect or "").lower() in {"postgres", "postgresql"} else "MySQL"
    role_name = "admin" if (role or "").lower() == "admin" else "user"

    return f"""
You are a local Text-to-SQL assistant for En2SQL.

Use only the information below.

User prompt:
{user_prompt or ""}

Selected SQL dialect:
{dialect_name}

User role:
{role_name}

Safe schema summary:
{schema_summary or "No schema summary provided."}

Strict SQL generation rules:
- Generate SQL only using the provided schema summary.
- Do not invent tables.
- Do not invent columns.
- Use the selected dialect: MySQL or PostgreSQL.
- Return two options when possible:
  Option 1: Recommended Query
  Option 2: Alternative Query
- Include why Option 1 is best.
- Include why Option 2 is less favourable.
- Keep explanations simple and bullet-point based.
- Do not generate DROP, ALTER, TRUNCATE, GRANT, REVOKE, or CREATE USER.
- Do not generate CREATE TABLE from the normal workspace.
- Do not generate UPDATE or DELETE without a WHERE clause.
- If the request cannot be answered using the schema, return UNSUPPORTED_REQUEST.
- Return JSON only.

Expected JSON format:
{{
  "recommended_query": {{
    "sql": "...",
    "why_best": ["..."],
    "explanation": ["..."]
  }},
  "alternative_query": {{
    "sql": "...",
    "why_less_favourable": ["..."],
    "explanation": ["..."]
  }}
}}

If only one strong query exists, return only recommended_query and include this
explanation item: "No strong alternative query is needed for this request."
""".strip()


def generate_sql_with_llm(
    user_prompt: str,
    dialect: str,
    schema_summary: str,
    role: str,
) -> Optional[dict[str, Any]]:
    """Call local Ollama and return parsed SQL options, or None on any failure."""
    if not is_llm_enabled():
        return None

    provider = (getattr(Config, "LLM_PROVIDER", "") or "").strip().lower()
    if provider != "local_llama":
        return None
    if requests is None:
        print("[En2SQL LLM] requests is not installed; skipping local LLM call.")
        return None

    prompt = build_llm_prompt(user_prompt, dialect, schema_summary, role)
    url = f"{str(Config.LOCAL_LLM_URL).rstrip('/')}/api/generate"
    payload = {
        "model": Config.LOCAL_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=getattr(Config, "LLM_TIMEOUT_SECONDS", 30),
        )
        response.raise_for_status()
        data = response.json()
        return parse_llm_sql_response(str(data.get("response", "")))
    except Exception as exc:
        print(f"[En2SQL LLM] Local LLM unavailable or returned an error: {exc}")
        return None


def parse_llm_sql_response(response_text: str) -> Optional[dict[str, Any]]:
    """Parse the local LLM JSON response without validating SQL content."""
    text = (response_text or "").strip()
    if not text:
        return None

    if "UNSUPPORTED_REQUEST" in text:
        return {
            "unsupported": True,
            "message": "UNSUPPORTED_REQUEST",
        }

    payload = _parse_json_object(text)
    if not isinstance(payload, dict):
        return None

    recommended = _normalize_query_option(payload.get("recommended_query"))
    alternative = _normalize_query_option(payload.get("alternative_query"))

    if not recommended:
        return None

    normalized: dict[str, Any] = {
        "recommended_query": recommended,
    }
    if alternative:
        normalized["alternative_query"] = alternative
    return normalized


def _parse_json_object(text: str) -> Optional[dict[str, Any]]:
    """Parse JSON, extracting the first balanced object if needed."""
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    extracted = _extract_first_json_object(text)
    if not extracted:
        return None
    try:
        data = json.loads(extracted)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_first_json_object(text: str) -> str:
    """Return the first balanced JSON object substring, respecting strings."""
    start = text.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return ""


def _normalize_query_option(value: Any) -> Optional[dict[str, Any]]:
    """Keep the expected option fields while tolerating missing list values."""
    if not isinstance(value, dict):
        return None

    sql = str(value.get("sql") or "").strip()
    if not sql:
        return None

    option = {
        "sql": sql,
        "explanation": _as_text_list(value.get("explanation")),
    }
    if "why_best" in value:
        option["why_best"] = _as_text_list(value.get("why_best"))
    if "why_less_favourable" in value:
        option["why_less_favourable"] = _as_text_list(value.get("why_less_favourable"))
    return option


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []
