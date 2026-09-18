from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import (
    BudgetValue,
    Explanation,
    HistoryPoint,
    NodeDetail,
    ReleaseInfo,
    SourceRef,
    TreeNode,
)

SOURCE_ID = UUID("00000000-0000-4000-8000-000000000024")
SHA256 = "b" * 64
RELEASE_ID = UUID("00000000-0000-4000-8000-000000000052")
SOURCE = SourceRef(
    source_fragment_id=SOURCE_ID,
    url="https://example.test/lfi-2026.pdf",  # type: ignore[arg-type]
    sha256=SHA256,
    locator="page=4",
    legal_stage="LFI",
    document_type="LFI",
    retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
    source_version="2026.1",
)
RELEASE = ReleaseInfo(
    release_id=RELEASE_ID,
    version="2026.1",
    released_at=datetime(2026, 1, 15, tzinfo=UTC),
    fiscal_year=2026,  # type: ignore[arg-type]
    source_snapshot_hash="c" * 64,
)


def test_node_detail_exposes_history_provenance_and_explanation() -> None:
    parent = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000049"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme parent",
        budget=BudgetValue(cp=Decimal("19.00")),
        source_refs=(SOURCE,),
    )
    detail = NodeDetail(
        id=UUID("00000000-0000-4000-8000-000000000050"),
        release=RELEASE,
        node_type="action",  # type: ignore[arg-type]
        name="Action pilote",
        code="01",
        budget=BudgetValue(ae=Decimal("20.00"), cp=Decimal("19.00")),
        description="Description officielle.",
        parent=parent,
        history=(
            HistoryPoint(
                year=2025,  # type: ignore[arg-type]
                budget=BudgetValue(cp=Decimal("18.00")),
                provenance=(SOURCE,),
            ),
        ),
        provenance=(SOURCE,),
        explanation=Explanation(
            summary="Résumé documenté.",
            what_it_funds="Le périmètre financé est documenté.",
            main_changes="La nomenclature publiée est inchangée.",
            limitations="La source ne permet pas d'expliquer toute variation.",
            source_fragment_ids=(SOURCE_ID,),
        ),
    )

    restored = NodeDetail.model_validate_json(detail.model_dump_json())

    assert detail.release.fiscal_year.value == 2026
    assert detail.history[0].year.value == 2025
    assert detail.provenance[0].source_fragment_id == SOURCE_ID
    assert detail.explanation is not None
    assert detail.explanation.source_fragment_ids == (SOURCE_ID,)
    assert isinstance(restored.history, tuple)
    assert isinstance(restored.provenance, tuple)
    assert restored == detail


def test_history_point_requires_non_empty_provenance() -> None:
    with pytest.raises(ValidationError):
        HistoryPoint(
            year=2025,  # type: ignore[arg-type]
            budget=BudgetValue(cp=Decimal("18.00")),
            provenance=(),
        )

    history = HistoryPoint(
        year=2025,  # type: ignore[arg-type]
        budget=BudgetValue(cp=Decimal("18.00")),
        provenance=(SOURCE,),
    )
    assert history.provenance == (SOURCE,)


def test_node_detail_requires_non_empty_provenance() -> None:
    with pytest.raises(ValidationError):
        NodeDetail(
            id=UUID("00000000-0000-4000-8000-000000000051"),
            release=RELEASE,
            node_type="mission",  # type: ignore[arg-type]
            name="Mission",
            budget=BudgetValue(cp=Decimal("19.00")),
            provenance=(),
        )


def test_node_detail_id_is_a_uuid() -> None:
    with pytest.raises(ValidationError):
        NodeDetail(
            id="action-1",  # type: ignore[arg-type]
            release=RELEASE,
            node_type="mission",  # type: ignore[arg-type]
            name="Mission",
            budget=BudgetValue(cp=Decimal("19.00")),
            provenance=(SOURCE,),
        )

    detail = NodeDetail(
        id=UUID("00000000-0000-4000-8000-000000000025"),
        release=RELEASE,
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("19.00")),
        provenance=(SOURCE,),
    )
    assert detail.id.version == 4


def test_node_detail_requires_valid_parent_and_children_by_level() -> None:
    wrong_parent = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000026"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme",
        budget=BudgetValue(cp=Decimal("20.00")),
        source_refs=(SOURCE,),
    )

    with pytest.raises(ValidationError):
        NodeDetail(
            id=UUID("00000000-0000-4000-8000-000000000027"),
            release=RELEASE,
            node_type="programme",  # type: ignore[arg-type]
            name="Programme",
            budget=BudgetValue(cp=Decimal("19.00")),
            parent=wrong_parent,
            provenance=(SOURCE,),
        )

    mission_parent = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000028"),
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("20.00")),
        source_refs=(SOURCE,),
    )
    invalid_child = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000029"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme enfant invalide",
        budget=BudgetValue(cp=Decimal("1.00")),
        source_refs=(SOURCE,),
    )
    with pytest.raises(ValidationError):
        NodeDetail(
            id=UUID("00000000-0000-4000-8000-000000000030"),
            release=RELEASE,
            node_type="programme",  # type: ignore[arg-type]
            name="Programme",
            budget=BudgetValue(cp=Decimal("19.00")),
            parent=mission_parent,
            children=(invalid_child,),
            provenance=(SOURCE,),
        )

    with pytest.raises(ValidationError):
        NodeDetail(
            id=UUID("00000000-0000-4000-8000-000000000031"),
            release=RELEASE,
            node_type="action",  # type: ignore[arg-type]
            name="Action sans parent",
            budget=BudgetValue(cp=Decimal("1.00")),
            provenance=(SOURCE,),
        )

    with pytest.raises(ValidationError):
        NodeDetail(
            id=UUID("00000000-0000-4000-8000-000000000032"),
            release=RELEASE,
            node_type="mission",  # type: ignore[arg-type]
            name="Mission avec parent",
            budget=BudgetValue(cp=Decimal("1.00")),
            parent=mission_parent,
            provenance=(SOURCE,),
        )
