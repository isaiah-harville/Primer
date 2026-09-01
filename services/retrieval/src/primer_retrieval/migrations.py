"""Programmatic access to the vector schema's migrations, for tests and entrypoints."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from primer_retrieval.db import as_sync_url

ALEMBIC_DIR = Path(__file__).parent / "alembic"


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", as_sync_url(url))
    return config


def upgrade_to_head(url: str) -> None:
    command.upgrade(alembic_config(url), "head")


def downgrade_to_base(url: str) -> None:
    command.downgrade(alembic_config(url), "base")
