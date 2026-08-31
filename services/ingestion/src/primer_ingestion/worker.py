"""Worker entrypoint.

Run with: celery -A primer_ingestion.worker worker -Q ingestion.parse,...

Registering every stage in one place means a worker either knows how to run
a stage or fails it loudly. A process that silently lacked a handler would
mark documents failed for a deployment reason, so the registration is not
conditional on anything.
"""

from __future__ import annotations

from primer_contracts.ingestion import StageName

from primer_ingestion.config import Settings
from primer_ingestion.stages.delete import DeleteStage
from primer_ingestion.stages.embed import EmbedStage
from primer_ingestion.stages.index import IndexStage
from primer_ingestion.stages.parse import ParseStage
from primer_ingestion.tasks import app, register_handler


def register_stages(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    register_handler(StageName.PARSE, ParseStage(settings))
    register_handler(StageName.EMBED, EmbedStage(settings))
    register_handler(StageName.INDEX, IndexStage(settings))
    register_handler(StageName.DELETE, DeleteStage(settings))


register_stages()

__all__ = ["app", "register_stages"]
