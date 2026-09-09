import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository
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
        top_n: int = settings.search_top_n,
    ) -> list[dict]:
        query_vector = await embed(settings.embedding_model, query)
        return await EmbeddingRepository(self._session).search(query_vector, top_n, archive_id)
