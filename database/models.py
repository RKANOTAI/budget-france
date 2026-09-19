from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL source of truth."""


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        CheckConstraint(
            "url ~* '^https?://([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?[.])*"
            "[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?([/?#][^[:space:]]*)?$'"
        ),
        CheckConstraint("btrim(document_type) <> ''"),
        CheckConstraint("legal_stage IN ('PLF', 'LFI')"),
        CheckConstraint("fiscal_year IN (2025, 2026)"),
        CheckConstraint("btrim(source_version) <> ''"),
        CheckConstraint("sha256 ~ '^[0-9a-fA-F]{64}$'"),
        CheckConstraint("btrim(media_type) <> ''"),
        CheckConstraint("storage_size_bytes IS NULL OR storage_size_bytes >= 0"),
        UniqueConstraint("url", "source_version", "sha256"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_stage: Mapped[str] = mapped_column(String(3), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    media_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fragments: Mapped[list[SourceFragment]] = relationship(back_populates="source_document")
    release_links: Mapped[list[ReleaseSourceDocument]] = relationship(
        back_populates="source_document"
    )


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        CheckConstraint("fiscal_year IN (2025, 2026)"),
        CheckConstraint("legal_stage IN ('PLF', 'LFI')"),
        CheckConstraint("btrim(version) <> ''"),
        CheckConstraint("status IN ('draft', 'validated', 'published', 'rejected')"),
        CheckConstraint("source_snapshot_hash ~ '^[0-9a-fA-F]{64}$'"),
        UniqueConstraint("fiscal_year", "legal_stage", "version"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    fiscal_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    legal_stage: Mapped[str] = mapped_column(String(3), nullable=False)
    version: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="draft", server_default=text("'draft'")
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_document_links: Mapped[list[ReleaseSourceDocument]] = relationship(
        back_populates="release"
    )


class SourceFragment(Base):
    __tablename__ = "source_fragments"
    __table_args__ = (
        CheckConstraint("fragment_hash ~ '^[0-9a-fA-F]{64}$'"),
        CheckConstraint("btrim(locator) <> ''"),
        CheckConstraint("btrim(content) <> ''"),
        UniqueConstraint("source_document_id", "fragment_hash"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=False
    )
    fragment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    fragment_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('french'::regconfig, coalesce(content, ''::text))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_document: Mapped[SourceDocument] = relationship(back_populates="fragments")


class ReleaseSourceDocument(Base):
    __tablename__ = "release_source_documents"

    release_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("releases.id", ondelete="RESTRICT"), primary_key=True
    )
    source_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    release: Mapped[Release] = relationship(back_populates="source_document_links")
    source_document: Mapped[SourceDocument] = relationship(back_populates="release_links")


class BudgetNode(Base):
    __tablename__ = "budget_nodes"
    __table_args__ = (
        CheckConstraint("node_type IN ('mission', 'programme', 'action')"),
        CheckConstraint("btrim(code) <> ''"),
        CheckConstraint("slug ~ '^[a-z0-9][a-z0-9-]*$'"),
        CheckConstraint("btrim(name) <> ''"),
        UniqueConstraint("release_id", "id"),
        ForeignKeyConstraint(
            ["release_id", "parent_id"],
            ["budget_nodes.release_id", "budget_nodes.id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    release_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("releases.id", ondelete="RESTRICT"), nullable=False
    )
    parent_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    node_type: Mapped[str] = mapped_column(String(10), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('french'::regconfig, name || ' ' || code || ' ' || slug || ' ' || "
            "coalesce(description, ''))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BudgetAmount(Base):
    __tablename__ = "budget_amounts"
    __table_args__ = (
        CheckConstraint("metric IN ('AE', 'CP')"),
        CheckConstraint("btrim(unit) <> ''"),
        CheckConstraint("btrim(aggregation) <> ''"),
        UniqueConstraint("node_id", "metric"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("budget_nodes.id", ondelete="RESTRICT"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AmountSourceFragment(Base):
    __tablename__ = "amount_source_fragments"

    amount_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("budget_amounts.id", ondelete="RESTRICT"), primary_key=True
    )
    source_fragment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_fragments.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    amount: Mapped[BudgetAmount] = relationship()
    source_fragment: Mapped[SourceFragment] = relationship()


class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''"),
        CheckConstraint("severity IN ('info', 'warning', 'error', 'critical')"),
        CheckConstraint("btrim(message) <> ''"),
        CheckConstraint("severity NOT IN ('error', 'critical') OR blocked"),
        ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["release_id", "node_id"],
            ["budget_nodes.release_id", "budget_nodes.id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    release_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    blocked: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Validation(Base):
    __tablename__ = "validations"
    __table_args__ = (
        CheckConstraint("btrim(validation_type) <> ''"),
        CheckConstraint("result IN ('passed', 'failed', 'warning')"),
        CheckConstraint("btrim(validator) <> ''"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    release_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("releases.id", ondelete="RESTRICT"), nullable=False
    )
    validation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    result: Mapped[str] = mapped_column(String(12), nullable=False)
    blocking: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    validator: Mapped[str] = mapped_column(String(160), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("btrim(pipeline) <> ''"),
        CheckConstraint("status IN ('running', 'succeeded', 'failed')"),
        CheckConstraint("row_count IS NULL OR row_count >= 0"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    release_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("releases.id", ondelete="RESTRICT"), nullable=True
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True
    )
    pipeline: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class PublishedRelease(Base):
    __tablename__ = "published_releases"
    __table_args__ = (
        CheckConstraint("fiscal_year IN (2025, 2026)"),
        CheckConstraint("legal_stage IN ('PLF', 'LFI')"),
    )

    fiscal_year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    legal_stage: Mapped[str] = mapped_column(String(3), primary_key=True)
    release_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("releases.id", ondelete="RESTRICT"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FragmentEmbedding(Base):
    __tablename__ = "fragment_embeddings"
    __table_args__ = (
        CheckConstraint("btrim(model) <> ''"),
        UniqueConstraint("source_fragment_id", "model"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_fragment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_fragments.id", ondelete="RESTRICT"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index("source_fragments_search_idx", SourceFragment.search_vector, postgresql_using="gin")
Index("budget_nodes_search_idx", BudgetNode.search_vector, postgresql_using="gin")
Index("budget_nodes_release_parent_idx", BudgetNode.release_id, BudgetNode.parent_id)
Index("budget_amounts_node_idx", BudgetAmount.node_id)
Index("anomalies_release_blocked_idx", Anomaly.release_id, Anomaly.blocked)
Index(
    "budget_nodes_code_scope_idx",
    BudgetNode.release_id,
    func.coalesce(BudgetNode.parent_id, text("'00000000-0000-0000-0000-000000000000'::uuid")),
    BudgetNode.code,
    unique=True,
)
Index(
    "budget_nodes_slug_scope_idx",
    BudgetNode.release_id,
    func.coalesce(BudgetNode.parent_id, text("'00000000-0000-0000-0000-000000000000'::uuid")),
    BudgetNode.slug,
    unique=True,
)
Index(
    "fragment_embeddings_hnsw_idx",
    FragmentEmbedding.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
