from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from database.connection import create_database_engine
from database.settings import DatabaseSettings

from .service import DatabaseBudgetService


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create one pooled PostgreSQL engine per API process."""

    return create_database_engine(DatabaseSettings())


def get_budget_service() -> Iterator[DatabaseBudgetService]:
    """Yield a read-only transaction-scoped public budget service."""

    with Session(get_engine()) as session:
        yield DatabaseBudgetService(session)
