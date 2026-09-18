from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import (
    BudgetValue,
    ReleaseInfo,
    SourceRef,
    TreeNode,
    TreeResponse,
)

SOURCE = SourceRef(
    source_fragment_id=UUID("00000000-0000-4000-8000-000000000013"),
    url="https://example.test/source",  # type: ignore[arg-type]
    sha256="a" * 64,
    locator="page=1",
    legal_stage="PLF",
    document_type="PAP",
    retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
    source_version="2026.1",
)
RELEASE = ReleaseInfo(
    release_id=UUID("00000000-0000-4000-8000-000000000042"),
    version="2026.1",
    released_at=datetime(2026, 1, 15, tzinfo=UTC),
    fiscal_year=2026,  # type: ignore[arg-type]
    source_snapshot_hash="b" * 64,
)


def test_tree_response_carries_recursive_budget_nodes_and_release() -> None:
    action = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000040"),
        node_type="action",  # type: ignore[arg-type]
        name="Action 01",
        budget=BudgetValue(cp=Decimal("11.00")),
        source_refs=(SOURCE,),
    )
    child = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000041"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme 146",
        code="146",
        budget=BudgetValue(ae=Decimal("12.00"), cp=Decimal("11.00")),
        children=(action,),
        source_refs=(SOURCE,),
    )
    root = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000043"),
        node_type="mission",  # type: ignore[arg-type]
        name="Action extérieure de l'État",
        code="AE",
        budget=BudgetValue(ae=Decimal("100.00"), cp=Decimal("90.00")),
        children=(child,),
        source_refs=(SOURCE,),
    )

    response = TreeResponse(release=RELEASE, root=root)
    restored = TreeResponse.model_validate_json(response.model_dump_json())

    assert response.release.fiscal_year.value == 2026
    assert response.root.children[0].node_type.value == "programme"
    assert '"cp":"90.00"' in response.model_dump_json()
    assert isinstance(restored.root.children, tuple)
    assert restored == response


def test_tree_json_arrays_round_trip_to_immutable_tuples() -> None:
    child = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000043"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme 146",
        budget=BudgetValue(cp=Decimal("11.00")),
        source_refs=(SOURCE,),
    )
    root = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000044"),
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("90.00")),
        children=(child,),
        source_refs=(SOURCE,),
    )

    json_payload = root.model_dump_json()
    restored = TreeNode.model_validate_json(json_payload)
    python_payload = root.model_dump()
    python_payload["children"] = list(python_payload["children"])
    python_payload["source_refs"] = list(python_payload["source_refs"])
    restored_from_dump = TreeNode.model_validate(python_payload)

    assert isinstance(restored.children, tuple)
    assert isinstance(restored.source_refs, tuple)
    assert isinstance(restored_from_dump.children, tuple)
    assert restored.children[0] == child


def test_tree_node_id_is_a_uuid() -> None:
    with pytest.raises(ValidationError):
        TreeNode(
            id="mission-ae",  # type: ignore[arg-type]
            node_type="mission",  # type: ignore[arg-type]
            name="Mission",
            budget=BudgetValue(cp=Decimal("90.00")),
            source_refs=(SOURCE,),
        )

    node = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000011"),
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("90.00")),
        source_refs=(SOURCE,),
    )
    assert node.id.version == 4


def test_tree_node_requires_non_empty_provenance() -> None:
    with pytest.raises(ValidationError):
        TreeNode(
            id=UUID("00000000-0000-4000-8000-000000000014"),
            node_type="mission",  # type: ignore[arg-type]
            name="Mission",
            budget=BudgetValue(cp=Decimal("90.00")),
            source_refs=(),
        )


def test_tree_node_requires_mission_programme_action_children() -> None:
    action = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000015"),
        node_type="action",  # type: ignore[arg-type]
        name="Action",
        budget=BudgetValue(cp=Decimal("1.00")),
        source_refs=(SOURCE,),
    )
    programme = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000016"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme",
        budget=BudgetValue(cp=Decimal("2.00")),
        source_refs=(SOURCE,),
    )

    with pytest.raises(ValidationError):
        TreeNode(
            id=UUID("00000000-0000-4000-8000-000000000017"),
            node_type="mission",  # type: ignore[arg-type]
            name="Mission",
            budget=BudgetValue(cp=Decimal("3.00")),
            children=(action,),
            source_refs=(SOURCE,),
        )
    with pytest.raises(ValidationError):
        TreeNode(
            id=UUID("00000000-0000-4000-8000-000000000018"),
            node_type="programme",  # type: ignore[arg-type]
            name="Programme",
            budget=BudgetValue(cp=Decimal("3.00")),
            children=(programme,),
            source_refs=(SOURCE,),
        )
    with pytest.raises(ValidationError):
        TreeNode(
            id=UUID("00000000-0000-4000-8000-000000000019"),
            node_type="action",  # type: ignore[arg-type]
            name="Action",
            budget=BudgetValue(cp=Decimal("3.00")),
            children=(action,),
            source_refs=(SOURCE,),
        )


def test_tree_response_uses_release_as_canonical_year_and_unique_node_uuids() -> None:
    child = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000020"),
        node_type="programme",  # type: ignore[arg-type]
        name="Programme",
        budget=BudgetValue(cp=Decimal("1.00")),
        source_refs=(SOURCE,),
    )
    root = TreeNode(
        id=UUID("00000000-0000-4000-8000-000000000021"),
        node_type="mission",  # type: ignore[arg-type]
        name="Mission",
        budget=BudgetValue(cp=Decimal("2.00")),
        children=(child,),
        source_refs=(SOURCE,),
    )
    response = TreeResponse(release=RELEASE, root=root)

    assert response.release.fiscal_year.value == 2026
    assert "year" not in TreeNode.model_fields
    assert "year" not in TreeResponse.model_fields

    duplicate_child = child.model_copy(update={"id": root.id})
    duplicate_root = root.model_copy(update={"children": (duplicate_child,)})
    with pytest.raises(ValidationError):
        TreeResponse(release=RELEASE, root=duplicate_root)
