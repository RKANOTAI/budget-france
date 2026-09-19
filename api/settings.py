from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Non-secret HTTP settings for the public API service."""

    cors_origins: str = Field(
        default="https://rkanotai.github.io,http://localhost:4173",
        validation_alias=AliasChoices("CORS_ORIGINS", "API_CORS_ORIGINS"),
    )
    app_version: str = Field(default="0.1.0", validation_alias="API_VERSION")

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must contain explicit HTTPS origins")
        return origins
