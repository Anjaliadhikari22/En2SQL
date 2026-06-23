"""
Automated tests for NL-to-SQL query generation pipeline.

Run from project root:
    cd backend
    python -m pytest ../tests
"""

import re

import pytest

from impact_analyzer import analyze_impact
from prompt_processor import process_prompt
from query_generator import generate_all_queries
from schema_reader import get_demo_schema, get_table_names
from validator import validate_query


SCHEMA = get_demo_schema()
TABLES = get_table_names(SCHEMA)

DB_TYPES = ["mysql", "postgresql"]


def normalize_sql(sql: str) -> str:
    """Collapse whitespace for flexible SQL comparison."""
    return re.sub(r"\s+", " ", sql.strip())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=DB_TYPES)
def db_type(request):
    return request.param


def run_pipeline(prompt: str, db_type: str):
    """Run prompt → intent → SQL → validation → impact."""
    intent = process_prompt(prompt, TABLES, SCHEMA)
    queries = generate_all_queries(intent, SCHEMA, db_type)
    sql = queries[0]
    validation = validate_query(sql, SCHEMA)
    impact = analyze_impact(sql, intent, SCHEMA, db_type)
    return intent, queries, sql, validation, impact


# ---------------------------------------------------------------------------
# Category 1: SELECT with WHERE
# ---------------------------------------------------------------------------


class TestSelectWithWhere:
    PROMPT = "Show all employees whose salary is greater than 50000"
    EXPECTED = """SELECT * FROM Employee
WHERE Salary > 50000;"""

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_select_where_employee_salary(self, db_type):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert impact["affected_tables"] == ["Employee"]
        assert impact["affected_columns"] == ["Salary"]
        assert "25 rows may be returned" in impact["expected_output"]
        assert len(queries) == 1
        assert "MAX(*)" not in sql
        assert "`" not in sql


# ---------------------------------------------------------------------------
# Category 2: TOP N / ORDER BY
# ---------------------------------------------------------------------------


class TestTopNOrderBy:
    PROMPT = "Find top 5 students with highest CGPA"
    EXPECTED = """SELECT * FROM Students
ORDER BY CGPA DESC
LIMIT 5;"""

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_top_n_students_cgpa(self, db_type):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert "MAX(*)" not in sql.upper()
        assert "5 rows may be returned" in impact["expected_output"]
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# Category 3: COUNT (user-requested)
# ---------------------------------------------------------------------------


class TestCountQuery:
    PROMPT = "Count total students in CSE department"
    EXPECTED = """SELECT COUNT(*) FROM Students
WHERE Department = 'CSE';"""

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_count_students_cse(self, db_type):
        intent, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert "COUNT" in intent.get("aggregates", [])
        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert len(queries) == 1
        assert "COUNT(*)" in sql
        assert "RowCount" not in sql  # internal alias not exposed


# ---------------------------------------------------------------------------
# Category 4: UPDATE
# ---------------------------------------------------------------------------


class TestUpdateQuery:
    PROMPT = "Increase salary of all employees in IT department by 10 percent"
    EXPECTED = """UPDATE Employee
SET Salary = Salary * 1.10
WHERE DepartmentID IN (
    SELECT DepartmentID
    FROM Department
    WHERE DepartmentName = 'IT'
);"""

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_update_salary_it_department(self, db_type):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert validation["risks"]["is_risky"]
        assert "UPDATE" in validation["warning_message"]
        assert "42 rows will be modified" in impact["expected_output"]
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# Category 5: DELETE
# ---------------------------------------------------------------------------


class TestDeleteQuery:
    PROMPT = "Delete students whose attendance is less than 75"
    EXPECTED = "DELETE FROM Students WHERE Attendance < 75;"

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_delete_students_attendance(self, db_type):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert validation["risks"]["is_risky"]
        assert "DELETE" in validation["warning_message"]
        assert "12 rows will be deleted" in impact["expected_output"]
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# Category 6: INNER JOIN
# ---------------------------------------------------------------------------


class TestInnerJoin:
    PROMPT = "Show employee name with department name"
    EXPECTED = """SELECT Employee.Name, Department.DepartmentName
FROM Employee
INNER JOIN Department
ON Employee.DepartmentID = Department.DepartmentID;"""

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_inner_join_employee_department(self, db_type):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert "INNER JOIN" in sql
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# Category 7: LEFT JOIN
# ---------------------------------------------------------------------------


class TestLeftJoin:
    PROMPT = "Display all departments even if no employee exists"
    EXPECTED = """SELECT Department.DepartmentName, Employee.Name
FROM Department
LEFT JOIN Employee
ON Department.DepartmentID = Employee.DepartmentID;"""

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_left_join_departments(self, db_type):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, db_type)

        assert normalize_sql(sql) == normalize_sql(self.EXPECTED)
        assert validation["validation"]["valid"]
        assert "LEFT JOIN" in sql
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# Category 8: TRANSACTION (MySQL vs PostgreSQL)
# ---------------------------------------------------------------------------


class TestTransaction:
    PROMPT = "Transfer 5000 from account 101 to account 102"

    def test_transaction_mysql(self):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, "mysql")

        expected = (
            "START TRANSACTION; "
            "UPDATE Account SET Balance = Balance - 5000 WHERE AccountID = 101; "
            "UPDATE Account SET Balance = Balance + 5000 WHERE AccountID = 102; "
            "COMMIT;"
        )
        assert normalize_sql(sql) == normalize_sql(expected)
        assert validation["validation"]["valid"]
        assert validation["risks"]["is_risky"]
        assert "2 rows may be modified inside this transaction" in impact["expected_output"]
        assert len(queries) == 1

    def test_transaction_postgresql(self):
        _, queries, sql, validation, impact = run_pipeline(self.PROMPT, "postgresql")

        expected = (
            "BEGIN; "
            "UPDATE Account SET Balance = Balance - 5000 WHERE AccountID = 101; "
            "UPDATE Account SET Balance = Balance + 5000 WHERE AccountID = 102; "
            "COMMIT;"
        )
        assert normalize_sql(sql) == normalize_sql(expected)
        assert validation["validation"]["valid"]
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# General safety checks
# ---------------------------------------------------------------------------


class TestGeneralSafety:
    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_generated_query_not_empty(self, db_type):
        prompts = [
            "Show all employees whose salary is greater than 50000",
            "Find top 5 students with highest CGPA",
            "Count total students in CSE department",
        ]
        for prompt in prompts:
            _, queries, sql, _, _ = run_pipeline(prompt, db_type)
            assert sql.strip()
            assert not sql.strip().startswith("-- Error")
            assert len(queries) >= 1

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_no_invalid_max_star(self, db_type):
        prompt = "Find top 5 students with highest CGPA"
        _, _, sql, _, _ = run_pipeline(prompt, db_type)
        assert "MAX(*)" not in sql.upper()

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_no_internal_count_in_generated_queries(self, db_type):
        """Non-COUNT prompts must not include internal impact COUNT queries."""
        prompt = "Show all employees whose salary is greater than 50000"
        _, queries, _, _, _ = run_pipeline(prompt, db_type)
        for q in queries:
            assert "RowCount" not in q
            assert normalize_sql(q).count("COUNT(*)") == 0

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_select_star_optimization_hint(self, db_type):
        prompt = "Show all employees whose salary is greater than 50000"
        _, _, sql, validation, _ = run_pipeline(prompt, db_type)
        assert "SELECT *" in sql
        assert "required columns" in validation["optimization_message"].lower()

    @pytest.mark.parametrize("db_type", DB_TYPES)
    def test_update_delete_show_warnings(self, db_type):
        update_prompt = "Increase salary of all employees in IT department by 10 percent"
        delete_prompt = "Delete students whose attendance is less than 75"

        _, _, _, update_val, _ = run_pipeline(update_prompt, db_type)
        _, _, _, delete_val, _ = run_pipeline(delete_prompt, db_type)

        assert update_val["warning_message"]
        assert delete_val["warning_message"]
        assert update_val["risks"]["is_risky"]
        assert delete_val["risks"]["is_risky"]
