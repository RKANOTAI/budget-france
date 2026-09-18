"""Export and verify the public Pydantic contract JSON Schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.contracts import (  # noqa: E402
    AnomalySummary,
    BudgetValue,
    Explanation,
    FiscalYear,
    HistoryPoint,
    Money,
    NodeApiResponse,
    NodeDetail,
    NodeType,
    ProblemDetails,
    ReleaseInfo,
    SearchApiResponse,
    SearchHit,
    SearchResponse,
    SourceRef,
    TreeApiResponse,
    TreeNode,
    TreeResponse,
)

SCHEMA_TYPES: dict[str, Any] = {
    "fiscal_year": FiscalYear,
    "node_type": NodeType,
    "release_info": ReleaseInfo,
    "money": Money,
    "budget_value": BudgetValue,
    "source_ref": SourceRef,
    "explanation": Explanation,
    "tree_node": TreeNode,
    "tree_response": TreeResponse,
    "history_point": HistoryPoint,
    "node_detail": NodeDetail,
    "search_hit": SearchHit,
    "search_response": SearchResponse,
    "anomaly_summary": AnomalySummary,
    "tree_api_response": TreeApiResponse,
    "node_api_response": NodeApiResponse,
    "search_api_response": SearchApiResponse,
    "problem_details": ProblemDetails,
}

SCHEMA_DIR = ROOT / "packages" / "contracts" / "schemas"


def _schema_for(contract_type: Any) -> dict[str, Any]:
    return TypeAdapter(contract_type).json_schema(mode="serialization")


def _render_schemas() -> dict[str, str]:
    return {
        f"{name}.json": json.dumps(
            _schema_for(contract_type),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
        for name, contract_type in SCHEMA_TYPES.items()
    }


def export_schemas(output_dir: Path = SCHEMA_DIR, *, check: bool = False) -> int:
    """Write schemas, or return non-zero when committed files differ."""

    expected = _render_schemas()
    actual = (
        {path.name: path.read_text(encoding="utf-8") for path in output_dir.glob("*.json")}
        if output_dir.exists()
        else {}
    )

    expected_names = set(expected)
    actual_names = set(actual)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    changed = sorted(
        name for name in expected_names & actual_names if actual[name] != expected[name]
    )

    if check:
        if missing or extra or changed:
            for name in missing:
                print(f"missing schema: {output_dir / name}")
            for name in changed:
                print(f"out-of-date schema: {output_dir / name}")
            for name in extra:
                print(f"unexpected schema: {output_dir / name}")
            return 1
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (output_dir / name).write_text(content, encoding="utf-8")
    for name in extra:
        (output_dir / name).unlink()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated files are stale")
    args = parser.parse_args()
    return export_schemas(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
