"""Worker configuration.

Workers hold no database credentials. Everything they may do to a job goes
through the Control API, so the only secrets here are a broker URL and the
service credential that identifies this process to Control.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment configuration for an ingestion worker."""

    model_config = SettingsConfigDict(env_prefix="PRIMER_", extra="forbid")

    broker_url: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        description="RabbitMQ URL for ingestion queues",
    )
    control_url: str = Field(
        default="http://control-api:8000",
        description="Cluster-internal base URL of the Control API",
    )
    service_token: SecretStr | None = Field(
        default=None,
        description="Credential presented to the Control internal API",
    )

    request_timeout_seconds: float = Field(default=15.0, gt=0)
    #: Renewed well inside Control's lease so a slow stage is not mistaken
    #: for a dead worker.
    heartbeat_seconds: float = Field(default=60.0, gt=0)

    source_store_url: str = Field(
        default="file:///var/lib/primer/sources",
        description="The same fsspec URL Control writes uploads to",
    )
    max_source_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1,
        description="Matches Control's upload limit; workers only ever read",
    )

    retrieval_url: str = Field(
        default="http://retrieval:8000",
        description="Cluster-internal base URL of the Retrieval service",
    )
    retrieval_token: SecretStr | None = Field(
        default=None,
        description="Credential for Retrieval; falls back to service_token when unset",
    )
    retrieval_timeout_seconds: float = Field(default=120.0, gt=0)
    index_batch_size: int = Field(
        default=64,
        gt=0,
        description="Chunks per index call; bounds embedding cost lost to one timeout",
    )

    chunk_tokenizer: str | None = Field(
        default=None,
        description="Tokenizer of the embedding model, so chunks fit its context window",
    )
    max_chunk_tokens: int = Field(
        default=512,
        gt=0,
        description="Token ceiling per chunk; ignored when no tokenizer is configured",
    )
    max_chunks_per_document: int = Field(
        default=5000,
        gt=0,
        description="Refuse rather than silently index part of an enormous document",
    )
    parse_deadline_seconds: float = Field(
        default=900.0,
        gt=0,
        description="Budget for converting one document, checked between phases",
    )

    max_retries: int = Field(
        default=4,
        ge=0,
        description="Celery retries per stage; Control holds an independent hard bound",
    )
    retry_backoff_seconds: float = Field(default=10.0, gt=0)
    retry_backoff_max_seconds: float = Field(default=600.0, gt=0)

    #: A stage killed at the hard limit never acknowledges, so its lease
    #: expires and the job is re-claimed rather than lost.
    task_time_limit_seconds: int = Field(default=1800, gt=0)
    task_soft_time_limit_seconds: int = Field(default=1500, gt=0)
