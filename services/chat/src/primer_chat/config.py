"""Chat configuration.

Chat holds its own database credentials and its own schema. It shares a
PostgreSQL instance with Control but not a migration history, so the two can
be released independently.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment configuration for the Chat service."""

    model_config = SettingsConfigDict(env_prefix="PRIMER_", extra="forbid")

    database_url: str = Field(
        default="postgresql+asyncpg://primer:primer@localhost:5432/primer",
        description="PostgreSQL URL; migrations are applied out of band, never at startup",
    )

    control_url: str = Field(default="http://control-api:8000")
    retrieval_url: str = Field(default="http://retrieval:8000")
    service_token: SecretStr | None = Field(
        default=None,
        description="Credential presented to Control and Retrieval",
    )
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    #: Any OpenAI-compatible endpoint: vLLM, Ollama, llama.cpp, or a hosted
    #: API. Primer ships no model of its own.
    chat_base_url: str | None = Field(default=None)
    chat_model: str = Field(default="gpt-4o-mini")
    chat_api_key: SecretStr | None = Field(default=None)
    chat_timeout_seconds: float = Field(default=120.0, gt=0)

    retrieval_limit: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Passages retrieved per question; bounds prompt size and cost",
    )
    heartbeat_seconds: float = Field(
        default=15.0,
        gt=0,
        description="Idle keepalive, so a proxy does not close a slow stream",
    )

    subject_header: str = Field(default="X-Auth-Request-User")
    email_header: str = Field(default="X-Auth-Request-Email")
    auth_mode: str = Field(default="disabled")
