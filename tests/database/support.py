from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class ReleaseFixture:
    release_id: UUID
    document_id: UUID
    fragment_id: UUID
    node_id: UUID
    amount_id: UUID


def seed_release(
    connection: Connection,
    *,
    version: str,
    with_amount: bool = True,
    with_source: bool = True,
    fiscal_year: int = 2026,
    legal_stage: str = "PLF",
) -> ReleaseFixture:
    release_id = uuid4()
    document_id = uuid4()
    fragment_id = uuid4()
    node_id = uuid4()
    amount_id = uuid4()
    connection.execute(
        text(
            """
            INSERT INTO source_documents (
                id, url, document_type, legal_stage, fiscal_year, source_version,
                collected_at, sha256, media_type
            ) VALUES (
                :id, :url, 'CSV', :legal_stage, :fiscal_year, :source_version,
                '2026-01-01T00:00:00Z', :sha256, 'text/csv'
            )
            """
        ),
        {
            "id": document_id,
            "url": f"https://example.test/{version}.csv",
            "legal_stage": legal_stage,
            "fiscal_year": fiscal_year,
            "source_version": version,
            "sha256": sha256(version.encode()).hexdigest(),
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO source_fragments (id, source_document_id, fragment_hash, locator, content)
            VALUES (:id, :source_document_id, :fragment_hash, 'row=1', 'Mission pilote AE CP')
            """
        ),
        {"id": fragment_id, "source_document_id": document_id, "fragment_hash": "e" * 64},
    )
    connection.execute(
        text(
            """
            INSERT INTO releases (
                id, fiscal_year, legal_stage, version, source_snapshot_hash
            ) VALUES (:id, :fiscal_year, :legal_stage, :version, :snapshot_hash)
            """
        ),
        {
            "id": release_id,
            "fiscal_year": fiscal_year,
            "legal_stage": legal_stage,
            "version": version,
            "snapshot_hash": "f" * 64,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO budget_nodes (id, release_id, node_type, code, slug, name)
            VALUES (:id, :release_id, 'mission', '001', :slug, 'Mission pilote')
            """
        ),
        {"id": node_id, "release_id": release_id, "slug": f"mission-{version}"},
    )
    if with_amount:
        connection.execute(
            text(
                """
                INSERT INTO budget_amounts (id, node_id, metric, amount, unit, aggregation)
                VALUES (:id, :node_id, 'AE', :amount, 'EUR', 'reported')
                """
            ),
            {"id": amount_id, "node_id": node_id, "amount": Decimal("0")},
        )
        if with_source:
            connection.execute(
                text(
                    """
                    INSERT INTO amount_source_fragments (amount_id, source_fragment_id)
                    VALUES (:amount_id, :source_fragment_id)
                    """
                ),
                {"amount_id": amount_id, "source_fragment_id": fragment_id},
            )
    return ReleaseFixture(release_id, document_id, fragment_id, node_id, amount_id)
