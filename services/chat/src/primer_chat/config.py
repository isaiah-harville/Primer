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
    #: Further models on the same endpoint that a user may choose between.
    #: Listed by the operator rather than discovered: an endpoint often serves
    #: models nobody meant to expose here, and one of them being expensive or
    #: unreviewed is not something to find out from a dropdown.
    chat_models: tuple[str, ...] = Field(default=())
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

    @property
    def selectable_models(self) -> tuple[str, ...]:
        """Every model a user may ask for, the default first.

        Order is the offer: the configured `chat_model` is what a request
        with no preference gets, so it leads. Duplicates are dropped rather
        than rejected, because listing the default again in `chat_models` is
        an easy thing to write and a silly thing to fail startup over.
        """
        ordered = [self.chat_model, *self.chat_models]
        return tuple(dict.fromkeys(name for name in ordered if name))

    def resolve_model(self, requested: str | None) -> str | None:
        """The model to use, or None if the request named an unknown one.

        An unknown name is refused rather than silently replaced with the
        default. A user who picked a model and got an answer from a different
        one has been misled about where the answer came from, and Primer
        records that model against the message as provenance.
        """
        if requested is None:
            return self.chat_model
        return requested if requested in self.selectable_models else None

    subject_header: str = Field(default="X-Auth-Request-User")
    email_header: str = Field(default="X-Auth-Request-Email")
    auth_mode: str = Field(default="disabled")
