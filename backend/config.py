"""
Application configuration for the Natural Language to SQL Generator.

Centralizes environment variables and database connection settings so that
Flask routes and service modules stay free of hard-coded credentials.
"""

import os


class Config:
    """Base configuration shared across environments."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    # Default database dialect when the client does not specify one
    DEFAULT_DB_TYPE = os.getenv("DEFAULT_DB_TYPE", "mysql")

    # MySQL connection (SQLAlchemy URI format)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "test")
    MYSQL_URL_EXAMPLE = "mysql+pymysql://root:YOUR_PASSWORD@localhost/test"
    MYSQL_URL = os.getenv("MYSQL_URL")

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
