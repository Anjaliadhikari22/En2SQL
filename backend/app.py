"""
Flask application entry point — Natural Language to SQL Generator.

Pipeline orchestration (each step in its own module):
  1. prompt_processor  — rule-based NLP intent detection
  2. query_generator   — SQL template builders
  3. validator         — sqlparse syntax + risk checks
  4. query_explainer   — plain-English explanation
  5. impact_analyzer   — tables, columns, expected output
  6. history           — persist to JSON file

Run: cd backend && python app.py
URL: http://localhost:5000
"""

import os
import re
import traceback
from typing import Any, Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from auth import (
    admin_password_login,
    clear_otp,
    create_user_if_missing,
    create_otp,
    create_token,
    get_request_user,
    normalize_email,
    normalize_role,
    send_otp_email,
    send_unauthorized_admin_alert,
    validate_role_email,
    verify_otp,
)
from auth import require_role
from config import Config
from database import execute_query, get_database_key, is_db_connected, test_connection
from history import add_entry, clear_history, get_history
from impact_analyzer import analyze_impact
from llm_service import generate_sql_with_llm, is_llm_enabled
from prompt_processor import process_prompt
from query_accuracy_guard import validate_query_accuracy
from query_explainer import generate_explanation
from query_generator import ensure_two_query_options, generate_all_queries
from schema_reader import detect_schema_pack, get_schema_details, get_table_names, load_schema, normalize_schema_pack
from security import create_limiter
from validator import check_operation_permission, classify_sql_operation, validate_query, get_statement_type

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})
limiter = create_limiter(app)


def _normalize_database_type(raw: str) -> str:
    """Accept 'mysql', 'postgresql', or 'postgres' and return canonical form."""
    db_type = (raw or Config.DEFAULT_DB_TYPE).lower()
    if db_type in ("postgres", "postgresql"):
        return "postgresql"
    if db_type == "mysql":
        return "mysql"
    raise ValueError(f"Unsupported database_type: {raw}")


def _generic_user_impact(query_type: str) -> str:
    """Return privacy-safe impact text for non-admin users."""
    if query_type in (
        "INVALID_PROMPT",
        "MULTIPLE_PROMPTS_DETECTED",
        "UNSUPPORTED_SCHEMA",
        "UNSUPPORTED_DOMAIN",
        "UNSAFE_REQUEST",
        "UNSAFE_SCHEMA_OPERATION",
        "SCHEMA_CREATION_GUIDANCE",
        "ACCESS_DENIED_OPERATION",
    ):
        return "No SQL query was generated."
    if query_type == "SELECT":
        return "This query may return matching records. Exact row counts and schema details are restricted."
    return "This query may affect database records. Execution, exact row counts, and schema details are restricted."


def _sanitize_response_for_role(response: dict, role: str) -> dict:
    """Remove admin-only metadata from user responses."""
    if role == "admin":
        return response
    sanitized = dict(response)
    query_type = sanitized.get("query_type", "SELECT")
    sanitized["affected_tables"] = []
    sanitized["affected_columns"] = []
    sanitized["expected_output"] = _generic_user_impact(query_type)
    sanitized["role_scope"] = "user"
    for option_key in ("recommended_query", "alternative_query"):
        option = sanitized.get(option_key)
        if isinstance(option, dict):
            option = dict(option)
            impact = dict(option.get("impact") or {})
            impact["summary"] = _generic_user_impact(query_type)
            impact.pop("affected_tables", None)
            impact.pop("affected_columns", None)
            option["impact"] = impact
            sanitized[option_key] = option
    for key in (
        "available_schema",
        "required_tables",
        "schema_details",
        "detected_tables",
        "exact_row_count",
        "schema_pack",
        "detected_domain",
        "database_key",
    ):
        sanitized.pop(key, None)

    if query_type in ("UNSUPPORTED_SCHEMA", "UNSUPPORTED_DOMAIN"):
        sanitized.update({
            "query_type": query_type,
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "Unsupported request.",
                "This request needs data that is not available in the current connected databases.",
                "No SQL query was generated to avoid incorrect output.",
                "Please contact the admin if this type of data needs to be added.",
            ],
            "expected_output": "No SQL query was generated.",
            "validation": "Unsupported request",
            "optimization_suggestion": "Contact the admin to add or connect the required database.",
            "suggestion": "Contact the admin to add or connect the required database.",
            "warning": "Unsupported request.",
        })
    return sanitized


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _query_option_reason(sql: str, intent: dict[str, Any], *, recommended: bool) -> list[str]:
    normalized = intent.get("normalized_text", "")
    upper = sql.upper()
    if recommended:
        if "ROW_NUMBER()" in upper:
            return [
                "ROW_NUMBER gives exactly the requested number of rows per group.",
                "It is clear and efficient for ranking within groups.",
                "It is widely used for top-N-per-group queries.",
            ]
        if "SELECT MAX(SALARY)" in upper:
            return [
                "This query finds the salary using a focused aggregate subquery.",
                "It avoids hardcoding salary values.",
                "It is simple, readable, and efficient.",
            ]
        if "JOIN DEPARTMENTS" in upper and "employee" in normalized and "department" in normalized:
            if "AVG(E2.SALARY)" in upper and "E2.DEPARTMENT_ID = E.DEPARTMENT_ID" in upper:
                return [
                    "It directly compares each employee against their own department average.",
                    "It is simple and clear.",
                    "It avoids returning employees based on the overall company average.",
                ]
            return [
                "This query directly joins employees with departments.",
                "It uses the correct foreign key relationship.",
                "It keeps first name and last name available as separate fields.",
            ]
        return [
            "This query is recommended because it is simple and efficient.",
            "It uses the most direct relationship between the required tables.",
            "It is easier to understand and maintain.",
        ]

    if "DENSE_RANK()" in upper:
        return [
            "DENSE_RANK handles ties but may return more rows than requested.",
            "It is useful when tied values should be included.",
            "It is less suitable if the user expects an exact row count per group.",
        ]
    if "WITH DEPARTMENT_AVG AS" in upper or "JOIN DEPARTMENT_AVG" in upper:
        return [
            "This query is also correct.",
            "It precomputes department averages using a CTE.",
            "It may be more readable for complex queries but is slightly longer.",
        ]
    if "CONCAT(" in upper or " || " in sql:
        return [
            "This query is also correct but combines first and last name into one column.",
            "It is less flexible if separate name fields are needed.",
            "It is useful when a single full-name column is preferred.",
        ]
    if "NOT EXISTS" in upper:
        return [
            "This query is also correct but uses an anti-subquery style.",
            "It may be less familiar than a LEFT JOIN with IS NULL.",
            "Use it when you prefer existence checks.",
        ]
    return [
        "This query is also correct but may be less preferred.",
        "It may be slightly less readable or less efficient than the recommended query.",
        "Use it when the alternative style is specifically needed.",
    ]


def _query_optimization(sql: str, *, recommended: bool) -> list[str]:
    upper = sql.upper()
    if " JOIN " in upper:
        return ["Indexes on join columns can improve performance."]
    if "ORDER BY" in upper:
        return ["Indexes on sorting and filtering columns can improve performance."]
    if not recommended:
        return ["Recommended query is preferred for clarity and performance."]
    return ["Keep relevant filter columns indexed for better performance."]


def _build_query_option_payload(
    *,
    label: str,
    title: str,
    sql: str,
    intent: dict[str, Any],
    schema: dict[str, Any],
    database_type: str,
    schema_pack: str,
    recommended: bool,
    fallback_explanation: Any = None,
) -> dict[str, Any]:
    validation = validate_query(sql, schema)
    explanation = _as_list(fallback_explanation) if recommended and fallback_explanation else generate_explanation(intent, sql, database_type)
    impact = analyze_impact(sql, intent, schema, database_type, schema_pack=schema_pack)
    return {
        "label": label,
        "title": title,
        "sql": sql,
        "why_best" if recommended else "why_less_favourable": _query_option_reason(sql, intent, recommended=recommended),
        "explanation": explanation,
        "validation": {
            "is_valid": bool(validation["validation"]["valid"]),
            "message": validation["validation_message"],
        },
        "impact": {
            "summary": impact["expected_output"],
            "affected_tables": impact["affected_tables"],
            "affected_columns": impact["affected_columns"],
        },
        "optimization": _query_optimization(sql, recommended=recommended),
        "warning": validation["warning_message"],
    }


def _safe_schema_summary(schema: dict[str, Any]) -> str:
    """Build an internal-only schema summary for the local LLM."""
    lines: list[str] = []
    for table_name, info in sorted((schema.get("tables") or {}).items()):
        columns = ", ".join(str(col) for col in info.get("columns", []))
        lines.append(f"- {table_name}: {columns}")
    relationships = schema.get("relationships") or []
    if relationships:
        lines.append("Relationships:")
        for rel in relationships:
            lines.append(f"- {rel.get('from', '')} -> {rel.get('to', '')}")
    return "\n".join(lines)


def _schema_maps(schema: dict[str, Any]) -> tuple[dict[str, set[str]], set[str]]:
    tables: dict[str, set[str]] = {}
    all_columns: set[str] = set()
    for table_name, info in (schema.get("tables") or {}).items():
        columns = {str(col).lower() for col in info.get("columns", [])}
        tables[str(table_name).lower()] = columns
        all_columns.update(columns)
    return tables, all_columns


def _strip_sql_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", " ", sql or "")


def _extract_cte_names(sql: str) -> set[str]:
    return {
        match.group(1).lower()
        for match in re.finditer(r"\b(?:WITH|,)\s+(\w+)\s+AS\s*\(", sql, re.IGNORECASE)
    }


def _extract_table_refs(sql: str) -> tuple[list[str], dict[str, str]]:
    cte_names = _extract_cte_names(sql)
    tables: list[str] = []
    aliases: dict[str, str] = {}
    stop_words = {
        "where", "on", "group", "order", "limit", "inner", "left", "right",
        "full", "join", "cross", "union", "having", "set", "values",
    }
    pattern = re.compile(
        r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql or ""):
        table = match.group(1).lower()
        alias = (match.group(2) or "").lower()
        if table not in cte_names and table not in tables:
            tables.append(table)
        if alias and alias not in stop_words:
            aliases[alias] = table
        aliases[table] = table
    return tables, aliases


def _split_select_expressions(select_clause: str) -> list[str]:
    expressions: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(select_clause):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            expressions.append(select_clause[start:index])
            start = index + 1
    expressions.append(select_clause[start:])
    return expressions


def _schema_reference_error(sql: str, schema: dict[str, Any]) -> str:
    """Return an error if SQL references tables/columns outside the schema."""
    schema_tables, all_columns = _schema_maps(schema)
    table_refs, aliases = _extract_table_refs(sql)
    cte_names = _extract_cte_names(sql)

    for table in table_refs:
        if table not in schema_tables:
            return f"Unknown table referenced by LLM SQL: {table}"

    cleaned = _strip_sql_literals(sql)
    known_aliases = set(aliases)
    derived_aliases = {
        match.group(1).lower()
        for match in re.finditer(r"\bAS\s+(\w+)\b", cleaned, re.IGNORECASE)
    }

    for qualifier, column in re.findall(r"\b(\w+)\.(\w+)\b", cleaned):
        qualifier = qualifier.lower()
        column = column.lower()
        if column == "*":
            continue
        if qualifier in cte_names:
            continue
        table = aliases.get(qualifier, qualifier)
        if table not in schema_tables:
            return f"Unknown table or alias referenced by LLM SQL: {qualifier}"
        if column not in schema_tables[table]:
            return f"Unknown column referenced by LLM SQL: {qualifier}.{column}"

    sql_keywords = {
        "select", "from", "where", "join", "inner", "left", "right", "full",
        "outer", "on", "and", "or", "as", "order", "by", "group", "having",
        "limit", "offset", "distinct", "case", "when", "then", "else", "end",
        "with", "over", "partition", "desc", "asc", "null", "is", "not", "in",
        "like", "ilike", "between", "exists", "count", "sum", "avg", "min",
        "max", "row_number", "dense_rank", "rank", "extract", "date", "lower",
        "upper", "concat", "current_date", "curdate", "rand", "random",
    }
    allowed = all_columns | known_aliases | derived_aliases | cte_names | set(schema_tables)

    for match in re.finditer(r"\bSELECT\s+(.*?)\s+FROM\b", cleaned, re.IGNORECASE | re.DOTALL):
        for expr in _split_select_expressions(match.group(1)):
            expr = re.sub(r"\bAS\s+\w+\b", " ", expr, flags=re.IGNORECASE)
            expr = re.sub(r"\b\w+\s*\(", " ", expr)
            expr = re.sub(r"\b\w+\.\w+\b", " ", expr)
            for token in re.findall(r"\b[A-Za-z_]\w*\b", expr):
                lower = token.lower()
                if lower not in sql_keywords and lower not in allowed:
                    return f"Unknown column referenced by LLM SQL: {token}"

    for token in re.findall(r"\b([A-Za-z_]\w*)\s*(?:=|<>|!=|>=|<=|>|<|\bLIKE\b|\bILIKE\b|\bIN\b)", cleaned, re.IGNORECASE):
        lower = token.lower()
        if lower not in sql_keywords and lower not in allowed:
            return f"Unknown column referenced by LLM SQL: {token}"

    return ""


def _dialect_error(sql: str, database_type: str) -> str:
    upper = (sql or "").upper()
    if database_type == "mysql":
        if " ILIKE " in upper or "::" in sql or "RANDOM()" in upper:
            return "LLM SQL used PostgreSQL-only syntax for a MySQL request."
    if database_type == "postgresql":
        if "CURDATE()" in upper or "RAND()" in upper or "`" in sql:
            return "LLM SQL used MySQL-only syntax for a PostgreSQL request."
    return ""


def _has_multiple_statements(sql: str) -> bool:
    return len([part for part in (sql or "").split(";") if part.strip()]) > 1


def _validate_llm_sql(
    sql: str,
    *,
    intent: dict[str, Any],
    schema: dict[str, Any],
    database_type: str,
    role: str,
) -> Optional[dict[str, Any]]:
    """Validate LLM SQL through En2SQL's existing operation and safety policy."""
    sql = (sql or "").strip()
    if not sql or _has_multiple_statements(sql):
        return None

    operation = classify_sql_operation(sql)
    expected = (intent.get("action") or "SELECT").upper()
    if expected in {"SELECT", "INSERT", "UPDATE", "DELETE"} and operation != expected:
        return None

    if operation in ("UPDATE", "DELETE") and "WHERE" not in sql.upper():
        return None

    permission = check_operation_permission(operation, role, confirmed=False, for_execution=False)
    if not permission["allowed"]:
        return None

    if _dialect_error(sql, database_type):
        return None

    if _schema_reference_error(sql, schema):
        return None

    validation = validate_query(sql, schema)
    if not validation["validation"]["valid"]:
        return None

    unsafe_schema = operation in {"CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE", "CREATE_USER"}
    if unsafe_schema or any(keyword in sql.upper() for keyword in ("DROP ", "ALTER ", "TRUNCATE", "GRANT ", "REVOKE ", "CREATE USER")):
        return None

    return {
        "sql": sql,
        "operation": operation,
        "validation": validation,
    }


def _build_llm_query_option_payload(
    *,
    label: str,
    title: str,
    option: dict[str, Any],
    validation: dict[str, Any],
    intent: dict[str, Any],
    schema: dict[str, Any],
    database_type: str,
    schema_pack: str,
    recommended: bool,
    no_alternative: bool = False,
) -> dict[str, Any]:
    sql = option["sql"]
    explanation = _as_list(option.get("explanation"))
    if no_alternative and "No strong alternative query is needed for this request." not in explanation:
        explanation.append("No strong alternative query is needed for this request.")
    impact = analyze_impact(sql, intent, schema, database_type, schema_pack=schema_pack)
    return {
        "label": label,
        "title": title,
        "sql": sql,
        "why_best" if recommended else "why_less_favourable": _as_list(
            option.get("why_best") if recommended else option.get("why_less_favourable")
        ),
        "explanation": explanation,
        "validation": {
            "is_valid": bool(validation["validation"]["valid"]),
            "message": validation["validation_message"],
        },
        "impact": {
            "summary": impact["expected_output"],
            "affected_tables": impact["affected_tables"],
            "affected_columns": impact["affected_columns"],
        },
        "optimization": validation["optimizations"],
        "warning": validation["warning_message"],
    }


def _try_llm_generation(
    *,
    prompt: str,
    database_type: str,
    role: str,
    schema_pack: str,
    schema: dict[str, Any],
    intent: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Return a fully-shaped LLM generation payload, or None for rule fallback."""
    if not is_llm_enabled():
        return None

    try:
        llm_result = generate_sql_with_llm(
            prompt,
            database_type,
            _safe_schema_summary(schema),
            role,
        )
    except Exception as exc:
        print(f"[En2SQL LLM] LLM generation failed safely: {exc}")
        return None

    if not llm_result or llm_result.get("unsupported"):
        return None

    recommended_raw = llm_result.get("recommended_query") or {}
    alternative_raw = llm_result.get("alternative_query") or {}
    recommended = _validate_llm_sql(
        recommended_raw.get("sql", ""),
        intent=intent,
        schema=schema,
        database_type=database_type,
        role=role,
    )
    if not recommended:
        return None

    alternative = None
    if alternative_raw:
        alternative = _validate_llm_sql(
            alternative_raw.get("sql", ""),
            intent=intent,
            schema=schema,
            database_type=database_type,
            role=role,
        )

    generated_queries = [recommended["sql"]]
    if alternative:
        generated_queries.append(alternative["sql"])

    selected_query = recommended["sql"]
    selected_validation = recommended["validation"]
    operation = recommended["operation"]
    if operation in ("INSERT", "UPDATE", "DELETE"):
        selected_validation["warning_message"] = (
            selected_validation["warning_message"] + " | " if selected_validation["warning_message"] else ""
        ) + "This query may modify database records and requires confirmation before execution."

    explanation = _as_list(recommended_raw.get("explanation"))
    no_alternative = alternative is None
    if no_alternative and "No strong alternative query is needed for this request." not in explanation:
        explanation.append("No strong alternative query is needed for this request.")

    impact = analyze_impact(selected_query, intent, schema, database_type, schema_pack=schema_pack)
    recommended_query = _build_llm_query_option_payload(
        label="Option 1",
        title="Recommended Query",
        option={**recommended_raw, "sql": recommended["sql"]},
        validation=selected_validation,
        intent=intent,
        schema=schema,
        database_type=database_type,
        schema_pack=schema_pack,
        recommended=True,
        no_alternative=no_alternative,
    )
    alternative_query = _build_llm_query_option_payload(
        label="Option 2",
        title="Alternative Query",
        option={**alternative_raw, "sql": alternative["sql"]},
        validation=alternative["validation"],
        intent=intent,
        schema=schema,
        database_type=database_type,
        schema_pack=schema_pack,
        recommended=False,
    ) if alternative else None

    return {
        "generated_queries": generated_queries,
        "selected_query": selected_query,
        "operation": operation,
        "validation_result": selected_validation,
        "explanation": explanation,
        "impact": impact,
        "recommended_query": recommended_query,
        "alternative_query": alternative_query,
    }


def _run_pipeline(prompt: str, database_type: str, role: str = "admin", schema_pack: str = "auto") -> dict:
    """
    Execute the full NL → SQL pipeline and return the API response dict.

    Steps follow the viva-friendly orchestration order:
      prompt → generate → validate → explain → impact → history
    """
    def scoped(response: dict) -> dict:
        response.setdefault("generation_source", "rule_based")
        return _sanitize_response_for_role(response, role)

    schema_decision = detect_schema_pack(prompt, schema_pack)
    if schema_decision.get("unsupported"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": normalize_schema_pack(schema_pack),
            "detected_domain": schema_decision.get("detected_domain", ""),
            "required_tables": [],
            "suggestion": "Ask an admin to add a matching schema pack for this domain.",
            "query_type": "UNSUPPORTED_DOMAIN",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request does not match any currently available schema pack.",
                "No SQL query was generated to avoid incorrect output.",
                "Ask an admin to add a matching schema pack for this domain.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because no matching local schema pack was found.",
            "validation": "Unsupported domain",
            "optimization_suggestion": "Choose a supported schema pack or add a new local schema pack.",
            "warning": "Unsupported domain.",
        })

    resolved_schema_pack = schema_decision["schema_pack"]
    schema = load_schema(database_type, resolved_schema_pack)
    known_tables = get_table_names(schema)

    # Step 1: Rule-based NLP
    intent = process_prompt(prompt, known_tables, schema)

    if intent.get("schema_creation_guidance"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "SCHEMA_CREATION_GUIDANCE",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "Schema creation is not available from the normal Text-to-SQL workspace.",
                "Admins can add new schemas by importing approved SQL schema files.",
                "This protects the database from accidental or incomplete table creation.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated for schema creation.",
            "validation": "Schema creation guidance",
            "optimization_suggestion": "Create a schema pack SQL file and import it manually through MySQL or PostgreSQL.",
            "suggestion": "Create a schema pack SQL file and import it manually through MySQL or PostgreSQL.",
            "warning": "Schema creation is blocked from this workspace.",
        })

    if intent.get("unsafe_schema_operation"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "UNSAFE_SCHEMA_OPERATION",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request attempts to change or remove database structure.",
                "For safety, En2SQL blocks destructive schema operations such as DROP, ALTER, TRUNCATE, GRANT, and REVOKE.",
                "Schema-level changes should be performed manually by an authorized database administrator.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because schema-level operations are blocked.",
            "validation": "Blocked unsafe schema operation",
            "optimization_suggestion": "Use approved schema pack SQL files for schema-level changes.",
            "warning": "Blocked unsafe schema operation.",
        })

    if role == "user" and intent.get("action") in ("INSERT", "UPDATE", "DELETE", "TRANSACTION"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "ACCESS_DENIED_OPERATION",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This operation can modify database records.",
                "User accounts are allowed to generate read-only SELECT queries only.",
                "Please contact the admin for modification operations.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because this operation is restricted to admin.",
            "validation": "Access denied",
            "optimization_suggestion": "Try a SELECT request that only reads data.",
            "warning": "Access denied.",
        })

    if intent.get("invalid_prompt"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "INVALID_PROMPT",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "Please enter a clear request in English.",
                "Example: Show all employees whose salary is greater than 50000.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because the prompt was empty or unclear.",
            "validation": "Please enter a clear request.",
            "optimization_suggestion": "Try a complete prompt such as: Show all employees whose salary is greater than 50000.",
            "warning": "Invalid prompt.",
        })

    if intent.get("unsafe_request"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "UNSAFE_REQUEST",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request may modify or remove database objects.",
                "For safety, En2SQL did not generate this query automatically.",
                "Please use a clear and safe request.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because the request may be unsafe.",
            "validation": "Unsafe request detected.",
            "optimization_suggestion": "Use a safe read-only request or a clearly supported update/delete request.",
            "warning": "Unsafe request detected.",
        })

    if intent.get("multiple_prompts_detected"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "MULTIPLE_PROMPTS_DETECTED",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "I found more than one request in your input.",
                "Please enter one SQL request at a time so the generated query is accurate.",
                "Generate the first query, then enter the next request separately.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because multiple prompts were entered together.",
            "validation": "Please enter one request at a time.",
            "optimization_suggestion": "Split your input into separate prompts and generate them one by one.",
            "warning": "Multiple prompts detected.",
        })

    if intent.get("unsupported_schema"):
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "UNSUPPORTED_SCHEMA",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request needs tables that are not available in the current database.",
                "No SQL query was generated to avoid an incorrect result.",
                "Use the available HR tables such as employees, departments, jobs, locations, countries, regions, and dependents.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No query generated because required schema is missing.",
            "validation": "Unsupported schema",
            "optimization_suggestion": "Add the required schema or use one of the available demo tables.",
            "warning": "Unsupported schema.",
        })

    llm_enabled = is_llm_enabled()
    generation_source = "llm_fallback_rule_based" if llm_enabled else "rule_based"
    llm_generation = _try_llm_generation(
        prompt=prompt,
        database_type=database_type,
        role=role,
        schema_pack=resolved_schema_pack,
        schema=schema,
        intent=intent,
    ) if llm_enabled else None

    if llm_generation:
        generation_source = "llm"
        generated_queries = llm_generation["generated_queries"]
        selected_query = llm_generation["selected_query"]
        validation_result = llm_generation["validation_result"]
        operation = llm_generation["operation"]
        explanation = llm_generation["explanation"]
        impact = llm_generation["impact"]
        recommended_query = llm_generation["recommended_query"]
        alternative_query = llm_generation["alternative_query"]
        accuracy_result = {}
    else:
        # Step 2: SQL generation (user-facing queries only)
        generated_queries = generate_all_queries(intent, schema, database_type)

        # Step 2b: Logic-level guard — catches syntactically valid but incomplete
        # SQL for common HR/interview prompts before validation and explanation.
        accuracy_result = validate_query_accuracy(
            prompt,
            generated_queries,
            intent.get("action", "SELECT"),
            database_type,
        )
        generated_queries = accuracy_result["generated_queries"]
        generated_queries = ensure_two_query_options(intent, schema, database_type, generated_queries)
        selected_query = generated_queries[0] if generated_queries else accuracy_result["selected_query"]

        # Step 3: Validation (sqlparse — preserves clean academic SQL format)
        validation_result = validate_query(selected_query, schema)
        operation = classify_sql_operation(selected_query)

    if operation in ("UPDATE", "DELETE") and "WHERE" not in selected_query.upper():
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "UNSAFE_REQUEST",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request may modify many database records.",
                "UPDATE and DELETE queries must include a specific WHERE condition.",
                "Please provide a specific condition such as employee_id to avoid modifying multiple records.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because the modification was too broad.",
            "validation": "Specific WHERE condition required",
            "optimization_suggestion": "Please provide a specific condition such as employee_id to avoid modifying multiple records.",
            "warning": "Please provide a specific condition such as employee_id to avoid modifying multiple records.",
            "generation_source": generation_source,
        })

    permission = check_operation_permission(operation, role, confirmed=False, for_execution=False)
    if not permission["allowed"]:
        if permission.get("guidance"):
            return scoped({
                "user_prompt": prompt,
                "database_type": database_type,
                "schema_pack": resolved_schema_pack,
                "detected_domain": resolved_schema_pack,
                "query_type": "SCHEMA_CREATION_GUIDANCE",
                "generated_queries": [],
                "selected_query": "",
                "explanation": [
                    "Schema creation is not available from the normal Text-to-SQL workspace.",
                    "Admins can add new schemas by importing approved SQL schema files.",
                    "This protects the database from accidental or incomplete table creation.",
                ],
                "affected_tables": [],
                "affected_columns": [],
                "expected_output": "No SQL query was generated for schema creation.",
                "validation": "Schema creation guidance",
                "optimization_suggestion": "Create a schema pack SQL file and import it manually through MySQL or PostgreSQL.",
                "suggestion": "Create a schema pack SQL file and import it manually through MySQL or PostgreSQL.",
                "warning": "Schema creation is blocked from this workspace.",
            })
        return scoped({
            "user_prompt": prompt,
            "database_type": database_type,
            "schema_pack": resolved_schema_pack,
            "detected_domain": resolved_schema_pack,
            "query_type": "UNSAFE_SCHEMA_OPERATION" if permission.get("unsafe_schema_operation") else "ACCESS_DENIED_OPERATION",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request is not allowed by the En2SQL operation policy.",
                permission.get("reason", "The operation is blocked."),
                "Please use a safe read-only request or contact the admin.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated.",
            "validation": "Operation blocked",
            "optimization_suggestion": "Use a supported SELECT request or an approved admin workflow.",
            "warning": permission.get("reason", "Operation blocked."),
            "generation_source": generation_source,
        })

    if not llm_generation:
        if accuracy_result.get("guard_applied"):
            validation_result["validation_message"] += (
                f" Query accuracy guard applied: {accuracy_result.get('guard_reason')}"
            )
        if operation in ("INSERT", "UPDATE", "DELETE"):
            validation_result["warning_message"] = (
                validation_result["warning_message"] + " | " if validation_result["warning_message"] else ""
            ) + "This query may modify database records and requires confirmation before execution."

        # Step 4: Explanation
        explanation = (
            accuracy_result.get("explanation")
            or generate_explanation(intent, selected_query, database_type)
        )

        # Step 5: Impact analysis (COUNT(*) used internally, not in generated_queries)
        impact = analyze_impact(selected_query, intent, schema, database_type, schema_pack=resolved_schema_pack)
        recommended_query = _build_query_option_payload(
            label="Option 1",
            title="Recommended Query",
            sql=generated_queries[0],
            intent=intent,
            schema=schema,
            database_type=database_type,
            schema_pack=resolved_schema_pack,
            recommended=True,
            fallback_explanation=explanation,
        ) if generated_queries else None
        alternative_query = _build_query_option_payload(
            label="Option 2",
            title="Alternative Query",
            sql=generated_queries[1],
            intent=intent,
            schema=schema,
            database_type=database_type,
            schema_pack=resolved_schema_pack,
            recommended=False,
        ) if len(generated_queries) > 1 else None

    # Step 6: Save admin generations to history. User generations are kept
    # generation-only and are not written to the admin history file.
    if role == "admin":
        try:
            add_entry(
                user_prompt=prompt,
                generated_sql=selected_query,
                database_type=database_type,
                query_type=intent.get("action", "SELECT"),
                explanation=explanation,
                expected_output=impact["expected_output"],
                affected_tables=impact["affected_tables"],
                metadata={
                    "affected_columns": impact["affected_columns"],
                    "validation": validation_result["validation_message"],
                    "warning": validation_result["warning_message"],
                    "generation_source": generation_source,
                },
            )
        except Exception as exc:
            print(f"[En2SQL history] Failed to save query history: {exc}")

    response = {
        "user_prompt": prompt,
        "database_type": database_type,
        "schema_pack": resolved_schema_pack,
        "detected_domain": resolved_schema_pack,
        "database_key": get_database_key(database_type, resolved_schema_pack),
        "dialect": database_type,
        "query_type": intent.get("action", "SELECT"),
        "generated_queries": generated_queries,
        "selected_query": selected_query,
        "recommended_query": recommended_query,
        "alternative_query": alternative_query,
        "explanation": explanation,
        "affected_tables": impact["affected_tables"],
        "affected_columns": impact["affected_columns"],
        "expected_output": impact["expected_output"],
        "validation": validation_result["validation_message"],
        "optimization_suggestion": validation_result["optimization_message"],
        "warning": validation_result["warning_message"],
        "generation_source": generation_source,
    }
    return _sanitize_response_for_role(response, role)


# ---------------------------------------------------------------------------
# Routes — Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def serve_index():
    """Serve the main HTML page."""
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/auth/send-otp", methods=["POST"])
@limiter.limit("5 per minute")
def send_otp():
    """Start OTP verification for a user/admin login attempt."""
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email", ""))
    role = normalize_role(data.get("role", ""))

    ok, message = validate_role_email(email, role)
    if not ok:
        if role == "admin":
            send_unauthorized_admin_alert(
                attempted_email=email,
                attempted_role=role,
                ip=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                user_agent=request.headers.get("User-Agent", ""),
            )
        return jsonify({"error": "Access denied", "message": message}), 403

    otp = create_otp(email, role)
    sent = send_otp_email(email, otp)
    if not sent:
        clear_otp(email, role)
        return jsonify({
            "success": False,
            "message": "Email OTP service is not configured properly. Please check SMTP settings.",
        }), 503

    return jsonify({
        "success": True,
        "message": "OTP sent successfully to your email.",
    })


@app.route("/api/auth/verify-otp", methods=["POST"])
@limiter.limit("10 per minute")
def verify_otp_route():
    """Verify an OTP and complete user login or continue admin password login."""
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email", ""))
    role = normalize_role(data.get("role", ""))
    otp = str(data.get("otp", "")).strip()

    ok, message = validate_role_email(email, role)
    if not ok:
        return jsonify({"error": "Access denied", "message": message}), 403

    verified, msg = verify_otp(email, role, otp)
    if not verified:
        return jsonify({"verified": False, "message": msg}), 400

    if role == "user":
        user = create_user_if_missing(email, "user")
        clear_otp(email, "user")
        return jsonify({
            "verified": True,
            "login_complete": True,
            "token": create_token(user),
            "role": user["role"],
            "email": user["email"],
            "name": user.get("name", ""),
            "message": "OTP verified. Login successful.",
        })

    return jsonify({
        "verified": True,
        "login_complete": False,
        "requires_admin_password": True,
        "message": "OTP verified. Please enter your admin password.",
    })


@app.route("/api/auth/admin-password-login", methods=["POST"])
@limiter.limit("5 per minute")
def admin_password_login_route():
    """Create/verify the admin password after admin OTP verification."""
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email", ""))
    password = data.get("password", "")

    ok, message, user = admin_password_login(email, password)
    if not ok or not user:
        status = 403 if "authorized" in message.lower() else 400
        return jsonify({"success": False, "message": message}), status

    return jsonify({
        "token": create_token(user),
        "role": user["role"],
        "email": user["email"],
        "name": user.get("name", ""),
        "message": "Admin login successful.",
    })


@app.route("/api/health", methods=["GET"])
def health():
    """Health check with database connectivity status."""
    db_type = request.args.get("database_type", Config.DEFAULT_DB_TYPE)
    try:
        db_type = _normalize_database_type(db_type)
    except ValueError:
        db_type = Config.DEFAULT_DB_TYPE

    schema_pack = normalize_schema_pack(request.args.get("schema_pack") or "hr")
    connection = test_connection(db_type, schema_pack)
    return jsonify({
        "status": "ok",
        "app": "Natural Language to SQL Generator",
        "database": {
            "connected": connection["connected"],
            "db_type": connection["db_type"],
            "mode": connection["mode"],
        },
    })


@app.route("/api/schema", methods=["GET"])
@limiter.limit("10 per minute")
@require_role("admin")
def schema():
    """
    Return HR schema details for:
    regions, countries, locations, jobs, departments, employees, dependents.
    """
    try:
        db_type = _normalize_database_type(request.args.get("database_type") or Config.DEFAULT_DB_TYPE)
        details = get_schema_details(request.args.get("schema_pack") or "hr", db_type=db_type)
        return jsonify(details)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/generate", methods=["POST"])
@limiter.limit("20 per minute")
@require_role("admin", "user")
def generate():
    """
    Core endpoint: natural language → SQL + full analysis.

    Request JSON:
        {
            "prompt": "Show all employees whose salary is greater than 50000",
            "database_type": "mysql"
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        schema_pack = data.get("schema_pack") or "auto"

        try:
            database_type = _normalize_database_type(
                data.get("database_type") or data.get("db_type")
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        user = get_request_user() or {}
        response = _run_pipeline(prompt, database_type, role=user.get("role", "user"), schema_pack=schema_pack)
        return jsonify(response)

    except Exception as exc:
        if Config.DEBUG:
            traceback.print_exc()
        return jsonify({"error": f"Generation failed: {exc}"}), 500


@app.route("/api/execute", methods=["POST"])
@limiter.limit("10 per minute")
@require_role("admin")
def execute():
    """
    Execute a validated SQL query against the database (or demo mode).

    Request JSON:
        {
            "query": "SELECT ...",
            "database_type": "mysql"
        }

    Response JSON:
        {
            "status": "success" | "error",
            "columns": [],
            "rows": [],
            "message": ""
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or data.get("sql") or "").strip()
        confirmed = bool(data.get("confirmed"))

        if not query:
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": "Field 'query' is required and cannot be empty.",
            }), 400

        try:
            database_type = _normalize_database_type(
                data.get("database_type") or data.get("db_type")
            )
        except ValueError as exc:
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": str(exc),
            }), 400

        operation = classify_sql_operation(query)
        permission = check_operation_permission(operation, "admin", confirmed=confirmed, for_execution=True)
        if not permission["allowed"]:
            if permission.get("confirmation_required"):
                return jsonify({
                    "error": "Confirmation required",
                    "message": "This query may modify database records. Please confirm before execution.",
                }), 400
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": permission.get("reason", "Operation blocked."),
            }), 403

        if operation in ("UPDATE", "DELETE") and "WHERE" not in query.upper():
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": "UPDATE and DELETE queries must include a WHERE condition.",
            }), 400

        # Validate before execution
        validation = validate_query(query)
        if not validation["validation"]["valid"]:
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": validation["validation_message"],
            }), 400

        is_read = get_statement_type(query) in ("SELECT", "UNKNOWN")
        schema_pack = normalize_schema_pack(data.get("schema_pack") or data.get("detected_domain") or "hr")
        result = execute_query(database_type, query, fetch=is_read, schema_pack=schema_pack)

        if result["success"]:
            mode_note = ""
            if result.get("mode") == "demo":
                mode_note = " (demo mode — no live database connected)"
            msg = result.get("message") or (
                f"Query executed successfully{mode_note}. "
                f"{result['row_count']} row(s) affected/returned."
            )
            return jsonify({
                "status": "success",
                "columns": result["columns"],
                "rows": result["rows"],
                "message": msg,
                "schema_pack": schema_pack,
                "database_key": result.get("database_key") or get_database_key(database_type, schema_pack),
            })

        return jsonify({
            "status": "error",
            "columns": [],
            "rows": [],
            "message": result.get("error", "Query execution failed."),
        }), 500

    except Exception as exc:
        if Config.DEBUG:
            traceback.print_exc()
        return jsonify({
            "status": "error",
            "columns": [],
            "rows": [],
            "message": f"Execution failed: {exc}",
        }), 500


@app.route("/api/history", methods=["GET"])
@limiter.limit("10 per minute")
@require_role("admin")
def history_list():
    """
    Return all previous prompts with generated SQL, explanation,
    expected output, database type, and timestamp.
    """
    try:
        limit = request.args.get("limit", 100, type=int)
        entries = get_history(limit=limit)
        return jsonify({"history": entries, "count": len(entries)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["DELETE"])
@limiter.limit("10 per minute")
@require_role("admin")
def history_clear():
    """Clear all stored history entries."""
    clear_history()
    return jsonify({"success": True, "message": "History cleared."})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(os.path.dirname(Config.HISTORY_FILE), exist_ok=True)
    demo_mode = not is_db_connected("mysql", "hr") and not is_db_connected("postgresql", "hr")
    print("=" * 60)
    print("  Natural Language to SQL Generator")
    print(f"  Running at: http://localhost:5000")
    print(f"  Database mode: {'DEMO (no live DB)' if demo_mode else 'LIVE'}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
