"""Content-addressed storage for uploaded source bytes.

Control writes source objects and workers read them. Sharing one
implementation means both agree on how a hash maps to a stored object, which
is the whole basis of Primer's deduplication.
"""

from primer_storage.source_store import (
    DOCX_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    SUPPORTED_EXTENSIONS,
    QuotaExceeded,
    SourceStore,
    SourceStoreError,
    StoredSource,
    UnsupportedContent,
    detect_media_type,
)

__all__ = [
    "DOCX_MEDIA_TYPE",
    "PDF_MEDIA_TYPE",
    "SUPPORTED_EXTENSIONS",
    "QuotaExceeded",
    "SourceStore",
    "SourceStoreError",
    "StoredSource",
    "UnsupportedContent",
    "detect_media_type",
]

__version__ = "0.1.0"
