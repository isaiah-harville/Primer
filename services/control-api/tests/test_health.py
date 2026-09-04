"""Health, readiness, error shape, and correlation behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient
from primer_control.app import create_app
from primer_control.config import Settings
from primer_control.health import DependencyRegistry
from primer_service.db import Database


class ReachableDatabase(Database):
    """A database whose connectivity probe succeeds without a server."""

    async def check(self) -> bool:
        return True


def test_liveness_needs_no_identity(oidc_client: TestClient) -> None:
    assert oidc_client.get("/health/live").status_code == 200


def test_readiness_passes_when_every_dependency_is_reachable() -> None:
    settings = Settings(auth_mode="disabled")
    app = create_app(settings, database=ReachableDatabase(settings.database_url))
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": True}}


def test_readiness_reports_an_unreachable_database(disabled_client: TestClient) -> None:
    """The fixture points at a database that is not running."""
    response = disabled_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False


def test_a_probe_that_raises_counts_as_unready() -> None:
    def explode() -> bool:
        raise RuntimeError("probe blew up")

    registry = DependencyRegistry()
    registry.register("storage", explode)
    settings = Settings(auth_mode="disabled")
    app = create_app(
        settings, dependencies=registry, database=ReachableDatabase(settings.database_url)
    )
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"storage": False, "database": True}


def test_errors_use_the_problem_detail_contract(oidc_client: TestClient) -> None:
    body = oidc_client.get("/api/v1/me").json()
    assert set(body) >= {"code", "title", "status", "request_id"}
    assert body["status"] == 401


def test_responses_echo_a_client_request_id(disabled_client: TestClient) -> None:
    response = disabled_client.get("/api/v1/me", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_responses_generate_a_request_id_when_absent(disabled_client: TestClient) -> None:
    assert disabled_client.get("/api/v1/me").headers["x-request-id"]


def test_openapi_documents_the_identity_and_health_routes(disabled_client: TestClient) -> None:
    paths = disabled_client.get("/openapi.json").json()["paths"]
    assert {"/api/v1/me", "/health/live", "/health/ready"} <= set(paths)
