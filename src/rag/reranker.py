"""P5 Cross-Encoder Re-ranker.

Pure stdlib at module level; lazy imports sentence_transformers inside.

Cross-encoder ``predict`` returns raw logits (typically in roughly
``[-12, +12]`` for ``ms-marco-MiniLM`` family). The retrieval layer
compares scores against thresholds in ``[0.0, 1.0]`` (see
``rag.config.RetrievalConfig``), so logits are squashed through a
logistic sigmoid before being attached to :class:`QueryHit`. The
ordering induced by sigmoid is identical to the ordering induced by
the raw logits, so ranking quality is preserved.
"""

from __future__ import annotations
import logging
import math
from typing import List
from rag._query_store import QueryHit
from rag.embedder import EmbedderError

logger = logging.getLogger("rag.reranker")


def _sigmoid(x: float) -> float:
    # Numerically stable logistic; clamps to (0, 1).
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class CrossEncoderReranker:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_id)
            except ImportError as exc:
                raise EmbedderError("[ERR_EMBEDDING_MODEL] sentence-transformers not installed.") from exc

    def rerank(self, query: str, hits: List[QueryHit], top_k: int) -> List[QueryHit]:
        if not hits:
            return []

        self._load()

        # Prepare pairs for cross-encoding
        pairs = [[query, hit.document] for hit in hits]
        scores = self._model.predict(pairs)

        # Pair scores with hits and sort. Squash raw logits to [0, 1] via
        # sigmoid so downstream threshold gates (ood_threshold / min_score)
        # remain meaningful.
        ranked_hits = []
        for i, score in enumerate(scores):
            normalized = _sigmoid(float(score))
            ranked_hits.append(QueryHit(
                hits[i].id,
                normalized,
                hits[i].metadata,
                hits[i].document,
                hits[i].embedding,
            ))

        ranked_hits.sort(key=lambda x: x.score, reverse=True)
        return ranked_hits[:top_k]