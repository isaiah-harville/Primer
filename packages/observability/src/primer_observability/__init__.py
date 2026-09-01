"""Structured logging, tracing, and metrics shared by Primer's services.

The rule this package exists to enforce is that a user's documents never
reach a log, a span, or a metric label. Primer's whole premise is that
people's sources stay on their infrastructure and out of anyone else's
hands; a log line quoting a retrieved passage sends it to whatever collects
logs, which is usually somewhere with much broader read access than the
library it came from.
"""

from primer_observability.logging import (
    CONTENT_FIELDS,
    ContentRedactionFilter,
    JsonFormatter,
    bind_correlation,
    configure_logging,
    correlation_id,
)
from primer_observability.metrics import Metrics, configure_metrics
from primer_observability.tracing import configure_tracing, span_for

__all__ = [
    "CONTENT_FIELDS",
    "ContentRedactionFilter",
    "JsonFormatter",
    "Metrics",
    "bind_correlation",
    "configure_logging",
    "configure_metrics",
    "configure_tracing",
    "correlation_id",
    "span_for",
]

__version__ = "0.1.0"
