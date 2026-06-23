"""Schema introspection module for the HR dataset."""

from typing import Any

from sqlalchemy import inspect

from database import get_engine, is_db_connected


HR_RELATIONSHIPS: list[dict[str, str]] = [
    {"from": "countries.region_id", "to": "regions.region_id"},
    {"from": "locations.country_id", "to": "countries.country_id"},
    {"from": "departments.location_id", "to": "locations.location_id"},
    {"from": "employees.job_id", "to": "jobs.job_id"},
    {"from": "employees.department_id", "to": "departments.department_id"},
    {"from": "employees.manager_id", "to": "employees.employee_id"},
    {"from": "dependents.employee_id", "to": "employees.employee_id"},
]


HR_SCHEMA: dict[str, Any] = {
    "source": "hr",
    "relationships": HR_RELATIONSHIPS,
    "tables": {
        "regions": {
            "description": "Geographic regions",
            "columns": ["region_id", "region_name"],
            "primary_key": ["region_id"],
        },
        "countries": {
            "description": "Countries mapped to regions",
            "columns": ["country_id", "country_name", "region_id"],
            "primary_key": ["country_id"],
        },
        "locations": {
            "description": "Office locations mapped to countries",
            "columns": ["location_id", "street_address", "postal_code", "city", "state_province", "country_id"],
            "primary_key": ["location_id"],
        },
        "jobs": {
            "description": "Job titles and salary bands",
            "columns": ["job_id", "job_title", "min_salary", "max_salary"],
            "primary_key": ["job_id"],
        },
        "departments": {
            "description": "Departments mapped to locations",
            "columns": ["department_id", "department_name", "location_id"],
            "primary_key": ["department_id"],
        },
        "employees": {
            "description": "Employee records with job, manager, department, hire date, and salary",
            "columns": [
                "employee_id", "first_name", "last_name", "email", "phone_number",
                "hire_date", "job_id", "salary", "manager_id", "department_id",
            ],
            "primary_key": ["employee_id"],
        },
        "dependents": {
            "description": "Employee dependents",
            "columns": ["dependent_id", "first_name", "last_name", "relationship", "employee_id"],
            "primary_key": ["dependent_id"],
        },
    },
}


def get_demo_schema() -> dict[str, Any]:
    """Return the built-in HR schema used when live DB introspection is unavailable."""
    return HR_SCHEMA.copy()


def read_schema_from_db(db_type: str) -> dict[str, Any]:
    """Introspect the live database and return a schema dictionary."""
    engine = get_engine(db_type)
    inspector = inspect(engine)
    schema: dict[str, Any] = {"source": "database", "relationships": HR_RELATIONSHIPS, "tables": {}}

    for table_name in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        pk = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        schema["tables"][table_name] = {
            "columns": columns,
            "primary_key": pk,
        }

    return schema


def load_schema(db_type: str) -> dict[str, Any]:
    """Load schema from live DB when connected; otherwise use demo schema."""
    if is_db_connected(db_type):
        try:
            return read_schema_from_db(db_type)
        except Exception:
            pass
    return get_demo_schema()


def get_schema_details() -> dict[str, Any]:
    """Return full HR schema details for GET /api/schema."""
    schema = load_schema("mysql")
    tables_detail = []
    for name, info in schema["tables"].items():
        tables_detail.append({
            "name": name,
            "description": info.get("description", ""),
            "columns": info["columns"],
            "primary_key": info.get("primary_key", []),
        })

    return {
        "mode": "demo" if not is_db_connected("mysql") and not is_db_connected("postgresql") else "live",
        "tables": tables_detail,
        "relationships": schema.get("relationships", HR_RELATIONSHIPS),
        "table_count": len(tables_detail),
    }


def get_table_names(schema: dict[str, Any]) -> list[str]:
    """Return sorted list of table names."""
    return sorted(schema.get("tables", {}).keys())


def get_columns_for_table(schema: dict[str, Any], table_name: str) -> list[str]:
    """Return column names for a given table."""
    for key, info in schema.get("tables", {}).items():
        if key.lower() == table_name.lower():
            return info.get("columns", [])
    return []
