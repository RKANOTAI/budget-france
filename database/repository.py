from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import BudgetNode, Release


class ReleaseRepository:
    """Small transaction-scoped repository for release lifecycle operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_release(
        self,
        *,
        fiscal_year: int,
        legal_stage: str,
        version: str,
        source_snapshot_hash: str,
    ) -> Release:
        release = Release(
            fiscal_year=fiscal_year,
            legal_stage=legal_stage,
            version=version,
            status="draft",
            source_snapshot_hash=source_snapshot_hash,
            created_at=datetime.now(UTC),
        )
        self._session.add(release)
        self._session.flush()
        return release

    def register_provenance(self, amount_id: UUID, source_fragment_id: UUID) -> None:
        """Attach one source fragment to one AE/CP fact."""

        self._session.execute(
            text(
                """
                INSERT INTO amount_source_fragments (amount_id, source_fragment_id)
                VALUES (:amount_id, :source_fragment_id)
                """
            ),
            {"amount_id": amount_id, "source_fragment_id": source_fragment_id},
        )

    def list_children(self, release_id: UUID, *, parent_id: UUID | None = None) -> list[BudgetNode]:
        """Return one deterministic Mission → Programme → Action level."""

        statement = select(BudgetNode).where(BudgetNode.release_id == release_id)
        if parent_id is None:
            statement = statement.where(BudgetNode.parent_id.is_(None))
        else:
            statement = statement.where(BudgetNode.parent_id == parent_id)
        statement = statement.order_by(BudgetNode.code, BudgetNode.name, BudgetNode.id)
        return list(self._session.scalars(statement))

    def node_history(self, *, node_type: str, code: str) -> list[tuple[Release, BudgetNode]]:
        """Return published versions of a node key, oldest release first."""

        statement = (
            select(Release, BudgetNode)
            .join(BudgetNode, BudgetNode.release_id == Release.id)
            .where(
                Release.status == "published",
                BudgetNode.node_type == node_type,
                BudgetNode.code == code,
            )
            .order_by(
                Release.fiscal_year,
                Release.released_at.nulls_last(),
                Release.version,
                Release.id,
            )
        )
        return list(self._session.execute(statement).tuples().all())

    def search_nodes(self, release_id: UUID, query: str, *, limit: int = 50) -> list[BudgetNode]:
        """Return lexical matches in stable rank/key order for one release."""

        if limit < 1:
            raise ValueError("limit must be positive")
        search_text = query.strip()
        if not search_text:
            return []
        tsquery = func.plainto_tsquery("french", search_text)
        rank = func.ts_rank_cd(BudgetNode.search_vector, tsquery)
        statement = (
            select(BudgetNode)
            .where(
                BudgetNode.release_id == release_id,
                BudgetNode.search_vector.op("@@")(tsquery),
            )
            .order_by(
                rank.desc(),
                BudgetNode.node_type,
                BudgetNode.code,
                BudgetNode.name,
                BudgetNode.id,
            )
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def record_validation(
        self,
        release_id: UUID,
        *,
        validation_type: str,
        result: str,
        blocking: bool,
        validator: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self._session.execute(
            text(
                """
                INSERT INTO validations (
                    release_id, validation_type, result, blocking, validator, details, completed_at
                ) VALUES (
                    :release_id, :validation_type, :result, :blocking, :validator,
                    CAST(:details AS jsonb), now()
                )
                """
            ),
            {
                "release_id": release_id,
                "validation_type": validation_type,
                "result": result,
                "blocking": blocking,
                "validator": validator,
                "details": _json_object(details or {}),
            },
        )

    def validate_release(self, release_id: UUID, *, validator: str) -> UUID:
        result = self._session.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": release_id, "validator": validator},
        ).scalar_one()
        return _as_uuid(result)

    def reject_release(self, release_id: UUID) -> UUID:
        result = self._session.execute(
            text("SELECT budget_reject_release(:release_id)"),
            {"release_id": release_id},
        ).scalar_one()
        return _as_uuid(result)

    def publish_release(self, release_id: UUID) -> UUID:
        result = self._session.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": release_id},
        ).scalar_one()
        return _as_uuid(result)


def _as_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _json_object(value: dict[str, object]) -> str:
    import json

    return json.dumps(value, separators=(",", ":"), sort_keys=True)
