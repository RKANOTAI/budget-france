import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_budget_service
from api.service import NodeNotFound
from packages.contracts.models import (
    BudgetValue,
    NodeDetail,
    NodeType,
    ReleaseInfo,
    SearchHit,
    SearchResponse,
    SourceRef,
    TreeCollection,
    TreeNode,
)

RELEASE_ID = UUID("00000000-0000-4000-8000-000000000101")
MISSION_ID = UUID("00000000-0000-4000-8000-000000000102")
SOURCE_ID = UUID("00000000-0000-4000-8000-000000000103")
SNAPSHOT_HASH = "a" * 64


def _source() -> SourceRef:
    return SourceRef(
        source_fragment_id=SOURCE_ID,
        url="https://www.budget.gouv.fr/documentation/file.csv",
        sha256="b" * 64,
        locator="sheet=budget;row=1",
        legal_stage="PLF",
        document_type="CSV",
        retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
        source_version="2026.1",
    )


def _release() -> ReleaseInfo:
    return ReleaseInfo(
        release_id=RELEASE_ID,
        version="2026.1",
        released_at=datetime(2026, 1, 20, tzinfo=UTC),
        fiscal_year=2026,  # type: ignore[arg-type]
        source_snapshot_hash=SNAPSHOT_HASH,
    )


class FakeBudgetService:
    def tree(self, *, fiscal_year: int, legal_stage: str) -> TreeCollection:
        assert (fiscal_year, legal_stage) == (2026, "PLF")
        source = _source()
        return TreeCollection(
            release=_release(),
            roots=(
                TreeNode(
                    id=MISSION_ID,
                    node_type=NodeType.MISSION,
                    name="Mission pilote",
                    code="001",
                    budget=BudgetValue(ae=Decimal("100.00"), cp=Decimal("90.00")),
                    source_refs=(source,),
                ),
            ),
        )

    def node(self, *, node_id: UUID, fiscal_year: int, legal_stage: str) -> NodeDetail:
        if node_id != MISSION_ID:
            raise NodeNotFound
        source = _source()
        return NodeDetail(
            id=MISSION_ID,
            release=_release(),
            node_type=NodeType.MISSION,
            name="Mission pilote",
            code="001",
            budget=BudgetValue(ae=Decimal("100.00"), cp=Decimal("90.00")),
            provenance=(source,),
        )

    def search(
        self, *, query: str, fiscal_year: int, legal_stage: str, limit: int
    ) -> SearchResponse:
        return SearchResponse(
            query=query,
            hits=(
                SearchHit(
                    node_id=MISSION_ID,
                    node_type=NodeType.MISSION,
                    name="Mission pilote",
                    code="001",
                    score=1.0,
                    match_kind="exact",
                ),
            ),
            total=1,
            release=_release(),
        )


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_budget_service] = lambda: FakeBudgetService()
    return TestClient(app)


def test_health_endpoint_is_public() -> None:
    response = _client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tree_endpoint_returns_contract_and_cors_header() -> None:
    response = _client().get(
        "/api/v1/tree?fiscal_year=2026&legal_stage=PLF",
        headers={"Origin": "https://rkanotai.github.io"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://rkanotai.github.io"
    payload = TreeCollection.model_validate_json(json.dumps(response.json()["data"]))
    assert payload.roots[0].name == "Mission pilote"
    assert response.headers["x-request-id"]


def test_search_endpoint_preserves_typed_envelope() -> None:
    response = _client().get("/api/v1/search?q=mission&limit=8")

    assert response.status_code == 200
    payload = SearchResponse.model_validate_json(json.dumps(response.json()["data"]))
    assert payload.query == "mission"
    assert payload.hits[0].match_kind == "exact"
    assert response.json()["request_id"]


def test_node_endpoint_returns_problem_details_for_unknown_node() -> None:
    response = _client().get("/api/v1/nodes/00000000-0000-4000-8000-000000000199")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Nœud introuvable"
