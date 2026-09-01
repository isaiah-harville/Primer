"""The storage backends a deployment can actually be pointed at.

`fsspec` dispatches on the URL scheme and imports the backend lazily, so a
missing one is not a startup error or an import error in this package: it is
an `ImportError` raised the first time somebody uploads a file. These tests
resolve each scheme Primer documents, so dropping a backend fails here
instead of in production.
"""

from __future__ import annotations

import fsspec
import pytest

#: Every scheme Primer's configuration and chart tell an operator to use.
#: `file` is the Compose default; `s3` is the chart's.
DOCUMENTED_SCHEMES = ["file:///var/lib/primer/sources", "s3://primer-sources"]


@pytest.mark.parametrize("url", DOCUMENTED_SCHEMES)
def test_a_documented_source_store_url_resolves(url: str) -> None:
    """No network is touched: resolving a URL only selects the backend."""
    filesystem, path = fsspec.core.url_to_fs(url)

    assert filesystem is not None
    assert path
