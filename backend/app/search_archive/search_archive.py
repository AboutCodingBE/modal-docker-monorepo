import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository
from app.shared.embedding_settings_repository import EmbeddingSettingsRepository
from app.shared.models import Archive
from app.shared.ollama_client import embed


class SearchArchive:
    """Use-case: embed een zoekvraag en zoek de best passende chunks binnen één archief.

    Hergebruikt hetzelfde embedding_model als de embedding-pipeline (app/config.py) —
    de zoekvraag moet in dezelfde vectorruimte liggen als de opgeslagen chunks.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(
        self,
        archive_id: uuid.UUID,
        query: str,
        top_n: int | None = None,
    ) -> list[dict] | None:
        """Geeft None terug als archive_id niet bestaat (router zet dit om naar 404) —
        een bestaand archief zonder resultaten geeft wel gewoon [] terug."""
        result = await self._session.execute(select(Archive.id).where(Archive.id == archive_id))
        if result.scalar_one_or_none() is None:
            return None

        embedding_settings = await EmbeddingSettingsRepository(self._session).get()
        resolved_top_n = top_n if top_n is not None else embedding_settings.search_top_n
        max_distance = embedding_settings.search_max_distance

        query_vector = await embed(settings.embedding_model, query)
        return await EmbeddingRepository(self._session).search(
            query_vector, resolved_top_n, archive_id, max_distance
        )
