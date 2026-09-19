from __future__ import annotations

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import ReleaseFixture, seed_release


def _publish_one(engine: Engine) -> ReleaseFixture:
    with engine.begin() as connection:
        release = seed_release(connection, version="immutable-1")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": release.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": release.release_id},
        )
        return release


def _assert_mutation_rejected(
    engine: Engine, statement: str, parameters: dict[str, object]
) -> None:
    with engine.begin() as connection:
        try:
            connection.execute(text(statement), parameters)
        except DBAPIError as error:
            assert "immutable" in str(error) or "cannot" in str(error)
        else:
            raise AssertionError("published release mutation unexpectedly succeeded")


def test_published_release_facts_provenance_and_release_are_immutable(
    postgres_engine: Engine,
) -> None:
    release = _publish_one(postgres_engine)
    _assert_mutation_rejected(
        postgres_engine,
        "UPDATE releases SET version = 'changed' WHERE id = :release_id",
        {"release_id": release.release_id},
    )
    _assert_mutation_rejected(
        postgres_engine,
        "UPDATE budget_nodes SET name = 'changed' WHERE id = :node_id",
        {"node_id": release.node_id},
    )
    _assert_mutation_rejected(
        postgres_engine,
        "UPDATE budget_amounts SET amount = amount WHERE id = :amount_id",
        {"amount_id": release.amount_id},
    )
    _assert_mutation_rejected(
        postgres_engine,
        "UPDATE source_fragments SET content = 'changed' WHERE id = :fragment_id",
        {"fragment_id": release.fragment_id},
    )
    _assert_mutation_rejected(
        postgres_engine,
        "UPDATE source_documents SET media_type = 'changed' WHERE id = :document_id",
        {"document_id": release.document_id},
    )
    _assert_mutation_rejected(
        postgres_engine,
        "DELETE FROM release_source_documents WHERE release_id = :release_id",
        {"release_id": release.release_id},
    )
    _assert_mutation_rejected(
        postgres_engine,
        "DELETE FROM amount_source_fragments WHERE amount_id = :amount_id",
        {"amount_id": release.amount_id},
    )


def test_publication_transition_does_not_leave_a_mutation_bypass_in_transaction(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = _publish_one_in_connection(connection)
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE budget_nodes SET name = 'changed' WHERE id = :node_id"),
                {"node_id": release.node_id},
            )


def _publish_one_in_connection(connection: Connection) -> ReleaseFixture:
    release = seed_release(connection, version="immutable-2")
    connection.execute(
        text("SELECT budget_validate_release(:release_id, :validator)"),
        {"release_id": release.release_id, "validator": "test"},
    )
    connection.execute(
        text("SELECT budget_publish_release(:release_id)"),
        {"release_id": release.release_id},
    )
    return release
