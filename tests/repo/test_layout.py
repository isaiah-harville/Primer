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


def test_the_web_app_s_types_are_generated_rather_than_transcribed() -> None:
    """A contract change the web app has not followed should not compile.

    The schemas under `schemas/` are what the types are generated from, and
    CI regenerates both and diffs them. Asserting the wiring here means the
    guard cannot be quietly removed - a hand-written `interface
    LibrarySummary` would pass every other test in this repository.
    """
    types = (REPO_ROOT / "apps" / "web" / "src" / "lib" / "api" / "types.ts").read_text()

    assert "./generated/control" in types
    assert "./generated/chat" in types
    for shape in ("LibrarySummary", "DocumentSummary", "MessageSummary", "ConversationSummary"):
        assert f"export type {shape} = " in types, shape
        assert f"export interface {shape}" not in types, shape


def test_the_identity_boundary_is_still_written_by_hand() -> None:
    """Generation stops at the shapes.

    Which headers this server forwards to Primer is the thing that decides
    who a request is from. It is reviewed, not emitted by a tool from a
    document describing something else.
    """
    server = REPO_ROOT / "apps" / "web" / "src" / "lib" / "server"
    forwarding = (server / "api.ts").read_text() + (server / "chat.ts").read_text()

    assert forwarding.count("x-auth-request-user") == 2
    assert "generated" not in forwarding


def test_the_schemas_are_written_deterministically() -> None:
    """Or the check that they have not drifted fails on dict ordering."""
    script = (REPO_ROOT / "scripts" / "dump_openapi.py").read_text()

    assert "sort_keys=True" in script
