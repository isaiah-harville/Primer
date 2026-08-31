"""Alembic environment for the Control schema.

Runs synchronously: migrations are a one-shot operational step, so the async
driver the application uses buys nothing here and complicates failure modes.
"""

from __future__ import annotations

import os

from alembic import context
from primer_control.db import as_sync_url
from primer_control.models import CONTROL_SCHEMA, Base
from sqlalchemy import engine_from_config, pool, text

config = context.config
target_metadata = Base.metadata


def resolve_database_url() -> str:
    """Where migrations run.

    The URL comes from the caller rather than the ini file, so no
    deployment's credentials live in the repository. primer_control.migrations
    sets it directly; the alembic CLI reads PRIMER_DATABASE_URL.
    """
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    from_env = os.environ.get("PRIMER_DATABASE_URL")
    if not from_env:
        raise RuntimeError("Set PRIMER_DATABASE_URL to run migrations from the alembic CLI")
    return as_sync_url(from_env)


DATABASE_URL = resolve_database_url()
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Ignore other services' tables sharing this database."""
    if type_ == "table":
        return obj.schema == CONTROL_SCHEMA
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_object=include_object,
        version_table_schema=CONTROL_SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = dict(config.get_section(config.config_ini_section, {}))
    section["sqlalchemy.url"] = DATABASE_URL
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {CONTROL_SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema=CONTROL_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
