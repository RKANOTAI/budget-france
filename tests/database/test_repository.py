from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from database.repository import ReleaseRepository
from tests.database.support import seed_release


def test_release_repository_creates_validates_and_publishes_with_provenance(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        repository = ReleaseRepository(session)
        release = repository.create_release(
            fiscal_year=2026,
            legal_stage="PLF",
            version="repository-1",
            source_snapshot_hash="1" * 64,
        )
        document_id = uuid4()
        fragment_id = uuid4()
        node_id = uuid4()
        amount_id = uuid4()
        session.execute(
            text(
                """
                INSERT INTO source_documents (
                    id, url, document_type, legal_stage, fiscal_year, source_version,
                    collected_at, sha256, media_type
                ) VALUES (:id, 'https://example.test/repository.csv', 'CSV', 'PLF', 2026,
                          'repository-1', '2026-01-01T00:00:00Z', :sha256, 'text/csv')
                """
            ),
            {"id": document_id, "sha256": "2" * 64},
        )
        session.execute(
            text(
                """
                INSERT INTO source_fragments (
                    id, source_document_id, fragment_hash, locator, content
                )
                VALUES (:id, :document_id, :fragment_hash, 'row=1', 'repository provenance')
                """
            ),
            {"id": fragment_id, "document_id": document_id, "fragment_hash": "3" * 64},
        )
        session.execute(
            text(
                """
                INSERT INTO budget_nodes (id, release_id, node_type, code, slug, name)
                VALUES (
                    :id, :release_id, 'mission', '001', 'repository-mission',
                    'Repository mission'
                )
                """
            ),
            {"id": node_id, "release_id": release.id},
        )
        session.execute(
            text(
                """
                INSERT INTO budget_amounts (id, node_id, metric, amount, unit, aggregation)
                VALUES (:id, :node_id, 'CP', :amount, 'EUR', 'reported')
                """
            ),
            {"id": amount_id, "node_id": node_id, "amount": Decimal("0")},
        )
        repository.register_provenance(amount_id, fragment_id)
        repository.validate_release(release.id, validator="repository-test")
        published = repository.publish_release(release.id)

        assert published == release.id
        assert (
            session.scalar(
                text("SELECT status FROM releases WHERE id = :release_id"),
                {"release_id": release.id},
            )
            == "published"
        )


def test_release_repository_search_is_stable_for_equal_rank_results(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="repository-search-1")
        connection.execute(
            text(
                """
                INSERT INTO budget_nodes (release_id, parent_id, node_type, code, slug, name)
                VALUES
                    (:release_id, :parent_id, 'programme', '002', 'programme-002',
                     'Défense opérationnelle'),
                    (:release_id, :parent_id, 'programme', '001', 'programme-001',
                     'Défense opérationnelle')
                """
            ),
            {"release_id": release.release_id, "parent_id": release.node_id},
        )

    with Session(postgres_engine) as session:
        repository = ReleaseRepository(session)
        first = repository.search_nodes(release.release_id, "défense")
        second = repository.search_nodes(release.release_id, "défense")

    assert [node.code for node in first] == ["001", "002"]
    assert [node.id for node in first] == [node.id for node in second]


def test_release_repository_lists_hierarchy_children_in_code_order(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="repository-tree-1")
        connection.execute(
            text(
                """
                INSERT INTO budget_nodes (release_id, parent_id, node_type, code, slug, name)
                VALUES
                    (:release_id, :parent_id, 'programme', '002', 'programme-002', 'Programme 2'),
                    (:release_id, :parent_id, 'programme', '001', 'programme-001', 'Programme 1')
                """
            ),
            {"release_id": release.release_id, "parent_id": release.node_id},
        )

    with Session(postgres_engine) as session:
        children = ReleaseRepository(session).list_children(
            release.release_id, parent_id=release.node_id
        )

    assert [node.code for node in children] == ["001", "002"]


def test_release_repository_returns_published_node_history_in_release_order(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="repository-history-1")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": first.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": first.release_id},
        )
    with postgres_engine.begin() as connection:
        second = seed_release(connection, version="repository-history-2")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": second.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": second.release_id},
        )

    with Session(postgres_engine) as session:
        history = ReleaseRepository(session).node_history(node_type="mission", code="001")

    assert [release.version for release, _node in history] == [
        "repository-history-1",
        "repository-history-2",
    ]
