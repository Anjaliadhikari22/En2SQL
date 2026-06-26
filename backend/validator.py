"""
SQL validation module using sqlparse.

Accepts clean academic SQL (no backticks required).
SELECT * is valid — only receives a performance optimization hint.
"""

import re
from typing import Any, Optional

import sqlparse
from sqlparse.tokens import Keyword, DML


RISKY_KEYWORDS = {"DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE"}
DESTRUCTIVE_DML = {"DELETE", "UPDATE"}


SCHEMA_OPERATIONS = {"CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE", "CREATE_USER"}


def _strip_leading_comments(sql: str) -> str:
    """Remove leading SQL comments before operation classification."""
    text = (sql or "").strip()
    while True:
        new_text = re.sub(r"^\s*--[^\n]*(?:\n|$)", "", text).strip()
        new_text = re.sub(r"^\s*/\*.*?\*/", "", new_text, flags=re.DOTALL).strip()
        if new_text == text:
            return text
        text = new_text


def classify_sql_operation(sql: str) -> str:
    """Classify the first SQL operation, ignoring leading comments and spaces."""
    text = _strip_leading_comments(sql)
    upper = text.upper()
    if not upper:
        return "UNKNOWN"
    if re.match(r"WITH\b", upper):
        return "SELECT" if re.search(r"\bSELECT\b", upper) else "UNKNOWN"
    if re.match(r"CREATE\s+USER\b", upper):
        return "CREATE_USER"
    if re.match(r"CREATE\s+TABLE\b", upper):
        return "CREATE"
    for operation in ("SELECT", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE"):
        if re.match(rf"{operation}\b", upper):
            return operation
    return "UNKNOWN"


def check_operation_permission(
    operation: str,
    role: str,
    confirmed: bool = False,
    *,
    for_execution: bool = False,
) -> dict[str, Any]:
    """Apply En2SQL's final SQL operation permission policy."""
    op = (operation or "UNKNOWN").upper()
    user_role = (role or "user").lower()

    if op == "SELECT":
        if for_execution and user_role != "admin":
            return {"allowed": False, "reason": "User accounts cannot execute SQL queries."}
        return {"allowed": True, "reason": ""}

    if op in ("INSERT", "UPDATE", "DELETE"):
        if user_role != "admin":
            return {"allowed": False, "reason": "User accounts are allowed to generate read-only SELECT queries only."}
        if for_execution and not confirmed:
            return {
                "allowed": False,
                "reason": "This query may modify database records. Please confirm before execution.",
                "confirmation_required": True,
            }
        return {"allowed": True, "reason": "Admin modification operation requires confirmation before execution."}

    if op == "CREATE":
        return {
            "allowed": False,
            "reason": "Schema creation is not available from the normal Text-to-SQL workspace.",
            "guidance": True,
        }

    if op in SCHEMA_OPERATIONS:
        return {
            "allowed": False,
            "reason": "Blocked unsafe schema operation.",
            "unsafe_schema_operation": True,
        }

    return {"allowed": False, "reason": "Unsupported or unknown SQL operation."}


def parse_sql(sql: str) -> sqlparse.sql.Statement:
    """Parse SQL into a sqlparse Statement object."""
    formatted = sqlparse.format(sql.strip(), strip_comments=True)
    statements = sqlparse.parse(formatted)
    return statements[0] if statements else sqlparse.parse("")[0]


def get_statement_type(sql: str) -> str:
    """Return the primary DML/DDL keyword."""
    classified = classify_sql_operation(sql)
    if classified != "UNKNOWN":
        return "TRANSACTION" if classified in ("BEGIN", "START") else classified

    upper = sql.strip().upper()
    if upper.startswith("WITH") and re.search(r"\bSELECT\b", upper):
        return "SELECT"

    parsed = parse_sql(sql)
    for token in parsed.tokens:
        if token.ttype is DML:
            return token.value.upper()
        if token.ttype is Keyword and token.value.upper() in (
            "DROP", "CREATE", "ALTER", "TRUNCATE", "BEGIN",
        ):
            return token.value.upper()
    if "BEGIN" in sql.upper() or "START TRANSACTION" in sql.upper():
        return "TRANSACTION"
    return "UNKNOWN"


def validate_syntax(sql: str) -> dict[str, Any]:
    """Basic syntax validation — accepts clean academic SQL without backticks."""
    errors: list[str] = []

    if not sql or not sql.strip():
        errors.append("Query is empty.")
        return {"valid": False, "errors": errors, "formatted_sql": ""}

    if sql.strip().startswith("-- Error"):
        errors.append(sql.strip())
        return {"valid": False, "errors": errors, "formatted_sql": sql}

    operation = classify_sql_operation(sql)
    upper = sql.upper()
    if operation in ("UPDATE", "DELETE") and "WHERE" not in upper:
        errors.append(f"{operation} queries must include a WHERE condition.")

    parsed = parse_sql(sql)
    if not parsed.tokens or str(parsed).strip() == "":
        errors.append("Could not parse SQL — check for unbalanced quotes or parentheses.")

    # Return original SQL as formatted_sql to preserve clean academic format
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "formatted_sql": sql.strip(),
    }


def detect_risks(sql: str) -> dict[str, Any]:
    """Flag queries that could damage data."""
    warnings: list[str] = []
    upper = sql.upper()
    stmt_type = get_statement_type(sql)

    for kw in RISKY_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            warnings.append(f"Contains risky keyword: {kw}")

    if stmt_type in DESTRUCTIVE_DML:
        warnings.append(f"{stmt_type} modifies existing data.")
        if "WHERE" not in upper:
            warnings.append(f"{stmt_type} without WHERE clause may affect ALL rows.")

    if re.search(r"DELETE\s+FROM\s+\w+\s*;", upper):
        warnings.append("DELETE without WHERE will remove every row in the table.")

    if stmt_type == "TRANSACTION" or "BEGIN" in upper or "START TRANSACTION" in upper:
        warnings.append("Transaction modifies multiple rows — ensure accounts are locked.")

    if any(kw in upper for kw in RISKY_KEYWORDS):
        risk_level = "high"
    elif stmt_type in DESTRUCTIVE_DML or stmt_type == "TRANSACTION":
        risk_level = "medium"
    elif warnings:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "is_risky": len(warnings) > 0,
        "warnings": warnings,
        "risk_level": risk_level,
    }


def suggest_optimizations(sql: str, schema: Optional[dict[str, Any]] = None) -> list[str]:
    """
    Rule-based optimization hints.

    SELECT * is valid — only suggest listing specific columns for performance.
    """
    _ = schema
    suggestions: list[str] = []
    upper = sql.upper()

    if re.search(r"SELECT\s+\*", upper):
        return [
            "For better performance, select only required columns instead of using SELECT *."
        ]

    if "SELECT" in upper and "WHERE" not in upper and "LIMIT" not in upper:
        suggestions.append("Consider adding a WHERE or LIMIT clause to avoid full table scans.")

    if "ORDER BY" in upper and "LIMIT" not in upper:
        suggestions.append("ORDER BY without LIMIT sorts the entire result set — add LIMIT if possible.")

    if not suggestions:
        suggestions.append("No obvious optimizations detected — query structure looks reasonable.")

    return suggestions


def validation_message(syntax: dict[str, Any]) -> str:
    if syntax["valid"]:
        return "Valid SQL syntax — query passed sqlparse structural checks."
    return "Invalid SQL: " + "; ".join(syntax["errors"])


def optimization_message(suggestions: list[str]) -> str:
    return " ".join(suggestions)


def warning_message(risks: dict[str, Any]) -> str:
    if not risks["warnings"]:
        return ""
    return " | ".join(risks["warnings"])


def validate_query(
    sql: str,
    schema: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Full validation pipeline for /api/generate."""
    syntax = validate_syntax(sql)
    risks = detect_risks(sql)
    optimizations = suggest_optimizations(sql, schema)

    return {
        "validation": syntax,
        "risks": risks,
        "optimizations": optimizations,
        "statement_type": get_statement_type(sql),
        "validation_message": validation_message(syntax),
        "optimization_message": optimization_message(optimizations),
        "warning_message": warning_message(risks),
        "formatted_sql": syntax.get("formatted_sql", sql),
    }
