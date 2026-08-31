"""Generate the HTTP API reference from the services' OpenAPI schemas.

Run: uv run python scripts/generate_api_reference.py

Generated rather than written by hand so it cannot drift: a route that
changes its shape changes this page in the same commit, and a route nobody
documented still appears.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "reference" / "http-api.md"

METHOD_ORDER = ["get", "post", "patch", "put", "delete"]


def load_schemas() -> list[tuple[str, str, dict[str, Any]]]:
    """Every service that exposes an HTTP surface, and what it is for."""
    from primer_control.app import create_app as control_app
    from primer_control.config import Settings as ControlSettings

    # A real database is never touched: the schema comes from the route
    # signatures, and the app is built with settings that connect to nothing.
    control = control_app(ControlSettings(auth_mode="oidc"))
    return [
        (
            "Control API",
            "Everything a user's browser talks to: libraries, documents, and identity.",
            control.openapi(),
        )
    ]


def render_schema(name: str, blurb: str, schema: dict[str, Any]) -> list[str]:
    lines = [f"## {name}", "", blurb, ""]
    for path, operations in sorted(schema.get("paths", {}).items()):
        for method in METHOD_ORDER:
            operation = operations.get(method)
            if operation is None:
                continue
            lines += render_operation(method, path, operation)
    return lines


def render_operation(method: str, path: str, operation: dict[str, Any]) -> list[str]:
    summary = operation.get("summary") or path
    lines = [f"### `{method.upper()} {path}`", "", f"{summary}.", ""]

    parameters = operation.get("parameters") or []
    if parameters:
        lines += ["| Parameter | In | Required |", "| --- | --- | --- |"]
        for parameter in parameters:
            required = "yes" if parameter.get("required") else "no"
            lines.append(f"| `{parameter['name']}` | {parameter['in']} | {required} |")
        lines.append("")

    responses = operation.get("responses") or {}
    if responses:
        lines += ["| Status | Meaning |", "| --- | --- |"]
        for status, response in sorted(responses.items()):
            lines.append(f"| `{status}` | {response.get('description', '').strip()} |")
        lines.append("")
    return lines


def main() -> None:
    lines = [
        "# HTTP API",
        "",
        "Generated from the running services' OpenAPI schemas, so it cannot",
        "drift from the routes it describes.",
        "",
        "Every error response is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)",
        "problem document with a stable `code`. Endpoints under `/internal` are",
        "not listed: they are reachable only from inside the cluster, and the",
        "edge proxy must not route them.",
        "",
    ]
    for name, blurb, schema in load_schemas():
        lines += render_schema(name, blurb, schema)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines).rstrip() + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
