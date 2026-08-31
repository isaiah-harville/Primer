"""Identity introspection for the current principal."""

from __future__ import annotations

from fastapi import APIRouter
from primer_contracts.identity import Principal

from primer_control.identity import CurrentPrincipal

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.get("/me", summary="Describe the acting principal")
def me(principal: CurrentPrincipal) -> Principal:
    return principal
