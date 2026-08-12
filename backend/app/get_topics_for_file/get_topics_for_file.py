import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_topics_for_file.repository import TopicsForFileRepository


def _extract_topics(jsonb_list: list | None) -> list[str]:
    if not jsonb_list:
        return []
    return [item["topic"] for item in jsonb_list if "topic" in item]


class GetTopicsForFile:
    def __init__(self, session: AsyncSession):
        self._repo = TopicsForFileRepository(session)

    async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(archive_id, file_id)
        if file is None:
            return None

        row = await self._repo.get_topics_for_file(file_id)
        topic_detection, model = row if row else (None, None)

        topics = _extract_topics(topic_detection.topics) if topic_detection else []

        return {
            "file_id": str(file_id),
            "file_name": file.name,
            "model": model,
            "topics": topics,
            "total_topics": len(topics),
        }
