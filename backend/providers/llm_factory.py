from config.settings import settings
from providers.base_llm_provider import BaseLLMProvider
from providers.claude_provider import ClaudeProvider
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from providers.openai_provider import OpenAIProvider


def get_llm_provider() -> BaseLLMProvider:
    if settings.LLM_PROVIDER == "gemini":
        return GeminiProvider()
    elif settings.LLM_PROVIDER == "openai":
        return OpenAIProvider()
    elif settings.LLM_PROVIDER == "ollama":
        return OllamaProvider()
    elif settings.LLM_PROVIDER == "claude":
        return ClaudeProvider()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
            f"Valid options: gemini, openai, ollama, claude"
        )
