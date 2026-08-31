"""Liveness and readiness.

Liveness answers only "is this process running". Readiness answers "can this
service do its job", and components register their own probes here, so a slow
dependency cannot trigger a pointless container restart.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

DependencyCheck = Callable[[], bool]
AsyncDependencyCheck = Callable[[], Awaitable[bool]]


class DependencyRegistry:
    """Readiness checks contributed by the components a deployment enables."""

    def __init__(self) -> None:
        self._checks: dict[str, DependencyCheck | AsyncDependencyCheck] = {}

    def register(self, name: str, check: DependencyCheck) -> None:
        self._checks[name] = check

    def register_async(self, name: str, check: AsyncDependencyCheck) -> None:
        self._checks[name] = check

    async def evaluate(self) -> dict[str, bool]:
        """Run every check, treating a raised exception as unready.

        A probe that blows up is information about the dependency, not about
        the readiness endpoint, so it reports False instead of a 500.
        """
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                outcome = check()
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                results[name] = bool(outcome)
            except Exception:  # noqa: BLE001 - a failing probe is an unready probe
                results[name] = False
        return results
