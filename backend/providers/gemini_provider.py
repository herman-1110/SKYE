from google import genai
from google.genai import types

from config.settings import settings
from providers.base_llm_provider import BaseLLMProvider

# We never pass tools to generate_content, so automatic function calling has
# nothing to do — but the SDK still logs an "AFC is enabled..." info/warning
# pair on every call unless explicitly disabled. Silenced as pure log noise,
# not a behaviour change: no tools means AFC was always a no-op here.
_NO_AFC = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


class GeminiProvider(BaseLLMProvider):

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def generate(self, prompt: str) -> str:
        # temperature (was 1.0 — already the SDK default) dropped: temperature/top_p/top_k
        # are deprecated as sampling params on the new SDK. Not an oversight.
        response = self._client.models.generate_content(
            model=settings.LLM_MODEL_NAME,
            contents=prompt,
            config=_NO_AFC,
        )
        return response.text

    def get_model_name(self) -> str:
        return settings.LLM_MODEL_NAME
