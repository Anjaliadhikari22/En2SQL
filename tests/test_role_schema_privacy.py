"""Role-based schema/table/column privacy tests."""

from app import _run_pipeline, app
from auth import create_token


FORBIDDEN_USER_WORDS = {
    "employees",
    "departments",
    "jobs",
    "locations",
    "countries",
    "regions",
    "dependents",
    "required tables",
    "available hr schema",
}


def _response_text(response: dict) -> str:
    parts = []
    for key in ("explanation", "optimization_suggestion", "suggestion", "warning", "expected_output"):
        value = response.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts).lower()


def test_user_unsupported_domain_hides_schema_details():
    result = _run_pipeline("Show planets discovered by telescope", "mysql", role="user")

    assert result["query_type"] == "UNSUPPORTED_DOMAIN"
    assert result["affected_tables"] == []
    assert result["affected_columns"] == []
    assert "schema_pack" not in result
    assert "detected_domain" not in result
    assert "required_tables" not in result
    text = _response_text(result)
    assert "contact the admin" in text
    assert not any(word in text for word in FORBIDDEN_USER_WORDS)


def test_user_supported_join_hides_affected_tables_and_columns():
    result = _run_pipeline("Show employee name with department name", "mysql", role="user")

    assert result["query_type"] == "SELECT"
    assert result["selected_query"]
    assert result["affected_tables"] == []
    assert result["affected_columns"] == []
    assert "exact row counts and schema details are restricted" in result["expected_output"].lower()


def test_admin_supported_join_keeps_affected_tables_and_columns():
    result = _run_pipeline("Show employee name with department name", "mysql", role="admin")

    assert result["query_type"] == "SELECT"
    assert result["affected_tables"]
    assert result["affected_columns"]
    assert "employees" in [item.lower() for item in result["affected_tables"]]


def test_user_manual_schema_endpoint_is_forbidden():
    token = create_token({"email": "user@example.com", "role": "user", "name": "User"})
    response = app.test_client().get(
        "/api/schema",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
