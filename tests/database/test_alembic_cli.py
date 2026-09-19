from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.postgres_test_server import PostgresTestServer

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_cli_consumes_validated_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PostgresTestServer.start()
    try:
        monkeypatch.setenv("DATABASE_URL", server.database_url)
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
        environment = os.environ.copy()
        upgrade = subprocess.run(
            ["uv", "run", "alembic", "-c", "database/alembic.ini", "upgrade", "head"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        assert upgrade.returncode == 0, upgrade.stderr
        downgrade = subprocess.run(
            ["uv", "run", "alembic", "-c", "database/alembic.ini", "downgrade", "base"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        assert downgrade.returncode == 0, downgrade.stderr
    finally:
        server.stop()
