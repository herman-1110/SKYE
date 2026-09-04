import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from google import genai
from google.genai import types

from config.settings import settings
from repositories.feedback_repository import feedback_repository

logger = logging.getLogger(__name__)

_TOP_K = 3
_EMBED_CACHE_MAX = 500


class RagService:
    """
    Hybrid RAG pipeline: rule-based pre-filter (alert_type) over supervisor
    feedback via FeedbackRepository, then semantic re-rank by embedding
    cosine similarity against the query.

    Strictly additive by design: report generation must succeed with or without
    this pipeline. Every failure mode (bad API key, empty corpus, a single bad
    embedding call) degrades to no context rather than raising.
    """

    _EMBED_MODEL = "gemini-embedding-001"

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        # (feedback_id, text_hash) -> embedding vector. Keyed on text hash too so
        # an edited feedback doc re-embeds instead of serving a stale vector.
        # No TTL — embeddings are deterministic for the same text. Bounded and
        # evicted oldest-first (plain dict preserves insertion order) so a long
        # uptime can't grow this unbounded.
        self._embed_cache: Dict[Tuple[str, str], List[float]] = {}

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _embed(self, text: str, task_type: str) -> Optional[List[float]]:
        """Embed text via gemini-embedding-001 (3072-dim default — kept, MRL
        truncation isn't worth it at this corpus size). Returns None on ANY
        failure; callers treat that as 'no context available', never raise."""
        try:
            result = self._client.models.embed_content(
                model=self._EMBED_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.warning("[RAG] WARNING: embedding call failed: %s", e)
            return None

    def _embed_document_cached(self, feedback_id: str, text: str) -> Optional[List[float]]:
        key = (feedback_id, self._text_hash(text))
        cached = self._embed_cache.get(key)
        if cached is not None:
            return cached

        vec = self._embed(text, task_type="RETRIEVAL_DOCUMENT")
        if vec is None:
            return None

        if len(self._embed_cache) >= _EMBED_CACHE_MAX:
            oldest_key = next(iter(self._embed_cache))
            del self._embed_cache[oldest_key]
        self._embed_cache[key] = vec
        return vec

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        va, vb = np.asarray(a), np.asarray(b)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        return float(np.dot(va, vb) / denom) if denom else 0.0

    @staticmethod
    def _candidate_text(item: Dict[str, Any]) -> str:
        return (
            f"{item.get('alert_type', '')} {item.get('zone', '')} "
            f"{item.get('feedback', '')} {item.get('feedback_reason') or ''}"
        )

    def _retrieve(self, query: str, alert_type: str = "") -> Tuple[str, List[str]]:
        """Core hybrid retrieval. Returns (context_string, feedback_ids_used) —
        both empty on any failure or when nothing clears RAG_SIMILARITY_FLOOR.
        Never raises."""
        try:
            candidates: List[Dict[str, Any]] = []
            if alert_type:
                candidates = feedback_repository.get_by_alert_type(alert_type)
            if not candidates:
                candidates = feedback_repository.get_resolved_with_feedback()

            # Empty corpus is the expected state early on — silent and free,
            # no API call, no log spam.
            if not candidates:
                return "", []

            query_emb = self._embed(query, task_type="RETRIEVAL_QUERY")
            if query_emb is None:
                return "", []

            scored: List[Tuple[float, Dict[str, Any]]] = []
            for item in candidates:
                feedback_id = item.get("feedback_id")
                if not feedback_id:
                    continue
                item_emb = self._embed_document_cached(feedback_id, self._candidate_text(item))
                if item_emb is None:
                    continue
                scored.append((self._cosine(query_emb, item_emb), item))

            scored.sort(key=lambda t: t[0], reverse=True)
            top = [
                item for score, item in scored[:_TOP_K]
                if score >= settings.RAG_SIMILARITY_FLOOR
            ]
            if not top:
                return "", []

            lines = ["Similar past incidents:"]
            used_ids: List[str] = []
            for item in top:
                lines.append(
                    f"- [{item.get('alert_type')}] zone={item.get('zone')} "
                    f"feedback={item.get('feedback')} reason={item.get('feedback_reason', 'N/A')}"
                )
                used_ids.append(item["feedback_id"])
            return "\n".join(lines), used_ids

        except Exception as e:
            logger.warning("[RAG] WARNING: retrieval failed: %s", e)
            return "", []

    def get_context(self, query: str, alert_type: str = "") -> str:
        """Plain-string contract, preserved for any caller that only wants
        formatted context and not the audit trail. Never raises."""
        context, _ = self._retrieve(query, alert_type)
        return context

    def get_context_with_sources(self, query: str, alert_type: str = "") -> Tuple[str, List[str]]:
        """Same retrieval as get_context(), plus the feedback_ids actually used —
        for callers populating an audit trail (AuditReportRecord.rag_examples_used).
        Never raises."""
        return self._retrieve(query, alert_type)


rag_service = RagService()
