from typing import List, Dict, Any

import google.generativeai as genai

from config.settings import settings
from repositories.feedback_repository import feedback_repository


class RagService:
    """
    Hybrid RAG pipeline:
      1. Rule-based pre-filter (same alert_type preferred).
      2. Semantic re-ranking via Google text-embedding-004.
      3. Inject top-3 examples into the LLM prompt.
    """

    _EMBED_MODEL = "models/text-embedding-004"

    def __init__(self) -> None:
        genai.configure(api_key=settings.GEMINI_API_KEY)

    def _embed(self, text: str) -> List[float]:
        result = genai.embed_content(model=self._EMBED_MODEL, content=text)
        return result["embedding"]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x**2 for x in a) ** 0.5
        mag_b = sum(x**2 for x in b) ** 0.5
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

    def get_context(self, query: str, alert_type: str = "") -> str:
        """Return a formatted string of the top-3 semantically similar past incidents."""
        candidates: List[Dict[str, Any]] = feedback_repository.get_resolved_with_feedback()
        if not candidates:
            return ""

        # Rule-based pre-filter: prefer same alert type, fall back to all
        if alert_type:
            filtered = [c for c in candidates if c.get("alert_type") == alert_type]
            if len(filtered) < 3:
                filtered = candidates
        else:
            filtered = candidates

        query_emb = self._embed(query)
        scored = []
        for item in filtered:
            text = f"{item.get('alert_type', '')} {item.get('zone', '')} {item.get('feedback', '')}"
            score = self._cosine(query_emb, self._embed(text))
            scored.append((score, item))

        scored.sort(key=lambda t: t[0], reverse=True)
        top3 = [item for _, item in scored[:3]]

        lines = ["Similar past incidents:"]
        for item in top3:
            lines.append(
                f"- [{item.get('alert_type')}] zone={item.get('zone')} "
                f"feedback={item.get('feedback')} reason={item.get('feedback_reason', 'N/A')}"
            )
        return "\n".join(lines)


rag_service = RagService()
