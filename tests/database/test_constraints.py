from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import seed_release


def _assert_db_rejected(engine: Engine, statement: str, parameters: dict[str, object]) -> None:
    with engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(text(statement), parameters)


def test_source_document_url_hash_and_year_checks_are_database_constraints(
    postgres_engine: Engine,
) -> None:
    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO source_documents (
            url, document_type, legal_stage, fiscal_year, source_version,
            collected_at, sha256, media_type
        ) VALUES ('ftp://example.test/bad', 'CSV', 'PLF', 2026, 'bad-url',
                  '2026-01-01T00:00:00Z', :sha256, 'text/csv')
        """,
        {"sha256": "a" * 64},
    )
    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO source_documents (
            url, document_type, legal_stage, fiscal_year, source_version,
            collected_at, sha256, media_type
        ) VALUES ('https://example.test/bad-hash', 'CSV', 'PLF', 2026, 'bad-hash',
                  '2026-01-01T00:00:00Z', :sha256, 'text/csv')
        """,
        {"sha256": "not-a-sha"},
    )
    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO source_documents (
            url, document_type, legal_stage, fiscal_year, source_version,
            collected_at, sha256, media_type
        ) VALUES ('https://example.test/bad-year', 'CSV', 'PLF', 2024, 'bad-year',
                  '2026-01-01T00:00:00Z', :sha256, 'text/csv')
        """,
        {"sha256": "b" * 64},
    )


def test_source_document_urls_cannot_contain_empty_hosts_or_credentials(
    postgres_engine: Engine,
) -> None:
    for url in (
        "https://?query=1",
        "https://user:secret@example.test/document",
        "https://example.test/path with space",
        "https://example..test/document",
        "https://example.test./document",
    ):
        _assert_db_rejected(
            postgres_engine,
            """
            INSERT INTO source_documents (
                url, document_type, legal_stage, fiscal_year, source_version,
                collected_at, sha256, media_type
            ) VALUES (:url, 'CSV', 'PLF', 2026, :source_version,
                      '2026-01-01T00:00:00Z', :sha256, 'text/csv')
            """,
            {
                "url": url,
                "source_version": f"bad-url-{url[8:12]}",
                "sha256": "c" * 64,
            },
        )


def test_budget_tree_rejects_invalid_parent_level_and_cross_release_parent(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="tree-1")
        second = seed_release(connection, version="tree-2")
        programme_id = uuid4()
        connection.execute(
            text(
                """
                INSERT INTO budget_nodes (
                    id, release_id, parent_id, node_type, code, slug, name
                ) VALUES (
                    :id, :release_id, :parent_id, 'programme', '010',
                    'programme-010', 'Programme'
                )
                """
            ),
            {"id": programme_id, "release_id": first.release_id, "parent_id": first.node_id},
        )

    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO budget_nodes (release_id, parent_id, node_type, code, slug, name)
        VALUES (:release_id, :parent_id, 'action', '011', 'action-011', 'Action')
        """,
        {"release_id": second.release_id, "parent_id": first.node_id},
    )
    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO budget_nodes (release_id, parent_id, node_type, code, slug, name)
        VALUES (:release_id, :parent_id, 'action', '012', 'action-012', 'Action')
        """,
        {"release_id": first.release_id, "parent_id": first.node_id},
    )
    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO budget_nodes (release_id, parent_id, node_type, code, slug, name)
        VALUES (:release_id, :parent_id, 'programme', '010', 'programme-duplicate', 'Duplicate')
        """,
        {"release_id": first.release_id, "parent_id": first.node_id},
    )


def test_error_anomalies_must_be_blocking(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="anomaly-1")
    _assert_db_rejected(
        postgres_engine,
        """
        INSERT INTO anomalies (release_id, code, severity, message, blocked)
        VALUES (:release_id, 'ERROR', 'error', 'not blocked', false)
        """,
        {"release_id": release.release_id},
    )
