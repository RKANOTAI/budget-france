from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from database.migrations.runner import current_revision, downgrade, upgrade
from scripts.postgres_test_server import temporary_postgres


def test_initial_migration_provisions_postgresql_schema_and_vector() -> None:
    with temporary_postgres() as database_url:
        engine = create_engine(database_url)
        try:
            upgrade(engine)
            with engine.connect() as connection:
                extension = connection.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                ).scalar_one_or_none()
                tables = connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name IN ('source_documents', 'releases', 'budget_nodes')
                        """
                    )
                ).scalar_one()
            assert extension == "vector"
            assert tables == 3
            assert current_revision(engine) == "0001_postgresql_provenance"

            downgrade(engine)
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                    ).scalar_one()
                    == 1
                )
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM pg_extension WHERE extname = 'pgcrypto'")
                    ).scalar_one()
                    == 1
                )
                assert (
                    connection.execute(
                        text(
                            """
                            SELECT count(*)
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = 'budget_nodes'
                            """
                        )
                    ).scalar_one()
                    == 0
                )

            upgrade(engine)
            assert current_revision(engine) == "0001_postgresql_provenance"
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                    ).scalar_one()
                    == "vector"
                )
        finally:
            downgrade(engine)
            engine.dispose()


def test_downgrade_refuses_unrelated_dependents_without_cascade() -> None:
    with temporary_postgres() as database_url:
        engine = create_engine(database_url)
        try:
            upgrade(engine)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE unrelated_release_reference (
                            release_id uuid PRIMARY KEY REFERENCES public.releases(id)
                        )
                        """
                    )
                )
            with pytest.raises(DBAPIError):
                downgrade(engine)
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text(
                            """
                            SELECT count(*) FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = 'releases'
                            """
                        )
                    ).scalar_one()
                    == 1
                )
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE unrelated_release_reference"))
            downgrade(engine)
        finally:
            engine.dispose()
