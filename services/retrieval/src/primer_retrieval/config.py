"""Retrieval configuration.

The vector backend is a deployment-wide choice, not a per-library or
per-request one. Mixing backends would mean two isolation implementations to
prove correct instead of one, and the conformance suite exists precisely so
that choosing either is not a change in behavior.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VectorStore = Literal["pgvector", "qdrant"]


class Settings(BaseSettings):
    """Deployment configuration for the Retrieval service."""

    model_config = SettingsConfigDict(env_prefix="PRIMER_", extra="forbid")

    vector_store: VectorStore = "pgvector"

    #: pgvector keeps its tables in their own schema, away from Control's, so
    #: neither service's migrations touch the other's tables.
    database_url: str = Field(default="postgresql://primer:primer@localhost:5432/primer")
    vector_schema: str = Field(default="vectors")
    vector_table: str = Field(default="chunks")

    qdrant_url: str | None = Field(default=None)
    qdrant_index: str = Field(default="primer_chunks")

    #: Any OpenAI-compatible endpoint: a hosted model, or a local server.
    #: Primer never ships an embedding model of its own.
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536, gt=0)
    embedding_base_url: str | None = Field(default=None)
    embedding_api_key: SecretStr | None = Field(default=None)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)

    internal_api_token: SecretStr | None = Field(
        default=None,
        description="Shared credential for this cluster-internal API; unset denies it",
    )

    @model_validator(mode="after")
    def _qdrant_needs_a_url(self) -> Settings:
        """Fail at startup rather than on the first search.

        A Qdrant deployment with no URL cannot answer anything. Discovering
        that when a user asks their first question means the failure surfaces
        as a broken product rather than a broken deployment.
        """
        if self.vector_store == "qdrant" and not self.qdrant_url:
            raise ValueError("vector_store='qdrant' requires qdrant_url")
        return self
