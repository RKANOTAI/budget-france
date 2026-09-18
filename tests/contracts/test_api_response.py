from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import (
    ApiResponse,
    BudgetValue,
    NodeApiResponse,
    NodeDetail,
    ProblemDetails,
    ReleaseInfo,
    SearchApiResponse,
    SearchResponse,
    SourceRef,
    TreeApiResponse,
    TreeNode,
    TreeResponse,
)

RELEASE_ID = UUID("00000000-0000-4000-8000-000000000080")
SNAPSHOT_HASH = "d" * 64


def _release() -> ReleaseInfo:
    return ReleaseInfo(
        release_id=RELEASE_ID,
        version="2026.1",
        released_at=datetime(2026, 1, 15, tzinfo=UTC),
        fiscal_year=2026,  # type: ignore[arg-type]
        source_snapshot_hash=SNAPSHOT_HASH,
    )


def test_generic_api_response_preserves_payload_type() -> None:
    search = SearchResponse(query="défense", hits=(), total=0, release=_release())

    response = ApiResponse[SearchResponse](data=search)
    restored = ApiResponse[SearchResponse].model_validate_json(response.model_dump_json())

    assert isinstance(response.data, SearchResponse)
    assert response.data.query == "défense"
    assert restored == response


def test_problem_details_uses_rfc7807_members_and_forbids_extensions() -> None:
    problem = ProblemDetails(
        type="https://budget.example.test/problems/not-found",
        title="Nœud introuvable",
        status=404,
        detail="Le nœud demandé n'existe pas dans cette release.",
        instance="/api/node/missing",
    )

    assert problem.status == 404
    assert problem.type.startswith("https://")

    with pytest.raises(ValidationError):
        ProblemDetails(title="Erreur", status=99)
    with pytest.raises(ValidationError):
        ProblemDetails(title="Erreur", status=500, arbitrary="extension")  # type: ignore[call-arg]


def test_api_request_id_is_a_uuid() -> None:
    with pytest.raises(ValidationError):
        ApiResponse[ProblemDetails](
            data=ProblemDetails(title="Erreur", status=500),
            request_id="request-1",  # type: ignore[arg-type]
        )

    response = ApiResponse[ProblemDetails](
        data=ProblemDetails(title="Erreur", status=500),
        request_id=UUID("00000000-0000-4000-8000-000000000012"),
    )
    assert response.request_id is not None
    assert response.request_id.version == 4


def test_concrete_api_responses_have_concrete_typed_data() -> None:
    search = SearchResponse(query="défense", hits=(), total=0, release=_release())

    response = SearchApiResponse(data=search)

    assert isinstance(response.data, SearchResponse)
    assert SearchApiResponse.model_fields["data"].annotation is SearchResponse
    assert TreeApiResponse.model_fields["data"].annotation is TreeResponse
    assert NodeApiResponse.model_fields["data"].annotation is NodeDetail


def test_concrete_api_responses_round_trip_their_nested_payloads() -> None:
    source = SourceRef(
        source_fragment_id=UUID("00000000-0000-4000-8000-000000000081"),
        url="https://example.test/source",  # type: ignore[arg-type]
        sha256="c" * 64,
        locator="page=1",
        legal_stage="PLF",
        document_type="PAP",
        retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
        source_version="2026.1",
    )
    root = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000082"),
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("1.00")),
        source_refs=(source,),
    )
    tree = TreeResponse(release=_release(), root=root)
    node = NodeDetail(
        id=UUID("00000000-0000-4000-8000-000000000083"),
        release=_release(),
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("1.00")),
        provenance=(source,),
    )
    search = SearchResponse(query="mission", hits=(), total=0, release=_release())

    responses = (
        TreeApiResponse(data=tree),
        NodeApiResponse(data=node),
        SearchApiResponse(data=search),
    )
    for response in responses:
        restored = type(response).model_validate_json(response.model_dump_json())
        assert restored.data == response.data
