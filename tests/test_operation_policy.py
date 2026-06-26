"""Tests for En2SQL operation permissions and hidden schema detection."""

from pathlib import Path

from app import _run_pipeline, app
from auth import create_token
from validator import classify_sql_operation, validate_query


def test_user_update_generation_is_access_denied():
    result = _run_pipeline("Update employee salary to 50000 where employee id is 1", "mysql", role="user")

    assert result["query_type"] == "ACCESS_DENIED_OPERATION"
    assert result["generated_queries"] == []
    assert result["selected_query"] == ""


def test_admin_update_generation_has_where_and_warning():
    result = _run_pipeline("Update employee salary to 50000 where employee id is 1", "mysql", role="admin")

    assert result["query_type"] == "UPDATE"
    assert "UPDATE employees" in result["selected_query"]
    assert "WHERE employee_id = 1" in result["selected_query"]
    assert "requires confirmation" in result["warning"].lower()


def test_admin_delete_generation_has_where_and_warning():
    result = _run_pipeline("Delete employee where employee id is 1", "mysql", role="admin")

    assert result["query_type"] == "DELETE"
    assert "DELETE FROM employees" in result["selected_query"]
    assert "WHERE employee_id = 1" in result["selected_query"]
    assert "requires confirmation" in result["warning"].lower()


def test_admin_delete_all_employees_is_blocked():
    result = _run_pipeline("Delete all employees", "mysql", role="admin")

    assert result["query_type"] == "UNSAFE_REQUEST"
    assert result["generated_queries"] == []
    assert "specific condition" in result["warning"].lower()


def test_drop_table_blocked_for_admin_and_user():
    for role in ("admin", "user"):
        result = _run_pipeline("Drop employees table", "mysql", role=role)
        assert result["query_type"] == "UNSAFE_SCHEMA_OPERATION"
        assert result["generated_queries"] == []


def test_create_table_returns_guidance():
    result = _run_pipeline("Create table students", "mysql", role="admin")

    assert result["query_type"] == "SCHEMA_CREATION_GUIDANCE"
    assert result["generated_queries"] == []
    assert "schema pack" in result["suggestion"].lower()


def test_validator_blocks_update_delete_without_where():
    assert not validate_query("UPDATE employees SET salary = 50000;")["validation"]["valid"]
    assert not validate_query("DELETE FROM employees;")["validation"]["valid"]


def test_classifier_ignores_comments_and_case():
    assert classify_sql_operation("  -- comment\nselect * from employees;") == "SELECT"
    assert classify_sql_operation("/* x */ CREATE USER demo;") == "CREATE_USER"


def test_admin_execute_select_allowed_but_modification_requires_confirmation():
    token = create_token({"email": "admin@example.com", "role": "admin", "name": "Admin"})
    client = app.test_client()

    select_response = client.post(
        "/api/execute",
        json={"query": "SELECT * FROM employees;", "database_type": "mysql"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert select_response.status_code in (200, 500)

    update_response = client.post(
        "/api/execute",
        json={"query": "UPDATE employees SET salary = 50000 WHERE employee_id = 1;", "database_type": "mysql"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_response.status_code == 400
    assert update_response.get_json()["error"] == "Confirmation required"


def test_user_execute_is_forbidden_even_if_manual():
    token = create_token({"email": "user@example.com", "role": "user", "name": "User"})
    client = app.test_client()

    response = client.post(
        "/api/execute",
        json={"query": "SELECT * FROM employees;", "database_type": "mysql"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_app_has_no_schema_dropdown_or_auto_detect_text():
    html = Path("frontend/app.html").read_text()

    assert 'id="schema-pack"' not in html
    assert "Auto Detect" not in html


def test_internal_schema_detection_still_generates_hr_and_ecommerce():
    hr = _run_pipeline("Find the top 5 highest-paid employees", "mysql", role="user")
    ecommerce = _run_pipeline("Find the top 3 products by total sales revenue", "mysql", role="user")

    assert hr["query_type"] == "SELECT"
    assert "FROM employees" in hr["selected_query"]
    assert ecommerce["query_type"] == "SELECT"
    assert "FROM products" in ecommerce["selected_query"]
