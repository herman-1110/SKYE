import google.generativeai as genai

from config.settings import settings
from providers.base_llm_provider import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):

    def __init__(self) -> None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(
            model_name=settings.LLM_MODEL_NAME,
            generation_config=genai.GenerationConfig(temperature=1.0),
        )

    def generate(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text

    def get_model_name(self) -> str:
        return settings.LLM_MODEL_NAME
