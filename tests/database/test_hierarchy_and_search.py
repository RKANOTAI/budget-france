from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Engine, text

from tests.database.support import seed_release


def test_three_level_tree_full_text_and_separate_ae_cp_rows(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="tree-valid")
        programme_id = uuid4()
        action_id = uuid4()
        cp_amount_id = uuid4()
        connection.execute(
            text(
                """
                INSERT INTO budget_nodes (
                    id, release_id, parent_id, node_type, code, slug, name
                ) VALUES (
                    :id, :release_id, :parent_id, 'programme', '146',
                    'programme-146', 'Programme Défense'
                )
                """
            ),
            {
                "id": programme_id,
                "release_id": release.release_id,
                "parent_id": release.node_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO budget_nodes (
                    id, release_id, parent_id, node_type, code, slug, name
                ) VALUES (
                    :id, :release_id, :parent_id, 'action', '01',
                    'action-01', 'Action opérationnelle'
                )
                """
            ),
            {
                "id": action_id,
                "release_id": release.release_id,
                "parent_id": programme_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO budget_amounts (node_id, metric, amount, unit, aggregation)
                VALUES (:node_id, 'CP', :amount, 'EUR', 'reported')
                """
            ),
            {"node_id": action_id, "amount": Decimal("0")},
        )
        connection.execute(
            text(
                """
                INSERT INTO budget_amounts (id, node_id, metric, amount, unit, aggregation)
                VALUES (:id, :node_id, 'AE', :amount, 'EUR', 'reported')
                """
            ),
            {"id": cp_amount_id, "node_id": action_id, "amount": Decimal("0")},
        )
        tree_count = connection.execute(
            text("SELECT count(*) FROM budget_nodes WHERE release_id = :release_id"),
            {"release_id": release.release_id},
        ).scalar_one()
        metric_count = connection.execute(
            text("SELECT count(*) FROM budget_amounts WHERE node_id = :node_id"),
            {"node_id": action_id},
        ).scalar_one()
        lexical_count = connection.execute(
            text(
                """
                SELECT count(*)
                FROM budget_nodes
                WHERE search_vector @@ plainto_tsquery('french', :query)
                """
            ),
            {"query": "Défense"},
        ).scalar_one()
        embedding_type = connection.execute(
            text(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = 'fragment_embeddings'
                  AND a.attname = 'embedding'
                """
            )
        ).scalar_one()

    assert tree_count == 3
    assert metric_count == 2
    assert lexical_count == 1
    assert embedding_type == "vector(1536)"
