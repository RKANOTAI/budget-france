from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from database.migrations.runner import downgrade, upgrade
from scripts.postgres_test_server import temporary_postgres


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    with temporary_postgres() as database_url:
        engine = create_engine(database_url)
        upgrade(engine)
        try:
            yield database_url
        finally:
            downgrade(engine)
            engine.dispose()


@pytest.fixture()
def postgres_engine(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    fragment_embeddings,
                    published_releases,
                    ingestion_runs,
                    validations,
                    anomalies,
                    amount_source_fragments,
                    budget_amounts,
                    budget_nodes,
                    release_source_documents,
                    source_fragments,
                    releases,
                    source_documents
                """
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
