import httpx

from app.config import settings


class OllamaUnavailableError(Exception):
    pass


async def generate(model: str, prompt: str) -> str:
    """Send a prompt to Ollama and return the response text."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["response"]
    except httpx.ConnectError as e:
        raise OllamaUnavailableError("Ollama service unavailable") from e
