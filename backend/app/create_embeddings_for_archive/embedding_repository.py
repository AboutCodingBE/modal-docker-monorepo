import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Embedding


class EmbeddingRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, file_id: uuid.UUID) -> bool:
        """Returns True if this file already has embeddings (resumability check).
           query: SELECT id FROM embeddings WHERE file_id = :file_id LIMIT 1
        """
        result = await self._session.execute(
            select(Embedding.id).where(Embedding.file_id == file_id).limit(1)
        )
        #geeft UUID terug als rij gevonden, anders None => exists als er 1 result is!
        return result.scalar_one_or_none() is not None

    async def persist(
        self,
        file_id: uuid.UUID,
        chunks: list[tuple[int, str, list[float]]],
    ) -> None:
        """Slaat alle chunks van één bestand op als aparte Embedding-rijen.

        chunks: lijst van (chunk_index, chunk_text, embedding) — token_count wordt
        hier niet meegegeven, want dat is optioneel en enkel bedoeld voor debugging.
        """
        for chunk_index, chunk_text, embedding in chunks:
            self._session.add(Embedding(
                file_id=file_id,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
                embedding=embedding,
            ))
        await self._session.flush()
