"""Intermediate results handed between ingestion stages.

Stages run in separate processes and communicate only through job ids, so
what one stage produces has to be durable somewhere the next can read it.
Artifacts live beside source objects in the same filesystem, keyed by
version and generation, so a rebuilt generation writes a new artifact
instead of overwriting the one a running search still depends on.

Everything here is synchronous: only workers use it, and workers have no
event loop to block.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import fsspec


class ArtifactStore:
    """Reads and writes per-generation stage output."""

    def __init__(self, url: str, *, prefix: str = "artifacts") -> None:
        self._fs, self._root = fsspec.core.url_to_fs(url)
        self._prefix = prefix

    def key(self, version_id: UUID, generation_id: UUID, name: str) -> str:
        return str(
            PurePosixPath(self._root, self._prefix, str(version_id), str(generation_id), name)
        )

    def write_json(self, version_id: UUID, generation_id: UUID, name: str, payload: Any) -> str:
        key = self.key(version_id, generation_id, name)
        self._fs.makedirs(str(PurePosixPath(key).parent), exist_ok=True)
        with self._fs.open(key, "wb") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")).encode())
        return key

    def read_json(self, version_id: UUID, generation_id: UUID, name: str) -> Any:
        with self._fs.open(self.key(version_id, generation_id, name), "rb") as handle:
            return json.loads(handle.read())

    def exists(self, version_id: UUID, generation_id: UUID, name: str) -> bool:
        return bool(self._fs.exists(self.key(version_id, generation_id, name)))

    def discard_generation(self, version_id: UUID, generation_id: UUID) -> None:
        """Remove everything a generation produced, once it is no longer needed."""
        directory = str(
            PurePosixPath(self._root, self._prefix, str(version_id), str(generation_id))
        )
        try:
            self._fs.rm(directory, recursive=True)
        except FileNotFoundError:
            return
