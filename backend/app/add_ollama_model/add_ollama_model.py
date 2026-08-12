import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.add_ollama_model import download_progress
from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository
from app.add_ollama_model.ollama_pull_client import OllamaPullError, pull_model
from app.shared.models import AnalysisType

_logger = logging.getLogger("app")

_ALL_TYPES = (AnalysisType.SUMMARY, AnalysisType.NER, AnalysisType.TOPIC_DETECTION)


class AddOllamaModel:
    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(self, download_id: uuid.UUID, model: str) -> None:
        download_progress.create(download_id)

        def _on_progress(event: dict) -> None:
            download_progress.update(
                download_id,
                status=event.get("status", ""),
                completed_bytes=event.get("completed"),
                total_bytes=event.get("total"),
            )

        try:
            async with self._session_factory() as session:
                if await AnalysisConfigurationRepository(session).model_exists(model):
                    download_progress.update(download_id, done=True, status="already added")
                    return

            await pull_model(model, _on_progress)

            async with self._session_factory() as session:
                repo = AnalysisConfigurationRepository(session)
                for analysis_type in _ALL_TYPES:
                    await repo.create(analysis_type, model, is_default=False)
                await session.commit()

            download_progress.update(download_id, done=True, status="success")

        except OllamaPullError as e:
            _logger.error(f"Failed to pull Ollama model '{model}': {e}")
            download_progress.update(download_id, done=True, error=str(e))
        except Exception as e:
            _logger.error(f"Unexpected error adding Ollama model '{model}': {e}")
            download_progress.update(download_id, done=True, error="Unexpected error, check logs")
