from __future__ import annotations

from sqlalchemy import Engine, create_engine

from .settings import DatabaseSettings


def create_database_engine(settings: DatabaseSettings | None = None) -> Engine:
    """Create a PostgreSQL engine; SQLite URLs are intentionally rejected."""

    resolved = settings or DatabaseSettings()
    url = resolved.sqlalchemy_url
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("database engine must use PostgreSQL with psycopg 3")
    return create_engine(url, pool_pre_ping=True)
