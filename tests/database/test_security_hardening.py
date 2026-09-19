from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import ReleaseFixture, seed_release

APP_ROLE = "budget_test_app"


def _prepare_non_owner_app_role(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'budget_test_app') THEN
                        DROP OWNED BY budget_test_app;
                    END IF;
                END
                $$
                """
            )
        )
        connection.execute(text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
        connection.execute(
            text(f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION")
        )
        connection.execute(text(f"GRANT budget_app TO {APP_ROLE}"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
            )
        )


def _app_engine(engine: Engine) -> Engine:
    _prepare_non_owner_app_role(engine)
    return create_engine(engine.url.set(username=APP_ROLE, password=None), pool_pre_ping=True)


def _publish_one(engine: Engine, version: str) -> ReleaseFixture:
    with engine.begin() as connection:
        release = seed_release(connection, version=version)
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": release.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": release.release_id},
        )
    return release


def test_all_database_guard_functions_pin_search_path(
    postgres_engine: Engine,
) -> None:
    names = {
        "budget_enforce_release_status",
        "budget_protect_source_document",
        "budget_protect_source_fragment",
        "budget_guard_fragment_embedding",
        "budget_enforce_release_source",
        "budget_enforce_node_hierarchy",
        "budget_guard_node_amount",
        "budget_enforce_amount_provenance",
        "budget_guard_release_child",
        "budget_enforce_published_pointer",
    }
    with postgres_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT p.proname, p.proconfig
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname = ANY(:names)
                """
            ),
            {"names": list(names)},
        ).all()
    assert {row[0] for row in rows} == names
    assert all(
        any(setting == "search_path=pg_catalog, public" for setting in (row[1] or []))
        for row in rows
    )


def test_arbitrary_transition_guc_cannot_mutate_published_rows(
    postgres_engine: Engine,
) -> None:
    release = _publish_one(postgres_engine, "security-guc-1")
    app_engine = _app_engine(postgres_engine)
    try:
        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.release_transition', 'publish', false)")
            )
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("UPDATE budget_nodes SET name = 'tampered' WHERE id = :node_id"),
                    {"node_id": release.node_id},
                )
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("UPDATE releases SET status = 'published' WHERE id = :release_id"),
                    {"release_id": release.release_id},
                )
    finally:
        app_engine.dispose()


def test_non_owner_app_can_only_use_scoped_lifecycle_functions(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="security-function-2")
    app_engine = _app_engine(postgres_engine)
    try:
        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT budget_reject_release(:release_id)"),
                {"release_id": release.release_id},
            )
            assert (
                connection.execute(
                    text("SELECT status FROM releases WHERE id = :release_id"),
                    {"release_id": release.release_id},
                ).scalar_one()
                == "rejected"
            )
    finally:
        app_engine.dispose()


def test_mutation_started_before_publication_cannot_commit_after_it(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="security-race-3")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": release.release_id, "validator": "test"},
        )

    writer = postgres_engine.connect()
    writer_transaction = writer.begin()
    writer.execute(
        text(
            """
            INSERT INTO budget_amounts (id, node_id, metric, amount, unit, aggregation)
            VALUES (:id, :node_id, 'CP', 1, 'EUR', 'reported')
            """
        ),
        {"id": uuid4(), "node_id": release.node_id},
    )

    publication_started = threading.Event()
    publication_finished = threading.Event()
    publication_pid: list[int] = []
    publication_error: list[BaseException] = []

    def publish() -> None:
        try:
            with postgres_engine.begin() as connection:
                publication_pid.append(
                    connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
                )
                publication_started.set()
                connection.execute(
                    text("SELECT budget_publish_release(:release_id)"),
                    {"release_id": release.release_id},
                )
        except BaseException as error:  # asserted below
            publication_error.append(error)
        finally:
            publication_finished.set()

    thread = threading.Thread(target=publish)
    thread.start()
    assert publication_started.wait(timeout=5)

    deadline = time.monotonic() + 5
    blocked = False
    while time.monotonic() < deadline:
        with postgres_engine.connect() as connection:
            blocked = (
                connection.execute(
                    text(
                        """
                        SELECT wait_event_type = 'Lock'
                        FROM pg_stat_activity
                        WHERE pid <> pg_backend_pid() AND pid = :pid
                        """
                    ),
                    {"pid": publication_pid[0]},
                ).scalar_one_or_none()
                is True
            )
        if blocked:
            break
        time.sleep(0.01)

    writer_transaction.commit()
    writer.close()
    thread.join(timeout=5)

    assert blocked, "publication did not wait for the release-owned mutation"
    assert publication_finished.is_set()
    assert publication_error and isinstance(publication_error[0], DBAPIError)
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT status FROM releases WHERE id = :release_id"),
                {"release_id": release.release_id},
            ).scalar_one()
            == "validated"
        )


def test_release_owned_rows_cannot_be_reassigned_between_releases(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="security-cross-release-1")
        second = seed_release(connection, version="security-cross-release-2")
        connection.execute(
            text("UPDATE budget_nodes SET code = '002', slug = 'mission-002' WHERE id = :node_id"),
            {"node_id": second.node_id},
        )
        with pytest.raises(DBAPIError, match="release ownership"):
            connection.execute(
                text("UPDATE budget_nodes SET release_id = :new_release_id WHERE id = :node_id"),
                {"new_release_id": second.release_id, "node_id": first.node_id},
            )


def test_budget_node_identity_cannot_change_before_publication(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="security-node-id-7")
        node_id = connection.execute(
            text(
                """
                INSERT INTO budget_nodes (release_id, node_type, code, slug, name)
                VALUES (:release_id, 'mission', '002', 'mission-002', 'Second mission')
                RETURNING id
                """
            ),
            {"release_id": release.release_id},
        ).scalar_one()
        with pytest.raises(DBAPIError, match="identity is immutable"):
            connection.execute(
                text("UPDATE budget_nodes SET id = :new_id WHERE id = :node_id"),
                {"new_id": uuid4(), "node_id": node_id},
            )


def test_amount_provenance_release_ownership_cannot_change(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="security-provenance-cross-release-8")
        second = seed_release(
            connection, version="security-provenance-cross-release-9", with_source=False
        )
        with pytest.raises(DBAPIError, match="release ownership"):
            connection.execute(
                text(
                    """
                    UPDATE amount_source_fragments
                    SET amount_id = :new_amount_id
                    WHERE amount_id = :old_amount_id
                      AND source_fragment_id = :source_fragment_id
                    """
                ),
                {
                    "new_amount_id": second.amount_id,
                    "old_amount_id": first.amount_id,
                    "source_fragment_id": first.fragment_id,
                },
            )


def test_release_child_rows_cannot_be_reassigned_between_releases(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="security-child-cross-release-10")
        second = seed_release(
            connection, version="security-child-cross-release-11", with_source=False
        )
        validation_id = connection.execute(
            text(
                """
                INSERT INTO validations (
                    release_id, validation_type, result, blocking, validator
                ) VALUES (:release_id, 'fixture', 'passed', true, 'test')
                RETURNING id
                """
            ),
            {"release_id": first.release_id},
        ).scalar_one()
        with pytest.raises(DBAPIError, match="release ownership"):
            connection.execute(
                text("UPDATE validations SET release_id = :new_release_id WHERE id = :id"),
                {"new_release_id": second.release_id, "id": validation_id},
            )


def test_release_source_document_ownership_cannot_change(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="security-source-link-12")
        second = seed_release(connection, version="security-source-link-13", with_source=False)
        with pytest.raises(DBAPIError, match="release ownership"):
            connection.execute(
                text(
                    """
                    UPDATE release_source_documents
                    SET release_id = :new_release_id
                    WHERE release_id = :old_release_id
                      AND source_document_id = :source_document_id
                    """
                ),
                {
                    "new_release_id": second.release_id,
                    "old_release_id": first.release_id,
                    "source_document_id": first.document_id,
                },
            )


def test_budget_amount_release_ownership_cannot_change(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="security-amount-cross-release-1")
        second = seed_release(connection, version="security-amount-cross-release-2")
        target_node_id = connection.execute(
            text(
                """
                INSERT INTO budget_nodes (release_id, node_type, code, slug, name)
                VALUES (:release_id, 'mission', '002', 'mission-target', 'Target mission')
                RETURNING id
                """
            ),
            {"release_id": second.release_id},
        ).scalar_one()
        with pytest.raises(DBAPIError, match="release ownership"):
            connection.execute(
                text("UPDATE budget_amounts SET node_id = :node_id WHERE id = :amount_id"),
                {"node_id": target_node_id, "amount_id": first.amount_id},
            )


def test_release_identity_cannot_be_reassigned(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release_id = uuid4()
        connection.execute(
            text(
                """
                INSERT INTO releases (id, fiscal_year, legal_stage, version, source_snapshot_hash)
                VALUES (:id, 2026, 'PLF', 'security-release-id-6', :snapshot_hash)
                """
            ),
            {"id": release_id, "snapshot_hash": "f" * 64},
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE releases SET id = :new_id WHERE id = :release_id"),
                {"new_id": uuid4(), "release_id": release_id},
            )


def test_provenance_update_cannot_move_data_out_of_published_release(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        published = seed_release(connection, version="security-old-owner-4")
        embedding_id = uuid4()
        connection.execute(
            text(
                """
                INSERT INTO fragment_embeddings (id, source_fragment_id, model, embedding)
                VALUES (:id, :source_fragment_id, 'test', :embedding)
                """
            ),
            {
                "id": embedding_id,
                "source_fragment_id": published.fragment_id,
                "embedding": "[" + ",".join(["0"] * 1536) + "]",
            },
        )
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": published.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": published.release_id},
        )
    with postgres_engine.begin() as connection:
        draft = seed_release(connection, version="security-new-owner-5")

    with postgres_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text(
                """
                UPDATE amount_source_fragments
                SET amount_id = :new_amount_id
                WHERE amount_id = :old_amount_id
                  AND source_fragment_id = :old_fragment_id
                """
            ),
            {
                "new_amount_id": draft.amount_id,
                "old_amount_id": published.amount_id,
                "old_fragment_id": published.fragment_id,
            },
        )

    with postgres_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text(
                """
                UPDATE fragment_embeddings
                SET source_fragment_id = :new_fragment_id
                WHERE id = :id
                """
            ),
            {"id": embedding_id, "new_fragment_id": draft.fragment_id},
        )

    with postgres_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text(
                """
                UPDATE release_source_documents
                SET release_id = :new_release_id
                WHERE release_id = :old_release_id
                  AND source_document_id = :source_document_id
                """
            ),
            {
                "new_release_id": draft.release_id,
                "old_release_id": published.release_id,
                "source_document_id": published.document_id,
            },
        )
