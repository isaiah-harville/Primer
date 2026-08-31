"""Repository policy checks for the Primer monorepo toolchain."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _root_pyproject() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())


def test_python_runtime_is_pinned_to_3_13() -> None:
    assert (REPO_ROOT / ".python-version").read_text().strip() == "3.13"


def test_project_requires_python_3_13() -> None:
    config = _root_pyproject()
    assert config["project"]["requires-python"] == ">=3.13"


def test_dev_group_provides_the_supported_toolchain() -> None:
    dev = " ".join(_root_pyproject()["dependency-groups"]["dev"])
    for tool in ("ty", "ruff", "pytest"):
        assert tool in dev


def test_unsupported_type_checkers_are_not_configured() -> None:
    config = _root_pyproject()
    tools = config.get("tool", {})
    assert "mypy" not in tools
    assert "pyright" not in tools
    dev = " ".join(config["dependency-groups"]["dev"])
    assert "mypy" not in dev
    assert "pyright" not in dev


def test_workspace_members_cover_packages_and_services() -> None:
    members = _root_pyproject()["tool"]["uv"]["workspace"]["members"]
    assert "packages/*" in members
    assert "services/*" in members


def test_agent_planning_docs_are_untracked_by_policy() -> None:
    """Superpowers specs/plans stay local; user and API docs are tracked."""
    ignored = [
        line.strip().rstrip("/") for line in (REPO_ROOT / ".gitignore").read_text().splitlines()
    ]
    assert "docs/superpowers" in ignored
    assert "docs" not in ignored
