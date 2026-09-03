"""Holding a provider's API key without leaking it.

The value being protected is usually somebody's paid account with a third
party, and the thing it is being protected from is Primer's own database
turning up somewhere it should not - a backup, a replica, a support session.
So the properties worth pinning are about what an attacker holding the
database still does not have.
"""

from __future__ import annotations

import base64
import os

import pytest
from primer_chat.secrets import SecretBox, SecretsUnavailable, UndecryptableSecret

A_VALUE_TO_SEAL = "sk-not-a-real-key-only-something-to-encrypt"


def a_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def test_a_sealed_value_comes_back() -> None:
    box = SecretBox(a_key())
    assert box.open(box.seal(A_VALUE_TO_SEAL)) == A_VALUE_TO_SEAL


def test_the_stored_form_does_not_contain_the_secret() -> None:
    """The whole point: the database holds nothing usable."""
    sealed = SecretBox(a_key()).seal(A_VALUE_TO_SEAL)
    assert A_VALUE_TO_SEAL not in sealed


def test_sealing_the_same_value_twice_differs() -> None:
    """A fresh nonce each time.

    Reusing one under the same key is the single mistake AES-GCM does not
    survive, and identical ciphertexts would also tell a reader of the
    database which providers share a key.
    """
    box = SecretBox(a_key())
    assert box.seal(A_VALUE_TO_SEAL) != box.seal(A_VALUE_TO_SEAL)


def test_another_key_cannot_open_it() -> None:
    """Reported, not returned wrong.

    This is what a rotated or regenerated key looks like, and it is worth
    telling an operator apart from a provider that simply has no key.
    """
    sealed = SecretBox(a_key()).seal(A_VALUE_TO_SEAL)
    with pytest.raises(UndecryptableSecret):
        SecretBox(a_key()).open(sealed)


def test_a_tampered_value_is_refused() -> None:
    """GCM authenticates, so an edited row does not decrypt to anything."""
    box = SecretBox(a_key())
    sealed = box.seal(A_VALUE_TO_SEAL)
    tampered = base64.b64encode(bytes(base64.b64decode(sealed)[:-1]) + b"\x00").decode()
    with pytest.raises(UndecryptableSecret):
        box.open(tampered)


class TestWithNoEncryptionKeyConfigured:
    """Fails closed. Storing a credential in the clear is not a fallback."""

    def test_storing_is_refused(self) -> None:
        with pytest.raises(SecretsUnavailable):
            SecretBox(None).seal(A_VALUE_TO_SEAL)

    def test_reading_is_refused(self) -> None:
        with pytest.raises(SecretsUnavailable):
            SecretBox(None).open("anything")

    def test_it_says_so_rather_than_pretending(self) -> None:
        assert not SecretBox(None).available


class TestAKeyOfTheWrongShape:
    """Refused at construction, not padded into something weaker."""

    def test_a_short_key_is_refused(self) -> None:
        with pytest.raises(SecretsUnavailable):
            SecretBox(base64.b64encode(os.urandom(16)).decode())

    def test_nonsense_is_refused(self) -> None:
        with pytest.raises(SecretsUnavailable):
            SecretBox("not a key at all")

    def test_hex_is_accepted_too(self) -> None:
        """`openssl rand -hex 32` is what an operator reaches for."""
        box = SecretBox(os.urandom(32).hex())
        assert box.open(box.seal(A_VALUE_TO_SEAL)) == A_VALUE_TO_SEAL
