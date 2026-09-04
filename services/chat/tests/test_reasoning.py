"""Separating a reasoning model's thinking from its answer.

The hazard throughout is that these tags arrive in pieces. A model streams
`</think>` as readily in five fragments as in one, so every test here that
matters feeds the tag split at an awkward place: a splitter that passes on
whole tags and fails on divided ones would show readers half a tag mid
sentence, which is exactly the bug the buffering exists to prevent.
"""

from __future__ import annotations

from primer_chat.reasoning import Channel, Fragment, ReasoningSplitter


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
