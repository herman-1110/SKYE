from providers.base_llm_provider import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):

    def generate(self, prompt: str) -> str:
        raise NotImplementedError(
            "OpenAI provider not yet implemented. Add OPENAI_API_KEY to .env"
        )

    def get_model_name(self) -> str:
        return "openai-stub"
