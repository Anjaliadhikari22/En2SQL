"""
Database connection layer using SQLAlchemy.

Executes queries against MySQL/PostgreSQL when connected. Falls back to
small HR demo data when no database is available.
"""

import re
from contextlib import contextmanager
from typing import Any, Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import Config

# Cache engines and connection status per internal database.
_engines: dict[tuple[str, str], Engine] = {}
_connection_cache: dict[tuple[str, str], bool] = {}


def _normalize_db_type(db_type: str) -> str:
    """Normalize 'postgres' → 'postgresql'."""
    db_type = (db_type or Config.DEFAULT_DB_TYPE).lower()
    return "postgresql" if db_type in ("postgres", "postgresql") else "mysql"


def _normalize_schema_pack(schema_pack: str = "hr") -> str:
    """Normalize the internal database/schema-pack identifier."""
    raw = (schema_pack or "hr").strip().lower().replace("_", "-")
    aliases = {
        "auto": "hr",
        "auto-detect": "hr",
        "autodetect": "hr",
        "e-commerce": "ecommerce",
        "hotel": "booking",
        "hotel-booking": "booking",
        "hotel/booking": "booking",
        "human-resources": "hr",
    }
    return aliases.get(raw, raw)


def get_database_key(db_type: str, schema_pack: str = "hr") -> str:
    """Return a stable key that identifies the selected internal database."""
    db_type = _normalize_db_type(db_type)
    schema_pack = _normalize_schema_pack(schema_pack)
    database_name = Config.get_internal_database_name(db_type, schema_pack)
    return f"{db_type}:{schema_pack}:{database_name}"


def get_engine(db_type: str, schema_pack: str = "hr") -> Engine:
    """Return (and cache) a SQLAlchemy engine for the selected internal database."""
    db_type = _normalize_db_type(db_type)
    schema_pack = _normalize_schema_pack(schema_pack)
    key = (db_type, schema_pack)
    if key not in _engines:
        uri = Config.get_sqlalchemy_uri(db_type, schema_pack)
        _engines[key] = create_engine(
            uri,
            echo=Config.DEBUG,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
    return _engines[key]


def is_db_connected(db_type: str, schema_pack: str = "hr") -> bool:
    """
    Check whether the database is reachable (cached for performance).

    Returns False on connection failure — never raises.
    """
    db_type = _normalize_db_type(db_type)
    schema_pack = _normalize_schema_pack(schema_pack)
    key = (db_type, schema_pack)
    if key in _connection_cache:
        return _connection_cache[key]

    try:
        engine = get_engine(db_type, schema_pack)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _connection_cache[key] = True
    except Exception:
        _connection_cache[key] = False

    return _connection_cache[key]


def get_session_factory(db_type: str, schema_pack: str = "hr") -> sessionmaker:
    """Create a session factory bound to the selected internal database."""
    return sessionmaker(bind=get_engine(db_type, schema_pack), autocommit=False, autoflush=False)


@contextmanager
def get_session(db_type: str, schema_pack: str = "hr") -> Generator[Session, None, None]:
    """Context manager that yields a SQLAlchemy session and closes it safely."""
    SessionLocal = get_session_factory(db_type, schema_pack)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Demo-mode sample data returned when no real database is connected
# ---------------------------------------------------------------------------

DEMO_EMPLOYEES = [
    {"employee_id": 100, "first_name": "Steven", "last_name": "King", "email": "steven.king@sqltutorial.org", "salary": 24000.00, "department_id": 9},
    {"employee_id": 101, "first_name": "Neena", "last_name": "Kochhar", "email": "neena.kochhar@sqltutorial.org", "salary": 17000.00, "department_id": 9},
    {"employee_id": 103, "first_name": "Alexander", "last_name": "Hunold", "email": "alexander.hunold@sqltutorial.org", "salary": 9000.00, "department_id": 6},
    {"employee_id": 145, "first_name": "John", "last_name": "Russell", "email": "john.russell@sqltutorial.org", "salary": 14000.00, "department_id": 8},
    {"employee_id": 200, "first_name": "Jennifer", "last_name": "Whalen", "email": "jennifer.whalen@sqltutorial.org", "salary": 4400.00, "department_id": 1},
]

DEMO_DEPARTMENTS = [
    {"department_id": 1, "department_name": "Administration", "location_id": 1700},
    {"department_id": 6, "department_name": "IT", "location_id": 1400},
    {"department_id": 8, "department_name": "Sales", "location_id": 2500},
    {"department_id": 9, "department_name": "Executive", "location_id": 1700},
]

DEMO_JOBS = [
    {"job_id": 4, "job_title": "President"},
    {"job_id": 9, "job_title": "Programmer"},
    {"job_id": 15, "job_title": "Sales Manager"},
]


def _execute_demo_query(sql: str) -> dict[str, Any]:
    """
    Simulate query execution with realistic demo rows.

    Pattern-matches the SQL string to return appropriate sample data.
    """
    upper = sql.upper()

    # SELECT employees with salary filter
    if "EMPLOYEES" in upper and "SELECT" in upper:
        rows = DEMO_EMPLOYEES
        salary_match = re.search(r"SALARY\s*>\s*(\d+(?:\.\d+)?)", upper)
        if salary_match:
            threshold = float(salary_match.group(1))
            rows = [r for r in DEMO_EMPLOYEES if float(r["salary"]) > threshold]
        limit_match = re.search(r"LIMIT\s+(\d+)", upper)
        if limit_match:
            rows = rows[: int(limit_match.group(1))]
        columns = list(rows[0].keys()) if rows else ["employee_id", "first_name", "last_name", "email", "salary", "department_id"]
        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
            "mode": "demo",
        }

    if "DEPARTMENTS" in upper and "SELECT" in upper:
        rows = DEMO_DEPARTMENTS
        columns = list(rows[0].keys()) if rows else ["department_id", "department_name", "location_id"]
        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
            "mode": "demo",
        }

    if "JOBS" in upper and "SELECT" in upper:
        rows = DEMO_JOBS
        columns = list(rows[0].keys()) if rows else ["job_id", "job_title"]
        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
            "mode": "demo",
        }

    # Write operations — report affected rows without modifying anything
    if upper.strip().startswith("UPDATE"):
        return {
            "success": True,
            "columns": [],
            "rows": [],
            "row_count": 42,
            "error": None,
            "mode": "demo",
            "message": "Demo mode: UPDATE simulated — approximately 42 rows would be modified.",
        }

    if upper.strip().startswith("DELETE"):
        return {
            "success": True,
            "columns": [],
            "rows": [],
            "row_count": 12,
            "error": None,
            "mode": "demo",
            "message": "Demo mode: DELETE simulated — approximately 12 rows would be deleted.",
        }

    if "BEGIN" in upper or "COMMIT" in upper or "TRANSFER" in upper:
        return {
            "success": True,
            "columns": [],
            "rows": [],
            "row_count": 2,
            "error": None,
            "mode": "demo",
            "message": "Demo mode: TRANSACTION simulated — approximately 2 rows would be modified.",
        }

    # Generic SELECT fallback
    if "SELECT" in upper:
        return {
            "success": True,
            "columns": ["result"],
            "rows": [{"result": "Demo mode — no live database connected."}],
            "row_count": 1,
            "error": None,
            "mode": "demo",
        }

    return {
        "success": True,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "error": None,
        "mode": "demo",
        "message": "Demo mode: query acknowledged but no matching demo data.",
    }


def execute_query(
    db_type: str,
    sql: str,
    params: Optional[dict[str, Any]] = None,
    fetch: bool = True,
    schema_pack: str = "hr",
) -> dict[str, Any]:
    """
    Execute a SQL statement against the real DB, or return demo data on failure.

    Returns:
        Dict with keys: success, rows, row_count, columns, error, mode.
    """
    db_type = _normalize_db_type(db_type)
    schema_pack = _normalize_schema_pack(schema_pack)

    # Demo fallback when database is not connected
    if not is_db_connected(db_type, schema_pack):
        result = _execute_demo_query(sql)
        result["mode"] = "demo"
        result["database_key"] = get_database_key(db_type, schema_pack)
        return result

    result_payload: dict[str, Any] = {
        "success": False,
        "rows": [],
        "row_count": 0,
        "columns": [],
        "error": None,
        "mode": "live",
    }

    try:
        with get_session(db_type, schema_pack) as session:
            cursor_result = session.execute(text(sql), params or {})

            if fetch and cursor_result.returns_rows:
                rows = cursor_result.fetchall()
                result_payload["rows"] = [dict(row._mapping) for row in rows]
                result_payload["row_count"] = len(rows)
                result_payload["columns"] = list(cursor_result.keys())
            else:
                result_payload["row_count"] = cursor_result.rowcount or 0

            result_payload["success"] = True
    except Exception as exc:
        # Fall back to demo mode if live execution fails
        result_payload["error"] = str(exc)
        demo = _execute_demo_query(sql)
        demo["error"] = f"Live DB error: {exc}. Showing demo data instead."
        demo["database_key"] = get_database_key(db_type, schema_pack)
        return demo

    result_payload["database_key"] = get_database_key(db_type, schema_pack)
    return result_payload


def execute_count_query(
    db_type: str,
    sql: str,
    params: Optional[dict[str, Any]] = None,
    schema_pack: str = "hr",
) -> Optional[int]:
    """Execute a COUNT(*) query against the live DB; return None in demo/failure."""
    db_type = _normalize_db_type(db_type)
    schema_pack = _normalize_schema_pack(schema_pack)
    if not is_db_connected(db_type, schema_pack):
        return None
    try:
        with get_session(db_type, schema_pack) as session:
            value = session.execute(text(sql), params or {}).scalar()
            return int(value) if value is not None else None
    except Exception:
        return None


def test_connection(db_type: str, schema_pack: str = "hr") -> dict[str, Any]:
    """Ping the database to verify connectivity."""
    db_type = _normalize_db_type(db_type)
    schema_pack = _normalize_schema_pack(schema_pack)
    connected = is_db_connected(db_type, schema_pack)
    return {
        "connected": connected,
        "db_type": db_type,
        "schema_pack": schema_pack,
        "database_name": Config.get_internal_database_name(db_type, schema_pack),
        "database_key": get_database_key(db_type, schema_pack),
        "mode": "live" if connected else "demo",
    }
