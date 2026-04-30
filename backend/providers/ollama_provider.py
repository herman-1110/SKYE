from providers.base_llm_provider import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):

    def generate(self, prompt: str) -> str:
        raise NotImplementedError(
            "Ollama provider not yet implemented. Set OLLAMA_HOST in .env"
        )

    def get_model_name(self) -> str:
        return "ollama-stub"
