"""``POST /persona/compile`` — stateless persona composition (ADR-0003 §3, §4).

The request body specifies an ad-hoc ``character`` + ``domains`` selection.
The bridge loads each persona via :class:`persona_mcp.store.PersonaStore`
(which validates IDs and refuses path-escape / symlink tricks), then
returns the compiled profile in three formats.

Nothing is written to ``personas/active.yaml`` or anywhere else on disk.
The compiled profile is response-only and is never transmitted further.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from persona_mcp.compiler import PersonaCompiler
from persona_mcp.store import PersonaStore

from ..auth import require_bearer_token
from ..schemas import (
    PersonaCompileRequest,
    PersonaCompileResponse,
    PersonaListItem,
)

logger = logging.getLogger("spark_bridge.persona")

router = APIRouter(dependencies=[Depends(require_bearer_token)])

_REPO_ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _store() -> PersonaStore:
    return PersonaStore(_REPO_ROOT / "personas")


@lru_cache(maxsize=1)
def _compiler() -> PersonaCompiler:
    return PersonaCompiler()


@router.get("/persona/list", response_model=list[PersonaListItem])
def list_personas() -> list[PersonaListItem]:
    """List available personas (id, kind, name, version only).

    ADR-0003 §4: rule text is not exposed by this endpoint; the Spark UI
    fetches the full compiled profile via ``POST /persona/compile`` once the
    user makes a selection.
    """
    store = _store()
    items: list[PersonaListItem] = []
    try:
        for persona in store.list_personas():
            items.append(
                PersonaListItem(
                    id=persona.id,
                    kind=persona.kind,
                    name=persona.name,
                    version=persona.version,
                ),
            )
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Persona list failed: %s", exc)
        return []
    items.sort(key=lambda p: (p.kind, p.id))
    return items


@router.post("/persona/compile", response_model=PersonaCompileResponse)
def compile_persona(req: PersonaCompileRequest) -> PersonaCompileResponse:
    """Compose the requested personas and return the compiled profile.

    Args:
        req: Ad-hoc selection (character + domains).

    Returns:
        Dense, structured, and debug renderings of the composed profile.
    """
    store = _store()
    compiler = _compiler()

    selected = []
    try:
        if req.character:
            selected.append(store.load_persona(req.character))
        for did in req.domains:
            selected.append(store.load_persona(did))
        meta = store.load_meta_directives()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        dense = compiler.compile_dense(selected, meta)
        structured = compiler.compile_structured(selected, meta)
        debug = compiler.compile_debug(selected, meta)
    except Exception as exc:  # pragma: no cover — compiler is deterministic.
        logger.exception("Persona compilation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[ERR_COMPILE] {exc}",
        ) from exc

    # Validate that structured payload is JSON-serialisable before returning.
    try:
        json.dumps(structured)
    except (TypeError, ValueError) as exc:  # pragma: no cover — schema-stable.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[ERR_COMPILE] non-serialisable structured payload: {exc}",
        ) from exc

    return PersonaCompileResponse(dense=dense, structured=structured, debug=debug)
