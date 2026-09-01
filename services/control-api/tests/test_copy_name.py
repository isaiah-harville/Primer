"""Naming a copy.

The name is a column with a limit, and a library already at that limit still
has to be copyable. Losing the end of a long name is a smaller problem than
refusing the request.
"""

from __future__ import annotations

from primer_control.services.duplication import MAX_NAME, copy_name


def test_a_short_name_gains_a_suffix() -> None:
    assert copy_name("Papers") == "Papers (copy)"


def test_a_long_name_is_trimmed_to_fit() -> None:
    name = copy_name("x" * MAX_NAME)

    assert len(name) == MAX_NAME
    assert name.endswith(" (copy)")


def test_trimming_does_not_leave_a_dangling_space() -> None:
    """A name cut mid-word would otherwise read as 'Some words  (copy)'."""
    name = copy_name(f"{'x' * 110} word")

    assert "  (copy)" not in name
    assert len(name) <= MAX_NAME


def test_copying_a_copy_stays_within_the_limit() -> None:
    """Someone will do this repeatedly, and each round must still fit."""
    name = "Papers"
    for _ in range(10):
        name = copy_name(name)
        assert len(name) <= MAX_NAME
