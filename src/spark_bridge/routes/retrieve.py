"""``GET /retrieve`` — read-only RAG query proxy (ADR-0003 §3).

Calls :func:`rag.retrieve.query_rag` with the same backends used by the CLI
and returns a Pydantic-validated mirror of its response. No writes occur to
``wiki/``, ``data/`` or ``raw/``.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import asdict
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from rag.config import Config, ConfigError, load_config
from rag.retrieve import query_rag

from ..auth import require_bearer_token
from ..schemas import RetrievalResponseSchema

logger = logging.getLogger("spark_bridge.retrieve")

router = APIRouter(dependencies=[Depends(require_bearer_token)])


# ---- Lazy backend factories (model loads deferred to first call) ----------

@lru_cache(maxsize=1)
def _config() -> Config:
    return load_config()


@lru_cache(maxsize=1)
def _embedder():  # noqa: ANN202 — backend type intentionally opaque to bridge.
    cfg = _config()
    if os.environ.get("LLM_RAG_WIKI_TEST_STUB_EMBEDDER") == "1":
        from rag.embedder import DeterministicHashEmbedder
        return DeterministicHashEmbedder(dim=16)
    from rag.embedder import SentenceTransformersEmbedder
    return SentenceTransformersEmbedder(
        cfg.embedding.model_id,
        normalize=cfg.embedding.normalize_embeddings,
    )


@lru_cache(maxsize=1)
def _adapter():  # noqa: ANN202 — backend type intentionally opaque to bridge.
    cfg = _config()
    from rag._query_store import ChromaQueryAdapter
    return ChromaQueryAdapter(
        cfg.paths.index_dir,
        cfg.domain.name,
        distance_metric=cfg.retrieval.distance_metric,
    )


@lru_cache(maxsize=1)
def _reranker():  # noqa: ANN202 — backend type intentionally opaque to bridge.
    cfg = _config()
    if not cfg.reranking.enabled:
        return None
    if os.environ.get("LLM_RAG_WIKI_TEST_STUB_EMBEDDER") == "1":
        return None
    from rag.reranker import CrossEncoderReranker
    return CrossEncoderReranker(cfg.reranking.model_id)


# ---- Route ----------------------------------------------------------------

@router.get("/retrieve", response_model=RetrievalResponseSchema)
def retrieve(
    q: Annotated[str, Query(min_length=1, max_length=2048, description="Query string.")],
    top_k: Annotated[int | None, Query(ge=1, le=50)] = None,
    allow_stale: Annotated[bool, Query()] = False,
) -> RetrievalResponseSchema:
    """Run a RAG query and return the response object.

    Args:
        q: Free-text query.
        top_k: Optional override for ``retrieval.top_k``; capped at 50.
        allow_stale: If True, proceed even when manifest config_hash differs.

    Returns:
        Pydantic mirror of :class:`rag.retrieve.RetrievalResponse`.
    """
    try:
        cfg = _config()
    except ConfigError as exc:
        logger.error("Config load failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="[ERR_CONFIG] bridge config unavailable",
        ) from exc

    if top_k is not None:
        cfg = dataclasses.replace(
            cfg,
            retrieval=dataclasses.replace(cfg.retrieval, top_k=top_k),
        )

    # Construct backends inside the request so a missing/corrupt index
    # surfaces as a schema-compliant error response rather than HTTP 500.
    try:
        embedder = _embedder()
        adapter = _adapter()
        reranker = _reranker()
    except Exception as exc:  # noqa: BLE001 — backend errors are heterogeneous.
        logger.warning("Backend initialisation failed: %s", exc)
        return RetrievalResponseSchema(
            status="error",
            query=q,
            results=[],
            error_code="[ERR_DB]",
            message="Backend unavailable (index or model not initialised).",
        )

    response = query_rag(
        cfg,
        q,
        embedder=embedder,
        adapter=adapter,
        reranker=reranker,
        allow_stale=allow_stale,
    )
    return RetrievalResponseSchema.model_validate(asdict(response))
