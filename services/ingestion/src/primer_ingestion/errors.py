"""Failures a stage can report.

A worker is the only party that knows whether a failure was transient, so it
says so explicitly instead of leaving Control to guess from an error code.
"""

from __future__ import annotations

from primer_contracts.ingestion import FailureDisposition


class StageError(Exception):
    """A stage failure with a sanitized, user-visible code."""

    disposition = FailureDisposition.RETRY

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class UnsupportedDocument(StageError):
    """The document is not something Primer can ingest. Retrying cannot help."""

    disposition = FailureDisposition.UNSUPPORTED


class PermanentStageError(StageError):
    """The stage cannot succeed for this job, whatever the retry budget says."""

    disposition = FailureDisposition.FAILED
