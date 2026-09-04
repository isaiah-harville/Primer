"""Holding an API key a deployment typed in rather than deployed.

A provider added through the settings page has to keep its key somewhere
Primer can read back, which means Primer's own database. Storing it in the
clear there would make a database backup, a replica, or a stray `SELECT` into
a credential leak - and unlike Primer's own data, that credential is usually
somebody's paid account with a third party.

So it is encrypted with a key the deployment holds outside the database:
AES-GCM, from a value the chart generates once and the environment supplies.
Ciphertext is worthless to anyone who has the database and not that value.

This is deliberately not a general secrets system. Primer is self-hosted and
should not grow one: an operator who wants a real one puts the key in the
chart instead, where it never touches this module at all.

Fails closed everywhere. With no encryption key configured, a request to
store an API key is refused rather than stored in the clear, and a row that
cannot be decrypted reports that instead of returning something wrong. A
provider whose key cannot be read is a provider that will not authenticate,
and saying so beats sending the wrong header and reporting whatever the
endpoint makes of it.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: AES-256. The chart generates the key, so there is no reason to accept a
#: weaker one for compatibility with anything.
KEY_BYTES = 32

#: 96 bits, which is what GCM is specified for and what every implementation
#: is fastest at. Random per message: a repeated nonce under the same key is
#: the one mistake AES-GCM does not survive.
NONCE_BYTES = 12


class SecretsUnavailable(Exception):
    """No usable encryption key, so nothing may be stored."""


class UndecryptableSecret(Exception):
    """A stored value that this key cannot read.

    Almost always the key having been rotated or regenerated out from under
    the database. Distinguished from "no key" because the fixes differ:
    restore the old key, or re-enter the affected provider's key.
    """


class SecretBox:
    """Encrypts and decrypts values held in Primer's own storage."""

    def __init__(self, key: str | None) -> None:
        self._cipher = AESGCM(_key_from(key)) if key else None

    @property
    def available(self) -> bool:
        """Whether anything can be stored at all.

        Callers check this to refuse a request cleanly rather than raising
        from inside a transaction that has already written other fields.
        """
        return self._cipher is not None

    def seal(self, value: str) -> str:
        """Encrypt, returning something safe to put in a text column.

        The nonce travels with the ciphertext because it must, and it is not
        secret - only its uniqueness matters.
        """
        if self._cipher is None:
            raise SecretsUnavailable(
                "This deployment has no encryption key configured, so an API key cannot be stored."
            )
        nonce = os.urandom(NONCE_BYTES)
        return base64.b64encode(nonce + self._cipher.encrypt(nonce, value.encode(), None)).decode()

    def open(self, sealed: str) -> str:
        """Decrypt, or say that this key cannot."""
        if self._cipher is None:
            raise SecretsUnavailable(
                "This deployment has no encryption key configured, so a stored API key "
                "cannot be read."
            )
        try:
            raw = base64.b64decode(sealed, validate=True)
            nonce, payload = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
            return self._cipher.decrypt(nonce, payload, None).decode()
        except (InvalidTag, ValueError) as error:
            # Both are the same fact to a caller: this key does not open this
            # value. The distinction between a wrong key and a corrupt row is
            # not one an operator can act on differently.
            raise UndecryptableSecret(
                "A stored API key could not be decrypted with this deployment's encryption key."
            ) from error


def _key_from(configured: str) -> bytes:
    """Read the configured key, insisting it is the right size.

    Accepts base64 or hex, because an operator generating one by hand will
    reach for `openssl rand` and get whichever they asked for. A key of the
    wrong length is refused at startup rather than silently padded: a short
    key that appeared to work would be a weakness nobody would ever notice.
    """
    for decode in (_from_base64, bytes.fromhex):
        try:
            raw = decode(configured.strip())
        except (ValueError, TypeError):
            continue
        if len(raw) == KEY_BYTES:
            return raw
    raise SecretsUnavailable(
        f"The configured encryption key must be {KEY_BYTES} bytes, base64 or hex encoded."
    )


def _from_base64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)
