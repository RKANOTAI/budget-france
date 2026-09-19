from __future__ import annotations

import pytest

from scripts.postgres_test_server import (
    PostgresTestServer,
    _normalise_url,
    _redact_url,
    _select_external_url,
)


def test_database_url_redaction_never_emits_password() -> None:
    url = "postgresql://app:super-secret@example.test:5432/budget"
    redacted = _redact_url(_normalise_url(url))
    assert "super-secret" not in redacted
    assert "app:***@" in redacted
    assert "super-secret" not in repr(PostgresTestServer(database_url=_normalise_url(url)))


def test_ambient_database_url_is_not_a_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@example.test/budget")
    monkeypatch.delenv("BUDGET_FRANCE_ALLOW_EXTERNAL_TEST_DATABASE", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _select_external_url(None)


def test_external_test_database_requires_marker_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql://app:secret@example.test/budget_france_test_abc12345"
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setenv("BUDGET_FRANCE_ALLOW_EXTERNAL_TEST_DATABASE", "1")
    assert _select_external_url(None) == _normalise_url(url)

    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://app:secret@example.test/budget")
    with pytest.raises(RuntimeError, match="isolated"):
        _select_external_url(None)


def test_server_start_refuses_ambient_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@example.test/budget")
    monkeypatch.delenv("BUDGET_FRANCE_ALLOW_EXTERNAL_TEST_DATABASE", raising=False)
    with pytest.raises(RuntimeError, match="ambient DATABASE_URL"):
        PostgresTestServer.start(pgroot="/does/not/exist")
