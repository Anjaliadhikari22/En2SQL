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


def _nl(intent: dict[str, Any]) -> str:
    return intent.get("normalized_text", "")


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
    pack_queries = _schema_pack_queries(intent, schema, db_type)
    if pack_queries:
        return pack_queries[0]

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
        return build_department_employee_count_queries()[0]

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


def _schema_pack_queries(intent: dict[str, Any], schema: dict[str, Any], db_type: str) -> Optional[list[str]]:
    """Generate local schema-pack queries for common supported domains."""
    _ = db_type
    pack = (schema.get("schema_pack") or intent.get("schema_pack") or "hr").lower()
    text = _nl(intent)

    if pack == "ecommerce":
        top_match = re.search(r"\btop\s+(\d+)\b", text)
        if top_match and "product" in text and ("sales" in text or "revenue" in text):
            n = top_match.group(1)
            return [(
                "SELECT\n"
                "    p.product_id,\n"
                "    p.product_name,\n"
                "    SUM(oi.quantity * oi.unit_price) AS total_revenue\n"
                "FROM products p\n"
                "JOIN order_items oi\n"
                "ON p.product_id = oi.product_id\n"
                "JOIN orders o\n"
                "ON oi.order_id = o.order_id\n"
                "GROUP BY p.product_id, p.product_name\n"
                "ORDER BY total_revenue DESC\n"
                f"LIMIT {n};"
            )]
        if "revenue" in text and "category" in text:
            return [(
                "SELECT\n"
                "    c.category_name,\n"
                "    SUM(oi.quantity * oi.unit_price) AS total_revenue\n"
                "FROM categories c\n"
                "JOIN products p\n"
                "ON c.category_id = p.category_id\n"
                "JOIN order_items oi\n"
                "ON p.product_id = oi.product_id\n"
                "GROUP BY c.category_name\n"
                "ORDER BY total_revenue DESC;"
            )]
        if "customer" in text and re.search(r"\b(no orders|without orders)\b", text):
            return [(
                "SELECT\n"
                "    c.customer_id,\n"
                "    c.first_name,\n"
                "    c.last_name,\n"
                "    c.email\n"
                "FROM customers c\n"
                "LEFT JOIN orders o\n"
                "ON c.customer_id = o.customer_id\n"
                "WHERE o.order_id IS NULL;"
            )]
        if "monthly" in text and "revenue" in text:
            year = (re.search(r"\b(20\d{2}|19\d{2})\b", text) or [None, "2025"])[1]
            return [(
                "SELECT\n"
                "    EXTRACT(MONTH FROM o.order_date) AS revenue_month,\n"
                "    SUM(oi.quantity * oi.unit_price) AS total_revenue\n"
                "FROM orders o\n"
                "JOIN order_items oi\n"
                "ON o.order_id = oi.order_id\n"
                f"WHERE EXTRACT(YEAR FROM o.order_date) = {year}\n"
                "GROUP BY EXTRACT(MONTH FROM o.order_date)\n"
                "ORDER BY revenue_month;"
            )]

    if pack == "university":
        if "student" in text and "course" in text and ("enrolled" in text or "each course" in text):
            return [(
                "SELECT\n"
                "    c.course_name,\n"
                "    COUNT(e.student_id) AS student_count\n"
                "FROM courses c\n"
                "LEFT JOIN enrollments e\n"
                "ON c.course_id = e.course_id\n"
                "GROUP BY c.course_name\n"
                "ORDER BY student_count DESC;"
            )]
        if "average" in text and ("marks" in text or "grade" in text) and "course" in text:
            return [(
                "SELECT\n"
                "    c.course_name,\n"
                "    AVG(g.marks) AS average_marks\n"
                "FROM courses c\n"
                "JOIN enrollments e\n"
                "ON c.course_id = e.course_id\n"
                "JOIN grades g\n"
                "ON e.enrollment_id = g.enrollment_id\n"
                "GROUP BY c.course_name\n"
                "ORDER BY average_marks DESC;"
            )]
        if "student" in text and ("highest grade" in text or "highest grades" in text):
            return [(
                "SELECT\n"
                "    s.student_id,\n"
                "    s.first_name,\n"
                "    s.last_name,\n"
                "    g.marks\n"
                "FROM students s\n"
                "JOIN enrollments e\n"
                "ON s.student_id = e.student_id\n"
                "JOIN grades g\n"
                "ON e.enrollment_id = g.enrollment_id\n"
                "ORDER BY g.marks DESC\n"
                "LIMIT 5;"
            )]
        if "instructor" in text and "course" in text:
            return [(
                "SELECT\n"
                "    i.first_name,\n"
                "    i.last_name,\n"
                "    c.course_name\n"
                "FROM instructors i\n"
                "JOIN courses c\n"
                "ON i.instructor_id = c.instructor_id;"
            )]

    if pack == "healthcare":
        if "doctor" in text and "appointment" in text and "count" not in text:
            return [(
                "SELECT\n"
                "    d.doctor_id,\n"
                "    d.first_name,\n"
                "    d.last_name,\n"
                "    a.appointment_id,\n"
                "    a.appointment_date,\n"
                "    a.status\n"
                "FROM doctors d\n"
                "JOIN appointments a\n"
                "ON d.doctor_id = a.doctor_id;"
            )]
        if "patient" in text and "prescription" in text:
            return [(
                "SELECT\n"
                "    p.first_name,\n"
                "    p.last_name,\n"
                "    m.medicine_name,\n"
                "    pr.dosage\n"
                "FROM patients p\n"
                "JOIN appointments a\n"
                "ON p.patient_id = a.patient_id\n"
                "JOIN prescriptions pr\n"
                "ON a.appointment_id = pr.appointment_id\n"
                "JOIN medicines m\n"
                "ON pr.medicine_id = m.medicine_id;"
            )]
        if "count" in text and "appointment" in text and "doctor" in text:
            return [(
                "SELECT\n"
                "    d.doctor_id,\n"
                "    d.first_name,\n"
                "    d.last_name,\n"
                "    COUNT(a.appointment_id) AS appointment_count\n"
                "FROM doctors d\n"
                "LEFT JOIN appointments a\n"
                "ON d.doctor_id = a.doctor_id\n"
                "GROUP BY d.doctor_id, d.first_name, d.last_name\n"
                "ORDER BY appointment_count DESC;"
            )]
        if "patient" in text and re.search(r"\b(no appointments|without appointments)\b", text):
            return [(
                "SELECT\n"
                "    p.patient_id,\n"
                "    p.first_name,\n"
                "    p.last_name\n"
                "FROM patients p\n"
                "LEFT JOIN appointments a\n"
                "ON p.patient_id = a.patient_id\n"
                "WHERE a.appointment_id IS NULL;"
            )]

    if pack == "library":
        if "book" in text and ("borrowed" in text or "borrow" in text) and "member" in text:
            return [(
                "SELECT\n"
                "    m.first_name,\n"
                "    m.last_name,\n"
                "    b.title,\n"
                "    br.borrow_date,\n"
                "    br.return_date\n"
                "FROM members m\n"
                "JOIN borrow_records br\n"
                "ON m.member_id = br.member_id\n"
                "JOIN books b\n"
                "ON br.book_id = b.book_id;"
            )]
        if "most borrowed" in text or ("top" in text and "borrowed" in text):
            return [(
                "SELECT\n"
                "    b.title,\n"
                "    COUNT(br.borrow_id) AS borrow_count\n"
                "FROM books b\n"
                "JOIN borrow_records br\n"
                "ON b.book_id = br.book_id\n"
                "GROUP BY b.title\n"
                "ORDER BY borrow_count DESC\n"
                "LIMIT 5;"
            )]
        if "overdue" in text:
            return ["SELECT *\nFROM borrow_records\nWHERE return_date IS NULL\nAND due_date < CURRENT_DATE;"]
        if "author" in text and "book" in text:
            return [(
                "SELECT\n"
                "    a.author_name,\n"
                "    b.title\n"
                "FROM authors a\n"
                "JOIN books b\n"
                "ON a.author_id = b.author_id;"
            )]

    if pack == "banking":
        if "balance" in text and "customer" in text:
            return [(
                "SELECT\n"
                "    c.customer_id,\n"
                "    c.first_name,\n"
                "    c.last_name,\n"
                "    a.account_id,\n"
                "    a.balance\n"
                "FROM customers c\n"
                "JOIN accounts a\n"
                "ON c.customer_id = a.customer_id;"
            )]
        if "total" in text and "transaction" in text and "account" in text:
            return [(
                "SELECT\n"
                "    a.account_id,\n"
                "    COUNT(t.transaction_id) AS transaction_count,\n"
                "    SUM(t.amount) AS total_transaction_amount\n"
                "FROM accounts a\n"
                "LEFT JOIN transactions t\n"
                "ON a.account_id = t.account_id\n"
                "GROUP BY a.account_id\n"
                "ORDER BY transaction_count DESC;"
            )]
        if "customer" in text and re.search(r"\b(no transactions|without transactions)\b", text):
            return [(
                "SELECT\n"
                "    c.customer_id,\n"
                "    c.first_name,\n"
                "    c.last_name\n"
                "FROM customers c\n"
                "JOIN accounts a\n"
                "ON c.customer_id = a.customer_id\n"
                "LEFT JOIN transactions t\n"
                "ON a.account_id = t.account_id\n"
                "WHERE t.transaction_id IS NULL;"
            )]
        if "highest transaction" in text:
            return ["SELECT *\nFROM transactions\nORDER BY amount DESC\nLIMIT 5;"]

    if pack == "booking":
        if "booking" in text and "guest" in text:
            return [(
                "SELECT\n"
                "    g.first_name,\n"
                "    g.last_name,\n"
                "    b.booking_id,\n"
                "    b.check_in_date,\n"
                "    b.check_out_date,\n"
                "    b.status\n"
                "FROM guests g\n"
                "JOIN bookings b\n"
                "ON g.guest_id = b.guest_id;"
            )]
        if "available rooms" in text or ("room" in text and "available" in text):
            return [(
                "SELECT\n"
                "    h.hotel_name,\n"
                "    r.room_id,\n"
                "    r.room_number,\n"
                "    r.room_type,\n"
                "    r.price_per_night\n"
                "FROM rooms r\n"
                "JOIN hotels h\n"
                "ON r.hotel_id = h.hotel_id\n"
                "WHERE r.status = 'Available';"
            )]
        if "count" in text and "booking" in text and "hotel" in text:
            return [(
                "SELECT\n"
                "    h.hotel_name,\n"
                "    COUNT(b.booking_id) AS booking_count\n"
                "FROM hotels h\n"
                "LEFT JOIN rooms r\n"
                "ON h.hotel_id = r.hotel_id\n"
                "LEFT JOIN bookings b\n"
                "ON r.room_id = b.room_id\n"
                "GROUP BY h.hotel_name\n"
                "ORDER BY booking_count DESC;"
            )]
        if "payment" in text and "guest" in text:
            return [(
                "SELECT\n"
                "    g.first_name,\n"
                "    g.last_name,\n"
                "    SUM(p.amount) AS total_payment\n"
                "FROM guests g\n"
                "JOIN bookings b\n"
                "ON g.guest_id = b.guest_id\n"
                "JOIN payments p\n"
                "ON b.booking_id = p.booking_id\n"
                "GROUP BY g.first_name, g.last_name\n"
                "ORDER BY total_payment DESC;"
            )]

    return None


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
        "        d.department_name,\n"
        f"        {rank_function}() OVER (\n"
        "            PARTITION BY e.department_id\n"
        "            ORDER BY e.salary DESC\n"
        "        ) AS salary_rank\n"
        "    FROM employees e\n"
        "    JOIN departments d\n"
        "        ON e.department_id = d.department_id\n"
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
        "JOIN departments d\n"
        "    ON e.department_id = d.department_id\n"
        "WHERE (\n"
        "    SELECT COUNT(DISTINCT e2.salary)\n"
        "    FROM employees e2\n"
        "    WHERE e2.department_id = e.department_id\n"
        "      AND e2.salary > e.salary\n"
        f") < {limit}\n"
        "ORDER BY d.department_name, e.salary DESC;"
    )


def build_grouped_ranking_queries(intent: dict[str, Any]) -> list[str]:
    """Return user-facing alternatives for top-N employees within each department."""
    if (intent.get("grouped_ranking") or {}).get("type") == "HIGHEST_WITHIN_GROUP":
        return build_highest_paid_per_department_queries()

    return [
        _build_employee_department_window_rank_query(intent, "ROW_NUMBER"),
        _build_employee_department_window_rank_query(intent, "DENSE_RANK"),
        _build_employee_department_correlated_rank_query(intent),
    ]


def build_highest_paid_per_department_queries() -> list[str]:
    """Return alternatives for highest-paid employees in each department."""
    dense_rank_query = (
        "WITH ranked_employees AS (\n"
        "    SELECT\n"
        "        e.employee_id,\n"
        "        e.first_name,\n"
        "        e.last_name,\n"
        "        e.salary,\n"
        "        d.department_name,\n"
        "        DENSE_RANK() OVER (\n"
        "            PARTITION BY e.department_id\n"
        "            ORDER BY e.salary DESC\n"
        "        ) AS salary_rank\n"
        "    FROM employees e\n"
        "    JOIN departments d\n"
        "        ON e.department_id = d.department_id\n"
        ")\n"
        "SELECT\n"
        "    department_name,\n"
        "    employee_id,\n"
        "    first_name,\n"
        "    last_name,\n"
        "    salary\n"
        "FROM ranked_employees\n"
        "WHERE salary_rank = 1\n"
        "ORDER BY department_name;"
    )
    max_salary_query = (
        "SELECT\n"
        "    d.department_name,\n"
        "    e.employee_id,\n"
        "    e.first_name,\n"
        "    e.last_name,\n"
        "    e.salary\n"
        "FROM employees e\n"
        "JOIN departments d\n"
        "    ON e.department_id = d.department_id\n"
        "WHERE e.salary = (\n"
        "    SELECT MAX(e2.salary)\n"
        "    FROM employees e2\n"
        "    WHERE e2.department_id = e.department_id\n"
        ")\n"
        "ORDER BY d.department_name;"
    )
    return [dense_rank_query, max_salary_query]


def build_department_employee_count_queries() -> list[str]:
    """Return alternatives for counting employees in each department."""
    with_names = (
        "SELECT\n"
        "    d.department_name,\n"
        "    COUNT(e.employee_id) AS employee_count\n"
        "FROM departments d\n"
        "LEFT JOIN employees e\n"
        "ON d.department_id = e.department_id\n"
        "GROUP BY d.department_name\n"
        "ORDER BY employee_count DESC;"
    )
    by_id = (
        "SELECT\n"
        "    department_id,\n"
        "    COUNT(employee_id) AS employee_count\n"
        "FROM employees\n"
        "GROUP BY department_id\n"
        "ORDER BY employee_count DESC;"
    )
    return [with_names, by_id]


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
    normalized = intent.get("normalized_text", "")
    original = intent.get("original_text", "")
    if (schema.get("schema_pack") == "hr" or "employee" in normalized) and "employee" in normalized:
        name_match = (
            re.search(r"\bnamed\s+([a-z]+)(?:\s+([a-z]+))?", original, re.IGNORECASE)
            or re.search(r"\bemployee\s+([a-z]+)(?:\s+([a-z]+))?", original, re.IGNORECASE)
        )
        salary_match = re.search(r"\bsalary\s+(?:is\s+|to\s+)?(\d+(?:\.\d+)?)\b", normalized)
        if name_match and salary_match:
            first_name = name_match.group(1).title()
            last_name = (name_match.group(2) or "").title()
            cols = ["first_name"]
            vals = [_quote_string(first_name)]
            if last_name:
                cols.append("last_name")
                vals.append(_quote_string(last_name))
            cols.append("salary")
            vals.append(salary_match.group(1))
            col_lines = ",\n    ".join(cols)
            val_lines = ",\n    ".join(vals)
            return (
                "INSERT INTO employees (\n"
                f"    {col_lines}\n"
                ")\n"
                "VALUES (\n"
                f"    {val_lines}\n"
                ");"
            )

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
    normalized = intent.get("normalized_text", "")
    if (schema.get("schema_pack") == "hr" or "employee" in normalized) and "employee" in normalized and "salary" in normalized:
        salary_match = re.search(r"\bsalary\s+(?:to|=|is)\s+(\d+(?:\.\d+)?)\b", normalized)
        employee_id_match = re.search(r"\bemployee\s+id\s+(?:is\s+|=)?(\d+)\b|\bemployee_id\s*(?:=|is)?\s*(\d+)\b", normalized)
        if salary_match and employee_id_match:
            employee_id = next(g for g in employee_id_match.groups() if g)
            return (
                "UPDATE employees\n"
                f"SET salary = {salary_match.group(1)}\n"
                f"WHERE employee_id = {employee_id};"
            )

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
    normalized = intent.get("normalized_text", "")
    if (schema.get("schema_pack") == "hr" or "employee" in normalized) and "employee" in normalized:
        employee_id_match = re.search(r"\bemployee\s+id\s+(?:is\s+|=)?(\d+)\b|\bemployee_id\s*(?:=|is)?\s*(\d+)\b", normalized)
        if employee_id_match:
            employee_id = next(g for g in employee_id_match.groups() if g)
            return (
                "DELETE FROM employees\n"
                f"WHERE employee_id = {employee_id};"
            )

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

    pack_queries = _schema_pack_queries(intent, schema, db_type)
    if pack_queries:
        return pack_queries

    if intent.get("grouped_ranking"):
        return build_grouped_ranking_queries(intent)

    if intent.get("multi_query_type") == "COUNT_EMPLOYEES_BY_DEPARTMENT":
        return build_department_employee_count_queries()

    builders = {
        "SELECT": build_select_query,
        "INSERT": build_insert_query,
        "UPDATE": build_update_query,
        "DELETE": build_delete_query,
        "TRANSACTION": build_transaction_query,
    }

    builder = builders.get(action, build_select_query)
    return [builder(intent, schema, db_type)]
