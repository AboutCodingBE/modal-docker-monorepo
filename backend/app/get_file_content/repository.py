import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TikaAnalysis


class FileContentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_file(self, file_id: uuid.UUID) -> File | None:
        result = await self._session.execute(
            select(File).where(
                and_(File.id == file_id, File.is_directory == False)  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_tika_content(self, file_id: uuid.UUID) -> str | None:
        result = await self._session.execute(
            select(TikaAnalysis.content).where(TikaAnalysis.file_id == file_id)
        )
        return result.scalar_one_or_none()
