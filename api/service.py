from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from typing import Literal, Protocol, cast
from unicodedata import normalize
from uuid import UUID

from pydantic import AnyHttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    AmountSourceFragment,
    BudgetAmount,
    BudgetNode,
    PublishedRelease,
    Release,
    SourceDocument,
    SourceFragment,
)
from database.repository import ReleaseRepository
from packages.contracts.models import (
    BudgetValue,
    FiscalYear,
    HistoryPoint,
    MatchKind,
    NodeDetail,
    NodeType,
    ReleaseInfo,
    SearchHit,
    SearchResponse,
    SourceRef,
    TreeCollection,
    TreeNode,
)


class NodeNotFound(Exception):
    """Raised when a node is absent from the selected published release."""


class PublishedReleaseNotFound(Exception):
    """Raised when no published release exists for a requested year/stage."""


class PublishedDataError(Exception):
    """Raised when published data cannot satisfy the public contract."""


class BudgetService(Protocol):
    def tree(self, *, fiscal_year: int, legal_stage: str) -> TreeCollection: ...

    def node(self, *, node_id: UUID, fiscal_year: int, legal_stage: str) -> NodeDetail: ...

    def search(
        self,
        *,
        query: str,
        fiscal_year: int,
        legal_stage: str,
        limit: int,
    ) -> SearchResponse: ...


type BudgetFacts = tuple[BudgetValue, tuple[SourceRef, ...]]


class DatabaseBudgetService:
    """Read-only public view over immutable published PostgreSQL releases."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def tree(self, *, fiscal_year: int, legal_stage: str) -> TreeCollection:
        release = self._published_release(fiscal_year, legal_stage)
        nodes = list(
            self._session.scalars(
                select(BudgetNode)
                .where(BudgetNode.release_id == release.id)
                .order_by(BudgetNode.parent_id, BudgetNode.code, BudgetNode.name, BudgetNode.id)
            )
        )
        if not nodes:
            raise PublishedDataError("the published release has no budget nodes")

        facts = self._facts(node.id for node in nodes)
        children: dict[UUID | None, list[BudgetNode]] = defaultdict(list)
        for node in nodes:
            children[node.parent_id].append(node)

        def build(node: BudgetNode) -> TreeNode:
            budget, source_refs = facts[node.id]
            return TreeNode(
                id=node.id,
                node_type=_node_type(node.node_type),
                name=node.name,
                code=node.code,
                budget=budget,
                children=tuple(build(child) for child in children[node.id]),
                source_refs=source_refs,
            )

        roots = tuple(build(node) for node in children[None])
        if not roots:
            raise PublishedDataError("the published release has no mission roots")
        return TreeCollection(release=self._release_info(release), roots=roots)

    def node(self, *, node_id: UUID, fiscal_year: int, legal_stage: str) -> NodeDetail:
        release = self._published_release(fiscal_year, legal_stage)
        node = self._session.scalar(
            select(BudgetNode).where(
                BudgetNode.id == node_id,
                BudgetNode.release_id == release.id,
            )
        )
        if node is None:
            raise NodeNotFound

        parent = None
        if node.parent_id is not None:
            parent = self._session.scalar(
                select(BudgetNode).where(
                    BudgetNode.id == node.parent_id,
                    BudgetNode.release_id == release.id,
                )
            )
            if parent is None:
                raise PublishedDataError("node parent is missing from the published release")

        children = list(
            self._session.scalars(
                select(BudgetNode)
                .where(
                    BudgetNode.release_id == release.id,
                    BudgetNode.parent_id == node.id,
                )
                .order_by(BudgetNode.code, BudgetNode.name, BudgetNode.id)
            )
        )
        related_nodes = [node, *children]
        if parent is not None:
            related_nodes.append(parent)
        facts = self._facts(item.id for item in related_nodes)
        budget, provenance = facts[node.id]
        history = tuple(
            HistoryPoint(
                year=_fiscal_year(historical_release.fiscal_year),
                budget=facts_for_history[0],
                provenance=facts_for_history[1],
            )
            for historical_release, historical_node, facts_for_history in self._history_facts(
                node.node_type, node.code
            )
        )

        return NodeDetail(
            id=node.id,
            release=self._release_info(release),
            node_type=_node_type(node.node_type),
            name=node.name,
            code=node.code,
            budget=budget,
            description=node.description,
            parent=self._tree_node(parent, facts) if parent is not None else None,
            children=tuple(self._tree_node(child, facts) for child in children),
            history=history,
            provenance=provenance,
            explanation=None,
        )

    def search(
        self,
        *,
        query: str,
        fiscal_year: int,
        legal_stage: str,
        limit: int,
    ) -> SearchResponse:
        release = self._published_release(fiscal_year, legal_stage)
        nodes = ReleaseRepository(self._session).search_nodes(release.id, query, limit=limit)
        needle = _normalize_text(query)
        hits = tuple(
            SearchHit(
                node_id=node.id,
                node_type=_node_type(node.node_type),
                name=node.name,
                code=node.code,
                score=_search_score(node.name, node.code, needle),
                match_kind=_match_kind(node.name, node.code, needle),
            )
            for node in nodes
        )
        return SearchResponse(
            query=query.strip(),
            hits=hits,
            total=len(hits),
            release=self._release_info(release),
        )

    def _published_release(self, fiscal_year: int, legal_stage: str) -> Release:
        release = self._session.scalar(
            select(Release)
            .join(PublishedRelease, PublishedRelease.release_id == Release.id)
            .where(
                PublishedRelease.fiscal_year == fiscal_year,
                PublishedRelease.legal_stage == legal_stage,
            )
        )
        if release is None:
            raise PublishedReleaseNotFound
        return release

    def _history_facts(
        self, node_type: str, code: str
    ) -> list[tuple[Release, BudgetNode, BudgetFacts]]:
        history = ReleaseRepository(self._session).node_history(node_type=node_type, code=code)
        return [(*item, self._facts([item[1].id])[item[1].id]) for item in history]

    def _facts(self, node_ids: Iterable[UUID]) -> dict[UUID, BudgetFacts]:
        ids = tuple(dict.fromkeys(node_ids))
        if not ids:
            return {}
        amounts = list(
            self._session.scalars(
                select(BudgetAmount)
                .where(BudgetAmount.node_id.in_(ids))
                .order_by(BudgetAmount.node_id, BudgetAmount.metric)
            )
        )
        budgets: dict[UUID, BudgetValue] = {}
        by_metric: dict[UUID, dict[str, Decimal]] = defaultdict(dict)
        for amount in amounts:
            by_metric[amount.node_id][amount.metric] = amount.amount
        for node_id in ids:
            metrics = by_metric[node_id]
            budgets[node_id] = BudgetValue(
                ae=metrics.get("AE"),
                cp=metrics.get("CP"),
            )

        sources: dict[UUID, list[SourceRef]] = defaultdict(list)
        seen: set[tuple[UUID, UUID]] = set()
        rows = self._session.execute(
            select(BudgetAmount.node_id, SourceFragment, SourceDocument)
            .join(AmountSourceFragment, AmountSourceFragment.amount_id == BudgetAmount.id)
            .join(SourceFragment, SourceFragment.id == AmountSourceFragment.source_fragment_id)
            .join(SourceDocument, SourceDocument.id == SourceFragment.source_document_id)
            .where(BudgetAmount.node_id.in_(ids))
            .order_by(
                BudgetAmount.node_id,
                SourceDocument.url,
                SourceFragment.locator,
                SourceFragment.id,
            )
        )
        for node_id, fragment, document in rows:
            key = (node_id, fragment.id)
            if key in seen:
                continue
            seen.add(key)
            sources[node_id].append(self._source_ref(fragment, document))

        facts: dict[UUID, BudgetFacts] = {}
        for node_id in ids:
            if node_id not in sources:
                raise PublishedDataError(f"node {node_id} has no source provenance")
            facts[node_id] = (budgets[node_id], tuple(sources[node_id]))
        return facts

    def _tree_node(self, node: BudgetNode, facts: dict[UUID, BudgetFacts]) -> TreeNode:
        budget, source_refs = facts[node.id]
        return TreeNode(
            id=node.id,
            node_type=_node_type(node.node_type),
            name=node.name,
            code=node.code,
            budget=budget,
            source_refs=source_refs,
        )

    @staticmethod
    def _release_info(release: Release) -> ReleaseInfo:
        if release.released_at is None:
            raise PublishedDataError("published release has no released_at timestamp")
        return ReleaseInfo(
            release_id=release.id,
            version=release.version,
            released_at=release.released_at,
            fiscal_year=_fiscal_year(release.fiscal_year),
            source_snapshot_hash=release.source_snapshot_hash,
        )

    @staticmethod
    def _source_ref(fragment: SourceFragment, document: SourceDocument) -> SourceRef:
        return SourceRef(
            source_fragment_id=fragment.id,
            url=cast(AnyHttpUrl, document.url),
            sha256=document.sha256,
            locator=fragment.locator,
            legal_stage=cast(Literal["PLF", "LFI"], document.legal_stage),
            document_type=document.document_type,
            retrieved_at=document.collected_at,
            source_version=document.source_version,
            publication_date=document.publication_date,
        )


def _normalize_text(value: str) -> str:
    return " ".join(
        normalize("NFD", value).encode("ascii", "ignore").decode("ascii").lower().split()
    )


def _match_kind(name: str, code: str, needle: str) -> MatchKind:
    return (
        MatchKind.EXACT
        if needle in {_normalize_text(name), _normalize_text(code)}
        else MatchKind.LEXICAL
    )


def _search_score(name: str, code: str, needle: str) -> float:
    return 1.0 if _match_kind(name, code, needle) is MatchKind.EXACT else 0.7


def _node_type(value: str) -> NodeType:
    return NodeType(value)


def _fiscal_year(value: int) -> FiscalYear:
    return FiscalYear(value)
