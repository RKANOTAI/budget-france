from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from database.models import (
    AmountSourceFragment,
    BudgetAmount,
    BudgetNode,
    FragmentEmbedding,
    Release,
    ReleaseSourceDocument,
    SourceDocument,
    SourceFragment,
)


def test_valid_provenance_and_vector_rows_round_trip(postgres_engine: Engine) -> None:
    now = datetime.now(UTC)
    source_id = uuid4()
    fragment_id = uuid4()
    release_id = uuid4()
    node_id = uuid4()
    amount_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            SourceDocument(
                id=source_id,
                url="https://www.example.test/plf-2026.csv",
                document_type="CSV",
                legal_stage="PLF",
                fiscal_year=2026,
                source_version="2026.1",
                collected_at=now,
                sha256="a" * 64,
                media_type="text/csv",
                storage_key="raw/plf-2026.csv",
                storage_size_bytes=128,
                media_metadata={"encoding": "utf-8"},
                created_at=now,
            )
        )
        session.add(
            SourceFragment(
                id=fragment_id,
                source_document_id=source_id,
                fragment_hash="b" * 64,
                locator="sheet=budget;row=1",
                content="Mission pilote; AE; CP",
                fragment_metadata={"sheet": "budget"},
                created_at=now,
            )
        )
        session.add(
            Release(
                id=release_id,
                fiscal_year=2026,
                legal_stage="PLF",
                version="2026.1",
                source_snapshot_hash="c" * 64,
                created_at=now,
            )
        )
        session.flush()
        session.add(
            ReleaseSourceDocument(
                release_id=release_id,
                source_document_id=source_id,
                attached_at=now,
            )
        )
        session.add(
            BudgetNode(
                id=node_id,
                release_id=release_id,
                node_type="mission",
                code="001",
                slug="mission-pilote",
                name="Mission pilote",
                created_at=now,
            )
        )
        session.flush()
        session.add(
            BudgetAmount(
                id=amount_id,
                node_id=node_id,
                metric="AE",
                amount=Decimal("0"),
                unit="EUR",
                aggregation="reported",
                amount_metadata={"precision": "exact"},
                created_at=now,
            )
        )
        session.flush()
        session.add(
            AmountSourceFragment(
                amount_id=amount_id,
                source_fragment_id=fragment_id,
                linked_at=now,
            )
        )
        session.add(
            FragmentEmbedding(
                source_fragment_id=fragment_id,
                model="test-embedding-1536",
                embedding=[0.0] * 1536,
                created_at=now,
            )
        )

        assert session.scalar(select(BudgetAmount.amount)) == Decimal("0")
        assert session.scalar(select(AmountSourceFragment.amount_id)) == amount_id
        assert session.scalar(select(FragmentEmbedding.model)) == "test-embedding-1536"
