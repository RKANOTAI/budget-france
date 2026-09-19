from __future__ import annotations

import pytest
from pydantic import ValidationError

from database.settings import DatabaseSettings, validated_sqlalchemy_url


def test_database_settings_validates_postgresql_url_without_leaking_credentials() -> None:
    with pytest.raises(ValidationError) as error:
        DatabaseSettings(database_url="mysql://app:top-secret@example.test/budget")
    assert "top-secret" not in str(error.value)


def test_database_settings_normalizes_supported_postgresql_urls() -> None:
    settings = DatabaseSettings(database_url="postgresql://app@example.test/budget")
    assert settings.sqlalchemy_url == "postgresql+psycopg://app@example.test/budget"


def test_database_settings_serialization_is_redacted() -> None:
    settings = DatabaseSettings(database_url="postgresql://app:top-secret@example.test/budget")
    assert "top-secret" not in repr(settings)
    assert "top-secret" not in str(settings.model_dump())


def test_validated_sqlalchemy_url_uses_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://app@example.test/budget")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert validated_sqlalchemy_url() == "postgresql+psycopg://app@example.test/budget"
