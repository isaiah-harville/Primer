"""Chat's schema, and its separation from Control's."""

from __future__ import annotations

import sqlalchemy as sa
from primer_chat.migrations import check_for_drift, downgrade_to_base, upgrade_to_head
from primer_service.db import as_sync_url
from sqlalchemy import create_engine


def test_the_chat_schema_holds_its_own_tables(migrated_url: str) -> None:
    engine = create_engine(as_sync_url(migrated_url))
    try:
        tables = set(sa.inspect(engine).get_table_names(schema="chat"))
        assert tables >= {"conversations", "messages", "message_citations"}
    finally:
        engine.dispose()


def test_chat_does_not_reach_into_the_control_schema(migrated_url: str) -> None:
    """No foreign keys across the service boundary, in either direction."""
    engine = create_engine(as_sync_url(migrated_url))
    try:
        inspector = sa.inspect(engine)
        for table in ("conversations", "messages", "message_citations"):
            for key in inspector.get_foreign_keys(table, schema="chat"):
                assert key["referred_schema"] in (None, "chat")
    finally:
        engine.dispose()


def test_migrations_match_the_models(migrated_url: str) -> None:
    check_for_drift(migrated_url)


def test_upgrade_and_downgrade_round_trip(scratch_db_url: str) -> None:
    """A migration that cannot be rolled back cannot be safely deployed."""
    upgrade_to_head(scratch_db_url)
    downgrade_to_base(scratch_db_url)

    engine = create_engine(as_sync_url(scratch_db_url))
    try:
        tables = set(sa.inspect(engine).get_table_names(schema="chat"))
        assert not tables & {"conversations", "messages", "message_citations"}
    finally:
        engine.dispose()
