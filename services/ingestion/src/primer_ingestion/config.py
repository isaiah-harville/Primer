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
