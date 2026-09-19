from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import seed_release


def _add_node(
    connection: Connection,
    *,
    release_id: UUID,
    parent_id: UUID | None,
    node_type: str,
    code: str,
    amount: Decimal | None,
) -> UUID:
    node_id = uuid4()
    connection.execute(
        text(
            """
            INSERT INTO budget_nodes (id, release_id, parent_id, node_type, code, slug, name)
            VALUES (:id, :release_id, :parent_id, :node_type, :code, :slug, :name)
            """
        ),
        {
            "id": node_id,
            "release_id": release_id,
            "parent_id": parent_id,
            "node_type": node_type,
            "code": code,
            "slug": f"{node_type}-{code}",
            "name": f"{node_type} {code}",
        },
    )
    amount_id = uuid4()
    if amount is not None:
        connection.execute(
            text(
                """
                INSERT INTO budget_amounts (id, node_id, metric, amount, unit, aggregation)
                VALUES (:id, :node_id, 'AE', :amount, 'EUR', 'reported')
                """
            ),
            {"id": amount_id, "node_id": node_id, "amount": amount},
        )
        fragment_id = connection.execute(
            text(
                """
                SELECT sf.id
                FROM source_fragments sf
                JOIN source_documents sd ON sd.id = sf.source_document_id
                JOIN releases r ON r.fiscal_year = sd.fiscal_year
                    AND r.legal_stage = sd.legal_stage
                WHERE r.id = :release_id
                ORDER BY sf.id
                LIMIT 1
                """
            ),
            {"release_id": release_id},
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO amount_source_fragments (amount_id, source_fragment_id)
                VALUES (:amount_id, :fragment_id)
                """
            ),
            {"amount_id": amount_id, "fragment_id": fragment_id},
        )
    return node_id


def _assert_validation_rejected(engine: Engine, release_id: UUID, message: str) -> None:
    with engine.begin() as connection:
        try:
            connection.execute(
                text("SELECT budget_validate_release(:release_id, :validator)"),
                {"release_id": release_id, "validator": "test"},
            )
        except DBAPIError as error:
            assert message in str(error)
        else:
            raise AssertionError("invalid release unexpectedly validated")


def test_every_public_node_requires_a_present_amount(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="publish-node-amount-1")
        _add_node(
            connection,
            release_id=release.release_id,
            parent_id=release.node_id,
            node_type="programme",
            code="146",
            amount=None,
        )
    _assert_validation_rejected(postgres_engine, release.release_id, "without a budget amount")


def test_recursive_signed_totals_reconcile_and_preserve_metric_absence(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="publish-totals-2")
        connection.execute(
            text("UPDATE budget_amounts SET amount = -10 WHERE id = :id"),
            {"id": release.amount_id},
        )
        programme_id = _add_node(
            connection,
            release_id=release.release_id,
            parent_id=release.node_id,
            node_type="programme",
            code="146",
            amount=Decimal("-9"),
        )
        _add_node(
            connection,
            release_id=release.release_id,
            parent_id=programme_id,
            node_type="action",
            code="01",
            amount=Decimal("-9"),
        )
    _assert_validation_rejected(postgres_engine, release.release_id, "reconcile")


def test_missing_source_document_attachment_blocks_publication(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="publish-document-attachment-3")
        connection.execute(
            text(
                """
                DELETE FROM release_source_documents
                WHERE release_id = :release_id AND source_document_id = :document_id
                """
            ),
            {"release_id": release.release_id, "document_id": release.document_id},
        )
    _assert_validation_rejected(postgres_engine, release.release_id, "source document")


def test_failed_blocking_validation_blocks_validation_and_publish(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="publish-validation-4")
        connection.execute(
            text(
                """
                INSERT INTO validations (
                    release_id, validation_type, result, blocking, validator, completed_at
                ) VALUES (:release_id, 'totals', 'failed', true, 'test', now())
                """
            ),
            {"release_id": release.release_id},
        )
    _assert_validation_rejected(postgres_engine, release.release_id, "blocking validation")
