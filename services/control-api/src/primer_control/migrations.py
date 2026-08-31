"""Programmatic Alembic entry points.

Migrations are always an explicit step: a Compose init service, a Kubernetes
pre-upgrade Job, or a test fixture. Nothing here is called from application
startup, so a rolling deploy cannot have two replicas migrating at once.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from primer_control.db import as_sync_url

ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", as_sync_url(database_url))
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


def downgrade_to_base(database_url: str) -> None:
    command.downgrade(alembic_config(database_url), "base")


def check_for_drift(database_url: str) -> None:
    """Raise if the models describe a schema the migrations do not produce.

    Hand-written migrations drift from the ORM silently, and the first
    symptom is usually a production query against a column that never
    existed. This turns that into a test failure.
    """
    command.check(alembic_config(database_url))
