"""Test helpers shared by the Control API integration tests."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient, Response


class UserClient:
    """Acts as one edge-authenticated subject.

    Tests drive authorization the way the deployment does - through the
    trusted identity header the edge injects - rather than by overriding the
    principal dependency, so the boundary itself stays under test.
    """

    def __init__(self, http: AsyncClient, subject: str) -> None:
        self._http = http
        self._headers = {"X-Auth-Request-User": subject}

    async def get(self, path: str) -> Response:
        return await self._http.get(path, headers=self._headers)

    async def post(self, path: str, payload: dict[str, Any]) -> Response:
        return await self._http.post(path, json=payload, headers=self._headers)

    async def upload(
        self, library_id: str, filename: str, content: bytes, *, document_id: str | None = None
    ) -> Response:
        """Upload as multipart, the way a browser does.

        The part is deliberately labelled application/octet-stream: Primer
        decides the media type from the bytes, and a test that announced the
        real type would not exercise that.
        """
        path = f"/api/v1/libraries/{library_id}/documents"
        if document_id is not None:
            path += f"/{document_id}/versions"
        return await self._http.post(
            path,
            files={"file": (filename, content, "application/octet-stream")},
            headers=self._headers,
        )

    async def patch(self, path: str, payload: dict[str, Any]) -> Response:
        return await self._http.patch(path, json=payload, headers=self._headers)

    async def delete(self, path: str) -> Response:
        return await self._http.delete(path, headers=self._headers)
