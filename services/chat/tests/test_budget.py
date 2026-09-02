"""Choosing what to leave out of a prompt."""

from __future__ import annotations

from primer_chat.budget import (
    estimate_tokens,
    history_that_fits,
    passages_that_fit,
)
from primer_chat.rag import GroundedContext, HistoryTurn
from primer_contracts.chat import MessageRole


def user(content: str) -> HistoryTurn:
    return HistoryTurn(role=MessageRole.USER, content=content)


def assistant(content: str) -> HistoryTurn:
    return HistoryTurn(role=MessageRole.ASSISTANT, content=content)


def test_an_estimate_charges_for_more_than_the_characters() -> None:
    """A message costs its text plus the framing the endpoint puts around it."""
    assert estimate_tokens("") > 0
    assert estimate_tokens("x" * 400) > estimate_tokens("x" * 4)


def test_everything_fits_when_there_is_room() -> None:
    history = (user("first"), assistant("answer"))

    assert history_that_fits(history, budget=10_000) == history


def test_the_oldest_turns_are_dropped_first() -> None:
    """A conversation is understood from its end, not its beginning."""
    history = (user("a" * 400), assistant("b" * 400), user("c" * 40))

    kept = history_that_fits(history, budget=estimate_tokens("c" * 40) + 1)

    assert kept == (user("c" * 40),)


def test_an_answer_whose_question_was_cut_goes_with_it() -> None:
    """A reply with nothing to reply to reads as a non-sequitur."""
    history = (user("a" * 4000), assistant("short"))

    kept = history_that_fits(history, budget=estimate_tokens("short") + 1)

    assert kept == ()


def test_nothing_fits_in_nothing() -> None:
    assert history_that_fits((user("hello"),), budget=0) == ()
    assert history_that_fits((user("hello"),), budget=-500) == ()


def test_passages_are_kept_as_a_prefix() -> None:
    """The best-scoring ones, so the numbering still starts at one."""
    context = GroundedContext(passages=("[1] " + "a" * 400, "[2] " + "b" * 400), citations=())

    assert passages_that_fit(context, budget=10_000) == 2
    assert passages_that_fit(context, budget=estimate_tokens("[1] " + "a" * 400)) == 1
    assert passages_that_fit(context, budget=1) == 0
