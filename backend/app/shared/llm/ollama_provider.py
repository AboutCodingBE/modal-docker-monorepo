from app.shared.llm.provider import LlmProvider, LlmProviderUnavailableError
from app.shared.ollama_client import OllamaUnavailableError, generate


class OllamaProvider(LlmProvider):
    async def generate(self, model: str, prompt: str, format: str | None = None) -> str:
        try:
            return await generate(model, prompt, format)
        except OllamaUnavailableError as e:
            raise LlmProviderUnavailableError(str(e)) from e


ollama_provider = OllamaProvider()
