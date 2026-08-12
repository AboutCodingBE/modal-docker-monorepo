import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TopicDetection, ArchiveAnalysis


class TopicsForFolderRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_folder(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> File | None:
        result = await self._session.execute(
            select(File).where(
                and_(
                    File.id == folder_id,
                    File.archive_id == archive_id,
                    File.is_directory == True,  # noqa: E712
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_topics_for_folder(self, folder_id: uuid.UUID) -> tuple[TopicDetection, str] | None:
        result = await self._session.execute(
            select(TopicDetection, ArchiveAnalysis.model)
            .join(ArchiveAnalysis, ArchiveAnalysis.id == TopicDetection.analysis_id)
            .where(TopicDetection.file_id == folder_id)
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.first()
