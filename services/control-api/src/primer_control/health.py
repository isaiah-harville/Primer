"""Liveness and readiness.

Liveness answers only "is this process running". Readiness answers "can this
service do its job", and later tasks register PostgreSQL, storage, and
provider probes here. Keeping the two apart stops a slow dependency from
triggering a pointless container restart.
"""

from __future__ import annotations

from collections.abc import Callable

DependencyCheck = Callable[[], bool]


class DependencyRegistry:
    """Readiness checks contributed by the components a deployment enables."""

    def __init__(self) -> None:
        self._checks: dict[str, DependencyCheck] = {}

    def register(self, name: str, check: DependencyCheck) -> None:
        self._checks[name] = check

    def evaluate(self) -> dict[str, bool]:
        """Run every check, treating a raised exception as unready."""
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                results[name] = bool(check())
            except Exception:  # noqa: BLE001 - a failing probe is an unready probe
                results[name] = False
        return results
