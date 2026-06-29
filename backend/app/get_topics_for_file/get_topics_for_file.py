import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_topics_for_file.repository import TopicsForFileRepository


class GetTopicsForFile:
    def __init__(self, session: AsyncSession):
        self._repo = TopicsForFileRepository(session)

    async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(archive_id, file_id)
        if file is None:
            return None

        topic_detection = await self._repo.get_topics_for_file(file_id)

        topics = topic_detection.topics or [] if topic_detection else []

        return {
            "file_id": str(file_id),
            "file_name": file.name,
            "topics": topics,
            "total_topics": len(topics),
        }
