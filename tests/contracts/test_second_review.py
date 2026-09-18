import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from packages.contracts.models import (
    AnomalySummary,
    Explanation,
    NodeDetail,
    ReleaseInfo,
    SearchHit,
    SearchResponse,
    SourceRef,
    TreeNode,
    TreeResponse,
)

ROOT = Path(__file__).parents[2]
SCHEMA_DIR = ROOT / "packages" / "contracts" / "schemas"
SOURCE_ID = "00000000-0000-4000-8000-000000000101"
RELEASE_ID = "00000000-0000-4000-8000-000000000102"


def _source_payload(*, url: str = "https://example.test/source") -> dict[str, object]:
    return {
        "source_fragment_id": SOURCE_ID,
        "url": url,
        "sha256": "a" * 64,
        "locator": "page=1",
        "legal_stage": "LFI",
        "document_type": "LFI",
        "retrieved_at": "2026-01-15T10:30:00Z",
        "source_version": "2026.1",
    }


def _release_payload() -> dict[str, object]:
    return {
        "release_id": RELEASE_ID,
        "version": "2026.1",
        "released_at": "2026-01-15T10:30:00Z",
        "fiscal_year": 2026,
        "source_snapshot_hash": "b" * 64,
    }


def _budget_payload() -> dict[str, object]:
    return {"cp": "1.00", "currency": "EUR"}


def _tree_node_payload(
    node_type: str,
    node_id: str,
    *,
    children: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "node_type": node_type,
        "name": node_type.title(),
        "budget": _budget_payload(),
        "children": children or [],
        "source_refs": [_source_payload()],
    }


def _tree_response_payload() -> dict[str, object]:
    action = _tree_node_payload("action", "00000000-0000-4000-8000-000000000111")
    programme = _tree_node_payload(
        "programme",
        "00000000-0000-4000-8000-000000000112",
        children=[action],
    )
    mission = _tree_node_payload(
        "mission",
        "00000000-0000-4000-8000-000000000113",
        children=[programme],
    )
    return {"release": _release_payload(), "root": mission}


def _node_detail_payload() -> dict[str, object]:
    parent = _tree_node_payload("programme", "00000000-0000-4000-8000-000000000121")
    return {
        "id": "00000000-0000-4000-8000-000000000122",
        "release": _release_payload(),
        "node_type": "action",
        "name": "Action",
        "budget": _budget_payload(),
        "parent": parent,
        "children": [],
        "history": [],
        "provenance": [_source_payload()],
    }


def _schema(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _assert_schema_accepts(name: str, payload: Mapping[str, object]) -> None:
    errors = list(_schema(name).iter_errors(payload))
    assert not errors, "schema rejected valid payload: " + "; ".join(
        error.message for error in errors
    )


def _assert_schema_rejects(name: str, payload: Mapping[str, object]) -> None:
    errors = list(_schema(name).iter_errors(payload))
    assert errors, f"schema unexpectedly accepted invalid {name} payload"


def _assert_runtime_rejects(model: type[object], payload: Mapping[str, object]) -> None:
    with pytest.raises(ValidationError):
        cast(type[TreeResponse], model).model_validate_json(json.dumps(payload))


def test_release_is_the_only_published_year_and_required_snapshot_hash() -> None:
    tree_payload = _tree_response_payload()
    node_payload = _node_detail_payload()
    search_payload = {
        "query": "action",
        "hits": [
            {
                "node_id": "00000000-0000-4000-8000-000000000131",
                "node_type": "action",
                "name": "Action",
                "score": 0.9,
                "match_kind": "exact",
            }
        ],
        "total": 1,
        "release": _release_payload(),
    }

    tree = TreeResponse.model_validate_json(json.dumps(tree_payload))
    detail = NodeDetail.model_validate_json(json.dumps(node_payload))
    search = SearchResponse.model_validate_json(json.dumps(search_payload))

    assert tree.release.fiscal_year.value == 2026
    assert detail.release.fiscal_year.value == 2026
    assert search.release.fiscal_year.value == 2026
    assert not {"year"} & set(TreeNode.model_fields)
    assert not {"year"} & set(TreeResponse.model_fields)
    assert not {"year"} & set(NodeDetail.model_fields)
    assert not {"year"} & set(SearchHit.model_fields)
    assert "source_snapshot_hash" in ReleaseInfo.model_fields

    _assert_schema_accepts("tree_response", tree_payload)
    _assert_schema_accepts("node_detail", node_payload)
    _assert_schema_accepts("search_response", search_payload)

    without_hash = copy.deepcopy(_release_payload())
    del without_hash["source_snapshot_hash"]
    _assert_runtime_rejects(ReleaseInfo, without_hash)
    _assert_schema_rejects("release_info", without_hash)


def test_tree_schema_and_runtime_reject_action_directly_under_mission() -> None:
    payload = _tree_response_payload()
    root = cast(dict[str, object], payload["root"])
    root["children"] = [_tree_node_payload("action", "00000000-0000-4000-8000-000000000141")]

    _assert_runtime_rejects(TreeResponse, payload)
    _assert_schema_rejects("tree_response", payload)


def test_node_detail_schema_and_runtime_require_preceding_parent_level() -> None:
    payload = _node_detail_payload()
    parent = cast(dict[str, object], payload["parent"])
    payload["node_type"] = "programme"
    parent["node_type"] = "programme"

    _assert_runtime_rejects(NodeDetail, payload)
    _assert_schema_rejects("node_detail", payload)


def test_action_children_are_rejected_by_tree_schema_and_runtime() -> None:
    payload = _tree_node_payload(
        "action",
        "00000000-0000-4000-8000-000000000151",
        children=[_tree_node_payload("action", "00000000-0000-4000-8000-000000000152")],
    )

    _assert_runtime_rejects(TreeNode, payload)
    _assert_schema_rejects("tree_node", payload)


def test_error_and_critical_blocked_false_are_rejected_by_schema_and_runtime() -> None:
    for severity in ("error", "critical"):
        payload = {
            "code": "UNSAFE",
            "severity": severity,
            "message": "Publication must stop.",
            "blocked": False,
        }
        _assert_runtime_rejects(AnomalySummary, payload)
        _assert_schema_rejects("anomaly_summary", payload)


def test_source_ref_accepts_http_https_only_in_runtime_and_schema() -> None:
    for invalid_url in (
        "ftp://example.test/source",
        "https://",
        "https:///path",
        "https://?q=1",
    ):
        invalid_payload = _source_payload(url=invalid_url)
        _assert_runtime_rejects(SourceRef, invalid_payload)
        _assert_schema_rejects("source_ref", invalid_payload)

    _assert_schema_accepts("source_ref", _source_payload(url="http://example.test/source"))
    _assert_schema_accepts(
        "source_ref",
        _source_payload(
            url="https://www.budget.gouv.fr/documentation/file-download/32270",
        ),
    )


def test_search_hit_requires_match_kind_and_supports_semantic_reconstruction() -> None:
    payload = {
        "node_id": "00000000-0000-4000-8000-000000000161",
        "node_type": "mission",
        "name": "Mission",
        "score": 0.5,
        "match_kind": "semantic",
    }
    hit = SearchHit.model_validate_json(json.dumps(payload))

    assert hit.match_kind == "semantic"
    schema = SearchHit.model_json_schema()
    assert schema["$defs"]["MatchKind"]["enum"] == [
        "exact",
        "lexical",
        "semantic",
    ]
    _assert_schema_accepts("search_hit", payload)

    without_match_kind = copy.deepcopy(payload)
    del without_match_kind["match_kind"]
    _assert_runtime_rejects(SearchHit, without_match_kind)
    _assert_schema_rejects("search_hit", without_match_kind)


def test_explanation_requires_complete_non_empty_provenance_fields() -> None:
    payload = {
        "summary": "Résumé.",
        "what_it_funds": "Le périmètre financé.",
        "main_changes": "La variation publiée.",
        "limitations": "Aucune explication supplémentaire disponible.",
        "source_fragment_ids": [SOURCE_ID],
    }
    explanation = Explanation.model_validate_json(json.dumps(payload))

    assert explanation.limitations.startswith("Aucune")
    _assert_schema_accepts("explanation", payload)

    for field in ("summary", "what_it_funds", "main_changes", "limitations", "source_fragment_ids"):
        incomplete = copy.deepcopy(payload)
        del incomplete[field]
        _assert_runtime_rejects(Explanation, incomplete)
        _assert_schema_rejects("explanation", incomplete)


def test_released_at_must_be_utc() -> None:
    payload = _release_payload()
    payload["released_at"] = "2026-01-15T10:30:00+01:00"

    _assert_runtime_rejects(ReleaseInfo, payload)
    _assert_schema_rejects("release_info", payload)


def test_released_at_rejects_invalid_calendar_dates() -> None:
    payload = _release_payload()
    payload["released_at"] = "2026-02-30T10:30:00Z"

    _assert_runtime_rejects(ReleaseInfo, payload)
    _assert_schema_rejects("release_info", payload)


def test_tree_response_rejects_duplicate_node_uuids_at_runtime() -> None:
    payload = _tree_response_payload()
    root = cast(dict[str, object], payload["root"])
    children = cast(list[dict[str, object]], root["children"])
    children[0]["id"] = root["id"]

    _assert_runtime_rejects(TreeResponse, payload)
