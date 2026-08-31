from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from primer_control.app import create_app
from primer_control.config import Settings


@pytest.fixture
def disabled_client() -> Iterator[TestClient]:
    settings = Settings(auth_mode="disabled")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def oidc_client() -> Iterator[TestClient]:
    settings = Settings(auth_mode="oidc")
    with TestClient(create_app(settings)) as client:
        yield client
