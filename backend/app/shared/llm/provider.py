from abc import ABC, abstractmethod


class LlmProviderUnavailableError(Exception):
    """Raised by any LlmProvider implementation when it cannot fulfill a request."""


class LlmProvider(ABC):
    @abstractmethod
    async def generate(self, model: str, prompt: str, format: str | None = None) -> str:
        ...
