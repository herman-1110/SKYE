from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send prompt to the LLM and return the response text."""

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier string used by this provider."""
