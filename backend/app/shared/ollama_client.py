import httpx

from app.config import settings


class OllamaUnavailableError(Exception):
    pass


async def generate(model: str, prompt: str, format: str | None = None) -> str:
    """Send a prompt to Ollama and return the response text.

    Supports constrained decoding via the 'format' parameter (e.g., format="json").
    """
    payload: dict = {"model": model, "prompt": prompt, "stream": False}
    if format:
        payload["format"] = format

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["response"]
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise OllamaUnavailableError("Ollama service unavailable or timed out") from e
    except httpx.HTTPStatusError as e:
        raise Exception(f"Ollama returned HTTP error status: {e.response.status_code}") from e


async def embed(model: str, text: str) -> list[float]:
    """Send text to Ollama's embedding endpoint and return the embedding vector.

    /api/embed is batch-vormig (accepteert en retourneert lijsten), ook voor één
    input — vandaar de [0] om het enkele resultaat eruit te halen.
    """
    payload: dict = {"model": model, "input": text}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/embed",
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise OllamaUnavailableError("Ollama service unavailable or timed out") from e
    except httpx.HTTPStatusError as e:
        raise Exception(f"Ollama returned HTTP error status: {e.response.status_code}") from e
