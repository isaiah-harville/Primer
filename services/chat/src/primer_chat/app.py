"""Chat application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from primer_chat import __version__
from primer_chat.clients import ControlClient, LibraryAuthority, PassageSource, RetrievalClient
from primer_chat.config import Settings
from primer_chat.db import Database
from primer_chat.errors import ProblemError, problem_response, rendered, validation_problem
from primer_chat.generation import ChatGenerator, HaystackChatGenerator
from primer_chat.routes import router
from primer_chat.routes_tools import router as tool_router
from primer_chat.streaming import Responder


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    control: LibraryAuthority | None = None,
    retrieval: PassageSource | None = None,
    generator: ChatGenerator | None = None,
) -> FastAPI:
    """Build the Chat service.

    Control, Retrieval, and the model are injected so the orchestration can
    be exercised end to end without a cluster or an inference endpoint - the
    ordering guarantees are what most need testing, and they do not depend
    on any of the three being real.
    """
    settings = settings or Settings()
    app = FastAPI(
        title="Primer Chat",
        version=__version__,
        summary="Cited, streamed answers grounded in a user's own library",
    )
    app.state.settings = settings
    app.state.database = database or Database(settings.database_url)
    app.state.responder = Responder(
        settings,
        control or ControlClient(settings),
        retrieval or RetrievalClient(settings),
        generator or HaystackChatGenerator(settings),
    )

    @app.exception_handler(ProblemError)
    async def _handle_problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Answer a malformed request in the shape every other failure uses.

        Without this, FastAPI answers in its own: a list of objects under
        `detail`, where the contract promises a string. Clients read it as
        one, and a rejected field arrived on screen as "[object Object]".
        """
        return rendered(request, validation_problem(exc))

    @app.get("/health/live", summary="Process liveness")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", summary="Readiness")
    async def ready() -> JSONResponse:
        reachable = await app.state.database.check()
        return JSONResponse(
            status_code=200 if reachable else 503,
            content={"status": "ok" if reachable else "unready", "database": reachable},
        )

    app.include_router(router)
    app.include_router(tool_router)
    return app
