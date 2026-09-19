from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Engine, SmallInteger, text

from database.models import Base


def test_orm_metadata_matches_postgresql_types_checks_and_indexes(
    postgres_engine: Engine,
) -> None:
    expected_tables = {
        "source_documents",
        "releases",
        "source_fragments",
        "release_source_documents",
        "budget_nodes",
        "budget_amounts",
        "amount_source_fragments",
        "anomalies",
        "validations",
        "ingestion_runs",
        "published_releases",
        "fragment_embeddings",
    }
    assert set(Base.metadata.tables) == expected_tables
    with postgres_engine.connect() as connection:
        actual_tables = set(
            connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                      AND table_name <> 'alembic_version'
                    """
                )
            ).scalars()
        )
    assert actual_tables == expected_tables
    assert isinstance(Base.metadata.tables["source_documents"].c.fiscal_year.type, SmallInteger)
    assert isinstance(
        Base.metadata.tables["source_documents"].c.storage_size_bytes.type, BigInteger
    )
    assert isinstance(Base.metadata.tables["releases"].c.fiscal_year.type, SmallInteger)
    assert isinstance(Base.metadata.tables["ingestion_runs"].c.row_count.type, BigInteger)

    checks = {
        str(constraint.sqltext)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert any("fiscal_year" in expression for expression in checks)
    assert any("source_snapshot_hash" in expression for expression in checks)

    index_names = {index.name for table in Base.metadata.tables.values() for index in table.indexes}
    assert {
        "source_fragments_search_idx",
        "budget_nodes_search_idx",
        "budget_nodes_release_parent_idx",
        "budget_amounts_node_idx",
        "anomalies_release_blocked_idx",
        "budget_nodes_code_scope_idx",
        "budget_nodes_slug_scope_idx",
        "fragment_embeddings_hnsw_idx",
    } <= index_names
