import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, TikaAnalysis


class OcrRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def update_tika_content(
        self,
        file_id: str,
        content: str | None,
        word_count: int,
        language: str | None,
    ) -> None:
        result = await self._session.execute(
            select(TikaAnalysis).where(TikaAnalysis.file_id == uuid.UUID(file_id))
        )
        analysis = result.scalar_one_or_none()
        if analysis:
            analysis.content = content
            analysis.word_count = word_count
            analysis.language = language
            await self._session.flush()

    async def set_ocr_enabled(self, archive_id: uuid.UUID, value: bool) -> None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        archive = result.scalar_one_or_none()
        if archive:
            archive.ocr_enabled = value
            await self._session.flush()
