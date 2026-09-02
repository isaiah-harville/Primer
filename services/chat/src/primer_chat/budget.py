"""Fitting a prompt into the window the model actually has.

Two facts shape this. A context window is finite and differs per model, and
Primer cannot measure a prompt against one: it talks to any
OpenAI-compatible endpoint, so the tokenizer belongs to a model it has never
heard of. Downloading one would be a network call in an air-gapped
deployment and still wrong for half the models people run.

So this estimates, conservatively, and the estimate is tuned by
configuration rather than pretending to be exact. Overflowing is the failure
worth avoiding: a prompt one token too long is refused by the endpoint after
the user has waited, while a prompt that leaves a few hundred tokens unused
costs nothing anyone can see.

What gets cut, and in what order, is the part that matters. The passages
retrieved for this question go in first: an answer that cites the user's
documents is what a library is for, and one written without them is a
different kind of answer wearing the same clothes. The earlier turns go in
second, newest first, because a conversation is understood from its end.
"""

from __future__ import annotations

import math

from primer_contracts.chat import MessageRole

from primer_chat.rag import GroundedContext, HistoryTurn

#: Roughly right for English prose across the tokenizers in common use, and
#: an underestimate for code, tables, and non-Latin scripts - which is why it
#: is configurable. Lower it for a deployment whose documents are none of
#: those things.
CHARACTERS_PER_TOKEN = 4.0

#: Every message costs more than its text: a role, and the framing the
#: endpoint's template puts around it. The exact number is the template's
#: business, so this is a deliberate over-estimate.
MESSAGE_OVERHEAD_TOKENS = 8


def estimate_tokens(text: str, *, characters_per_token: float = CHARACTERS_PER_TOKEN) -> int:
    """What one message is likely to cost, rounded up."""
    return MESSAGE_OVERHEAD_TOKENS + math.ceil(len(text) / characters_per_token)


def passages_that_fit(
    context: GroundedContext,
    *,
    budget: int,
    characters_per_token: float = CHARACTERS_PER_TOKEN,
) -> int:
    """How many passages fit, counting from the best-scoring one.

    A prefix rather than a subset: the passages are numbered in the prompt
    and the citations are parallel to them, so keeping the first `n` is the
    only way to drop any without renumbering what the model was shown.
    """
    spent = 0
    for count, passage in enumerate(context.passages):
        spent += estimate_tokens(passage, characters_per_token=characters_per_token)
        if spent > budget:
            return count
    return len(context.passages)


def history_that_fits(
    history: tuple[HistoryTurn, ...],
    *,
    budget: int,
    characters_per_token: float = CHARACTERS_PER_TOKEN,
) -> tuple[HistoryTurn, ...]:
    """The most recent turns that fit, oldest dropped first."""
    kept: list[HistoryTurn] = []
    remaining = budget
    for turn in reversed(history):
        cost = estimate_tokens(turn.content, characters_per_token=characters_per_token)
        if cost > remaining:
            break
        remaining -= cost
        kept.append(turn)
    kept.reverse()

    # An answer whose question was cut is a non-sequitur, and a model shown
    # one will try to make sense of it. Better to start the replay at a
    # question.
    while kept and kept[0].role is MessageRole.ASSISTANT:
        kept.pop(0)
    return tuple(kept)
