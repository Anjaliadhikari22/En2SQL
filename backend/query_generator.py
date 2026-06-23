"""
SQL query generator using rule-based templates.

Produces clean academic SQL (no backticks, PascalCase identifiers).
Internal COUNT(*) for impact analysis is separate from user-facing COUNT prompts.
"""

import re
from typing import Any, Optional


COLUMN_NAME_MAP: dict[str, str] = {
    "salary": "salary",
    "name": "first_name",
    "firstname": "first_name",
    "first_name": "first_name",
    "lastname": "last_name",
    "last_name": "last_name",
    "employeeid": "employee_id",
    "employee_id": "employee_id",
    "departmentid": "department_id",
    "department_id": "department_id",
    "department": "department_name",
    "departmentname": "department_name",
    "department_name": "department_name",
    "jobid": "job_id",
    "job_id": "job_id",
    "jobtitle": "job_title",
    "job_title": "job_title",
    "hiredate": "hire_date",
    "hire_date": "hire_date",
    "city": "city",
}

COLUMN_TABLE_HINTS: dict[str, str] = {
    "salary": "employees",
    "first_name": "employees",
    "last_name": "employees",
    "employee_id": "employees",
    "hire_date": "employees",
    "department_id": "employees",
    "department_name": "departments",
    "job_title": "jobs",
    "city": "locations",
}


def normalize_column(name: str) -> str:
    """Map a natural-language column token to HR schema column name."""
    key = name.lower().replace(" ", "")
    return COLUMN_NAME_MAP.get(key, name.lower() if name else name)


def _format_value(val: str) -> str:
    if val.replace(".", "", 1).isdigit():
        return val
    return f"'{val}'"


def _quote_string(val: str) -> str:
    return "'" + str(val).replace("'", "''") + "'"


def _is_mysql(db_type: str) -> bool:
    return (db_type or "mysql").lower() == "mysql"


def _is_postgresql(db_type: str) -> bool:
    return (db_type or "mysql").lower() in ("postgres", "postgresql")


def resolve_target_table(intent: dict[str, Any], schema: dict[str, Any]) -> Optional[str]:
    tables = intent.get("tables", [])
    action = intent.get("action", "SELECT")

    if action in ("UPDATE", "DELETE", "INSERT"):
        for col in intent.get("columns", []):
            if col in COLUMN_TABLE_HINTS:
                return COLUMN_TABLE_HINTS[col]
        for cond in intent.get("conditions", []):
            col = normalize_column(cond.get("column", ""))
            if col in COLUMN_TABLE_HINTS:
                return COLUMN_TABLE_HINTS[col]
        for sv in intent.get("set_values", []):
            col = normalize_column(sv.get("column", ""))
            if col in COLUMN_TABLE_HINTS:
                return COLUMN_TABLE_HINTS[col]

    if tables:
        if action in ("UPDATE", "DELETE") and len(tables) > 1:
            for preferred in ("employees", "departments", "jobs"):
                for t in tables:
                    if t.lower() == preferred.lower():
                        return t
        return tables[0]

    schema_tables = list(schema.get("tables", {}).keys())
    return schema_tables[0] if schema_tables else None


def _build_where_clause(conditions: list[dict[str, str]], table: str = "") -> str:
    if not conditions:
        return ""

    parts = []
    for cond in conditions:
        col = normalize_column(cond["column"])
        op = cond["operator"]
        val = _format_value(cond["value"])

        if cond["column"] == "department_name":
            dept = cond["value"].strip("'")
            parts.append(
                "department_id IN (\n"
                "    SELECT department_id\n"
                "    FROM departments\n"
                f"    WHERE department_name = '{dept}'\n"
                ")"
            )
        else:
            parts.append(f"{col} {op} {val}")

    return "WHERE " + " AND ".join(parts)


def _wants_specific_columns(intent: dict[str, Any]) -> bool:
    normalized = intent.get("normalized_text", "")
    if re.search(r"\b(all|every)\b", normalized):
        return False
    if intent.get("limit"):
        return False
    if "COUNT" in intent.get("aggregates", []):
        return False
    if _wants_join(intent) or _wants_left_join(intent):
        return True

    explicit = intent.get("columns", [])
    condition_cols = {
        normalize_column(c["column"])
        for c in intent.get("conditions", [])
        if c.get("column") != "department_name"
    }
    extra = [c for c in explicit if c not in condition_cols]
    return len(extra) > 0


def _wants_join(intent: dict[str, Any]) -> bool:
    if _wants_left_join(intent):
        return False
    if "COUNT" in intent.get("aggregates", []):
        return False
    normalized = intent.get("normalized_text", "")
    return bool(
        "employee" in normalized
        and "department" in normalized
        and re.search(r"\bwith\b", normalized)
    )


def _wants_left_join(intent: dict[str, Any]) -> bool:
    normalized = intent.get("normalized_text", "")
    return bool(
        re.search(r"\bleft\s+join\b", normalized)
        or re.search(r"\beven\s+if\b", normalized)
        or (
            "department" in normalized
            and re.search(r"\b(all|every)\b", normalized)
            and "employee" in normalized
            and "no employee" in normalized
        )
        or "display all departments" in normalized
    )


def _select_clause(intent: dict[str, Any]) -> str:
    aggregates = intent.get("aggregates", [])
    if "COUNT" in aggregates:
        return "COUNT(*)"

    if _wants_specific_columns(intent) and not _wants_join(intent) and not _wants_left_join(intent):
        cols = intent.get("columns") or ["first_name"]
        return ", ".join(normalize_column(c) for c in cols)

    return "*"


def build_select_query(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    special = _build_hr_special_select(intent, db_type)
    if special:
        return special

    if intent.get("grouped_ranking"):
        return _build_employee_department_rank_query(intent)
    if intent.get("dialect_feature"):
        feature_type = intent["dialect_feature"].get("type")
        if feature_type == "NAME_CONTAINS":
            return _build_name_contains_query(intent, db_type)
        if feature_type == "EMPLOYEES_HIRED_TODAY":
            return _build_employees_hired_today_query(db_type)
        if feature_type == "RANDOM_ROWS":
            return _build_random_employees_query(intent, db_type)
    if _wants_left_join(intent):
        return _build_left_join_select(intent)
    if _wants_join(intent):
        return _build_inner_join_select(intent)

    table = resolve_target_table(intent, schema)
    if not table:
        return "-- Error: no table identified in prompt or schema"

    parts = [f"SELECT {_select_clause(intent)}", f"FROM {table}"]

    conditions = intent.get("conditions", [])
    if conditions:
        parts.append(_build_where_clause(conditions, table))

    order_by = intent.get("order_by")
    if order_by:
        col, _, direction = order_by.partition(" ")
        parts.append(f"ORDER BY {normalize_column(col)} {direction.upper()}")

    if intent.get("limit"):
        parts.append(f"LIMIT {intent['limit']}")

    return "\n".join(parts) + ";"


def _build_hr_special_select(intent: dict[str, Any], db_type: str) -> Optional[str]:
    normalized = intent.get("normalized_text", "")

    if re.search(r"\bemployees?\b", normalized) and re.search(r"\bjob\s+titles?\b", normalized):
        return (
            "SELECT\n"
            "    e.employee_id,\n"
            "    e.first_name,\n"
            "    e.last_name,\n"
            "    j.job_title,\n"
            "    e.salary\n"
            "FROM employees e\n"
            "INNER JOIN jobs j\n"
            "ON e.job_id = j.job_id;"
        )

    if re.search(r"\bdepartments?\b", normalized) and re.search(r"\bcity\b|\bcities\b", normalized):
        return (
            "SELECT\n"
            "    d.department_name,\n"
            "    l.city\n"
            "FROM departments d\n"
            "INNER JOIN locations l\n"
            "ON d.location_id = l.location_id;"
        )

    if re.search(r"\bemployees?\b", normalized) and re.search(r"\bhired\s+after\s+(\d{4})\b", normalized):
        year = re.search(r"\bhired\s+after\s+(\d{4})\b", normalized).group(1)
        return (
            "SELECT *\n"
            "FROM employees\n"
            f"WHERE hire_date > '{year}-12-31';"
        )

    if re.search(r"\bcount\b", normalized) and re.search(r"\bemployees?\b", normalized) and re.search(r"\beach\s+departments?\b|\bper\s+departments?\b|\bin\s+each\s+departments?\b", normalized):
        return (
            "SELECT\n"
            "    d.department_name,\n"
            "    COUNT(e.employee_id) AS employee_count\n"
            "FROM departments d\n"
            "LEFT JOIN employees e\n"
            "ON d.department_id = e.department_id\n"
            "GROUP BY d.department_name\n"
            "ORDER BY employee_count DESC;"
        )

    return None


def _build_name_contains_query(intent: dict[str, Any], db_type: str) -> str:
    feature = intent.get("dialect_feature") or {}
    term = _quote_string(f"%{feature.get('value', '')}%")
    if _is_postgresql(db_type):
        condition = f"first_name ILIKE {term}"
    else:
        condition = f"LOWER(first_name) LIKE LOWER({term})"
    return "\n".join([
        "SELECT *",
        "FROM employees",
        f"WHERE {condition};",
    ])


def _build_employees_hired_today_query(db_type: str) -> str:
    condition = "hire_date::date = CURRENT_DATE" if _is_postgresql(db_type) else "DATE(hire_date) = CURDATE()"
    return "\n".join([
        "SELECT *",
        "FROM employees",
        f"WHERE {condition};",
    ])


def _build_random_employees_query(intent: dict[str, Any], db_type: str) -> str:
    feature = intent.get("dialect_feature") or {}
    limit = feature.get("limit") or intent.get("limit") or 1
    random_function = "RANDOM()" if _is_postgresql(db_type) else "RAND()"
    return "\n".join([
        "SELECT *",
        "FROM employees",
        f"ORDER BY {random_function}",
        f"LIMIT {limit};",
    ])


def _grouped_rank_limit(intent: dict[str, Any]) -> int:
    grouped_ranking = intent.get("grouped_ranking") or {}
    return grouped_ranking.get("limit") or intent.get("limit") or 1


def _build_employee_department_rank_query(intent: dict[str, Any]) -> str:
    return _build_employee_department_window_rank_query(intent, "ROW_NUMBER")


def _build_employee_department_window_rank_query(intent: dict[str, Any], rank_function: str) -> str:
    limit = _grouped_rank_limit(intent)
    rank_function = rank_function.upper()
    return (
        "WITH ranked_employees AS (\n"
        "    SELECT\n"
        "        e.employee_id,\n"
        "        e.first_name,\n"
        "        e.last_name,\n"
        "        e.salary,\n"
        "        e.department_id,\n"
        "        d.department_name,\n"
        f"        {rank_function}() OVER (\n"
        "            PARTITION BY e.department_id\n"
        "            ORDER BY e.salary DESC\n"
        "        ) AS salary_rank\n"
        "    FROM employees e\n"
        "    INNER JOIN departments d\n"
        "    ON e.department_id = d.department_id\n"
        ")\n"
        "SELECT\n"
        "    department_name,\n"
        "    employee_id,\n"
        "    first_name,\n"
        "    last_name,\n"
        "    salary,\n"
        "    salary_rank\n"
        "FROM ranked_employees\n"
        f"WHERE salary_rank <= {limit}\n"
        "ORDER BY department_name, salary_rank;"
    )


def _build_employee_department_correlated_rank_query(intent: dict[str, Any]) -> str:
    limit = _grouped_rank_limit(intent)
    return (
        "SELECT\n"
        "    d.department_name,\n"
        "    e.employee_id,\n"
        "    e.first_name,\n"
        "    e.last_name,\n"
        "    e.salary\n"
        "FROM employees e\n"
        "INNER JOIN departments d\n"
        "ON e.department_id = d.department_id\n"
        "WHERE (\n"
        "    SELECT COUNT(DISTINCT e2.salary)\n"
        "    FROM employees e2\n"
        "    WHERE e2.department_id = e.department_id\n"
        "    AND e2.salary > e.salary\n"
        f") < {limit}\n"
        "ORDER BY d.department_name, e.salary DESC;"
    )


def build_grouped_ranking_queries(intent: dict[str, Any]) -> list[str]:
    """Return user-facing alternatives for top-N employees within each department."""
    return [
        _build_employee_department_window_rank_query(intent, "ROW_NUMBER"),
        _build_employee_department_window_rank_query(intent, "DENSE_RANK"),
        _build_employee_department_correlated_rank_query(intent),
    ]


def _build_inner_join_select(intent: dict[str, Any]) -> str:
    parts = [
        "SELECT\n"
        "    e.first_name,\n"
        "    e.last_name,\n"
        "    d.department_name",
        "FROM employees e",
        "INNER JOIN departments d",
        "ON e.department_id = d.department_id",
    ]
    conditions = intent.get("conditions", [])
    if conditions:
        parts.append(_build_where_clause(conditions))
    return "\n".join(parts) + ";"


def _build_left_join_select(intent: dict[str, Any]) -> str:
    parts = [
        "SELECT d.department_name, e.first_name, e.last_name",
        "FROM departments d",
        "LEFT JOIN employees e",
        "ON d.department_id = e.department_id",
    ]
    conditions = intent.get("conditions", [])
    if conditions:
        parts.append(_build_where_clause(conditions))
    return "\n".join(parts) + ";"


def build_count_query(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    """Internal COUNT(*) — used by impact_analyzer only, not in generated_queries."""
    _ = db_type
    table = resolve_target_table(intent, schema)
    if not table:
        return ""

    parts = ["SELECT COUNT(*) AS RowCount", f"FROM {table}"]
    conditions = intent.get("conditions", [])
    if conditions:
        parts.append(_build_where_clause(conditions, table))
    return "\n".join(parts) + ";"


def build_insert_query(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    table = resolve_target_table(intent, schema)
    if not table:
        return "-- Error: no target table for INSERT"

    cols = intent.get("columns") or schema.get("tables", {}).get(table, {}).get("columns", [])
    insert_cols = [c for c in cols if not c.endswith("ID")][:3]
    if not insert_cols:
        return f"INSERT INTO {table} VALUES (/* values */);"

    col_list = ", ".join(insert_cols)
    val_list = ", ".join("?" for _ in insert_cols)
    return f"INSERT INTO {table} ({col_list}) VALUES ({val_list});"


def build_update_query(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    _ = db_type
    table = resolve_target_table(intent, schema)
    if not table:
        return "-- Error: no target table for UPDATE"

    set_values = intent.get("set_values", [])
    if set_values:
        set_parts = []
        for sv in set_values:
            col = normalize_column(sv["column"])
            if sv.get("type") == "percentage":
                pct = float(sv["value"].replace("%", ""))
                multiplier = round(1 + pct / 100, 2)
                set_parts.append(f"{col} = {col} * {multiplier:.2f}")
            else:
                set_parts.append(f"{col} = {_format_value(sv['value'])}")
        set_clause = ", ".join(set_parts)
    else:
        target_col = normalize_column(
            intent.get("columns", ["salary"])[0] if intent.get("columns") else "salary"
        )
        set_clause = f"{target_col} = /* new_value */"

    parts = [f"UPDATE {table}", f"SET {set_clause}"]
    conditions = intent.get("conditions", [])
    if conditions:
        parts.append(_build_where_clause(conditions, table))
    return "\n".join(parts) + ";"


def build_delete_query(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    _ = db_type
    table = resolve_target_table(intent, schema)
    if not table:
        return "-- Error: no target table for DELETE"

    parts = [f"DELETE FROM {table}"]
    conditions = intent.get("conditions", [])
    if conditions:
        parts.append(_build_where_clause(conditions, table))
    return "\n".join(parts) + ";"


def build_transaction_query(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    _ = schema, db_type
    return "-- Error: transaction prompts require account tables, which are not available in the HR schema"


def generate_sql(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> str:
    if intent.get("unsupported_schema") or intent.get("action") == "UNSUPPORTED_SCHEMA":
        return ""
    queries = generate_all_queries(intent, schema, db_type)
    return queries[0] if queries else "-- Error: could not generate SQL"


def generate_all_queries(
    intent: dict[str, Any],
    schema: dict[str, Any],
    db_type: str,
) -> list[str]:
    """Generate user-facing SQL only (no internal impact COUNT duplicates)."""
    action = intent.get("action", "SELECT").upper()

    if intent.get("unsupported_schema") or action == "UNSUPPORTED_SCHEMA":
        return []

    if intent.get("grouped_ranking"):
        return build_grouped_ranking_queries(intent)

    builders = {
        "SELECT": build_select_query,
        "INSERT": build_insert_query,
        "UPDATE": build_update_query,
        "DELETE": build_delete_query,
        "TRANSACTION": build_transaction_query,
    }

    builder = builders.get(action, build_select_query)
    return [builder(intent, schema, db_type)]
