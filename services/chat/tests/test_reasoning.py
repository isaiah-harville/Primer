"""Separating a reasoning model's thinking from its answer.

The hazard throughout is that these tags arrive in pieces. A model streams
`</think>` as readily in five fragments as in one, so every test here that
matters feeds the tag split at an awkward place: a splitter that passes on
whole tags and fails on divided ones would show readers half a tag mid
sentence, which is exactly the bug the buffering exists to prevent.

The second hazard is that `<think>` is not the only spelling. Mistral's
reasoning models mark thinking with `[THINK]`, and a splitter that knows
one family hands the reader another family's scratch work as though it were
the reply - silently, since there is no tag left over to look wrong.
"""

from __future__ import annotations

import pytest
from primer_chat.reasoning import DELIMITERS, Channel, Delimiters, Fragment, ReasoningSplitter


def split(fragments: list[str]) -> list[Fragment]:
    splitter = ReasoningSplitter()
    out: list[Fragment] = []
    for fragment in fragments:
        out.extend(splitter.feed(fragment))
    out.extend(splitter.finish())
    return out


def joined(fragments: list[Fragment], channel: Channel) -> str:
    return "".join(f.text for f in fragments if f.channel is channel)


def test_an_answer_with_no_tags_is_all_answer() -> None:
    """Most models are not reasoning models, and must be untouched."""
    out = split(["Hello", " there"])
    assert joined(out, Channel.ANSWER) == "Hello there"
    assert joined(out, Channel.REASONING) == ""


def test_thinking_is_separated_from_the_answer() -> None:
    out = split(["<think>", "I should be brief.", "</think>", "Brief."])
    assert joined(out, Channel.REASONING) == "I should be brief."
    assert joined(out, Channel.ANSWER) == "Brief."


def test_a_tag_split_across_fragments_is_still_a_tag() -> None:
    """The regression this module exists for.

    Every character of both tags is delivered separately, which is the worst
    case a streaming endpoint can produce.
    """
    stream = [*"<think>", "thinking", *"</think>", "answer"]
    out = split(stream)

    assert joined(out, Channel.REASONING) == "thinking"
    assert joined(out, Channel.ANSWER) == "answer"
    assert "<" not in joined(out, Channel.ANSWER)


def test_a_tag_split_at_the_worst_place_is_still_a_tag() -> None:
    out = split(["<thi", "nk>reasoned", "</thi", "nk>said"])
    assert joined(out, Channel.REASONING) == "reasoned"
    assert joined(out, Channel.ANSWER) == "said"


def test_nothing_is_held_back_once_the_answer_is_running() -> None:
    """A reader must see tokens as they arrive, not in a lump at the end.

    Only a possible partial tag may be withheld, so a fragment that cannot
    be the start of one has to come straight out.
    """
    splitter = ReasoningSplitter()
    assert [f.text for f in splitter.feed("Hello there, reader")] == ["Hello there, reader"]


def test_text_ending_in_a_tag_prefix_waits_rather_than_leaking() -> None:
    """The tail is held only until the next fragment settles what it is."""
    splitter = ReasoningSplitter()
    first = list(splitter.feed("Answer<thi"))
    assert "".join(f.text for f in first) == "Answer"

    rest = [*splitter.feed("nk>hidden</think>done"), *splitter.finish()]
    assert joined(rest, Channel.REASONING) == "hidden"


def test_an_unfinished_tag_is_shown_rather_than_swallowed() -> None:
    """A stream cut off mid-tag is output, not a silently dropped fragment."""
    out = split(["Answer so far</thi"])
    assert joined(out, Channel.ANSWER) == "Answer so far</thi"


def test_thinking_resumed_mid_answer_is_still_thinking() -> None:
    """Reasoning models do re-enter thinking after starting to answer.

    The alternative - honouring a tag only at the very start - lets that
    raw markup through into the prose, which is the failure a reader
    actually sees.
    """
    out = split(["Part one.", "<think>", "reconsidering", "</think>", "Part two."])
    assert joined(out, Channel.REASONING) == "reconsidering"
    assert joined(out, Channel.ANSWER) == "Part one.Part two."


def test_unclosed_thinking_stays_thinking() -> None:
    """A model cut off mid-thought has not started answering.

    Emitting it as the answer would put raw scratch work where the reply
    goes, which reads as the model having lost its mind rather than having
    been interrupted.
    """
    out = split(["<think>", "still working on it"])
    assert joined(out, Channel.REASONING) == "still working on it"
    assert joined(out, Channel.ANSWER) == ""


def test_fragments_arrive_in_order_across_both_channels() -> None:
    """Order is what lets the reader watch thinking become an answer."""
    out = split(["<think>a</think>b<think>c</think>d"])
    assert [(f.channel, f.text) for f in out] == [
        (Channel.REASONING, "a"),
        (Channel.ANSWER, "b"),
        (Channel.REASONING, "c"),
        (Channel.ANSWER, "d"),
    ]


def test_mistral_thinking_is_separated() -> None:
    """Magistral and the Ministral 3 reasoning models, written out.

    Named with its literal tags rather than left to the parametrized tests
    below: those draw their cases from `DELIMITERS`, so deleting a pair
    deletes its case too and the suite stays green. This one goes red.
    """
    out = split(["[THINK]", "The budget doubled, so", "[/THINK]", "It doubled."])

    assert joined(out, Channel.REASONING) == "The budget doubled, so"
    assert joined(out, Channel.ANSWER) == "It doubled."


def test_minimax_thinking_is_separated() -> None:
    """Likewise, and for the same reason."""
    out = split(["<mm:think>", "checking the figure", "</mm:think>", "Confirmed."])

    assert joined(out, Channel.REASONING) == "checking the figure"
    assert joined(out, Channel.ANSWER) == "Confirmed."


@pytest.mark.parametrize("pair", DELIMITERS, ids=lambda pair: pair.open)
def test_every_recognized_family_is_separated(pair: Delimiters) -> None:
    """A pair added to `DELIMITERS` has to work, not merely be listed.

    These cases come from the set itself, so they cover additions rather
    than removals - the two tests above are what hold the current families
    in place.
    """
    out = split([pair.open, "scratch work", pair.close, "The answer."])

    assert joined(out, Channel.REASONING) == "scratch work"
    assert joined(out, Channel.ANSWER) == "The answer."


@pytest.mark.parametrize("pair", DELIMITERS, ids=lambda pair: pair.open)
def test_every_recognized_family_survives_being_split(pair: Delimiters) -> None:
    """One character at a time, which is the worst a streaming endpoint does."""
    out = split([*pair.open, "scratch work", *pair.close, "The answer."])

    assert joined(out, Channel.REASONING) == "scratch work"
    assert joined(out, Channel.ANSWER) == "The answer."
    assert "<" not in joined(out, Channel.ANSWER)
    assert "[" not in joined(out, Channel.ANSWER)


def test_no_tag_is_a_prefix_of_another() -> None:
    """The invariant `_find` rests on.

    The earliest match is taken without checking whether a longer tag starts
    in the same place. That is only safe while no tag begins with another;
    a pair that broke it would have its opening tag half-consumed and the
    remainder shown as though the model had written it.
    """
    tags = [tag for pair in DELIMITERS for tag in (pair.open, pair.close)]

    assert len(tags) > 1
    for tag in tags:
        others = [other for other in tags if other != tag]
        assert others
        assert not [other for other in others if other.startswith(tag)]


def test_pairs_are_never_crossed() -> None:
    """Another family's closing tag does not end this family's thought.

    A model discussing reasoning syntax will write the other spellings out,
    and honouring them would end the thought early and put the rest of the
    scratch work into the answer.
    """
    out = split(["<think>", "Mistral writes [/THINK] instead.", "</think>", "Noted."])

    assert joined(out, Channel.REASONING) == "Mistral writes [/THINK] instead."
    assert joined(out, Channel.ANSWER) == "Noted."


def test_an_unopened_closing_tag_is_left_alone() -> None:
    """The deliberate non-guess, kept for every family.

    A server that opened the thought in its prompt template sends only the
    closing tag. Treating what came before as thinking means holding a whole
    answer back on the chance one is coming, so it is answer text instead.
    """
    out = split(["Already answering[/THINK] and continuing."])

    assert joined(out, Channel.ANSWER) == "Already answering[/THINK] and continuing."
    assert joined(out, Channel.REASONING) == ""


def test_a_mistral_tag_prefix_waits_rather_than_leaking() -> None:
    """The held tail is computed from every tag that could still come."""
    splitter = ReasoningSplitter()
    first = list(splitter.feed("Answer[THI"))

    assert "".join(f.text for f in first) == "Answer"

    rest = [*splitter.feed("NK]hidden[/THINK]done"), *splitter.finish()]
    assert joined(rest, Channel.REASONING) == "hidden"
    assert joined(rest, Channel.ANSWER) == "done"
