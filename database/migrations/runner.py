from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _config(engine: Engine) -> Config:
    config = Config(str(_REPOSITORY_ROOT / "database" / "alembic.ini"))
    config.set_main_option("script_location", str(_REPOSITORY_ROOT / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Apply migrations to ``revision`` using the caller's PostgreSQL engine."""

    command.upgrade(_config(engine), revision)


def downgrade(engine: Engine, revision: str = "base") -> None:
    """Revert migrations to ``revision`` using the caller's PostgreSQL engine."""

    command.downgrade(_config(engine), revision)


def current_revision(engine: Engine) -> Any:
    """Return Alembic's current revision for diagnostics and integration tests."""

    from alembic.runtime.migration import MigrationContext

    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()
