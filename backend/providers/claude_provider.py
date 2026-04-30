from providers.base_llm_provider import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):

    # Future implementation:
    # client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    # message = client.messages.create(
    #     model=settings.LLM_MODEL_NAME,  # e.g. claude-sonnet-4-6
    #     max_tokens=1000,
    #     messages=[{"role": "user", "content": prompt}]
    # )
    # return message.content[0].text

    def generate(self, prompt: str) -> str:
        raise NotImplementedError(
            "Claude provider not yet implemented. Add ANTHROPIC_API_KEY to .env"
        )

    def get_model_name(self) -> str:
        return "claude-stub"
