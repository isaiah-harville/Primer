"""Validated Control API settings.

Authentication is either delegated to a trusted edge (`oidc`) or replaced by
one fixed local identity (`disabled`). Primer never validates OIDC tokens
itself, so the only auth-related configuration here is which trusted headers
the edge injects.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AuthMode = Literal["disabled", "oidc"]


class Settings(BaseSettings):
    """Deployment configuration for the Control API."""

    model_config = SettingsConfigDict(env_prefix="PRIMER_", extra="forbid")

    auth_mode: AuthMode = "disabled"

    database_url: str = Field(
        default="postgresql+asyncpg://primer:primer@localhost:5432/primer",
        description="PostgreSQL URL; migrations are applied out of band, never at startup",
    )

    subject_header: str = Field(
        default="X-Auth-Request-User",
        description="Edge-injected header carrying the stable OIDC subject",
    )
    email_header: str = Field(default="X-Auth-Request-Email")
    groups_header: str = Field(default="X-Auth-Request-Groups")
    groups_delimiter: str = Field(default=",", min_length=1)
    request_id_header: str = Field(default="X-Request-ID")

    @model_validator(mode="after")
    def _oidc_requires_configured_headers(self) -> Settings:
        """OIDC mode without a subject header would authenticate nobody.

        Failing at startup is the only safe outcome: the alternative is a
        deployment that believes it is authenticated but rejects every user,
        or worse, one that silently falls back to a local identity.
        """
        if self.auth_mode == "oidc" and not self.subject_header.strip():
            raise ValueError("auth_mode='oidc' requires a non-empty subject_header")
        return self

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode == "oidc"
