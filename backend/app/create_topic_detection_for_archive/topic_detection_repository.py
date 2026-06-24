import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import TopicDetection


class TopicDetectionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, analysis_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Returns True if a TopicDetection result already exists for this analysis + file (resumability check)."""
        result = await self._session.execute(
            select(TopicDetection.id).where(
                TopicDetection.analysis_id == analysis_id,
                TopicDetection.file_id == file_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def persist(
        self,
        analysis_id: uuid.UUID,
        archive_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        file_id: uuid.UUID,
        topic_detection_result: dict,
    ) -> None:
        topic_detection = TopicDetection(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=parent_folder_id,
            file_id=file_id,
            topics=topic_detection_result["topics"],
            topics_count=topic_detection_result["topics_count"],
        )
        self._session.add(topic_detection)
        await self._session.flush()
