"""
Human-readable explanation generator for SQL queries.

Combines intent analysis and SQL clause breakdown into a single string
suitable for the /api/generate response and viva demonstrations.
"""

from typing import Any


def explain_intent(intent: dict[str, Any]) -> str:
    """Explain what the NLP module understood from the user's sentence."""
    action = intent.get("action", "SELECT")
    tables = intent.get("tables") or ["an unspecified table"]
    parts = [
        f"Interpreted as a {action} operation on {', '.join(tables)}.",
    ]

    if intent.get("columns"):
        parts.append(f"Columns referenced: {', '.join(intent['columns'])}.")

    if intent.get("aggregates"):
        parts.append(f"Aggregate: {', '.join(intent['aggregates'])}.")

    if intent.get("conditions"):
        cond_desc = [
            f"{c['column']} {c['operator']} {c['value']}"
            for c in intent["conditions"]
        ]
        parts.append(f"Filters: {' AND '.join(cond_desc)}.")

    if intent.get("set_values"):
        set_desc = [
            f"{s['column']} = {s['value']}" for s in intent["set_values"]
        ]
        parts.append(f"Values to set: {', '.join(set_desc)}.")

    if intent.get("transfer"):
        t = intent["transfer"]
        if t.get("amount"):
            parts.append(
                f"Transfer amount: {t['amount']} from {t.get('from_account', '?')} "
                f"to {t.get('to_account', '?')}."
            )

    if intent.get("order_by"):
        parts.append(f"Ordered by: {intent['order_by']}.")

    if intent.get("limit"):
        parts.append(f"Limited to {intent['limit']} rows.")

    return " ".join(parts)


def explain_sql(sql: str, db_type: str) -> str:
    """Provide a clause-by-clause breakdown of the generated SQL."""
    parts: list[str] = []
    upper = sql.upper().strip()

    if upper.startswith("SELECT"):
        parts.append("Read-only SELECT — retrieves data without changes.")
    elif upper.startswith("INSERT"):
        parts.append("INSERT — adds new records.")
    elif upper.startswith("UPDATE"):
        parts.append("UPDATE — modifies existing records.")
    elif upper.startswith("DELETE"):
        parts.append("DELETE — removes records permanently.")
    elif "BEGIN" in upper or "START TRANSACTION" in upper:
        parts.append("TRANSACTION — groups multiple statements atomically.")

    if "WHERE" in upper:
        parts.append("WHERE filters rows by condition.")
    if "ORDER BY" in upper:
        parts.append("ORDER BY sorts results.")
    if "LIMIT" in upper:
        parts.append("LIMIT caps the result size.")
    if "JOIN" in upper:
        parts.append("JOIN combines data from multiple tables.")

    parts.append(f"Generated for {db_type.upper()} dialect.")
    return " ".join(parts)


def explain_dialect_feature(intent: dict[str, Any], db_type: str) -> str:
    """Explain SQL syntax that intentionally differs by database dialect."""
    feature = intent.get("dialect_feature") or {}
    feature_type = feature.get("type")
    database = "PostgreSQL" if (db_type or "").lower() in ("postgres", "postgresql") else "MySQL"

    if intent.get("action") == "TRANSACTION":
        if database == "PostgreSQL":
            return "Generated for PostgreSQL using BEGIN to start the transaction."
        return "Generated for MySQL using START TRANSACTION to start the transaction."

    if feature_type == "NAME_CONTAINS":
        if database == "PostgreSQL":
            return "Generated for PostgreSQL using ILIKE for case-insensitive name matching."
        return "Generated for MySQL using LOWER(first_name) LIKE LOWER(...) for case-insensitive name matching."

    if feature_type == "EMPLOYEES_HIRED_TODAY":
        if database == "PostgreSQL":
            return "Generated for PostgreSQL using hire_date::date = CURRENT_DATE."
        return "Generated for MySQL using DATE(hire_date) = CURDATE()."

    if feature_type == "RANDOM_ROWS":
        if database == "PostgreSQL":
            return "Generated for PostgreSQL using RANDOM() to order rows randomly."
        return "Generated for MySQL using RAND() to order rows randomly."

    return ""


def generate_explanation(
    intent: dict[str, Any],
    sql: str,
    db_type: str,
) -> str:
    """
    Main entry point: single explanation string for the API response.

    Combines intent interpretation and SQL clause analysis.
    """
    if intent.get("grouped_ranking"):
        limit = (intent.get("grouped_ranking") or {}).get("limit") or intent.get("limit") or 1
        return (
            "This query ranks employees inside each department by salary and returns "
            f"the top {limit} highest-paid employees from every department. "
            f"Option 1 uses ROW_NUMBER and returns exactly top {limit} employees per department. "
            "Option 2 uses DENSE_RANK and handles salary ties. "
            "Option 3 uses a correlated subquery and can work as an alternative ranking approach."
        )

    dialect_explanation = explain_dialect_feature(intent, db_type)
    if dialect_explanation:
        intent_part = explain_intent(intent)
        sql_part = explain_sql(sql, db_type)
        return f"{intent_part} {sql_part} {dialect_explanation}"

    intent_part = explain_intent(intent)
    sql_part = explain_sql(sql, db_type)
    return f"{intent_part} {sql_part}"
