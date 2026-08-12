from typing import Callable

from ollama import AsyncClient, ResponseError

from app.config import settings


class OllamaPullError(Exception):
    pass


async def pull_model(model: str, on_progress: Callable[[dict], None]) -> None:
    """Streams ollama pull progress events, calling on_progress(event) per event.

    Raises OllamaPullError if Ollama reports an error or is unreachable.
    """
    try:
        client = AsyncClient(host=settings.ollama_url)
        async for progress in await client.pull(model, stream=True):
            on_progress({
                "status": progress.status or "",
                "completed": progress.completed,
                "total": progress.total,
            })
    except ResponseError as e:
        raise OllamaPullError(e.error or str(e)) from e
    except Exception as e:
        raise OllamaPullError(f"Failed to reach Ollama: {e}") from e
