import subprocess
import sys
from pathlib import Path

from scripts.export_contracts import SCHEMA_TYPES

ROOT = Path(__file__).parents[2]


def test_contract_schema_export_check_command_is_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/export_contracts.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_schema_export_uses_concrete_typed_api_envelopes() -> None:
    assert "api_response" not in SCHEMA_TYPES
    assert {
        "tree_api_response",
        "node_api_response",
        "search_api_response",
    } <= SCHEMA_TYPES.keys()
