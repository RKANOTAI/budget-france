import pytest

from packages.contracts.models import NodeType


def test_node_type_only_accepts_budget_tree_levels() -> None:
    assert NodeType("mission").value == "mission"
    assert NodeType("programme").value == "programme"
    assert NodeType("action").value == "action"
    with pytest.raises(ValueError):
        NodeType("ministry")
