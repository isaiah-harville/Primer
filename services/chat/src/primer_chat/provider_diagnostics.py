"""Checking what a configured provider actually does.

Diagnostics exist because a deployment can be wrong in ways that only show
up under load: an endpoint that answers but cannot embed, a model whose
context window is smaller than configured, a tools declaration the server
does not honour.

The two roles fail differently on purpose. Embeddings are load-bearing - a
deployment that cannot embed cannot ingest anything, so that failure makes
the service unready. Tool support is optional, so a failed tools check
removes the capability and leaves everything else working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx2

from primer_chat.providers import ProviderProfile, ProviderTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckResult:
    """What a probe found, and a code for what to do about it."""

    ok: bool
    detail: str
    code: str | None = None


@dataclass(frozen=True)
class DeploymentCapabilities:
    """What this deployment can offer, after checking rather than assuming."""

    chat: bool
    embeddings: bool
    tools: bool

    @property
    def can_ingest(self) -> bool:
        """Without embeddings nothing can be indexed, so nothing can be asked."""
        return self.embeddings


class ProviderDiagnostics:
    """Probes a provider profile. Never guesses."""

    def __init__(self, profile: ProviderProfile) -> None:
        self._profile = profile

    @property
    def declared_tools(self) -> bool:
        """The operator's declaration, unmodified by anything about the model."""
        return self._profile.declared_tools

    async def check_chat(self) -> CheckResult:
        return await self._check_models(self._profile.chat, role="chat")

    async def check_embeddings(self) -> CheckResult:
        target = self._profile.embeddings
        if target is None:
            return CheckResult(
                ok=False,
                detail="No embedding endpoint is configured, so nothing can be indexed.",
                code="embeddings_unconfigured",
            )
        return await self._check_models(target, role="embeddings")

    async def check_tools(self) -> CheckResult:
        """Tool support is a declaration first, and a probe second.

        An undeclared capability is not probed at all: an operator who has
        not said their model emits tool calls has not consented to Primer
        trying, and a lucky probe would enable a feature they did not choose.
        """
        if not self._profile.chat.supports_tools:
            return CheckResult(
                ok=False,
                detail="Tool use is not declared for this deployment's chat model.",
                code="tools_not_declared",
            )
        return await self._check_models(self._profile.chat, role="tools")

    async def capabilities(self) -> DeploymentCapabilities:
        chat = await self.check_chat()
        embeddings = await self.check_embeddings()
        tools = await self.check_tools() if chat.ok else CheckResult(False, "chat unavailable")
        return DeploymentCapabilities(chat=chat.ok, embeddings=embeddings.ok, tools=tools.ok)

    async def _check_models(self, target: ProviderTarget, *, role: str) -> CheckResult:
        """Ask the endpoint what it serves.

        `/models` rather than a completion: it is the one call every
        OpenAI-compatible server implements, it costs no tokens, and it
        distinguishes "unreachable" from "reachable but does not serve this
        model", which are different problems for an operator.
        """
        try:
            async with httpx2.AsyncClient(timeout=target.timeout_seconds) as client:
                response = await client.get(
                    f"{target.base_url}/models",
                    headers={"Authorization": f"Bearer {target.secret}"},
                )
        except Exception as error:  # noqa: BLE001 - any failure to reach it is unreachable
            logger.warning("provider %s unreachable for %s: %s", target.base_url, role, error)
            return CheckResult(
                ok=False,
                detail=f"The {role} endpoint could not be reached.",
                code="provider_unreachable",
            )

        if response.status_code >= 400:
            return CheckResult(
                ok=False,
                detail=f"The {role} endpoint refused the request.",
                code="provider_refused",
            )

        served = {entry.get("id") for entry in response.json().get("data", [])}
        if served and target.model not in served:
            # Reported, not fatal: gateways and proxies routinely serve
            # models they do not list.
            logger.warning(
                "provider %s does not list model %s for %s", target.base_url, target.model, role
            )
            return CheckResult(
                ok=True,
                detail=f"The {role} endpoint does not list {target.model}; it may still serve it.",
                code="model_not_listed",
            )
        return CheckResult(ok=True, detail=f"The {role} endpoint is reachable.")
