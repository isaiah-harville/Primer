"""Alembic environment for the vector schema.

Retrieval owns a schema but not a set of models: the chunk table's shape is
the vector integration's contract, and it creates that table itself on first
use. What nothing else creates is the schema to put it in and the extension
it depends on, so those are what this migrates.

There is deliberately no `target_metadata`. Autogenerate against an empty
model set would propose dropping the integration's table, which is the one
thing a migration here must never do.
"""

from __future__ import annotations

import os

from alembic import context
from primer_retrieval.config import Settings
from primer_retrieval.db import as_sync_url
from sqlalchemy import engine_from_config, pool, text

config = context.config
VECTOR_SCHEMA = Settings().vector_schema


def resolve_database_url() -> str:
    """Where migrations run; never from a file in the repository."""
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    from_env = os.environ.get("PRIMER_DATABASE_URL")
    if not from_env:
        raise RuntimeError("Set PRIMER_DATABASE_URL to run migrations from the alembic CLI")
    return as_sync_url(from_env)


DATABASE_URL = resolve_database_url()
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=VECTOR_SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = dict(config.get_section(config.config_ini_section, {}))
    section["sqlalchemy.url"] = DATABASE_URL
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # The version table lives in this schema, so the schema has to exist
        # before Alembic can record that the first revision ran.
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {VECTOR_SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            include_schemas=True,
            version_table_schema=VECTOR_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
