"""Unit tests for the logic-level query accuracy guard."""

import re

from query_accuracy_guard import validate_query_accuracy


def compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip()).upper()


def test_guard_replaces_incomplete_second_highest_salary_query():
    bad_sql = "SELECT salary\nFROM employees\nORDER BY salary DESC;"

    result = validate_query_accuracy(
        "How do you find the second-highest salary in the employee table without hardcoding numbers?",
        [bad_sql],
        "SELECT",
        "mysql",
    )

    sql = compact(result["selected_query"])
    assert result["guard_applied"] is True
    assert sql != compact(bad_sql)
    assert "MAX(SALARY)" in sql or "SELECT DISTINCT SALARY" in sql


def test_guard_replaces_global_limit_for_department_top_n():
    bad_sql = "SELECT *\nFROM employees\nORDER BY salary DESC\nLIMIT 2;"

    result = validate_query_accuracy(
        "Find the top 2 highest-paid employees within each department",
        [bad_sql],
        "SELECT",
        "mysql",
    )

    assert result["guard_applied"] is True
    assert len(result["generated_queries"]) >= 2
    assert "PARTITION BY" in compact(result["selected_query"])


def test_guard_replaces_overall_average_for_department_average_prompt():
    bad_sql = (
        "SELECT *\n"
        "FROM employees\n"
        "WHERE salary > (\n"
        "    SELECT AVG(salary)\n"
        "    FROM employees\n"
        ");"
    )

    result = validate_query_accuracy(
        "List employees who earn more than the average salary of their own department, along with their department name and salary.",
        [bad_sql],
        "SELECT",
        "mysql",
    )

    selected = compact(result["selected_query"])
    assert result["guard_applied"] is True
    assert selected != compact(bad_sql)
    assert (
        "E2.DEPARTMENT_ID = E.DEPARTMENT_ID" in selected
        or ("WITH DEPARTMENT_AVG AS" in selected and "JOIN DEPARTMENT_AVG" in selected)
    )


def test_guard_preserves_database_dialect_for_random_rows():
    mysql = validate_query_accuracy("Show 3 random employees", [], "SELECT", "mysql")
    postgres = validate_query_accuracy("Show 3 random employees", [], "SELECT", "postgresql")

    assert "ORDER BY RAND()" in compact(mysql["selected_query"])
    assert "ORDER BY RANDOM()" in compact(postgres["selected_query"])
    assert "LIMIT 3" in compact(mysql["selected_query"])
    assert "LIMIT 3" in compact(postgres["selected_query"])
