"""Each failure is reported as itself, not as a model that stopped.

Every failure below the generator used to reach the reader as one sentence -
"The model stopped before finishing this answer." That is true of a model
that stopped and misleading about everything else, and it is the reader who
pays: on a self-hosted install the person reading the transcript is usually
the person who has to go and fix it, and this sentence sends all of them to
look at the model.

The case that prompted this was a 401. The endpoint's API key was wrong and
the transcript said the model stopped.
"""

from __future__ import annotations

import httpx2
import openai
import pytest
from primer_chat.failures import GENERIC, describe
from primer_chat.generation import NoEndpoint


def status_error(kind: type[openai.APIStatusError], code: int) -> openai.APIStatusError:
    """One of the openai errors that carries an HTTP response."""
    request = httpx2.Request("POST", "http://endpoint/v1/chat/completions")
    response = httpx2.Response(code, request=request, json={"error": {"message": "nope"}})
    return kind("nope", response=response, body=None)


def grouped(error: BaseException) -> BaseException:
    """As anyio delivers it: wrapped, and nested more than once."""
    inner: BaseExceptionGroup[BaseException] = BaseExceptionGroup("inner", [error])
    return BaseExceptionGroup("unhandled errors in a TaskGroup", [inner])


def test_a_rejected_api_key_says_so() -> None:
    """The regression. This arrived as "the model stopped"."""
    code, detail = describe(status_error(openai.AuthenticationError, 401))

    assert code == "endpoint_rejected_key"
    assert "key" in detail.lower()


def test_an_unreachable_endpoint_is_not_a_stopped_model() -> None:
    request = httpx2.Request("POST", "http://endpoint/v1/chat/completions")
    code, _ = describe(openai.APIConnectionError(request=request))

    assert code == "endpoint_unreachable"


def test_a_timeout_is_told_apart_from_a_refused_connection() -> None:
    """`APITimeoutError` subclasses `APIConnectionError`, so order matters.

    An endpoint that accepted the question and went quiet is a different
    problem from one that was never there.
    """
    request = httpx2.Request("POST", "http://endpoint/v1/chat/completions")
    code, _ = describe(openai.APITimeoutError(request=request))

    assert code == "endpoint_timed_out"


@pytest.mark.parametrize(
    ("kind", "status", "expected"),
    [
        (openai.PermissionDeniedError, 403, "endpoint_forbidden"),
        (openai.NotFoundError, 404, "model_not_found"),
        (openai.RateLimitError, 429, "endpoint_rate_limited"),
        (openai.BadRequestError, 400, "request_rejected"),
    ],
)
def test_each_status_is_reported_as_itself(
    kind: type[openai.APIStatusError], status: int, expected: str
) -> None:
    """All four descend from `APIStatusError`, so none may swallow another."""
    assert describe(status_error(kind, status))[0] == expected


def test_it_looks_inside_the_exception_group_anyio_raises() -> None:
    """The generator runs in a task group, so nothing arrives bare."""
    assert describe(grouped(status_error(openai.AuthenticationError, 401)))[0] == (
        "endpoint_rejected_key"
    )


def test_no_endpoint_keeps_the_message_primer_wrote() -> None:
    """It is the one failure whose detail Primer already knows precisely."""
    code, detail = describe(grouped(NoEndpoint("Nowhere to send this question.")))

    assert code == "no_endpoint"
    assert detail == "Nowhere to send this question."


def test_an_unrecognised_failure_still_says_something_true() -> None:
    """A model that genuinely stopped is what the old sentence described."""
    assert describe(RuntimeError("something else entirely")) == GENERIC


def test_the_underlying_error_text_is_never_forwarded() -> None:
    """The server writes it, and it may quote the credential it rejected.

    Primer has no business copying that into a transcript, which is why
    these details are written here rather than taken from the response.
    """
    secret = "sk-abcdef123456"  # noqa: S105 - the point is that it must not be echoed
    request = httpx2.Request("POST", "http://endpoint/v1/chat/completions")
    response = httpx2.Response(
        401, request=request, json={"error": {"message": f"Invalid API Key: {secret}"}}
    )
    _, detail = describe(
        openai.AuthenticationError(f"Invalid API Key: {secret}", response=response, body=None)
    )

    assert secret not in detail
