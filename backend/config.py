"""
Application configuration for the Natural Language to SQL Generator.

Centralizes environment variables and database connection settings so that
Flask routes and service modules stay free of hard-coded credentials.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except Exception:
    # python-dotenv is optional at import time; environment variables still work.
    pass


class Config:
    """Base configuration shared across environments."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))

    # Authentication
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "anjaliadhikari7890@gmail.com")
    OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))
    AUTH_USERS_FILE = os.getenv(
        "AUTH_USERS_FILE",
        os.path.join(os.path.dirname(__file__), "data", "auth_users.json"),
    )

    # SMTP for OTP and admin alert emails. Credentials must come from .env or
    # the environment; missing SMTP returns a clear API error instead of a
    # terminal-only OTP fallback.
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

    # Default database dialect when the client does not specify one
    DEFAULT_DB_TYPE = os.getenv("DEFAULT_DB_TYPE", "mysql")

    # Local-first model policy:
    # En2SQL defaults to rule_based mode and does not call external AI services.
    # Optional local_llama mode should call only a local endpoint and should never
    # send database rows, tokens, passwords, environment variables, or execution
    # results to any model.
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "rule_based")
    LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
    LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3")

    # MySQL connection (SQLAlchemy URI format)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "test")
    MYSQL_URL_EXAMPLE = "mysql+pymysql://root:YOUR_PASSWORD@localhost/test"
    MYSQL_URL = os.getenv("MYSQL_URL") or os.getenv("DATABASE_URL")

    # PostgreSQL connection
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE", "university_db")

    # Query history storage (simple JSON file for academic demo)
    HISTORY_FILE = os.getenv(
        "HISTORY_FILE",
        os.path.join(os.path.dirname(__file__), "data", "query_history.json"),
    )

    # Safety: block destructive statements unless explicitly allowed
    ALLOW_DESTRUCTIVE_QUERIES = (
        os.getenv("ALLOW_DESTRUCTIVE_QUERIES", "false").lower() == "true"
    )

    @classmethod
    def get_sqlalchemy_uri(cls, db_type: str) -> str:
        """
        Build a SQLAlchemy connection URI for the requested database type.

        Args:
            db_type: Either 'mysql' or 'postgresql'.

        Returns:
            A SQLAlchemy-compatible connection string.
        """
        db_type = (db_type or cls.DEFAULT_DB_TYPE).lower()

        if db_type == "mysql":
            if cls.MYSQL_URL:
                return cls.MYSQL_URL
            return (
                f"mysql+pymysql://{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}"
                f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
            )
        if db_type in ("postgresql", "postgres"):
            return (
                f"postgresql+psycopg2://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}"
                f"@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DATABASE}"
            )

        raise ValueError(f"Unsupported database type: {db_type}")
