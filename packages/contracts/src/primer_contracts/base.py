"""Base configuration shared by every Primer wire model.

Wire models are strict and immutable: unknown fields are rejected so a
producing service cannot silently ship a field a consumer ignores, and
frozen instances keep a contract from being mutated after validation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WireModel(BaseModel):
    """Strict, frozen base for cross-service payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
