"""FastAPI application entry point for the Spark bridge (ADR-0003).

Hard invariants enforced here:

* CORS allow-list is a hard-coded constant — never read from the environment
  and never widened to ``"*"``. Any change requires a superseding ADR.
* The ``host`` argument passed to ``uvicorn`` defaults to ``127.0.0.1``. The
  ``spark_bridge_host`` config key is read by ``scripts/start_bridge.sh``
  (K3) and must remain a loopback address.
* Auth is mandatory on every router (see ``routes/*.py``).

Run with::

    uvicorn src.spark_bridge.app:app --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import persona, retrieve, status

# ADR-0003 §2: CORS is locked. Do not parameterise this list.
_ALLOWED_ORIGIN = "https://spark.github.com"

logger = logging.getLogger("spark_bridge.app")


def create_app() -> FastAPI:
    """Build the FastAPI app with locked-down CORS and the K1 routers.

    Returns:
        Configured :class:`fastapi.FastAPI` instance.
    """
    app = FastAPI(
        title="llm-rag-wiki Bridge",
        description=(
            "Localhost-only HTTP bridge for the GitHub Spark micro-app. "
            "See adr/ADR-0003-spark-surface-boundary.md for binding "
            "invariants."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_ALLOWED_ORIGIN],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(retrieve.router, tags=["retrieve"])
    app.include_router(status.router, tags=["status"])
    app.include_router(persona.router, tags=["persona"])

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        """Unauthenticated liveness probe (no pipeline data is exposed)."""
        return {"status": "ok"}

    return app


app = create_app()
