"""Alembic behavior: fresh install, forward upgrade, and rollback."""

from __future__ import annotations

import sqlalchemy as sa
from primer_control.db import as_sync_url
from primer_control.migrations import check_for_drift, downgrade_to_base, upgrade_to_head
from sqlalchemy import create_engine


def test_upgrade_creates_the_control_schema(migrated_url: str) -> None:
    engine = create_engine(as_sync_url(migrated_url))
    try:
        inspector = sa.inspect(engine)
        assert set(inspector.get_table_names(schema="control")) >= {"users", "libraries"}
    finally:
        engine.dispose()


def test_control_tables_stay_out_of_the_public_schema(migrated_url: str) -> None:
    engine = create_engine(as_sync_url(migrated_url))
    try:
        assert "libraries" not in sa.inspect(engine).get_table_names(schema="public")
    finally:
        engine.dispose()


def test_constraint_names_are_deterministic(migrated_url: str) -> None:
    engine = create_engine(as_sync_url(migrated_url))
    try:
        inspector = sa.inspect(engine)
        unique = inspector.get_unique_constraints("users", schema="control")
        assert any(c["name"] == "uq_users_subject" for c in unique)
        foreign = inspector.get_foreign_keys("libraries", schema="control")
        assert any(c["name"] == "fk_libraries_owner_user_id_users" for c in foreign)
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_round_trip(scratch_db_url: str) -> None:
    """A migration that cannot be rolled back cannot be safely deployed.

    This runs against its own database so rolling the schema back cannot
    disturb the shared migrated fixture other tests depend on.
    """
    upgrade_to_head(scratch_db_url)
    downgrade_to_base(scratch_db_url)

    engine = create_engine(as_sync_url(scratch_db_url))
    try:
        tables = set(sa.inspect(engine).get_table_names(schema="control"))
        assert not tables & {"users", "libraries"}
    finally:
        engine.dispose()


def test_migrations_match_the_models(migrated_url: str) -> None:
    """The schema at head is exactly what the SQLAlchemy models describe."""
    check_for_drift(migrated_url)
