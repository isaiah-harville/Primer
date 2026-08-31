"""Repository-wide pytest configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark everything under an `integration/` directory automatically.

    These tests start a real PostgreSQL container, so a contributor without
    Docker can run `pytest -m "not integration"`. CI runs the whole suite.
    """
    for item in items:
        if "integration" in Path(str(item.fspath)).parts:
            item.add_marker("integration")
