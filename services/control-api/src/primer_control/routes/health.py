"""Health endpoints. These never require identity."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from primer_control.health import DependencyRegistry

router = APIRouter(tags=["health"])


def get_dependencies(request: Request) -> DependencyRegistry:
    return request.app.state.dependencies


@router.get("/health/live", summary="Liveness probe")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready", summary="Readiness probe")
def ready(
    response: Response,
    dependencies: Annotated[DependencyRegistry, Depends(get_dependencies)],
) -> dict[str, Any]:
    checks = dependencies.evaluate()
    healthy = all(checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "unready", "checks": checks}
