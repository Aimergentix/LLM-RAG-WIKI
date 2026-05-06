"""Pydantic v2 models mirroring the existing RAG / persona output contracts.

These schemas are the wire contract between the local bridge and the Spark
front-end (`spark/src/types.ts` is its TypeScript mirror). Field names and
ordering match :class:`rag.retrieve.RetrievalResult` /
:class:`rag.retrieve.RetrievalResponse` exactly so downstream YAML / JSON
consumers of the existing CLI keep working unchanged.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- Retrieval

class RetrievalResultSchema(BaseModel):
    """Single retrieval hit (mirrors :class:`rag.retrieve.RetrievalResult`)."""

    score: float
    source: str
    heading: str
    chunk_id: str
    excerpt: str


class RetrievalResponseSchema(BaseModel):
    """Top-level retrieval response (mirrors :class:`rag.retrieve.RetrievalResponse`)."""

    status: str
    query: str
    results: list[RetrievalResultSchema]
    degradation_meta: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None


# ---------------------------------------------------------------- Status

class StatusResponse(BaseModel):
    """Pipeline health snapshot served by ``GET /status``."""

    wiki_root: str
    wiki_page_count: int
    index_dir: str
    index_doc_count: int
    manifest_path: str
    last_ingest_at: str | None = None
    manifest_present: bool


# ---------------------------------------------------------------- Persona

class PersonaListItem(BaseModel):
    """Lightweight persona descriptor for the selector UI.

    Per ADR-0003 §4 the rule text and style weights are NOT exposed by the
    list endpoint; the Spark UI only needs IDs and human-readable names to
    populate the selector.
    """

    id: str
    kind: str
    name: str
    version: str


class PersonaCompileRequest(BaseModel):
    """Ad-hoc persona composition request.

    Per ADR-0003 §3 the result is ephemeral: nothing is written to
    ``personas/active.yaml`` or any other on-disk store.
    """

    character: str | None = Field(
        default=None,
        description="Optional character persona ID.",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domain persona IDs to compose with the character.",
    )


class PersonaCompileResponse(BaseModel):
    """Compiled persona profile in all three formats (dense / structured / debug)."""

    dense: str
    structured: dict[str, Any]
    debug: str
