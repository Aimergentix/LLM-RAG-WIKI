"""``GET /status`` — pipeline health snapshot (ADR-0003 §3).

Returns counts only. Never returns wiki page contents, chunk text, or
manifest body. The Spark UI uses this to show "index has N docs, last
ingest at T".
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from rag.config import ConfigError, load_config
from rag.manifest import ManifestError, load_manifest

from ..auth import require_bearer_token
from ..schemas import StatusResponse

logger = logging.getLogger("spark_bridge.status")

router = APIRouter(dependencies=[Depends(require_bearer_token)])


def _count_wiki_pages(wiki_root) -> int:  # noqa: ANN001 — Path
    if not wiki_root.is_dir():
        return 0
    return sum(1 for _ in wiki_root.rglob("*.md"))


@router.get("/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """Return wiki page count, indexed-doc count, and last-ingest timestamp."""
    try:
        cfg = load_config()
    except ConfigError as exc:
        logger.error("Config load failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="[ERR_CONFIG] bridge config unavailable",
        ) from exc

    wiki_root = cfg.paths.wiki_root
    index_dir = cfg.paths.index_dir
    manifest_path = cfg.paths.manifest_path

    wiki_page_count = _count_wiki_pages(wiki_root)

    index_doc_count = 0
    last_ingest_at: str | None = None
    manifest_present = manifest_path.exists()
    if manifest_present:
        try:
            manifest = load_manifest(manifest_path)
            index_doc_count = len(manifest.files)
            last_ingest_at = manifest.updated_at
        except ManifestError as exc:
            logger.warning("Manifest unreadable at %s: %s", manifest_path, exc)
            manifest_present = False

    return StatusResponse(
        wiki_root=str(wiki_root),
        wiki_page_count=wiki_page_count,
        index_dir=str(index_dir),
        index_doc_count=index_doc_count,
        manifest_path=str(manifest_path),
        last_ingest_at=last_ingest_at,
        manifest_present=manifest_present,
    )
