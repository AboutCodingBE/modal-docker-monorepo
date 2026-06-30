import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, Ner, ArchiveAnalysis


class NerForFileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_file(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> File | None:
        """Verify the file exists and belongs to this archive."""
        result = await self._session.execute(
            select(File).where(
                and_(
                    File.id == file_id,
                    File.archive_id == archive_id,
                    File.is_directory == False,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_ner_for_file(self, file_id: uuid.UUID) -> Ner | None:
        """Get the most recent NER result for a file."""
        result = await self._session.execute(
            select(Ner)
            .join(ArchiveAnalysis, ArchiveAnalysis.id == Ner.analysis_id)
            .where(Ner.file_id == file_id)
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
