import dataclasses
import os
import sys
import math
import logging
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List

from rag.config import load_config, config_hash, Config, ConfigError
from rag.manifest import load_manifest, ManifestError
from rag.embedder import EmbedderError
from rag.store import StoreError
from rag._query_store import QueryableStore, LexicalQueryable, QueryHit
from rag.security import is_injection_flagged

logger = logging.getLogger("rag.retrieve")


@dataclass(frozen=True)
class RetrievalResult:
    score: float
    source: str
    heading: str
    chunk_id: str
    excerpt: str

@dataclass(frozen=True)
class RetrievalResponse:
    status: str
    query: str
    results: list[RetrievalResult]
    degradation_meta: Optional[dict] = None
    error_code: Optional[str] = None
    message: Optional[str] = None

def _apply_mmr(hits: list[QueryHit], top_k: int, lambda_param: float) -> list[QueryHit]:
    """Maximal Marginal Relevance filter for diversity."""
    if not hits:
        return []
    
    selected: list[QueryHit] = []
    candidates = list(hits)

    def cosine_sim(v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        mag = math.sqrt(sum(a*a for a in v1)) * math.sqrt(sum(b*b for b in v2))
        return dot / mag if mag > 0 else 0

    while len(selected) < top_k and candidates:
        best_mmr_score = -float('inf')
        best_idx = -1

        for i, cand in enumerate(candidates):
            if cand.embedding is None or len(cand.embedding) == 0:
                score = cand.score # Fallback
            else:
                relevance = cand.score
                novelty = 0
                if selected:
                    novelty = max(cosine_sim(cand.embedding, s.embedding) for s in selected if s.embedding is not None and len(s.embedding) > 0)
                score = lambda_param * relevance - (1 - lambda_param) * novelty
            
            if score > best_mmr_score:
                best_mmr_score = score
                best_idx = i
        
        if best_idx == -1: break
        selected.append(candidates.pop(best_idx))
    return selected

def _format_excerpt(text: str, max_chars: int) -> str:
    # MASTER §8: Prompt-injection boundary.
    # The substring guard in `is_injection_flagged` is intentionally coarse
    # (defence-in-depth, not the sole barrier). Callers must additionally
    # treat retrieved excerpts as untrusted *data*, never instructions.
    if is_injection_flagged(text):
        return "[content withheld: potential prompt-injection]"

    collapsed = " ".join(text.split())
    if len(collapsed) > max_chars:
        return collapsed[:max_chars].strip() + "…"
    return collapsed

def query_rag(
    cfg: Config, 
    query: str, 
    *, 
    embedder=None, 
    adapter: QueryableStore = None,
    lexical_adapter: LexicalQueryable = None,
    reranker=None,
    manifest_path: Optional[Path] = None,
    allow_stale: bool = False,
) -> RetrievalResponse:
    try:
        m_path = manifest_path or cfg.paths.manifest_path
        if not m_path.exists():
            return RetrievalResponse("error", query, [], error_code="[ERR_INDEX_MISSING]", message="Manifest missing")
            
        manifest = load_manifest(m_path)
        
        if not manifest.files:
            return RetrievalResponse("error", query, [], error_code="[ERR_INDEX_EMPTY]", message="Index contains no files.")

        if manifest.config_hash != config_hash(cfg):
            if not allow_stale:
                return RetrievalResponse(
                    "error", query, [],
                    error_code="[ERR_INDEX_STALE]",
                    message=(
                        "Manifest config_hash does not match current config;"
                        " rebuild the index or pass --allow-stale."
                    ),
                )
            logger.warning("Manifest config_hash mismatch; --allow-stale set, proceeding.")

        # Cross-layer dirty signal: wiki.ingest touches
        # manifest_path.parent/.wiki_dirty after every successful page write;
        # rag.ingest removes it.  The sentinel lives in the RAG-owned data
        # directory — not inside wiki_root, which is a read-only upstream
        # per MASTER §8.
        try:
            sentinel = cfg.paths.manifest_path.parent / ".wiki_dirty"
            if sentinel.exists():
                logger.warning(
                    "wiki source has changed since last RAG ingest"
                    " (%s present); results may be stale.", sentinel,
                )
        except OSError:
            pass

        # 3. Fetch Candidates (Hybrid)
        vector = embedder.embed([query])[0]
        vector_hits = adapter.query(vector, cfg.reranking.top_n if cfg.reranking.enabled else cfg.retrieval.top_k)

        if lexical_adapter:
            lexical_hits = lexical_adapter.query(query, cfg.reranking.top_n if cfg.reranking.enabled else cfg.retrieval.top_k)
            
            # RRF Fusion
            rrf_k = 60
            fused_scores = {}
            hit_map = {}
            for rank, h in enumerate(vector_hits):
                fused_scores[h.id] = fused_scores.get(h.id, 0) + 1.0 / (rrf_k + rank + 1)
                hit_map[h.id] = h
            for rank, h in enumerate(lexical_hits):
                fused_scores[h.id] = fused_scores.get(h.id, 0) + 1.0 / (rrf_k + rank + 1)
                if h.id not in hit_map: hit_map[h.id] = h
            
            sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)
            hits = [hit_map[rid] for rid in sorted_ids]
        else:
            hits = vector_hits

        # 4. Re-ranking Layer
        if reranker and cfg.reranking.enabled:
            # Use the reranker to refine the top-N candidates
            hits = reranker.rerank(query, hits[:cfg.reranking.top_n], cfg.retrieval.top_k)

        # 5. Diversity Filter (MMR)
        if cfg.retrieval.mmr_enabled:
            hits = _apply_mmr(hits, cfg.retrieval.top_k, cfg.retrieval.mmr_lambda)

        if not hits:
            return RetrievalResponse("out_of_domain", query, [], error_code="[ERR_OUT_OF_DOMAIN]")

        top_score = hits[0].score
        
        # 5. Threshold Logic
        if top_score < cfg.retrieval.ood_threshold:
            return RetrievalResponse("out_of_domain", query, [], error_code="[ERR_OUT_OF_DOMAIN]")
            
        if top_score < cfg.retrieval.min_score:
            meta = {
                "highest_score_found": round(top_score, 4),
                "closest_topics_found": [f"{h.metadata.get('heading_path')} from {h.metadata.get('rel_path')}" for h in hits[:3]],
                "message": "Found related topics, but confidence is too low."
            }
            return RetrievalResponse("insufficient_context", query, [], degradation_meta=meta, error_code="[ERR_INSUFFICIENT_CONTEXT]")

        # 6. Success
        results = [
            RetrievalResult(
                score=round(h.score, 4),
                source=h.metadata.get("rel_path", "unknown"),
                heading=h.metadata.get("heading_path", "unknown"),
                chunk_id=h.id,
                excerpt=_format_excerpt(h.document, cfg.ops.max_context_chars)
            ) for h in hits if h.score >= cfg.retrieval.min_score
        ]
        
        return RetrievalResponse("ok", query, results)

    except ManifestError as e:
        code = str(e).split(" ", 1)[0] if str(e).startswith("[") else "[ERR_RUNTIME]"
        return RetrievalResponse("error", query, [], error_code=code, message="Manifest error")
    except StoreError:
        logger.error("Vector store error in query_rag", exc_info=True)
        return RetrievalResponse("error", query, [], error_code="[ERR_DB]", message="Vector store error")
    except EmbedderError:
        logger.error("Embedder error in query_rag", exc_info=True)
        return RetrievalResponse("error", query, [], error_code="[ERR_EMBEDDING_MODEL]", message="Embedder error")
    except Exception:
        logger.error("Unhandled exception in query_rag", exc_info=True)
        return RetrievalResponse("error", query, [], error_code="[ERR_RUNTIME]", message="Internal retrieval error")

def render_yaml(resp: RetrievalResponse) -> str:
    try:
        import yaml
    except ImportError:
        return json.dumps(asdict(resp), indent=2)
    
    # Canonical order per MASTER §7
    data = {
        "status": resp.status,
        "query": resp.query,
        "results": [asdict(r) for r in resp.results],
        "degradation_meta": resp.degradation_meta,
        "error_code": resp.error_code,
        "message": resp.message
    }
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

def main(argv: List[str] | None = None) -> int:
    import argparse
    if argv is None:
        argv = sys.argv[1:]
        
    parser = argparse.ArgumentParser(description="llm-rag-wiki Retrieval CLI")
    parser.add_argument("query", help="Query string")
    parser.add_argument("--config", type=Path, help="Path to config.yaml")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml")
    parser.add_argument("--strict-paths", action="store_true")
    parser.add_argument("--top-k", type=int)
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Proceed even if the manifest config_hash does not match current config.",
    )
    
    args = parser.parse_args(argv)
    
    try:
        cfg = load_config(args.config)
        
        if args.strict_paths and args.config:
            # Enforce that config path is within the current working directory.
            try:
                args.config.resolve().relative_to(Path.cwd().resolve())
            except ValueError:
                return 4
        
        # Production backend lazy imports
        from rag._query_store import ChromaQueryAdapter

        if os.environ.get("LLM_RAG_WIKI_TEST_STUB_EMBEDDER") == "1":
            from rag.embedder import DeterministicHashEmbedder
            embedder = DeterministicHashEmbedder(dim=16)
        else:
            from rag.embedder import SentenceTransformersEmbedder
            embedder = SentenceTransformersEmbedder(cfg.embedding.model_id, normalize=cfg.embedding.normalize_embeddings)
        adapter = ChromaQueryAdapter(cfg.paths.index_dir, cfg.domain.name, distance_metric=cfg.retrieval.distance_metric)
        
        reranker = None
        if cfg.reranking.enabled and os.environ.get("LLM_RAG_WIKI_TEST_STUB_EMBEDDER") != "1":
            from rag.reranker import CrossEncoderReranker  # noqa: PLC0415
            reranker = CrossEncoderReranker(cfg.reranking.model_id)

        if args.top_k:
            cfg = dataclasses.replace(cfg, retrieval=dataclasses.replace(cfg.retrieval, top_k=args.top_k))
        
        response = query_rag(cfg, args.query, embedder=embedder, adapter=adapter, reranker=reranker, allow_stale=args.allow_stale)
        
        if args.format == "json":
            print(json.dumps(asdict(response), indent=2))
        else:
            print(render_yaml(response))
            
        if response.status == "ok":
            return 0
        elif response.status in ("out_of_domain", "insufficient_context"):
            return 1
        elif response.error_code and response.error_code.startswith("[ERR_SECURITY]"):
            return 4
        elif response.error_code in ("[ERR_CONFIG]", "[ERR_SCHEMA]"):
            return 2
        elif response.error_code in ("[ERR_INDEX_MISSING]", "[ERR_INDEX_EMPTY]", "[ERR_DB]", "[ERR_EMBEDDING_MODEL]", "[ERR_INDEX_STALE]"):
            return 3
        return 5
    except ConfigError as exc:
        # MASTER §9: [ERR_CONFIG] / [ERR_SCHEMA] -> exit 2.
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        logger.exception("retrieve.main failed")
        print(f"[ERR_RUNTIME] {exc}", file=sys.stderr)
        return 5

if __name__ == "__main__":
    sys.exit(main())