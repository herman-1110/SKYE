from typing import List, Dict, Any

# RAG temporarily disabled — text-embedding-004 not available on v1beta API
# (google-generativeai==0.7.2 routes embed_content through v1beta).
# Re-enable once SDK is upgraded to v1 stable or a compatible embed model is used.
#
# import google.generativeai as genai
# from config.settings import settings
from repositories.feedback_repository import feedback_repository


class RagService:
    """
    Hybrid RAG pipeline (currently stubbed — see comment above).
    get_context() returns empty string so report generation proceeds without
    semantic context injection.
    """

    _EMBED_MODEL = "models/text-embedding-004"

    def __init__(self) -> None:
        # genai.configure(api_key=settings.GEMINI_API_KEY)
        pass

    # def _embed(self, text: str) -> List[float]:
    #     result = genai.embed_content(model=self._EMBED_MODEL, content=text)
    #     return result["embedding"]

    # @staticmethod
    # def _cosine(a: List[float], b: List[float]) -> float:
    #     dot = sum(x * y for x, y in zip(a, b))
    #     mag_a = sum(x**2 for x in a) ** 0.5
    #     mag_b = sum(x**2 for x in b) ** 0.5
    #     return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

    def get_context(self, query: str, alert_type: str = "") -> str:
        """RAG stubbed — returns empty string until embedding API is re-enabled."""
        return ""

    # def get_context_full(self, query: str, alert_type: str = "") -> str:
    #     """Full RAG pipeline — re-enable when SDK supports v1 embed endpoint."""
    #     candidates: List[Dict[str, Any]] = feedback_repository.get_resolved_with_feedback()
    #     if not candidates:
    #         return ""
    #     if alert_type:
    #         filtered = [c for c in candidates if c.get("alert_type") == alert_type]
    #         if len(filtered) < 3:
    #             filtered = candidates
    #     else:
    #         filtered = candidates
    #     query_emb = self._embed(query)
    #     scored = []
    #     for item in filtered:
    #         text = f"{item.get('alert_type', '')} {item.get('zone', '')} {item.get('feedback', '')}"
    #         score = self._cosine(query_emb, self._embed(text))
    #         scored.append((score, item))
    #     scored.sort(key=lambda t: t[0], reverse=True)
    #     top3 = [item for _, item in scored[:3]]
    #     lines = ["Similar past incidents:"]
    #     for item in top3:
    #         lines.append(
    #             f"- [{item.get('alert_type')}] zone={item.get('zone')} "
    #             f"feedback={item.get('feedback')} reason={item.get('feedback_reason', 'N/A')}"
    #         )
    #     return "\n".join(lines)


rag_service = RagService()
