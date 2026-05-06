"""Bearer-token auth for the Spark bridge (ADR-0003 §6).

The token is loaded from the ``SPARK_BRIDGE_TOKEN`` environment variable on
every request. Missing env var fails closed (HTTP 503) so misconfiguration is
loud rather than silent. Comparison uses :func:`secrets.compare_digest` to
defeat timing oracles.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, status

TOKEN_ENV_VAR = "SPARK_BRIDGE_TOKEN"


def _expected_token() -> str | None:
    """Return the configured bearer token, or ``None`` if the env var is unset."""
    val = os.environ.get(TOKEN_ENV_VAR)
    if val is None:
        return None
    val = val.strip()
    return val or None


def require_bearer_token(request: Request) -> None:
    """FastAPI dependency: enforce the ``Authorization: Bearer <token>`` header.

    Raises:
        HTTPException: 503 if the bridge has no configured token; 401 otherwise.
    """
    expected = _expected_token()
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bridge token not configured ({TOKEN_ENV_VAR} unset).",
        )

    auth = request.headers.get("Authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
