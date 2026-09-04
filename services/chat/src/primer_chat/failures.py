"""Saying which thing went wrong when an answer does not arrive.

Every failure below the generator used to reach the reader as one sentence:
"The model stopped before finishing this answer." For a model that genuinely
stopped that is true. For the rest it is actively misleading - it sends
whoever reads it to look at the model, and the model is usually fine.

The failures worth separating are the ones with different fixes. A rejected
API key is fixed in Primer's settings; an unreachable endpoint is fixed by
starting something; a model the endpoint does not serve is fixed by choosing
another. Collapsing those into one sentence means the person reading it has
to go and read the service log to learn which of them happened, and on a
self-hosted install that person is usually the one who has to fix it.

Two constraints shape what these say. The reader is not always an operator,
so each is a sentence rather than a status code. And none of them quote the
underlying error text: it is written by whatever server answered, it is not
guaranteed to be free of the credential that was rejected, and Primer has no
business forwarding it verbatim into a transcript.
"""

from __future__ import annotations

import openai

from primer_chat.generation import NoEndpoint

#: What the reader is told, by the exception that caused it.
#:
#: Ordered, and deliberately so: `openai` arranges these as a hierarchy, and
#: `APITimeoutError` is a kind of `APIConnectionError` while the four status
#: errors all descend from `APIStatusError`. A dictionary keyed by class
#: would answer for whichever key happened to be checked first, so this is a
#: sequence and the more specific entries come first.
FAILURES: tuple[tuple[type[BaseException], str, str], ...] = (
    (
        openai.AuthenticationError,
        "endpoint_rejected_key",
        "The inference endpoint rejected Primer's API key. The key for this "
        "provider needs to be corrected in settings.",
    ),
    (
        openai.PermissionDeniedError,
        "endpoint_forbidden",
        "The inference endpoint accepted Primer's API key but refused this "
        "request. The key may not be allowed to use this model.",
    ),
    (
        openai.NotFoundError,
        "model_not_found",
        "The inference endpoint does not serve this model. It may have been "
        "unloaded, or renamed since it was chosen.",
    ),
    (
        openai.RateLimitError,
        "endpoint_rate_limited",
        "The inference endpoint is refusing new requests for now. Trying "
        "again shortly is the usual fix.",
    ),
    (
        openai.APITimeoutError,
        "endpoint_timed_out",
        "The inference endpoint accepted the question but did not answer in time.",
    ),
    (
        openai.APIConnectionError,
        "endpoint_unreachable",
        "The inference endpoint could not be reached. It may be down, or "
        "pointed at the wrong address.",
    ),
    (
        openai.BadRequestError,
        "request_rejected",
        "The inference endpoint rejected the request. This usually means the "
        "conversation has grown longer than the model's context window.",
    ),
)

#: What is said when nothing above matches. The model really may have stopped.
GENERIC = ("generation_failed", "The model stopped before finishing this answer.")


def cause_within(error: BaseException, kind: type[BaseException]) -> BaseException | None:
    """Find an exception of `kind` inside whatever the task group raised.

    anyio wraps a failing task in an `ExceptionGroup`, and those nest, so
    this walks rather than checking the outermost type. Without it every
    failure below the generator arrives as a group and matches nothing.
    """
    if isinstance(error, kind):
        return error
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            found = cause_within(nested, kind)
            if found is not None:
                return found
    return None


def describe(error: BaseException) -> tuple[str, str]:
    """The code and the sentence for whatever went wrong.

    `NoEndpoint` carries its own message because it is the one failure whose
    detail is written by Primer rather than inferred: it already knows
    whether nothing was configured or the configured thing was empty.
    """
    missing = cause_within(error, NoEndpoint)
    if missing is not None:
        return "no_endpoint", str(missing)
    for kind, code, detail in FAILURES:
        if cause_within(error, kind) is not None:
            return code, detail
    return GENERIC
