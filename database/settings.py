from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_serializer, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Environment-backed settings for PostgreSQL-only application code."""

    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "TEST_DATABASE_URL"),
        min_length=1,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError("DATABASE_URL must use a PostgreSQL URL")
        if not parts.netloc or not parts.path.removeprefix("/"):
            raise ValueError("DATABASE_URL must include a host and database name")
        return value

    @field_serializer("database_url")
    def _serialize_database_url(self, _value: str) -> str:
        return "[REDACTED]"

    def __repr__(self) -> str:
        return "DatabaseSettings(database_url='[REDACTED]')"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return "postgresql+psycopg://" + self.database_url.removeprefix("postgres://")
        if self.database_url.startswith("postgresql://"):
            return "postgresql+psycopg://" + self.database_url.removeprefix("postgresql://")
        if self.database_url.startswith("postgresql+psycopg://"):
            return self.database_url
        raise ValueError("DATABASE_URL must use a PostgreSQL URL")


def validated_sqlalchemy_url(raw_url: str | None = None) -> str:
    """Return the validated SQLAlchemy URL used by application and Alembic code."""

    settings = DatabaseSettings(database_url=raw_url) if raw_url is not None else DatabaseSettings()
    return settings.sqlalchemy_url
