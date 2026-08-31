"""Inference provider targets, and what they are known to support.

Primer runs against any OpenAI-compatible endpoint - vLLM, Ollama's `/v1`,
llama.cpp's `llama-server`, or a hosted API. It ships no model.

Capabilities are declared by the operator, never inferred. A model called
`hermes-3-tool-use` may have been served without a chat template that emits
tool calls, and a model with a dull name may support them perfectly. Guessing
from a name produces a deployment that offers tool use and then fails at the
moment a user tries it, which is worse than not offering it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ProviderTarget(BaseModel):
    """One endpoint, for one role.

    Chat and embeddings are configured separately, because they are commonly
    served by different processes: a large generation model on a GPU and a
    small embedding model beside it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    #: Required, not optional. A context window Primer does not know is a
    #: context window Primer will overrun, and the failure arrives as a
    #: truncated answer rather than an error.
    max_context_tokens: int = Field(gt=0)

    #: Declared by the operator. Never inferred from the model's name.
    supports_tools: bool = False
    supports_json: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize(cls, value: str) -> str:
        """Trim trailing slashes and nothing else.

        Provider paths differ - Ollama and llama.cpp serve at `/v1`, some
        gateways at a prefix of their own - so Primer normalizes only what is
        unambiguous. Rewriting the path would break every deployment whose
        URL was already correct.
        """
        trimmed = value.strip().rstrip("/")
        if not trimmed:
            raise ValueError("base_url must not be empty")
        return trimmed

    @property
    def secret(self) -> str:
        """Many local servers ignore the key but require the header to exist."""
        return self.api_key.get_secret_value() if self.api_key else "none"


class ProviderProfile(BaseModel):
    """Both roles of a deployment, and what it can do."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chat: ProviderTarget
    embeddings: ProviderTarget | None = None

    @property
    def declared_tools(self) -> bool:
        return self.chat.supports_tools
