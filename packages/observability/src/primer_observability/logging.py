"""JSON logs that cannot carry a user's documents.

Redaction here is structural rather than pattern-based. Trying to recognise
document text in a log line is hopeless - a passage about database
passwords looks like a leaked credential, and a passage about anything else
looks like nothing in particular. Instead, fields that are known to carry
content are dropped by name, and anything not explicitly logged is not
logged at all.

The consequence is deliberate: a developer who wants to log a passage has to
add its field name to a place that says, in writing, why it must not be
there.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

#: Fields that carry a user's own text, or a credential. Dropped from every
#: log record regardless of who set them. Names rather than heuristics:
#: guessing at content is how a redactor misses the one line that mattered.
CONTENT_FIELDS = frozenset(
    {
        "content",
        "excerpt",
        "passage",
        "passages",
        "chunk",
        "chunks",
        "document_text",
        "query",
        "question",
        "message",
        "answer",
        "prompt",
        "system_prompt",
        "user_prompt",
        "arguments",
        "output",
        "tool_output",
        "api_key",
        "token",
        "secret",
        "password",
        "authorization",
        # Primer's own field names for a user's filename. Not bare
        # `filename`: that is a standard LogRecord attribute holding the
        # source file, so redacting it would blank the one field telling an
        # operator where a line came from - and Python refuses to let it be
        # set through `extra` anyway.
        "document_filename",
        "source_filename",
        "upload_filename",
    }
)

#: Standard LogRecord attributes, so `extra` fields can be told apart.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}

_correlation: ContextVar[str | None] = ContextVar("primer_correlation_id", default=None)


def correlation_id() -> str | None:
    """The id tying this log line to a request, job, or conversation."""
    return _correlation.get()


def bind_correlation(value: str | None) -> None:
    """Attach a correlation id to everything logged on this task.

    Correlation is the substitute for content. An operator debugging a
    failed ingestion cannot be shown the document, so they are given an id
    that appears on every line the job produced.
    """
    _correlation.set(value)


class ContentRedactionFilter(logging.Filter):
    """Removes content-bearing fields from every record.

    A filter rather than a formatter concern, so it applies no matter how a
    handler is configured. A deployment that added a plain-text handler for
    local debugging would otherwise bypass redaction entirely.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for field in list(record.__dict__):
            if field.lower() in CONTENT_FIELDS:
                record.__dict__[field] = "[redacted]"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the correlation id if there is one.

    The message itself is formatted from the record's own arguments. Those
    are the developer's words; the redaction filter has already replaced any
    structured field that carried user text.
    """

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (current := correlation_id()) is not None:
            payload["correlation_id"] = current

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            # The trace is for the operator, and it is the one place a
            # library might print something it read. It is included because
            # a failure nobody can diagnose is its own harm, and excluded
            # from anything user-facing.
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(service: str, *, level: int = logging.INFO) -> None:
    """Install JSON logging with redaction, replacing any existing handlers."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service))
    handler.addFilter(ContentRedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # These log full request lines including query strings, which is where a
    # search term would end up. Primer logs its own request records instead.
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
