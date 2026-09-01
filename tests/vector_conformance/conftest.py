"""One suite, run against every backend Primer claims to support.

A vector store is only usable here if it can keep one library's contents
away from another's. Running identical cases against each backend is how
that claim is checked, rather than trusted because the integration exists.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conformance_support import DIMENSIONS
from haystack.document_stores.types import DocumentStore
from primer_retrieval.config import Settings
from primer_retrieval.migrations import upgrade_to_head
from primer_retrieval.stores import build_document_store
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.qdrant import QdrantContainer

POSTGRES_IMAGE = "pgvector/pgvector:pg17"
QDRANT_IMAGE = "qdrant/qdrant:v1.19.0"

BACKENDS = ["pgvector", "qdrant"]


@pytest.fixture(scope="session")
def pgvector_url() -> Iterator[str]:
    """Prepared by the migration, the way a deployment prepares one.

    Installing the vector extension is the migration's job. Doing it inline
    here would let these keep passing on the day the migration stopped.
    """
    with PostgresContainer(POSTGRES_IMAGE) as container:
        url = container.get_connection_url(driver=None)
        upgrade_to_head(url)
        yield url


@pytest.fixture(scope="session")
def qdrant_url() -> Iterator[str]:
    with QdrantContainer(QDRANT_IMAGE) as container:
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(6333)}"


@pytest.fixture(params=BACKENDS)
def settings(request: pytest.FixtureRequest) -> Settings:
    """Configuration for one backend, with a fresh index per test.

    Each test gets its own table or collection. Sharing one and deleting
    between tests would make every isolation assertion depend on the cleanup
    working, which is not what is being tested.
    """
    unique = abs(hash(request.node.nodeid)) % 10**9
    if request.param == "qdrant":
        return Settings(
            vector_store="qdrant",
            qdrant_url=request.getfixturevalue("qdrant_url"),
            qdrant_index=f"conformance_{unique}",
            embedding_dimensions=DIMENSIONS,
        )
    return Settings(
        vector_store="pgvector",
        database_url=request.getfixturevalue("pgvector_url"),
        vector_schema="public",
        vector_table=f"conformance_{unique}",
        embedding_dimensions=DIMENSIONS,
    )


@pytest.fixture
def store(settings: Settings) -> DocumentStore:
    return build_document_store(settings)
