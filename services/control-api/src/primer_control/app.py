"""Control API application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from primer_control import __version__
from primer_control.config import Settings
from primer_control.db import Database
from primer_control.errors import ProblemError, problem_response
from primer_control.health import DependencyRegistry
from primer_control.middleware import RequestIDMiddleware
from primer_control.routes import health as health_routes
from primer_control.routes import identity as identity_routes
from primer_control.routes import libraries as library_routes


def create_app(
    settings: Settings | None = None,
    dependencies: DependencyRegistry | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Build the Control API.

    Settings, the readiness registry, and the database are injected rather
    than read from module globals so tests, and later the Compose and Helm
    entrypoints, can compose a deployment without mutating process state.
    """
    settings = settings or Settings()
    app = FastAPI(
        title="Primer Control API",
        version=__version__,
        summary="Public domain operations and authorization for Primer",
    )
    app.state.settings = settings
    app.state.database = database or Database(settings.database_url)
    registry = dependencies or DependencyRegistry()
    registry.register_async("database", app.state.database.check)
    app.state.dependencies = registry

    app.add_middleware(RequestIDMiddleware, header_name=settings.request_id_header)

    @app.exception_handler(ProblemError)
    async def _handle_problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc)

    app.include_router(health_routes.router)
    app.include_router(identity_routes.router)
    app.include_router(library_routes.router)
    return app
