"""Reordering a shortlist, and what happens when that cannot be done.

The reranker is an improvement to an ordering that is already correct. So
the properties worth pinning are mostly about it getting out of the way: a
deployment without one behaves exactly as it did before, and one whose
reranker is down returns the vector ordering rather than an error.

A search that failed because the optional stage failed would be a
regression dressed as a feature.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from primer_retrieval.reranking import Reranked, Reranker, reorder


@dataclass
class Hit:
    """Stands in for a retrieved chunk; only its text is read."""

    content: str


def hits(*texts: str) -> list[Hit]:
    return [Hit(content=text) for text in texts]


def text_of(hit: Hit) -> str:
    return hit.content


class Fake(Reranker):
    """A reranker that returns a fixed order, or refuses."""

    def __init__(self, order: list[int] | None = None, fail: bool = False) -> None:
        self.order = order or []
        self.fail = fail
        self.asked: list[tuple[str, int]] = []

    def rank(self, query: str, passages: list[str], keep: int) -> list[Reranked]:
        self.asked.append((query, len(passages)))
        if self.fail:
            raise RuntimeError("the reranker went away")
        return [Reranked(index=index, score=1.0) for index in self.order][:keep]


def test_with_no_reranker_the_vector_order_is_kept() -> None:
    """A deployment without one behaves exactly as it did before."""
    found = hits("a", "b", "c")

    assert reorder(None, "q", found, text_of, 2) == found[:2]


def test_the_reranker_decides_the_order() -> None:
    found = hits("first", "second", "third")
    reordered = reorder(Fake(order=[2, 0, 1]), "q", found, text_of, 2)

    assert [hit.content for hit in reordered] == ["third", "first"]


def test_a_failing_reranker_falls_back_rather_than_failing_the_search() -> None:
    """The one that matters. The vector results are already an answer."""
    found = hits("a", "b", "c")

    assert reorder(Fake(fail=True), "q", found, text_of, 2) == found[:2]


def test_a_reranker_returning_nothing_falls_back_too() -> None:
    """An empty ordering is not an instruction to answer with nothing."""
    found = hits("a", "b", "c")

    assert reorder(Fake(order=[]), "q", found, text_of, 2) == found[:2]


def test_an_index_nobody_retrieved_is_dropped() -> None:
    """A server inventing a position must not index into the wrong passage.

    Out of range is dropped rather than clamped: clamping would silently
    return a passage the reranker never scored, and cite it.
    """
    found = hits("a", "b")
    reordered = reorder(Fake(order=[1, 99, -1, 0]), "q", found, text_of, 4)

    assert [hit.content for hit in reordered] == ["b", "a"]


def test_it_is_given_every_candidate_and_asked_for_the_answer_size() -> None:
    """Search widely, keep a few - the whole point of the two numbers."""
    reranker = Fake(order=[0])
    reorder(reranker, "q", hits(*[str(index) for index in range(20)]), text_of, 6)

    assert reranker.asked == [("q", 20)]


def test_nothing_retrieved_asks_nothing() -> None:
    """A library with no match should not cost a reranker call."""
    reranker = Fake(order=[])
    assert reorder(reranker, "q", [], text_of, 6) == []
    assert reranker.asked == []


@pytest.mark.parametrize("keep", [1, 3, 50])
def test_never_more_than_asked_for(keep: int) -> None:
    found = hits(*[str(index) for index in range(10)])
    assert len(reorder(Fake(order=list(range(10))), "q", found, text_of, keep)) <= keep


# --- The relevance floor ------------------------------------------------
#
# A vector search always returns its top k, so a question the library
# cannot answer comes back with a full set of passages that are merely the
# closest of a bad lot. Measured on a live library before this existed:
# "Describe the plot of the film Casablanca" scored 0.392 against a corpus
# of mortgage paperwork, beating a question the corpus did answer.


@dataclass
class Scored:
    """Stands in for a retrieved chunk that has been ranked."""

    content: str
    score: float | None


def settings_with(floor: float | None):
    from primer_retrieval.config import Settings

    return Settings(database_url="postgresql://x/y", min_score=floor)


def test_nothing_is_dropped_when_no_floor_is_set() -> None:
    """The default, and every deployment that predates this."""
    from primer_retrieval.app import above_floor

    found = [Scored("a", 0.9), Scored("b", 0.01)]

    assert above_floor(found, settings_with(None)) == found


def test_passages_below_the_floor_are_not_returned() -> None:
    from primer_retrieval.app import above_floor

    found = [Scored("answers it", 0.71), Scored("near miss", 0.44), Scored("unrelated", 0.19)]

    kept = above_floor(found, settings_with(0.5))

    assert [hit.content for hit in kept] == ["answers it"]


def test_a_question_the_library_cannot_answer_returns_nothing() -> None:
    """Returning fewer than `limit` is the point, not a side effect.

    An empty result is a true statement about the corpus. A full one made
    of the least bad passages is not, and everything downstream reads it as
    evidence.
    """
    from primer_retrieval.app import above_floor

    assert above_floor([Scored("x", 0.33), Scored("y", 0.31)], settings_with(0.5)) == []


def test_an_unscored_passage_is_treated_as_no_match() -> None:
    """A missing score is not a high one.

    Reading None as zero keeps a store that omits scores from silently
    admitting everything the floor exists to exclude.
    """
    from primer_retrieval.app import above_floor

    assert above_floor([Scored("x", None)], settings_with(0.1)) == []
