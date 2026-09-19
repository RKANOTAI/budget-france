from __future__ import annotations

from database.connection import create_database_engine
from database.migrations.runner import upgrade
from database.settings import DatabaseSettings


def main() -> None:
    engine = create_database_engine(DatabaseSettings())
    try:
        upgrade(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
