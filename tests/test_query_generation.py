"""Golden tests for En2SQL HR query generation accuracy."""

import re

from prompt_processor import process_prompt
from query_accuracy_guard import validate_query_accuracy
from query_generator import generate_all_queries
from config import Config
from database import get_database_key
from schema_reader import detect_schema_pack, get_schema_pack, get_table_names
from validator import validate_query


SCHEMA = get_schema_pack("hr")
TABLES = get_table_names(SCHEMA)


def compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip()).upper()


def guarded_pipeline(prompt: str, db_type: str = "mysql"):
    decision = detect_schema_pack(prompt, "auto")
    schema = get_schema_pack(decision["schema_pack"] or "hr")
    tables = get_table_names(schema)
    intent = process_prompt(prompt, tables, schema)
    if intent.get("unsupported_schema") or intent.get("unsafe_request"):
        return intent, [], ""
    generated = generate_all_queries(intent, schema, db_type)
    guarded = validate_query_accuracy(prompt, generated, intent.get("action", "SELECT"), db_type)
    sql = guarded["selected_query"]
    validation = validate_query(sql, schema)
    assert validation["validation"]["valid"], validation
    return intent, guarded["generated_queries"], sql


def test_second_highest_salary_not_plain_sorted_list():
    prompt = "How do you find the second-highest salary in the employee table without hardcoding numbers?"
    _, queries, sql = guarded_pipeline(prompt)
    upper = compact(sql)

    assert queries
    assert (
        "MAX(SALARY)" in upper and "WHERE SALARY <" in upper and "SELECT MAX(SALARY)" in upper
    ) or (
        "SELECT DISTINCT SALARY" in upper and "LIMIT 1 OFFSET 1" in upper
    ) or (
        ("DENSE_RANK()" in upper or "ROW_NUMBER()" in upper) and "SALARY_RANK = 2" in upper
    )
    assert upper != "SELECT SALARY FROM EMPLOYEES ORDER BY SALARY DESC;"


def test_top_5_highest_paid_employees_has_order_and_limit():
    _, _, sql = guarded_pipeline("Find the top 5 highest-paid employees")
    upper = compact(sql)

    assert "ORDER BY SALARY DESC" in upper
    assert "LIMIT 5" in upper


def test_top_2_highest_paid_employees_within_each_department_is_grouped():
    _, queries, sql = guarded_pipeline("Find the top 2 highest-paid employees within each department")
    upper = compact(sql)

    assert len(queries) >= 2
    assert "PARTITION BY" in upper or "E2.DEPARTMENT_ID = E.DEPARTMENT_ID" in upper
    assert compact(sql) != "SELECT * FROM EMPLOYEES ORDER BY SALARY DESC LIMIT 2;"


def test_employees_earning_more_than_average_salary():
    _, _, sql = guarded_pipeline("Find employees earning more than the average salary")
    upper = compact(sql)

    assert "SALARY >" in upper
    assert "SELECT AVG(SALARY)" in upper
    assert "FROM EMPLOYEES" in upper


def test_employees_earning_less_than_average_salary():
    _, _, sql = guarded_pipeline("Find employees earning less than the average salary")
    upper = compact(sql)

    assert "SALARY <" in upper
    assert "SELECT AVG(SALARY)" in upper
    assert "FROM EMPLOYEES" in upper


def test_count_employees_in_each_department():
    _, queries, sql = guarded_pipeline("Count employees in each department")
    assert len(queries) >= 1
    upper = compact(sql)

    assert "COUNT(" in upper
    assert "GROUP BY" in upper


def test_departments_with_no_employees():
    _, _, sql = guarded_pipeline("Show departments with no employees")
    upper = compact(sql)

    assert "FROM DEPARTMENTS" in upper
    assert "LEFT JOIN EMPLOYEES" in upper
    assert "IS NULL" in upper


def test_employees_not_assigned_to_any_department():
    _, _, sql = guarded_pipeline("Show employees who are not assigned to any department")
    upper = compact(sql)

    assert "DEPARTMENT_ID IS NULL" in upper or ("LEFT JOIN DEPARTMENTS" in upper and "IS NULL" in upper)


def test_display_all_departments_even_if_no_employee_exists():
    _, _, sql = guarded_pipeline("Display all departments even if no employee exists")
    upper = compact(sql)

    assert "FROM DEPARTMENTS" in upper
    assert "LEFT JOIN EMPLOYEES" in upper


def test_duplicate_email_addresses():
    _, _, sql = guarded_pipeline("Find duplicate email addresses")
    upper = compact(sql)

    assert "GROUP BY EMAIL" in upper
    assert "HAVING COUNT(*) > 1" in upper


def test_employee_name_with_department_name():
    _, _, sql = guarded_pipeline("Show employee name with department name")
    upper = compact(sql)

    assert "FROM EMPLOYEES" in upper
    assert "JOIN DEPARTMENTS" in upper
    assert "DEPARTMENT_NAME" in upper


def test_employees_with_job_titles():
    _, _, sql = guarded_pipeline("Show employees with their job titles")
    upper = compact(sql)

    assert "FROM EMPLOYEES" in upper
    assert "JOIN JOBS" in upper
    assert "JOB_TITLE" in upper


def test_random_employees_mysql():
    _, _, sql = guarded_pipeline("Show 3 random employees", "mysql")
    upper = compact(sql)

    assert "ORDER BY RAND()" in upper
    assert "LIMIT 3" in upper


def test_random_employees_postgresql():
    _, _, sql = guarded_pipeline("Show 3 random employees", "postgresql")
    upper = compact(sql)

    assert "ORDER BY RANDOM()" in upper
    assert "LIMIT 3" in upper


def test_ecommerce_top_products_by_revenue():
    _, _, sql = guarded_pipeline("Find the top 3 products by total sales revenue")
    upper = compact(sql)

    assert "FROM PRODUCTS" in upper
    assert "JOIN ORDER_ITEMS" in upper
    assert "SUM(OI.QUANTITY * OI.UNIT_PRICE)" in upper
    assert "ORDER BY TOTAL_REVENUE DESC" in upper
    assert "LIMIT 3" in upper


def test_university_students_enrolled_in_each_course():
    _, _, sql = guarded_pipeline("Show students enrolled in each course")
    upper = compact(sql)

    assert "FROM COURSES" in upper
    assert "LEFT JOIN ENROLLMENTS" in upper
    assert "COUNT(" in upper
    assert "GROUP BY" in upper


def test_healthcare_doctors_with_appointments():
    _, _, sql = guarded_pipeline("Show doctors with their appointments")
    upper = compact(sql)

    assert "FROM DOCTORS" in upper
    assert "JOIN APPOINTMENTS" in upper


def test_library_books_borrowed_by_each_member():
    _, _, sql = guarded_pipeline("Show books borrowed by each member")
    upper = compact(sql)

    assert "FROM MEMBERS" in upper
    assert "JOIN BORROW_RECORDS" in upper
    assert "JOIN BOOKS" in upper


def test_banking_account_balance_for_each_customer():
    _, _, sql = guarded_pipeline("Show account balance for each customer")
    upper = compact(sql)

    assert "FROM CUSTOMERS" in upper
    assert "JOIN ACCOUNTS" in upper
    assert "BALANCE" in upper


def test_booking_bookings_by_guest():
    _, _, sql = guarded_pipeline("Show bookings by guest")
    upper = compact(sql)

    assert "FROM GUESTS" in upper
    assert "JOIN BOOKINGS" in upper


def test_drop_table_is_unsafe_request():
    intent = process_prompt("DROP TABLE employees", TABLES, SCHEMA)

    assert intent["query_type"] == "UNSAFE_SCHEMA_OPERATION"
    assert intent.get("unsafe_schema_operation") is True


def test_unknown_domain_does_not_match_schema_pack():
    decision = detect_schema_pack("Show planets discovered by telescope", "auto")

    assert decision["unsupported"] is True
    assert decision["schema_pack"] == ""


def test_detected_domains_resolve_to_separate_internal_databases():
    banking = detect_schema_pack("Transfer 5000 from account ACC001 to account ACC002", "auto")
    booking = detect_schema_pack("Show bookings by guest", "auto")

    assert banking["schema_pack"] == "banking"
    assert booking["schema_pack"] == "booking"
    assert get_database_key("mysql", banking["schema_pack"]) != get_database_key("mysql", booking["schema_pack"])


def test_acceptance_prompts_detect_expected_internal_domains():
    cases = {
        "Find the top 5 highest-paid employees": "hr",
        "Show students enrolled in each course": "university",
        "Show doctors with their appointments": "healthcare",
        "Show books borrowed by members": "library",
        "Find the top 3 products by total sales revenue": "ecommerce",
        "Show all transactions for account id 1": "banking",
        "Show hotel bookings with guest names": "booking",
    }

    for prompt, expected_pack in cases.items():
        assert detect_schema_pack(prompt, "auto")["schema_pack"] == expected_pack


def test_mysql_schema_pack_database_names_match_internal_mapping():
    expected = {
        "hr": "test",
        "university": "en2sql_university",
        "healthcare": "en2sql_healthcare",
        "library": "en2sql_library",
        "ecommerce": "en2sql_ecommerce",
        "banking": "en2sql_banking",
        "booking": "en2sql_booking",
    }

    for pack, database_name in expected.items():
        assert Config.get_internal_database_name("mysql", pack) == database_name


def test_pipeline_returns_structured_recommended_and_alternative_queries():
    from app import _run_pipeline

    result = _run_pipeline("Show employee name with department name", "mysql", role="admin")

    assert result["dialect"] == "mysql"
    assert len(result["generated_queries"]) == 2
    assert result["recommended_query"]["label"] == "Option 1"
    assert result["recommended_query"]["title"] == "Recommended Query"
    assert result["recommended_query"]["sql"] == result["generated_queries"][0]
    assert result["recommended_query"]["why_best"]
    assert result["recommended_query"]["validation"]["is_valid"] is True
    assert result["alternative_query"]["label"] == "Option 2"
    assert result["alternative_query"]["title"] == "Alternative Query"
    assert result["alternative_query"]["sql"] == result["generated_queries"][1]
    assert result["alternative_query"]["why_less_favourable"]
    assert "CONCAT(" in result["alternative_query"]["sql"]


def test_postgresql_option_uses_selected_dialect_only():
    from app import _run_pipeline

    result = _run_pipeline("Show employee name with department name", "postgresql", role="admin")

    assert result["dialect"] == "postgresql"
    assert " || ' ' || " in result["alternative_query"]["sql"]
    assert "CONCAT(" not in result["alternative_query"]["sql"]
