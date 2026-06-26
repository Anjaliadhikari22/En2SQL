"""Logic-level query accuracy guard for common HR/interview prompts.

The normal validator checks syntax and safety. This module checks whether the
SQL actually matches common user intent, then replaces weak-but-valid SQL with a
stronger template when the intent is recognized.
"""

from __future__ import annotations

import re
from typing import Any


ORDINALS: dict[str, int] = {
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("-", " ")).strip()


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip()).upper()


def _extract_top_n(text: str, default: int = 1) -> int:
    normalized = _normalize(text)
    match = re.search(r"\b(?:top|first|limit)\s+(\d+)\b", normalized)
    if match:
        return int(match.group(1))
    return default


def _extract_nth_salary(text: str) -> int | None:
    normalized = _normalize(text)
    digit_match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+(?:highest|maximum)\s+salar", normalized)
    if digit_match:
        return int(digit_match.group(1))
    for word, value in ORDINALS.items():
        if re.search(rf"\b{word}\s+(?:highest|maximum)\s+salar", normalized):
            return value
    if re.search(r"\bsecond\s+maximum\s+salar", normalized):
        return 2
    return None


def _has_subquery(sql: str) -> bool:
    upper = _compact(sql)
    return bool(re.search(r"\(\s*SELECT\b", upper))


def _valid_second_highest_salary(sql: str, n: int) -> bool:
    upper = _compact(sql)
    has_max_subquery = bool(
        re.search(r"MAX\s*\(\s*SALARY\s*\).*WHERE\s+SALARY\s*<\s*\(\s*SELECT\s+MAX\s*\(\s*SALARY\s*\)", upper)
    )
    has_distinct_offset = (
        "SELECT DISTINCT SALARY" in upper
        and "ORDER BY SALARY DESC" in upper
        and "LIMIT 1" in upper
        and f"OFFSET {n - 1}" in upper
    )
    has_rank_filter = (
        ("DENSE_RANK()" in upper or "ROW_NUMBER()" in upper)
        and "ORDER BY" in upper
        and "SALARY DESC" in upper
        and re.search(rf"\b(?:SALARY_)?RANK\s*=\s*{n}\b", upper)
    )
    return has_max_subquery or has_distinct_offset or bool(has_rank_filter)


def _valid_top_n_salary(sql: str, n: int) -> bool:
    upper = _compact(sql)
    return "ORDER BY SALARY DESC" in upper and bool(re.search(rf"\bLIMIT\s+{n}\b", upper))


def _valid_group_ranking(sql: str) -> bool:
    upper = _compact(sql)
    has_partition = "PARTITION BY" in upper and "DEPARTMENT_ID" in upper
    has_correlated = (
        "SELECT COUNT(DISTINCT" in upper
        and "E2.SALARY" in upper
        and "E2.DEPARTMENT_ID = E.DEPARTMENT_ID" in upper
    )
    has_max_per_group = (
        "SELECT MAX(" in upper
        and "SALARY" in upper
        and "E2.DEPARTMENT_ID = E.DEPARTMENT_ID" in upper
    )
    return has_partition or has_correlated or has_max_per_group


def _is_mysql(database_type: str) -> bool:
    return (database_type or "mysql").lower() == "mysql"


def _is_postgresql(database_type: str) -> bool:
    return (database_type or "mysql").lower() in {"postgres", "postgresql"}


def _second_highest_salary_queries(n: int) -> list[str]:
    if n == 2:
        return [
            (
                "SELECT MAX(salary) AS second_highest_salary\n"
                "FROM employees\n"
                "WHERE salary < (\n"
                "    SELECT MAX(salary)\n"
                "    FROM employees\n"
                ");"
            ),
            (
                "SELECT DISTINCT salary\n"
                "FROM employees\n"
                "ORDER BY salary DESC\n"
                "LIMIT 1 OFFSET 1;"
            ),
        ]
    return [
        (
            "SELECT DISTINCT salary\n"
            "FROM employees\n"
            "ORDER BY salary DESC\n"
            f"LIMIT 1 OFFSET {n - 1};"
        )
    ]


def _top_n_employees_query(n: int) -> str:
    return f"SELECT *\nFROM employees\nORDER BY salary DESC\nLIMIT {n};"


def _grouped_ranking_queries(n: int) -> list[str]:
    row_number = (
        "WITH ranked_employees AS (\n"
        "    SELECT\n"
        "        e.employee_id,\n"
        "        e.first_name,\n"
        "        e.last_name,\n"
        "        e.salary,\n"
        "        d.department_name,\n"
        "        ROW_NUMBER() OVER (\n"
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
        f"WHERE salary_rank <= {n}\n"
        "ORDER BY department_name, salary_rank;"
    )
    dense_rank = row_number.replace("ROW_NUMBER() OVER", "DENSE_RANK() OVER")
    correlated = (
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
        f") < {n}\n"
        "ORDER BY d.department_name, e.salary DESC;"
    )
    return [row_number, dense_rank, correlated]


def _highest_paid_per_department_queries() -> list[str]:
    return [
        (
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
        ),
        (
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
        ),
    ]


def _avg_salary_query(operator: str) -> str:
    return (
        "SELECT *\n"
        "FROM employees\n"
        f"WHERE salary {operator} (\n"
        "    SELECT AVG(salary)\n"
        "    FROM employees\n"
        ");"
    )


def _count_by_department_queries() -> list[str]:
    return [
        (
            "SELECT\n"
            "    d.department_name,\n"
            "    COUNT(e.employee_id) AS employee_count\n"
            "FROM departments d\n"
            "LEFT JOIN employees e\n"
            "ON d.department_id = e.department_id\n"
            "GROUP BY d.department_name\n"
            "ORDER BY employee_count DESC;"
        ),
        (
            "SELECT\n"
            "    department_id,\n"
            "    COUNT(employee_id) AS employee_count\n"
            "FROM employees\n"
            "GROUP BY department_id\n"
            "ORDER BY employee_count DESC;"
        ),
    ]


def _departments_with_no_employees_query() -> str:
    return (
        "SELECT\n"
        "    d.department_id,\n"
        "    d.department_name\n"
        "FROM departments d\n"
        "LEFT JOIN employees e\n"
        "ON d.department_id = e.department_id\n"
        "WHERE e.employee_id IS NULL;"
    )


def _employees_without_department_query() -> str:
    return "SELECT *\nFROM employees\nWHERE department_id IS NULL;"


def _all_departments_with_or_without_employees_query() -> str:
    return (
        "SELECT\n"
        "    d.department_name,\n"
        "    e.employee_id,\n"
        "    e.first_name,\n"
        "    e.last_name\n"
        "FROM departments d\n"
        "LEFT JOIN employees e\n"
        "ON d.department_id = e.department_id;"
    )


def _duplicate_email_query() -> str:
    return (
        "SELECT\n"
        "    email,\n"
        "    COUNT(*) AS duplicate_count\n"
        "FROM employees\n"
        "GROUP BY email\n"
        "HAVING COUNT(*) > 1;"
    )


def _duplicate_employee_query() -> str:
    return (
        "SELECT\n"
        "    first_name,\n"
        "    last_name,\n"
        "    email,\n"
        "    COUNT(*) AS duplicate_count\n"
        "FROM employees\n"
        "GROUP BY first_name, last_name, email\n"
        "HAVING COUNT(*) > 1;"
    )


def _employee_department_query() -> str:
    return (
        "SELECT\n"
        "    e.first_name,\n"
        "    e.last_name,\n"
        "    d.department_name\n"
        "FROM employees e\n"
        "JOIN departments d\n"
        "ON e.department_id = d.department_id;"
    )


def _employee_job_titles_query() -> str:
    return (
        "SELECT\n"
        "    e.employee_id,\n"
        "    e.first_name,\n"
        "    e.last_name,\n"
        "    j.job_title,\n"
        "    e.salary\n"
        "FROM employees e\n"
        "JOIN jobs j\n"
        "ON e.job_id = j.job_id;"
    )


def _random_employees_query(n: int, database_type: str) -> str:
    function_name = "RANDOM()" if _is_postgresql(database_type) else "RAND()"
    return f"SELECT *\nFROM employees\nORDER BY {function_name}\nLIMIT {n};"


def _name_contains_query(term: str, database_type: str) -> str:
    if _is_postgresql(database_type):
        return f"SELECT *\nFROM employees\nWHERE first_name ILIKE '%{term}%';"
    return f"SELECT *\nFROM employees\nWHERE LOWER(first_name) LIKE LOWER('%{term}%');"


def _ecommerce_top_products_revenue_query(n: int) -> str:
    return (
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
    )


def _ecommerce_customers_no_orders_query() -> str:
    return (
        "SELECT\n"
        "    c.customer_id,\n"
        "    c.first_name,\n"
        "    c.last_name,\n"
        "    c.email\n"
        "FROM customers c\n"
        "LEFT JOIN orders o\n"
        "ON c.customer_id = o.customer_id\n"
        "WHERE o.order_id IS NULL;"
    )


def _result(
    generated_queries: list[str],
    *,
    explanation: list[str] | None = None,
    reason: str = "",
    applied: bool = False,
    query_type: str = "SELECT",
) -> dict[str, Any]:
    return {
        "generated_queries": generated_queries,
        "selected_query": generated_queries[0] if generated_queries else "",
        "query_type": query_type,
        "explanation": explanation,
        "guard_applied": applied,
        "guard_reason": reason,
    }


def validate_query_accuracy(
    prompt: str,
    generated_queries: list[str],
    query_type: str = "SELECT",
    database_type: str = "mysql",
) -> dict[str, Any]:
    """Return guarded SQL alternatives for recognized prompt categories."""
    normalized = _normalize(prompt)
    current_queries = list(generated_queries or [])
    first_sql = current_queries[0] if current_queries else ""
    query_type = (query_type or "SELECT").upper()

    if query_type in {
        "INVALID_PROMPT",
        "MULTIPLE_PROMPTS_DETECTED",
        "UNSUPPORTED_SCHEMA",
        "UNSUPPORTED_DOMAIN",
        "UNSAFE_REQUEST",
    }:
        return _result(current_queries, query_type=query_type)

    if "product" in normalized and "revenue" in normalized and re.search(r"\btop\s+\d+\b", normalized):
        n = _extract_top_n(normalized, 3)
        upper = _compact(first_sql)
        is_valid = (
            "SUM(OI.QUANTITY * OI.UNIT_PRICE)" in upper
            and "JOIN ORDER_ITEMS" in upper
            and "GROUP BY" in upper
            and "ORDER BY TOTAL_REVENUE DESC" in upper
            and f"LIMIT {n}" in upper
        )
        return _result(
            current_queries if current_queries and is_valid else [_ecommerce_top_products_revenue_query(n)],
            explanation=[
                "Calculates product revenue using quantity multiplied by unit price.",
                f"Sorts products by revenue and returns the top {n}.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured product revenue ranking uses SUM(quantity * unit_price), GROUP BY, ORDER BY, and LIMIT.",
            applied=not is_valid,
            query_type="SELECT",
        )

    if "customer" in normalized and re.search(r"\b(no orders|without orders)\b", normalized):
        upper = _compact(first_sql)
        is_valid = "LEFT JOIN ORDERS" in upper and "IS NULL" in upper
        return _result(
            current_queries if current_queries and is_valid else [_ecommerce_customers_no_orders_query()],
            explanation=[
                "Shows customers who have not placed any orders.",
                "Uses a LEFT JOIN and keeps only rows where no order matched.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured no-order customer detection uses LEFT JOIN and IS NULL.",
            applied=not is_valid,
            query_type="SELECT",
        )

    nth = _extract_nth_salary(normalized)
    if nth and re.search(r"\bsalar(?:y|ies)\b", normalized):
        if current_queries and _valid_second_highest_salary(first_sql, nth):
            return _result(current_queries, query_type=query_type)
        queries = _second_highest_salary_queries(nth)
        label = "second-highest" if nth == 2 else f"{nth}th-highest"
        return _result(
            queries,
            explanation=[
                f"Finds the {label} distinct salary without hardcoding a salary value.",
                "Uses either a subquery or DISTINCT with OFFSET to avoid returning all salaries.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Replaced incomplete salary ranking SQL with a distinct nth-highest salary query.",
            applied=True,
            query_type="SELECT",
        )

    is_group_prompt = bool(re.search(r"\b(?:within each department|per department|department wise|each department|every department)\b", normalized))
    has_salary_rank_words = bool(re.search(r"\bhighest(?: paid)?|maximum salary|top\s+\d+|salary\b", normalized))
    if is_group_prompt and "employee" in normalized and has_salary_rank_words:
        n = _extract_top_n(normalized, 1)
        if current_queries and all(_valid_group_ranking(sql) for sql in current_queries):
            return _result(current_queries, query_type=query_type)
        queries = _grouped_ranking_queries(n) if re.search(r"\btop\s+\d+", normalized) else _highest_paid_per_department_queries()
        return _result(
            queries,
            explanation=[
                f"Ranks employees separately inside each department by salary.",
                f"Returns the top {n} highest-paid employee{'s' if n != 1 else ''} from every department.",
                "Uses department-level ranking logic, not a global LIMIT.",
            ],
            reason="Replaced global ranking SQL with department-wise ranking SQL.",
            applied=True,
            query_type="SELECT",
        )

    if "employee" in normalized and re.search(r"\btop\s+\d+", normalized) and re.search(r"\bhighest(?: paid)?|salar", normalized):
        n = _extract_top_n(normalized, 1)
        if current_queries and _valid_top_n_salary(first_sql, n):
            return _result(current_queries, query_type=query_type)
        return _result(
            [_top_n_employees_query(n)],
            explanation=[
                f"Shows the top {n} highest-paid employees.",
                "Sorts employees by salary from highest to lowest.",
                "Limits the result so it does not return every employee.",
            ],
            reason="Added the required LIMIT for top-N salary ranking.",
            applied=True,
            query_type="SELECT",
        )

    if "employee" in normalized and re.search(r"\b(more than|greater than|above)\s+(?:the\s+)?average\s+salary\b|\bsalary\s+(?:greater than|more than|above)\s+(?:the\s+)?average\b", normalized):
        return _result(
            [_avg_salary_query(">")],
            explanation=[
                "Shows employees whose salary is above the average salary.",
                "Uses a subquery to calculate the average salary from the employees table.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured average-salary comparison uses an AVG(salary) subquery.",
            applied=not ("AVG(SALARY)" in _compact(first_sql) and ">" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "employee" in normalized and re.search(r"\b(less than|below|under)\s+(?:the\s+)?average\s+salary\b|\bsalary\s+(?:less than|below|under)\s+(?:the\s+)?average\b", normalized):
        return _result(
            [_avg_salary_query("<")],
            explanation=[
                "Shows employees whose salary is below the average salary.",
                "Uses a subquery to calculate the average salary from the employees table.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured average-salary comparison uses an AVG(salary) subquery.",
            applied=not ("AVG(SALARY)" in _compact(first_sql) and "<" in _compact(first_sql)),
            query_type="SELECT",
        )

    if re.search(r"\b(count|number of|how many)\b", normalized) and "employee" in normalized and "department" in normalized:
        return _result(
            _count_by_department_queries(),
            explanation=[
                "Counts how many employees are present in each department.",
                "Groups the result by department.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured department employee count uses COUNT and GROUP BY.",
            applied=not ("COUNT" in _compact(first_sql) and "GROUP BY" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "department" in normalized and re.search(r"\b(no employees|without employees|empty departments?)\b", normalized):
        return _result(
            [_departments_with_no_employees_query()],
            explanation=[
                "Shows departments that do not have any employees.",
                "Uses a LEFT JOIN and keeps only rows where no employee matched.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured missing-employee detection uses LEFT JOIN and IS NULL.",
            applied=not ("LEFT JOIN" in _compact(first_sql) and "IS NULL" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "employee" in normalized and re.search(r"\b(not assigned to (?:any )?department|without department|with no department|no department)\b", normalized):
        return _result(
            [_employees_without_department_query()],
            explanation=[
                "Shows employees who are not assigned to any department.",
                "Checks for NULL in the department_id column.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured unassigned employees are detected with department_id IS NULL.",
            applied=not ("DEPARTMENT_ID IS NULL" in _compact(first_sql) or "IS NULL" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "department" in normalized and "employee" in normalized and re.search(r"\beven if no employee exists|with or without employees|all departments\b", normalized):
        return _result(
            [_all_departments_with_or_without_employees_query()],
            explanation=[
                "Shows all departments, including departments with no employees.",
                "Uses a LEFT JOIN from departments to employees.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured all departments are preserved with a LEFT JOIN.",
            applied=not ("FROM DEPARTMENTS" in _compact(first_sql) and "LEFT JOIN EMPLOYEES" in _compact(first_sql)),
            query_type="SELECT",
        )

    if re.search(r"\bduplicate emails?|duplicate email addresses\b", normalized):
        return _result(
            [_duplicate_email_query()],
            explanation=[
                "Finds email addresses that appear more than once.",
                "Groups employees by email and filters groups with more than one row.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured duplicate emails use GROUP BY and HAVING.",
            applied=not ("GROUP BY EMAIL" in _compact(first_sql) and "HAVING COUNT(*) > 1" in _compact(first_sql)),
            query_type="SELECT",
        )

    if re.search(r"\bduplicate employees?|find duplicate employees?\b", normalized):
        return _result(
            [_duplicate_employee_query()],
            explanation=[
                "Finds possible duplicate employee records.",
                "Groups by first name, last name, and email.",
                "Keeps only groups that appear more than once.",
            ],
            reason="Ensured duplicate employees use GROUP BY and HAVING.",
            applied=not ("GROUP BY" in _compact(first_sql) and "HAVING COUNT(*) > 1" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "employee" in normalized and "department" in normalized and re.search(r"\bwith\b|\balong with\b", normalized):
        return _result(
            [_employee_department_query()],
            explanation=[
                "Shows each employee’s first name and last name.",
                "Also displays the department name for each employee.",
                "Uses a join between employees and departments.",
            ],
            reason="Ensured employee department prompts join employees and departments.",
            applied=not ("JOIN DEPARTMENTS" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "employee" in normalized and re.search(r"\bjob titles?\b|\bwith their job titles?\b", normalized):
        return _result(
            [_employee_job_titles_query()],
            explanation=[
                "Shows employees along with their job titles.",
                "Uses a join between employees and jobs.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured employee job title prompts join employees and jobs.",
            applied=not ("JOIN JOBS" in _compact(first_sql)),
            query_type="SELECT",
        )

    if "random" in normalized and "employee" in normalized:
        n = _extract_top_n(normalized, 3)
        # Also support "show 3 random employees".
        explicit = re.search(r"\b(\d+)\s+random\s+employees?\b", normalized)
        if explicit:
            n = int(explicit.group(1))
        query = _random_employees_query(n, database_type)
        return _result(
            [query],
            explanation=[
                f"Shows {n} randomly selected employees.",
                "Uses the correct random ordering function for the selected database.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured random employee query uses the selected SQL dialect.",
            applied=(_is_mysql(database_type) and "RAND()" not in _compact(first_sql)) or (_is_postgresql(database_type) and "RANDOM()" not in _compact(first_sql)),
            query_type="SELECT",
        )

    name_match = re.search(r"\b(?:first\s+name|name)\s+contains\s+([a-z][\w-]*)\b|\bsearch\s+employee\s+name\s+([a-z][\w-]*)\b", normalized)
    if "employee" in normalized and name_match:
        term = next(group for group in name_match.groups() if group)
        return _result(
            [_name_contains_query(term, database_type)],
            explanation=[
                f"Shows employees whose first name contains “{term}”.",
                "Uses a case-insensitive search.",
                "This is a read-only query, so it does not change any data.",
            ],
            reason="Ensured case-insensitive name search uses the selected SQL dialect.",
            applied=True,
            query_type="SELECT",
        )

    return _result(current_queries, query_type=query_type)
