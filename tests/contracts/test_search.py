from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import ReleaseInfo, SearchHit, SearchResponse

RELEASE_ID = UUID("00000000-0000-4000-8000-000000000070")
NODE_ID = UUID("00000000-0000-4000-8000-000000000071")
SNAPSHOT_HASH = "a" * 64


def test_search_response_contains_typed_hits_and_release() -> None:
    release = ReleaseInfo(
        release_id=RELEASE_ID,
        version="2026.1",
        released_at=datetime(2026, 1, 15, tzinfo=UTC),
        fiscal_year=2026,  # type: ignore[arg-type]
        source_snapshot_hash=SNAPSHOT_HASH,
    )
    hit = SearchHit(
        node_id=NODE_ID,
        node_type="mission",  # type: ignore[arg-type]
        name="Action extérieure de l'État",
        code="AE",
        score=0.98,
        match_kind="exact",  # type: ignore[arg-type]
    )

    response = SearchResponse(query="action extérieure", hits=(hit,), total=1, release=release)
    restored = SearchResponse.model_validate_json(response.model_dump_json())

    assert response.hits[0].node_id == NODE_ID
    assert response.hits[0].match_kind == "exact"
    assert response.total == 1
    assert response.release.release_id == RELEASE_ID
    assert isinstance(restored.hits, tuple)
    assert restored == response


def test_search_hit_node_id_is_a_uuid() -> None:
    with pytest.raises(ValidationError):
        SearchHit(
            node_id="mission-ae",  # type: ignore[arg-type]
            node_type="mission",  # type: ignore[arg-type]
            name="Mission",
            score=0.5,
            match_kind="lexical",  # type: ignore[arg-type]
        )

    hit = SearchHit(
        node_id=NODE_ID,
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        score=0.5,
        match_kind="lexical",  # type: ignore[arg-type]
    )
    assert hit.node_id.version == 4
