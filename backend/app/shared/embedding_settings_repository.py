from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import EmbeddingSettings


class EmbeddingSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self) -> EmbeddingSettings:
        """Returns the single embedding_settings row. Always exists (seeded by migration)."""
        result = await self._session.execute(select(EmbeddingSettings).limit(1))
        row = result.scalar_one_or_none()
        if row is None:
            raise RuntimeError("embedding_settings row missing — expected exactly one row, seeded by migration")
        return row

    async def update(
        self,
        embedding_chunk_size: int,
        embedding_max_chunks_per_file: int | None,
        search_max_distance: float,
        search_top_n: int,
    ) -> EmbeddingSettings:
        row = await self.get()
        row.embedding_chunk_size = embedding_chunk_size
        row.embedding_max_chunks_per_file = embedding_max_chunks_per_file
        row.search_max_distance = search_max_distance
        row.search_top_n = search_top_n
        await self._session.flush()
        return row

    async def set_model_downloaded(self) -> None:
        row = await self.get()
        row.embedding_model_downloaded = True
        await self._session.flush()
