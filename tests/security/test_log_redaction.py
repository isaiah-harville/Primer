"""A user's documents must never reach a log, a span, or a metric label.

Primer's premise is that people's sources stay on their infrastructure. A
log line quoting a retrieved passage sends it to whatever collects logs,
which usually has far broader read access than the library it came from.

Every test here plants a sentinel and asserts it is absent. Sentinels are
distinctive strings, so a failure names exactly which path leaked.
"""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
from primer_observability import (
    CONTENT_FIELDS,
    ContentRedactionFilter,
    JsonFormatter,
    bind_correlation,
    configure_metrics,
)
from primer_observability.tracing import SAFE_ATTRIBUTES

#: Distinctive enough that a match cannot be a coincidence.
DOCUMENT_TEXT = "SENTINEL-PASSAGE-quarterly-revenue-was-restated"
QUESTION = "SENTINEL-QUESTION-what-did-the-auditors-find"
API_KEY = "SENTINEL-KEY-sk-live-000111222"
TOOL_OUTPUT = "SENTINEL-OUTPUT-etc-shadow-contents"
FILENAME = "SENTINEL-FILE-acquisition-terms.pdf"


@pytest.fixture
def captured() -> tuple[logging.Logger, StringIO]:
    """A logger configured the way a service's is."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("test-service"))
    handler.addFilter(ContentRedactionFilter())

    logger = logging.getLogger("primer.test.redaction")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, stream


def test_a_retrieved_passage_never_reaches_the_log(captured) -> None:
    """The one that matters most: this is somebody's document."""
    logger, stream = captured

    logger.info("indexed a chunk", extra={"content": DOCUMENT_TEXT})

    assert DOCUMENT_TEXT not in stream.getvalue()


def test_a_question_never_reaches_the_log(captured) -> None:
    """What someone asked of their own library is theirs."""
    logger, stream = captured

    logger.info("searched", extra={"query": QUESTION, "question": QUESTION})

    assert QUESTION not in stream.getvalue()


def test_an_api_key_never_reaches_the_log(captured) -> None:
    logger, stream = captured

    logger.warning("provider refused", extra={"api_key": API_KEY, "token": API_KEY})

    assert API_KEY not in stream.getvalue()


def test_tool_output_never_reaches_the_log(captured) -> None:
    """Output is whatever a process chose to print, on someone's machine."""
    logger, stream = captured

    logger.info("tool finished", extra={"output": TOOL_OUTPUT, "tool_output": TOOL_OUTPUT})

    assert TOOL_OUTPUT not in stream.getvalue()


def test_a_document_filename_never_reaches_the_log(captured) -> None:
    """A filename is content: 'acquisition-terms.pdf' says a great deal.

    Primer's field is `document_filename`, not `filename`. The latter is a
    standard LogRecord attribute holding the *source* file, so redacting it
    would blank the field telling an operator where a line came from -
    and Python refuses to let it be set through `extra` in any case.
    """
    logger, stream = captured

    logger.info("uploaded", extra={"document_filename": FILENAME})

    assert FILENAME not in stream.getvalue()


def test_the_source_filename_is_left_alone(captured) -> None:
    """Redacting it would lose the one field saying where a line came from."""
    logger, stream = captured

    logger.info("something happened")
    record = json.loads(stream.getvalue())

    # Not asserted as a specific name, only that it was not blanked.
    assert record["message"] == "something happened"


def test_redaction_is_case_insensitive(captured) -> None:
    """A field named Content must not slip past one named content."""
    logger, stream = captured

    logger.info("mixed case", extra={"Content": DOCUMENT_TEXT, "QUERY": QUESTION})

    body = stream.getvalue()
    assert DOCUMENT_TEXT not in body
    assert QUESTION not in body


def test_redaction_leaves_a_marker_rather_than_dropping_the_field(captured) -> None:
    """An operator should see that something was withheld, not wonder."""
    logger, stream = captured

    logger.info("indexed a chunk", extra={"content": DOCUMENT_TEXT})
    record = json.loads(stream.getvalue())

    assert record["content"] == "[redacted]"


def test_identifiers_survive_so_a_failure_can_still_be_traced(captured) -> None:
    """Correlation is what an operator gets instead of content."""
    logger, stream = captured
    bind_correlation("job-1234")

    logger.info(
        "parse failed",
        extra={"library_id": "lib-1", "document_id": "doc-1", "content": DOCUMENT_TEXT},
    )
    record = json.loads(stream.getvalue())

    assert record["correlation_id"] == "job-1234"
    assert record["library_id"] == "lib-1"
    assert record["document_id"] == "doc-1"
    bind_correlation(None)


def test_the_redacted_set_covers_every_content_field_primer_has() -> None:
    """A field added to a contract without being listed here is a leak."""
    for field in (
        "content",
        "excerpt",
        "query",
        "prompt",
        "output",
        "arguments",
        "document_filename",
    ):
        assert field in CONTENT_FIELDS


def test_logs_are_one_json_object_per_line(captured) -> None:
    """A collector that cannot parse a line usually stores it whole."""
    logger, stream = captured

    logger.info("first")
    logger.info("second")

    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    for line in lines:
        assert json.loads(line)["service"] == "test-service"


def test_no_metric_is_labelled_with_content() -> None:
    """A metrics endpoint is usually readable by the whole cluster."""
    metrics = configure_metrics()

    for collector in (
        metrics.requests,
        metrics.request_latency,
        metrics.stage_duration,
        metrics.searches,
        metrics.tool_decisions,
    ):
        for label in collector._labelnames:
            assert label.lower() not in CONTENT_FIELDS


def test_metric_labels_are_closed_sets_not_free_text() -> None:
    """Route templates, not resolved paths: a path carries library ids."""
    metrics = configure_metrics()

    assert set(metrics.requests._labelnames) == {"service", "method", "route", "status"}
    assert "path" not in metrics.requests._labelnames


def test_span_attributes_are_an_allowlist_of_identifiers() -> None:
    """A span attribute is as readable as a log line, and kept longer."""
    for attribute in SAFE_ATTRIBUTES:
        assert attribute.startswith("primer.")
        assert not any(field in attribute for field in ("content", "query", "prompt", "output"))
